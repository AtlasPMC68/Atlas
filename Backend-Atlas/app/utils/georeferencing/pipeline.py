"""Fit a transform from control points and apply it to pixel-space features.

This is the orchestration that used to live inline in ``georeferencingSift.py``:
fit affine -> snap to coastline -> clip to land -> convert to EPSG:4326. The
stages themselves are unchanged; what changed is that the model, the
hyperparameters and the run record are now first-class objects the caller can
inspect, persist and compare.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from shapely.geometry import mapping, shape
from shapely.ops import transform

from app.utils.coastline_land_mask import (
    clip_zone_to_land_mask,
    load_land_mask_from_coastline_and_ocean_points,
)

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .frame import FrameBounds
from .models import AffineModel, ControlPoint, fit_affine_from_control_points
from .projection import (
    lonlat_arrays_to_webmercator,
    reference_latitude,
    webmercator_arrays_to_lonlat,
    webmercator_meters_to_km,
)
from .records import RunRecord
from .snapping import (
    estimate_pixel_diagonal_from_features,
    load_coastline_geometry,
    snap_geometry_to_coastline,
)

logger = logging.getLogger(__name__)

JSONDict = Dict[str, Any]


@dataclass
class GeorefResult:
    """What a georeferencing run produced, beyond the features themselves."""

    collections: List[JSONDict] = field(default_factory=list)
    model: Optional[AffineModel] = None
    record: Optional[RunRecord] = None

    @property
    def transform_payload(self) -> Optional[Dict[str, Any]]:
        """The fitted model in persistable form, for storing with the map."""
        return self.model.serialize() if self.model is not None else None


def georeference_features(
    pixel_feature_collections: Sequence[JSONDict],
    control_points: Sequence[ControlPoint],
    frame_bounds: Optional[FrameBounds] = None,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    record: Optional[RunRecord] = None,
    coastline_snap_tolerance_px: Optional[float] = None,
    model: Optional[AffineModel] = None,
    extra_properties: Optional[Dict[str, Any]] = None,
) -> GeorefResult:
    """Georeference pixel-space features with an affine fitted to *control_points*.

    Args:
        pixel_feature_collections: GeoJSON FeatureCollections in pixel space.
        control_points: pixel <-> geo pairs, with source and sigma.
        frame_bounds: the world area the user framed, used for the latitude at
            which reported distances are corrected. Optional.
        config: hyperparameters; see ``config.GeorefConfig``.
        record: optional run record, populated in place.
        coastline_snap_tolerance_px: explicit pixel tolerance override.
        model: a transform to apply instead of fitting one. Step 4 passes the
            gated alignment here; leaving it None reproduces the GCP-only fit.
        extra_properties: merged into every output feature's properties, so a
            consumer can see how the feature was placed.

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
    if model is None:
        with record.phase("fit"):
            model = fit_affine_from_control_points(control_points)
    elif model.residuals_3857.size == 0:
        # A model from Step 4's optimiser arrives without residuals; measure it
        # against the control points so its error is reported, not "unknown".
        model.measure_against(control_points)

    geo_points = [cp.geo for cp in control_points]
    ref_lat = reference_latitude(frame_bounds, geo_points)

    rmse_3857 = model.rmse_3857
    rmse_km = (
        webmercator_meters_to_km(rmse_3857, ref_lat)
        if (rmse_3857 is not None and ref_lat is not None)
        else None
    )
    rmse_status = "ok" if rmse_3857 is not None else "no_redundancy"
    if rmse_3857 is not None and ref_lat is None:
        # Without a latitude we cannot honestly convert 3857 metres to ground
        # kilometres, so we say so rather than reporting the inflated number.
        rmse_status = "no_reference_latitude"

    record.set_inputs(
        controlPoints=[cp.to_dict() for cp in control_points],
        controlPointCount=len(control_points),
        frameBounds=frame_bounds,
        referenceLatitude=ref_lat,
    )
    record.set_model("stage2_affine", model.serialize())
    record.set_errors(
        gcpResiduals3857=[float(v) for v in model.residuals_3857],
        gcpRmse3857=rmse_3857,
        gcpRmseKm=rmse_km,
        gcpRmseStatus=rmse_status,
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
        with record.phase("load_land_mask"):
            land_mask_wgs84 = load_land_mask_from_coastline_and_ocean_points()
            if land_mask_wgs84 is not None:
                land_mask_3857 = transform(
                    lonlat_arrays_to_webmercator, land_mask_wgs84
                )
            else:
                logger.warning(
                    "Land/ocean mask unavailable; ocean clipping will be skipped."
                )

    snap_tolerance_m = None
    if snapping_enabled:
        snap_tolerance_m = _resolve_snap_tolerance_m(
            model,
            pixel_feature_collections,
            config,
            coastline_snap_tolerance_px,
        )

    # --- apply --------------------------------------------------------------
    to_3857 = model.as_shapely_transform()

    total_boundary_points = 0
    total_snapped_points = 0
    dropped_off_land = 0
    georef_collections: List[JSONDict] = []

    with record.phase("apply"):
        for fc in pixel_feature_collections:
            if fc.get("type") != "FeatureCollection":
                continue

            new_features: List[JSONDict] = []

            for feat_idx, feat in enumerate(fc.get("features", [])):
                try:
                    geom = shape(feat.get("geometry"))
                except Exception as e:
                    logger.warning(
                        f"Failed to parse geometry at feature {feat_idx}: {e}"
                    )
                    continue

                props = dict(feat.get("properties", {}))

                try:
                    geom_3857 = transform(to_3857, geom)
                except Exception as e:
                    logger.error(
                        f"Failed to transform feature {feat_idx}: {e}", exc_info=True
                    )
                    continue

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

    record.set_errors(
        snapTotalBoundaryPoints=total_boundary_points,
        snapSnappedPoints=total_snapped_points,
        zonesDroppedOffLand=dropped_off_land,
    )
    record.set_inputs(
        snapToCoastline=snapping_enabled,
        snapToleranceMeters=snap_tolerance_m,
        clipToLandMask=bool(config.clip_to_land_mask and land_mask_3857 is not None),
    )

    return GeorefResult(collections=georef_collections, model=model, record=record)


def _resolve_snap_tolerance_m(
    model: AffineModel,
    pixel_feature_collections: Sequence[JSONDict],
    config: GeorefConfig,
    coastline_snap_tolerance_px: Optional[float],
) -> float:
    """Pixel-space snap tolerance, converted to EPSG:3857 metres and clamped."""
    if coastline_snap_tolerance_px is None:
        diagonal_px = estimate_pixel_diagonal_from_features(
            list(pixel_feature_collections)
        )
        if diagonal_px is not None:
            tolerance_px = diagonal_px * config.coastline_snap_ratio_of_diagonal
        else:
            tolerance_px = config.coastline_snap_fallback_px
    else:
        tolerance_px = float(coastline_snap_tolerance_px)

    tolerance_px = min(
        config.coastline_snap_max_px, max(config.coastline_snap_min_px, tolerance_px)
    )

    tolerance_m = tolerance_px * model.meters_per_pixel
    return min(
        config.coastline_snap_max_m, max(config.coastline_snap_min_m, tolerance_m)
    )
