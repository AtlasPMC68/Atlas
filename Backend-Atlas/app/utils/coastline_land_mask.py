import json
import os
import logging
from functools import lru_cache
from typing import List, Optional, Tuple, NamedTuple

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEOJSON_DIR = os.path.join(BASE_DIR, "..", "geojson")


def _load_geojson(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _extract_linework(data: dict) -> List[BaseGeometry]:
    lines: List[BaseGeometry] = []
    for feature in data.get("features", []):
        geom_data = feature.get("geometry")
        if not geom_data:
            continue
        try:
            geom = shape(geom_data)
        except Exception:
            continue
        if geom is None or geom.is_empty or not geom.is_valid:
            continue
        if isinstance(geom, (LineString, MultiLineString)):
            lines.append(geom)
    return lines


def _extract_ocean_points(data: dict) -> List[Point]:
    points: List[Point] = []
    for feature in data.get("features", []):
        geom_data = feature.get("geometry")
        if not geom_data:
            continue
        try:
            geom = shape(geom_data)
        except Exception:
            continue
        if isinstance(geom, Point) and not geom.is_empty:
            points.append(geom)
    return points


@lru_cache(maxsize=4)
def _build_land_mask_cached(
    coastline_path: str,
    coastline_mtime: float,
    ocean_points_path: str,
    ocean_points_mtime: float,
) -> Optional[BaseGeometry]:
    # Keep mtimes in signature so cache invalidates when files are updated.
    _ = coastline_mtime
    _ = ocean_points_mtime

    coastline_data = _load_geojson(coastline_path)
    ocean_points_data = _load_geojson(ocean_points_path)
    if not coastline_data or not ocean_points_data:
        return None

    coastline_lines = _extract_linework(coastline_data)
    ocean_points = _extract_ocean_points(ocean_points_data)
    if not coastline_lines or not ocean_points:
        return None

    world_bounds = box(-180.0, -89.9, 180.0, 89.9)

    # Build a planar arrangement where coastline lines and world boundary split faces.
    arrangement = unary_union([unary_union(coastline_lines), world_bounds.boundary])
    faces = list(polygonize(arrangement))
    if not faces:
        return None

    ocean_faces: List[BaseGeometry] = []
    for face in faces:
        if face.is_empty:
            continue
        prepared_face = prep(face)
        if any(prepared_face.contains(pt) for pt in ocean_points):
            ocean_faces.append(face)

    if not ocean_faces:
        return None

    ocean_geom = unary_union(ocean_faces)
    land_mask = world_bounds.difference(ocean_geom)

    if land_mask.is_empty:
        return None

    if not land_mask.is_valid:
        repaired = land_mask.buffer(0)
        if repaired.is_valid and not repaired.is_empty:
            land_mask = repaired
        else:
            return None

    return land_mask


def load_land_mask_from_coastline_and_ocean_points(
    coastline_file: str = "ne_coastline.geojson",
    ocean_points_file: str = "ne_ocean_points.geojson",
) -> Optional[BaseGeometry]:
    coastline_path = os.path.join(GEOJSON_DIR, coastline_file)
    ocean_points_path = os.path.join(GEOJSON_DIR, ocean_points_file)

    if not os.path.exists(coastline_path) or not os.path.exists(ocean_points_path):
        return None

    try:
        coastline_mtime = os.path.getmtime(coastline_path)
        ocean_points_mtime = os.path.getmtime(ocean_points_path)
    except OSError:
        return None

    return _build_land_mask_cached(
        coastline_path,
        float(coastline_mtime),
        ocean_points_path,
        float(ocean_points_mtime),
    )


class ZoneClippingResult(NamedTuple):
    """Result of attempting to clip a zone to the land mask."""

    clipped_geom: Optional[BaseGeometry]  # Clipped geometry (None if should skip)
    skip_reason: Optional[str]  # Reason if skipped (None if kept)
    land_percentage: float  # Percentage of zone on land (0-100)
    ocean_percentage: float  # Percentage of zone in ocean (0-100)


def _extract_polygonal_geometry(candidate_geom: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
    """Keep only polygonal parts (Polygon/MultiPolygon) from any geometry output."""
    if candidate_geom is None or candidate_geom.is_empty:
        return None
    if isinstance(candidate_geom, Polygon):
        return candidate_geom
    if isinstance(candidate_geom, MultiPolygon):
        return candidate_geom if len(candidate_geom.geoms) > 0 else None
    if hasattr(candidate_geom, "geoms"):
        polygon_parts: List[Polygon] = []
        for geom_part in candidate_geom.geoms:
            poly = _extract_polygonal_geometry(geom_part)
            if poly is None:
                continue
            if isinstance(poly, Polygon):
                polygon_parts.append(poly)
            elif isinstance(poly, MultiPolygon):
                polygon_parts.extend(list(poly.geoms))
        if not polygon_parts:
            return None
        if len(polygon_parts) == 1:
            return polygon_parts[0]
        return MultiPolygon(polygon_parts)
    return None


def _validate_and_repair_geometry(
    geom: Optional[BaseGeometry], feat_idx: int, context: str = "", zone_label: str = "unknown-zone"
) -> Tuple[Optional[BaseGeometry], bool]:
    """
    Validate and repair invalid geometries. Returns (repaired_geom, is_valid).

    Args:
        geom: Geometry to validate
        feat_idx: Feature index for logging
        context: Context string for logging (e.g., "before clipping")

    Returns:
        Tuple of (repaired geometry or None, is valid)
    """
    if geom is None or geom.is_empty:
        return geom, False

    if geom.is_valid:
        return geom, True

    # Try to repair with buffer(0)
    try:
        repaired = geom.buffer(0)
        if repaired.is_valid and not repaired.is_empty:
            logger.warning(
                "Geometry repaired for zone '%s' (feature %s) %s: buffer(0) fixed invalid topology.",
                zone_label,
                feat_idx,
                context,
            )
            return repaired, True
    except Exception as e:
        logger.error(
            "Failed to repair geometry for zone '%s' (feature %s) %s: %s",
            zone_label,
            feat_idx,
            context,
            e,
        )

    logger.error(
        "Geometry is invalid and could not be repaired for zone '%s' (feature %s) %s",
        zone_label,
        feat_idx,
        context,
    )
    return None, False


def clip_zone_to_land_mask(
    zone_geom_3857: BaseGeometry,
    land_mask_3857: BaseGeometry,
    feat_idx: int,
    zone_label: str = "unknown-zone",
    land_coverage_threshold: float = 0.10,
) -> ZoneClippingResult:
    """
    Clip a zone geometry to the land mask, removing ocean portions.

    Args:
        zone_geom_3857: Zone geometry in EPSG:3857 (Web Mercator)
        land_mask_3857: Land mask geometry in EPSG:3857
        feat_idx: Feature index for logging
        land_coverage_threshold: Minimum land percentage to keep zone (default 10%)

    Returns:
        ZoneClippingResult with clipped geometry, skip reason, and percentages
    """
    if zone_geom_3857 is None or zone_geom_3857.is_empty:
        return ZoneClippingResult(
            clipped_geom=None,
            skip_reason="empty_input",
            land_percentage=0.0,
            ocean_percentage=100.0,
        )

    original_area = float(zone_geom_3857.area)

    # Validate input geometry before clipping
    validated_geom, is_valid = _validate_and_repair_geometry(
        zone_geom_3857, feat_idx, "before ocean clipping", zone_label
    )
    if not is_valid:
        logger.error(
            "Zone '%s' (feature %s) has invalid geometry and cannot be clipped; skipping.",
            zone_label,
            feat_idx,
        )
        return ZoneClippingResult(
            clipped_geom=None,
            skip_reason="invalid_input_geometry",
            land_percentage=0.0,
            ocean_percentage=100.0,
        )

    zone_geom_3857 = validated_geom
    clipped_geom = None

    try:
        # Clip zone to land mask (removes ocean portions)
        clipped_geom = zone_geom_3857.intersection(land_mask_3857)
    except Exception as e:
        # Topology errors can happen with complex polygon boundaries.
        # Retry with repaired geometries before giving up on clipping.
        try:
            repaired_zone = zone_geom_3857.buffer(0)
            repaired_land = land_mask_3857.buffer(0)
            clipped_geom = repaired_zone.intersection(repaired_land)
            logger.info(
                "Zone '%s' (feature %s): topology exception fixed with buffer(0) repair.",
                zone_label,
                feat_idx,
            )
        except Exception as retry_e:
            logger.warning(
                "Failed to clip zone '%s' (feature %s): topology error %s (retry failed: %s). Skipping zone.",
                zone_label,
                feat_idx,
                e,
                retry_e,
            )
            clipped_geom = None

    if clipped_geom is None or clipped_geom.is_empty:
        logger.warning(
            "Zone '%s' (feature %s): clipping to land produced no geometry. Zone would be 100%% ocean. Skipping zone.",
            zone_label,
            feat_idx,
        )
        return ZoneClippingResult(
            clipped_geom=None,
            skip_reason="entirely_in_ocean",
            land_percentage=0.0,
            ocean_percentage=100.0,
        )

    # Validate and repair clipped geometry
    clipped_geom, is_valid = _validate_and_repair_geometry(
        clipped_geom, feat_idx, "after ocean clipping", zone_label
    )
    if not is_valid:
        logger.warning(
            "Zone '%s' (feature %s): clipped geometry is invalid and unrepairable. Skipping zone.",
            zone_label,
            feat_idx,
        )
        return ZoneClippingResult(
            clipped_geom=None,
            skip_reason="invalid_clipped_geometry",
            land_percentage=0.0,
            ocean_percentage=100.0,
        )

    # Frontend only renders Polygon/MultiPolygon zones, so discard non-polygon leftovers.
    clipped_geom = _extract_polygonal_geometry(clipped_geom)
    if clipped_geom is None or clipped_geom.is_empty:
        logger.warning(
            "Zone '%s' (feature %s): clipping result has no polygonal geometry to render; skipping zone.",
            zone_label,
            feat_idx,
        )
        return ZoneClippingResult(
            clipped_geom=None,
            skip_reason="non_polygon_clipped_geometry",
            land_percentage=0.0,
            ocean_percentage=100.0,
        )

    # Check ocean coverage: only keep if clipped area > threshold
    clipped_area = float(clipped_geom.area)
    land_percentage = (clipped_area / original_area) * 100.0 if original_area > 0 else 0.0
    ocean_percentage = 100.0 - land_percentage

    if land_percentage < (land_coverage_threshold * 100.0):
        logger.warning(
            "Zone '%s' (feature %s): %.1f%% in ocean, %.1f%% on land. Threshold is %.0f%% land minimum. Skipping zone.",
            zone_label,
            feat_idx,
            ocean_percentage,
            land_percentage,
            land_coverage_threshold * 100.0,
        )
        return ZoneClippingResult(
            clipped_geom=None,
            skip_reason="excessive_ocean_coverage",
            land_percentage=land_percentage,
            ocean_percentage=ocean_percentage,
        )

    logger.info(
        "Zone '%s' (feature %s): %.1f%% on land, %.1f%% in ocean. Keeping clipped geometry (type=%s, area=%.2f).",
        zone_label,
        feat_idx,
        land_percentage,
        ocean_percentage,
        clipped_geom.geom_type,
        float(clipped_geom.area),
    )

    return ZoneClippingResult(
        clipped_geom=clipped_geom,
        skip_reason=None,
        land_percentage=land_percentage,
        ocean_percentage=ocean_percentage,
    )
