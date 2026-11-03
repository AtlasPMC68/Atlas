"""Fit a transform from control points and apply it to pixel-space features."""

import logging
import math
from dataclasses import dataclass, field

import numpy as np
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import shapely
from shapely.geometry import mapping, shape
from shapely.ops import transform

from app.utils.coastline_land_mask import (
    clip_zone_to_land_mask,
)

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .frame import FrameBounds
from .affine import AffineModel, fit_affine_from_control_points
from .control_points import ControlPoint, count_by_source
from .piecewise import (
    RESIDUAL_IN_SAMPLE,
    PiecewiseAffineModel,
    fit_piecewise_from_control_points,
)
from .projection import (
    lonlat_arrays_to_webmercator,
    reference_latitude,
    webmercator_arrays_to_lonlat,
    webmercator_meters_to_km,
)
from .cleaning import land_mask_3857 as land_mask_3857_shared
from .quality import affine_leave_one_out, control_point_layout
from .records import RunRecord
from .snapping import (
    CoastIndex,
    load_coastline_geometry,
    snap_geometry_to_coastline,
    snap_geometry_to_coastline_stretches,
)

logger = logging.getLogger(__name__)

JSONDict = Dict[str, Any]

#: Either transform model. Both satisfy the same fit / apply / inverse /
#: serialize interface, which is what lets this module stay indifferent.
TransformModel = Union[AffineModel, PiecewiseAffineModel]


@dataclass
class GeorefResult:
    """What a georeferencing run produced, beyond the features themselves."""

    collections: List[JSONDict] = field(default_factory=list)
    model: Optional[TransformModel] = None
    record: Optional[RunRecord] = None
    #: The GCP-only affine, whatever was applied: the floor to compare against.
    baseline: Optional[AffineModel] = None
    #: The zones as the transform placed them, before snapping and the clip.
    raw_collections: List[JSONDict] = field(default_factory=list)
    #: With ``score_snapping``, the zones cleaned both ways whatever the config
    #: says: clipped without snapping, and snapped then clipped. Snapping is a
    #: last step on any transform, so the dev runners score every variant
    #: both ways rather than make it a variant (georeferencing-synthetic.md
    #: §10.6). Empty otherwise, and the snapped ones without a coastline.
    unsnapped_collections: List[JSONDict] = field(default_factory=list)
    snapped_collections: List[JSONDict] = field(default_factory=list)

    @property
    def transform_payload(self) -> Optional[Dict[str, Any]]:
        """The fitted model in persistable form, for storing with the map."""
        return self.model.serialize() if self.model is not None else None


def georeference_features(
    pixel_feature_collections: Sequence[JSONDict],
    control_points: Sequence[ControlPoint],
    *,
    frame_bounds: FrameBounds,
    image_size: Tuple[int, int],
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    record: Optional[RunRecord] = None,
    model: Optional[TransformModel] = None,
    extra_properties: Optional[Dict[str, Any]] = None,
    refine_piecewise: Optional[Callable[[Any, RunRecord], Any]] = None,
    bend_to_coast: Optional[Callable[[Any, RunRecord], Any]] = None,
    coast_misfit_px: Optional[Callable[[Any], float]] = None,
    score_snapping: bool = False,
) -> GeorefResult:
    """Georeference pixel-space features with an affine fitted to *control_points*."""

    record = record or RunRecord()
    record.set_config(config)

    if not pixel_feature_collections:
        logger.warning("No pixel feature collections provided")
        return GeorefResult(collections=[], model=None, record=record)

    # --- fit ----------------------------------------------------------------
    # The GCP-only affine is always fitted and recorded: it is the baseline
    # every other model is compared against, whichever one is applied.
    with record.phase("fit"):
        gcp_affine = fit_affine_from_control_points(control_points)
    record.set_model("gcp_affine", gcp_affine.serialize())

    base_is_gcp_affine = model is None
    if model is None:
        model = gcp_affine
    elif model.residuals_3857.size == 0:
        # A model from Step 4's optimiser arrives without residuals; measure it
        # against the control points so its error is reported, not "unknown".
        model.measure_against(control_points)

    use_piecewise = config.transform_model == "piecewise_affine"
    if config.transform_model == "auto":
        use_piecewise = _affine_misfit_exceeds_threshold(
            model, image_size, config, record
        )

    if use_piecewise:
        with record.phase("piecewise_correction"):
            model = _apply_piecewise_correction(
                model,
                control_points,
                config,
                record,
                image_size=image_size,
                refit_base=base_is_gcp_affine,
            )
    elif config.transform_model not in ("affine", "auto"):
        # A model named in the config that nothing here knows how to build
        # would otherwise place the map with the baseline and say nothing.
        raise ValueError(f"Unknown transform_model: {config.transform_model!r}")

    if config.align_after_piecewise:
        # Without a piecewise model (refused, or ``auto`` kept the affine), the
        # GCP affine is aligned instead: otherwise a run with no alignment
        # before the correction would end up with no alignment at all. An
        # affine that is already the aligned one is left as it is.
        if not isinstance(model, PiecewiseAffineModel) and not base_is_gcp_affine:
            record.set_errors(
                postAlignment={
                    "applied": False,
                    "skippedBecause": "no piecewise model, already aligned",
                }
            )
        elif refine_piecewise is None:
            record.set_errors(
                postAlignment={"applied": False, "skippedBecause": "no alignment inputs"}
            )
        else:
            with record.phase("post_piecewise_alignment"):
                model = refine_piecewise(model, record)

    if config.coast_bend:
        if bend_to_coast is None:
            record.set_errors(coastBend={"applied": False, "skippedBecause": "no alignment inputs"})
        else:
            with record.phase("coast_bend"):
                model = bend_to_coast(model, record)
        refused = not (record.errors.get("coastBend") or {}).get("applied")
        if config.coast_bend_fallback_piecewise and refused and not use_piecewise:
            # The bend was to replace the piecewise step and could not, or had
            # nothing to bend to: the step and the second alignment instead,
            # as before config v22.
            with record.phase("bend_fallback_piecewise"):
                model = _apply_piecewise_correction(
                    model,
                    control_points,
                    config,
                    record,
                    image_size=image_size,
                    refit_base=base_is_gcp_affine,
                )
                if isinstance(model, PiecewiseAffineModel) and refine_piecewise is not None:
                    model = refine_piecewise(model, record)
            record.set_errors(bendFallback={"applied": isinstance(model, PiecewiseAffineModel)})

    ref_lat = reference_latitude(frame_bounds)

    rmse_3857 = model.rmse_3857
    rmse_km = (
        webmercator_meters_to_km(rmse_3857, ref_lat) if rmse_3857 is not None else None
    )
    rmse_status = "ok" if rmse_3857 is not None else "no_redundancy"

    record.set_inputs(
        controlPoints=[cp.to_dict() for cp in control_points],
        controlPointCount=len(control_points),
        controlPointsBySource=count_by_source(control_points),
        # How the points cover the image, and the affine's leave-one-out:
        # inputs of the quality estimator (quality.py).
        controlPointLayout=control_point_layout(control_points, image_size),
        imageSize=[int(image_size[0]), int(image_size[1])],
        frameBounds=frame_bounds,
        referenceLatitude=ref_lat,
    )
    record.set_errors(
        affineLeaveOneOut=affine_leave_one_out(control_points, gcp_affine.meters_per_pixel)
    )
    # The model the features were actually placed with: the GCP affine, the
    # aligned affine, or either one under the piecewise correction.
    record.set_model("applied", model.serialize())
    record.set_errors(
        # None rather than NaN for a residual that could not be computed: a
        # leave-one-out pass reports NaN when its refit was impossible, and
        # NaN is not valid JSON for the readers of this record.
        gcpResiduals3857=[
            float(v) if math.isfinite(v) else None for v in model.residuals_3857
        ],
        gcpRmse3857=rmse_3857,
        gcpRmseKm=rmse_km,
        gcpRmseStatus=rmse_status,
        # in_sample, leave_one_out, or leave_one_out_fixed_base (optimistic:
        # the aligned affine underneath was fitted with every point).
        gcpRmseKind=getattr(model, "residuals_kind", RESIDUAL_IN_SAMPLE),
        # Which source is noisier is an empirical question (config.py, sigma),
        # and this is the number that answers it, one run at a time.
        gcpRmseKmBySource=_rmse_km_by_source(model, control_points, ref_lat),
        # Where the model puts each clicked pixel, in lon/lat, in the order of
        # inputs.controlPoints: the dev tool draws each residual on the map as
        # a line from the point's true position to this one.
        gcpPredictedLonLat=_predicted_lonlat(model, control_points),
    )

    # --- reference layers for snapping and clipping -------------------------
    coastline_geom_3857 = None
    land_mask_3857 = None

    if config.snap_to_coastline or score_snapping:
        with record.phase("load_coastline"):
            coastline_geom_wgs84 = load_coastline_geometry()
            if coastline_geom_wgs84 is not None:
                coastline_geom_3857 = transform(
                    lonlat_arrays_to_webmercator, coastline_geom_wgs84
                )

    snapping_enabled = config.snap_to_coastline and coastline_geom_3857 is not None

    if config.clip_to_land_mask:
        # Ocean and lakes, one mask, shared with the cleaning of expected zones
        # so a test scores the output against truth cut the same way
        # (cleaning.py; SUBTRACT_LAKES is the switch for both).
        with record.phase("load_land_mask"):
            land_mask_3857 = land_mask_3857_shared()

    both_ways = score_snapping and coastline_geom_3857 is not None
    snaps = snapping_enabled or both_ways
    # How far the reference coast sits from the drawn edges under the applied
    # model, for the measured tolerance; None without the alignment evidence.
    misfit_px = (
        coast_misfit_px(model)
        if snaps and config.coastline_snap_measured and coast_misfit_px is not None
        else None
    )
    snap_tolerance_m = (
        snap_tolerance_m_for(model, image_size, config, misfit_px) if snaps else None
    )
    coast_index = (
        CoastIndex.build(coastline_geom_3857)
        if snaps and config.coastline_snap_stretches
        else None
    )
    min_run_m = config.coastline_snap_min_run_px * model.meters_per_pixel

    def clean(geom_3857: Any, snap: bool) -> Tuple[Any, int, int]:
        """Snapped (with *snap*) then clipped to land: the zone in EPSG:3857, or
        None when the clip leaves too little of it; and the snap's counts."""
        total = snapped = 0
        if snap and coast_index is not None:
            geom_3857, total, snapped = snap_geometry_to_coastline_stretches(
                geom_3857,
                coast_index,
                snap_tolerance_m,
                min_run_m,
                config.coastline_snap_max_angle_deg,
                config.coastline_snap_max_area_change,
            )
        elif snap:
            geom_3857, total, snapped = snap_geometry_to_coastline(
                geom_3857, coastline_geom_3857, snap_tolerance_m
            )
        if config.clip_to_land_mask and land_mask_3857 is not None:
            geom_3857 = clip_zone_to_land_mask(
                geom_3857,
                land_mask_3857,
                land_coverage_threshold=config.land_coverage_threshold,
            )
        return geom_3857, total, snapped

    # --- apply --------------------------------------------------------------
    to_3857 = model.as_shapely_transform()

    # Only vertices are warped. A long straight edge crossing several of the
    # piecewise model's triangles, or under the coast bend, would stay
    # straight and cut across the correction, so geometries are densified
    # first. The affine maps straight lines to straight lines and needs none
    # of this.
    densify_px = (
        _densify_step_px(image_size, config)
        if not isinstance(model, AffineModel)
        else None
    )

    total_boundary_points = 0
    total_snapped_points = 0
    dropped_off_land = 0
    georef_collections: List[JSONDict] = []
    # The same zones straight out of the transform, before snapping and the
    # clip: what placement experiments are judged on, since cleaning corrects
    # and hides transform error.
    raw_collections: List[JSONDict] = []
    unsnapped_collections: List[JSONDict] = []
    snapped_collections: List[JSONDict] = []

    with record.phase("apply"):
        for fc in pixel_feature_collections:
            if fc.get("type") != "FeatureCollection":
                continue

            new_features: List[JSONDict] = []
            raw_features: List[JSONDict] = []
            both_features: Dict[bool, List[JSONDict]] = {False: [], True: []}

            for feat_idx, feat in enumerate(fc.get("features", [])):
                try:
                    geom = shape(feat.get("geometry"))
                except Exception as e:
                    logger.warning(
                        f"Failed to parse geometry at feature {feat_idx}: {e}"
                    )
                    continue

                props = dict(feat.get("properties", {}))
                props["is_pixel_space"] = False
                props["is_georeferenced"] = True
                props["crs"] = "EPSG:4326"
                props["transform_method"] = model.name
                # Ground kilometres, with the 1/cos(phi) WebMercator correction
                # applied. None means "not measurable", which is what an exact
                # 3-point fit actually tells you.
                props["rmse_km"] = (
                    float(round(rmse_km, 3)) if rmse_km is not None else None
                )
                props["rmse_status"] = rmse_status
                if extra_properties:
                    props.update(extra_properties)

                if densify_px:
                    geom = shapely.segmentize(geom, max_segment_length=densify_px)

                try:
                    geom_3857 = transform(to_3857, geom)
                except Exception as e:
                    logger.error(
                        f"Failed to transform feature {feat_idx}: {e}", exc_info=True
                    )
                    continue

                try:
                    raw_features.append(
                        {
                            "type": "Feature",
                            "properties": {**props, "cleaned": False},
                            "geometry": mapping(
                                transform(webmercator_arrays_to_lonlat, geom_3857)
                            ),
                        }
                    )
                except Exception as e:
                    logger.warning(f"Could not keep raw zone {feat_idx}: {e}")

                if both_ways:
                    for snap, out in both_features.items():
                        scored, _, _ = clean(geom_3857, snap)
                        if scored is not None:
                            out.append(
                                {
                                    "type": "Feature",
                                    "properties": props,
                                    "geometry": mapping(
                                        transform(webmercator_arrays_to_lonlat, scored)
                                    ),
                                }
                            )

                geom_3857, total_pts, snapped_pts = clean(geom_3857, snapping_enabled)
                total_boundary_points += total_pts
                total_snapped_points += snapped_pts
                if geom_3857 is None:
                    dropped_off_land += 1
                    continue

                try:
                    geom_wgs84 = transform(webmercator_arrays_to_lonlat, geom_3857)
                except Exception as e:
                    logger.error(
                        "Failed to convert transformed geometry to lon/lat at feature "
                        f"{feat_idx}: {e}",
                        exc_info=True,
                    )
                    continue

                new_features.append(
                    {
                        "type": "Feature",
                        "properties": props,
                        "geometry": mapping(geom_wgs84),
                    }
                )

            if new_features:
                georef_collections.append(
                    {"type": "FeatureCollection", "features": new_features}
                )
            if raw_features:
                raw_collections.append(
                    {"type": "FeatureCollection", "features": raw_features}
                )
            for snap, out in ((False, unsnapped_collections), (True, snapped_collections)):
                if both_features[snap]:
                    out.append({"type": "FeatureCollection", "features": both_features[snap]})

    record.set_errors(
        snapTotalBoundaryPoints=total_boundary_points,
        snapSnappedPoints=total_snapped_points,
        zonesDroppedOffLand=dropped_off_land,
    )
    record.set_inputs(
        snapToCoastline=snapping_enabled,
        snapToleranceMeters=snap_tolerance_m,
        snapMisfitPx=misfit_px,
        clipToLandMask=bool(config.clip_to_land_mask and land_mask_3857 is not None),
        densifyStepPx=densify_px,
    )

    return GeorefResult(
        collections=georef_collections,
        model=model,
        record=record,
        baseline=gcp_affine,
        raw_collections=raw_collections,
        unsnapped_collections=unsnapped_collections,
        snapped_collections=snapped_collections,
    )


def _affine_misfit_exceeds_threshold(
    affine: AffineModel,
    image_size: Tuple[int, int],
    config: GeorefConfig,
    record: RunRecord,
) -> bool:
    """``auto``: should the piecewise correction be applied on top of *affine*?"""

    diagonal_px = math.hypot(float(image_size[0]), float(image_size[1]))
    threshold_px = diagonal_px * config.auto_piecewise_rmse_ratio_of_diagonal
    rmse_3857 = affine.rmse_3857
    rmse_px = (
        rmse_3857 / affine.meters_per_pixel
        if rmse_3857 is not None and affine.meters_per_pixel > 0
        else None
    )
    use_piecewise = rmse_px is not None and rmse_px > threshold_px
    record.set_errors(
        autoAffineRmsePx=rmse_px,
        autoThresholdPx=threshold_px,
        autoChoseModel="piecewise_affine" if use_piecewise else "affine",
    )
    logger.info(
        f"[GEOREF] auto transform: affine RMSE "
        f"{'unknown' if rmse_px is None else f'{rmse_px:.2f} px'}"
        f" vs threshold {threshold_px:.2f} px ->"
        f" {'piecewise_affine' if use_piecewise else 'affine'}"
    )
    return use_piecewise


def _apply_piecewise_correction(
    base: AffineModel,
    control_points: Sequence[ControlPoint],
    config: GeorefConfig,
    record: RunRecord,
    image_size: Tuple[int, int],
    refit_base: bool = True,
) -> TransformModel:
    """Wrap *base* in a local correction, or return it unchanged."""

    # The frame the correction decays to zero on is padded around the image,
    # which holds every zone and every clicked point.
    extent = (0.0, 0.0, float(image_size[0]), float(image_size[1]))
    radius_px = None
    if config.piecewise_regularization == "local":
        radius_px = (
            math.hypot(float(image_size[0]), float(image_size[1]))
            * config.piecewise_influence_radius_ratio_of_diagonal
        )
    elif config.piecewise_regularization != "none":
        raise ValueError(
            f"Unknown piecewise_regularization: {config.piecewise_regularization!r}"
        )
    record.set_errors(
        piecewiseRegularization=config.piecewise_regularization,
        piecewiseInfluenceRadiusPx=radius_px,
    )
    try:
        model = fit_piecewise_from_control_points(
            control_points,
            extent=extent,
            base=None if refit_base else base,
            anchor_margin=config.piecewise_anchor_margin,
            influence_radius_px=radius_px,
        )
    except (ValueError, np.linalg.LinAlgError) as e:
        logger.warning(f"Piecewise correction refused, keeping the affine: {e}")
        record.set_errors(piecewiseApplied=False, piecewiseRefusedBecause=str(e))
        return base

    corrections = model.corrections_3857
    record.set_errors(
        piecewiseApplied=True,
        # How far the correction pulls the affine, in EPSG:3857 metres. A large
        # value is either real local distortion or a bad control point, and
        # this number alone cannot tell them apart.
        piecewiseMaxCorrection3857=float(corrections.max()) if corrections.size else 0.0,
        # Held-out error; `piecewiseResidualKind` says which kind.
        piecewiseLooRmse3857=model.rmse_3857,
        piecewiseResidualKind=model.residuals_kind,
        piecewiseExtentPx=list(extent),
    )
    return model


def snap_tolerance_m_for(
    model: TransformModel,
    image_size: Tuple[int, int],
    config: GeorefConfig,
    misfit_px: Optional[float] = None,
) -> float:
    """How far a zone vertex may be snapped, in EPSG:3857 metres: a share of
    the image diagonal, through the transform's scale. With
    ``coastline_snap_measured`` and a measured *misfit_px*, a multiple of it
    instead, between the floor and that share."""
    diagonal_px = math.hypot(float(image_size[0]), float(image_size[1]))
    tolerance_px = diagonal_px * config.coastline_snap_ratio_of_diagonal
    if config.coastline_snap_measured and misfit_px is not None and math.isfinite(misfit_px):
        tolerance_px = min(
            tolerance_px,
            max(config.coastline_snap_min_px, config.coastline_snap_misfit_factor * misfit_px),
        )
    return tolerance_px * model.meters_per_pixel


def _densify_step_px(image_size: Tuple[int, int], config: GeorefConfig) -> float:
    """Longest segment allowed before a piecewise warp, in pixels."""
    diagonal = math.hypot(float(image_size[0]), float(image_size[1]))
    return max(diagonal * config.piecewise_densify_ratio_of_diagonal, 1.0)


def _rmse_km_by_source(
    model: TransformModel,
    control_points: Sequence[ControlPoint],
    ref_lat: float,
) -> Dict[str, Optional[float]]:
    """RMS control-point error per source, in ground kilometres."""
    
    residuals = np.asarray(model.residuals_3857, dtype=float)
    no_evidence = model.rmse_3857 is None
    out: Dict[str, Optional[float]] = {}
    for source, count in count_by_source(control_points).items():
        if (
            count == 0
            or no_evidence
            or residuals.size != len(control_points)
        ):
            out[source] = None
            continue
        mask = np.array([cp.source == source for cp in control_points])
        r = residuals[mask]
        r = r[np.isfinite(r)]
        out[source] = (
            webmercator_meters_to_km(float(np.sqrt(np.mean(r**2))), ref_lat)
            if r.size
            else None
        )
    return out


def _predicted_lonlat(
    model: TransformModel, control_points: Sequence[ControlPoint]
) -> List[List[float]]:
    """``[lon, lat]`` the model maps each control point's pixel to."""
    if not control_points:
        return []
    pixels = np.array([cp.pixel for cp in control_points], dtype=float)
    X, Y = model(pixels[:, 0], pixels[:, 1])
    lon, lat = webmercator_arrays_to_lonlat(X, Y)
    return [[float(a), float(b)] for a, b in zip(np.ravel(lon), np.ravel(lat))]
