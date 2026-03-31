import json
import os
import logging
from functools import lru_cache
from typing import List, Optional, Tuple

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEOJSON_DIR = os.path.join(BASE_DIR, "..", "geojson")


def load_geojson(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def extract_linework(data: dict) -> List[BaseGeometry]:
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


def extract_ocean_points(data: dict) -> List[Point]:
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
def build_land_mask_cached(
    coastline_path: str,
    coastline_mtime: float,
    ocean_points_path: str,
    ocean_points_mtime: float,
) -> Optional[BaseGeometry]:
    
    # Here to silence unused variable warnings since we rely on lru_cache for caching based on these timestamps 
    _ = coastline_mtime
    _ = ocean_points_mtime

    coastline_data = load_geojson(coastline_path)
    ocean_points_data = load_geojson(ocean_points_path)
    if not coastline_data or not ocean_points_data:
        return None

    coastline_lines = extract_linework(coastline_data)
    ocean_points = extract_ocean_points(ocean_points_data)
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

    return build_land_mask_cached(
        coastline_path,
        float(coastline_mtime),
        ocean_points_path,
        float(ocean_points_mtime),
    )


# Keep only polygonal parts (Polygon/MultiPolygon) from any geometry output.
def extract_polygonal_geometry(candidate_geom: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
    if candidate_geom is None or candidate_geom.is_empty:
        return None
    if isinstance(candidate_geom, Polygon):
        return candidate_geom
    if isinstance(candidate_geom, MultiPolygon):
        return candidate_geom if len(candidate_geom.geoms) > 0 else None
    if hasattr(candidate_geom, "geoms"):
        polygon_parts: List[Polygon] = []
        for geom_part in candidate_geom.geoms:
            poly = extract_polygonal_geometry(geom_part)
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


def validate_and_repair_geometry(
    geom: Optional[BaseGeometry],
) -> Tuple[Optional[BaseGeometry], bool]:
    
    if geom is None or geom.is_empty:
        return geom, False

    if geom.is_valid:
        return geom, True

    try:
        repaired = geom.buffer(0)
        if repaired.is_valid and not repaired.is_empty:
            logger.warning("Geometry repaired: buffer(0) fixed invalid topology.")
            return repaired, True
    except Exception as e:
        logger.error("Failed to repair geometry: %s", e)

    logger.error("Geometry is invalid and could not be repaired.")
    return None, False


def clip_zone_to_land_mask(
    zone_geom_3857: BaseGeometry,
    land_mask_3857: BaseGeometry,
    land_coverage_threshold: float = 0.01,
) -> Optional[BaseGeometry]:
    
    if zone_geom_3857 is None or zone_geom_3857.is_empty:
        return None

    original_area = float(zone_geom_3857.area)

    # Validate input geometry before clipping
    validated_geom, is_valid = validate_and_repair_geometry(
        zone_geom_3857
    )
    if not is_valid:
        logger.error("Input geometry is invalid and cannot be clipped; skipping.")
        return None

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
        except Exception as retry_e:
            logger.warning(
                "Failed to clip geometry: topology error %s (retry failed: %s). Skipping.",
                e,
                retry_e,
            )
            clipped_geom = None

    if clipped_geom is None or clipped_geom.is_empty:
        logger.warning("Clipping to land produced no geometry; result would be 100%% ocean. Skipping.")
        return None

    # Validate and repair clipped geometry
    clipped_geom, is_valid = validate_and_repair_geometry(
        clipped_geom
    )
    if not is_valid:
        logger.warning("Clipped geometry is invalid and unrepairable. Skipping.")
        return None

    # Frontend only renders Polygon/MultiPolygon zones, so discard non-polygon leftovers.
    clipped_geom = extract_polygonal_geometry(clipped_geom)
    if clipped_geom is None or clipped_geom.is_empty:
        logger.warning("Clipping result has no polygonal geometry to render; skipping.")
        return None

    # Check minimum land coverage threshold
    clipped_area = float(clipped_geom.area)
    land_ratio = (clipped_area / original_area) if original_area > 0 else 0.0
    if land_ratio < land_coverage_threshold:
        logger.warning("Clipped geometry is below minimum land coverage threshold. Skipping.")
        return None

    return clipped_geom
