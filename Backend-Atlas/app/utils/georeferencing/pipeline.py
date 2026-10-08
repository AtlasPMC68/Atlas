"""Fit a transform from control points and apply it to pixel-space features.

This is the orchestration that used to live inline in ``georeferencingSift.py``:
fit affine -> snap to coastline -> clip to land -> convert to EPSG:4326. The
stages themselves are unchanged; what changed is that the model, the
hyperparameters and the run record are now first-class objects the caller can
inspect, persist and compare.
"""

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
from .records import RunRecord
from .snapping import load_coastline_geometry, snap_geometry_to_coastline

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
) -> GeorefResult:
    """Georeference pixel-space features with an affine fitted to *control_points*.

    Args:
        pixel_feature_collections: GeoJSON FeatureCollections in pixel space.
        control_points: pixel <-> geo pairs, with their source.
        frame_bounds: the world area the user framed; reported distances are
            corrected at its centre latitude.
        image_size: ``(width, height)`` of the scan, in pixels. The snap
            tolerance and the piecewise densification are shares of its
            diagonal, and the piecewise frame is padded around it.
        config: hyperparameters; see ``config.GeorefConfig``.
        record: optional run record, populated in place.
        model: a transform to apply instead of fitting one. Step 4 passes the
            gated alignment here; leaving it None reproduces the GCP-only fit.
        extra_properties: merged into every output feature's properties, so a
            consumer can see how the feature was placed.
        refine_piecewise: with ``config.align_after_piecewise``, called on the
            piecewise model to align it again (``post_align``), or on the GCP
            affine when there is no piecewise model. It needs the image's
            evidence, which this module never sees, so the caller supplies it.

    Returns:
        A ``GeorefResult`` whose ``collections`` are FeatureCollections in
        EPSG:4326.

    Raises:
        ValueError: If fewer than 3 control points are supplied.
    """
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
        frameBounds=frame_bounds,
        referenceLatitude=ref_lat,
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

    if config.snap_to_coastline:
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

    snap_tolerance_m = (
        snap_tolerance_m_for(model, image_size, config) if snapping_enabled else None
    )

    # --- apply --------------------------------------------------------------
    to_3857 = model.as_shapely_transform()

    # Only vertices are warped. A long straight edge crossing several of the
    # piecewise model's triangles would stay straight and cut across the
    # correction, so geometries are densified first. The affine maps straight
    # lines to straight lines and needs none of this.
    densify_px = (
        _densify_step_px(image_size, config)
        if isinstance(model, PiecewiseAffineModel)
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

    with record.phase("apply"):
        for fc in pixel_feature_collections:
            if fc.get("type") != "FeatureCollection":
                continue

            new_features: List[JSONDict] = []
            raw_features: List[JSONDict] = []

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

                if snapping_enabled:
                    geom_3857, total_pts, snapped_pts = snap_geometry_to_coastline(
                        geom_3857, coastline_geom_3857, snap_tolerance_m
                    )
                    total_boundary_points += total_pts
                    total_snapped_points += snapped_pts

                if config.clip_to_land_mask and land_mask_3857 is not None:
                    clipped_geom = clip_zone_to_land_mask(
                        geom_3857,
                        land_mask_3857,
                        land_coverage_threshold=config.land_coverage_threshold,
                    )
                    if clipped_geom is None:
                        dropped_off_land += 1
                        continue
                    geom_3857 = clipped_geom

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

    record.set_errors(
        snapTotalBoundaryPoints=total_boundary_points,
        snapSnappedPoints=total_snapped_points,
        zonesDroppedOffLand=dropped_off_land,
    )
    record.set_inputs(
        snapToCoastline=snapping_enabled,
        snapToleranceMeters=snap_tolerance_m,
        clipToLandMask=bool(config.clip_to_land_mask and land_mask_3857 is not None),
        densifyStepPx=densify_px,
    )

    return GeorefResult(
        collections=georef_collections,
        model=model,
        record=record,
        baseline=gcp_affine,
        raw_collections=raw_collections,
    )


def _affine_misfit_exceeds_threshold(
    affine: AffineModel,
    image_size: Tuple[int, int],
    config: GeorefConfig,
    record: RunRecord,
) -> bool:
    """``auto``: should the piecewise correction be applied on top of *affine*?

    Compares the affine's in-sample GCP RMS, in image pixels, against
    ``auto_piecewise_rmse_ratio_of_diagonal`` of the image diagonal. In-sample
    is what the affine can do with these points; the piecewise model reports
    its own leave-one-out error once applied. No redundancy (3 points) keeps
    the affine: an exact fit is no evidence of distortion.
    """
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
    """Wrap *base* in a local correction, or return it unchanged.

    ``refit_base``: *base* is the affine fitted to these same control points,
    so the piecewise model refits it itself -- identically -- and every
    leave-one-out fold refits it without the held-out point. Passing it as a
    fixed base instead lets the held-out point shape the affine it is measured
    against; with exactly 3 points that reported ~0 km. When *base* is the
    aligned model it cannot be refitted without the image, so it stays fixed
    and the error is labelled ``leave_one_out_fixed_base``.

    Raises only on a ``piecewise_regularization`` nothing here knows, like the
    caller does on an unknown ``transform_model``; otherwise never. The
    correction is refused for reasons that are properties of
    the user's clicks -- two points in the same place, or a set that folds the
    map -- and a refusal has to leave a working affine behind rather than fail
    the import. The reason is recorded either way, because "piecewise was on
    and the output is identical" is otherwise indistinguishable from a bug.
    """
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
    model: TransformModel, image_size: Tuple[int, int], config: GeorefConfig
) -> float:
    """How far a zone vertex may be snapped, in EPSG:3857 metres: a share of
    the image diagonal, through the transform's scale."""
    diagonal_px = math.hypot(float(image_size[0]), float(image_size[1]))
    return diagonal_px * config.coastline_snap_ratio_of_diagonal * model.meters_per_pixel


def _densify_step_px(image_size: Tuple[int, int], config: GeorefConfig) -> float:
    """Longest segment allowed before a piecewise warp, in pixels."""
    diagonal = math.hypot(float(image_size[0]), float(image_size[1]))
    return max(diagonal * config.piecewise_densify_ratio_of_diagonal, 1.0)


def _rmse_km_by_source(
    model: TransformModel,
    control_points: Sequence[ControlPoint],
    ref_lat: float,
) -> Dict[str, Optional[float]]:
    """RMS control-point error per source, in ground kilometres.

    Uses the model's own residuals -- leave-one-out for the piecewise model,
    whose in-sample residuals are 0 by construction. A source with no points,
    or whose residuals are unknown, reports None rather than 0 -- and so does
    every source when the fit has no redundancy (exactly 3 points), for the
    same reason ``rmse_3857`` does: an exact fit is no evidence, not 0 km.
    """
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
