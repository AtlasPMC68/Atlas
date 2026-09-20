"""Post-hoc vertex snapping of zone boundaries onto the reference coastline.

This is the crude version of an idea the roadmap replaces (roadmap section 4.3):
it is nearest-point with no orientation test and no confidence weighting, and it
runs *before* any alignment has happened. It stays untouched through Step 1 so
that output does not move, and it is expected to be turned off as soon as
chamfer alignment begins -- it will actively fight the alignment.
"""

import json
import logging
import math
import os
from functools import lru_cache
from typing import List, Optional, Tuple

from shapely.geometry import MultiPolygon, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOJSON_DIR = os.path.join(BASE_DIR, "..", "geojson")


@lru_cache(maxsize=8)
def _load_coastline_geometry_cached(
    coastline_path: str,
    mtime: float,
) -> Optional[BaseGeometry]:
    """Load and union coastline features; cache by path + mtime."""
    # Keep mtime in signature so cache invalidates automatically when file changes.
    _ = mtime

    try:
        with open(coastline_path, "r", encoding="utf-8") as f:
            coastline_data = json.load(f)

        line_geometries: List[BaseGeometry] = []
        for feature in coastline_data.get("features", []):
            geom_data = feature.get("geometry")
            if not geom_data:
                continue
            geom = shape(geom_data)
            if geom and geom.is_valid and not geom.is_empty:
                line_geometries.append(geom)

        if not line_geometries:
            logger.warning("No valid coastline geometries found")
            return None

        return unary_union(line_geometries)

    except Exception as e:
        logger.error(f"Failed to load coastline geometry: {e}", exc_info=True)
        return None


def load_coastline_geometry(
    coastline_file: str = "ne_coastline.geojson",
) -> Optional[BaseGeometry]:
    """Load coastline linework as a single geometry for snapping."""
    coastline_path = os.path.join(GEOJSON_DIR, coastline_file)

    if not os.path.exists(coastline_path):
        logger.warning(f"Coastline file not found: {coastline_path}")
        return None

    try:
        mtime = os.path.getmtime(coastline_path)
    except OSError as e:
        logger.warning(f"Cannot stat coastline file '{coastline_path}': {e}")
        return None

    return _load_coastline_geometry_cached(coastline_path, float(mtime))


def _snap_ring_coords_to_coastline(
    coords: List[Tuple[float, float]],
    coastline_geom,
    snap_tolerance: float,
) -> Tuple[List[Tuple[float, float]], int, int]:
    """Snap ring coordinates to coastline where points are within tolerance."""
    if not coords:
        return coords, 0, 0

    snapped_coords: List[Tuple[float, float]] = []
    total_points = 0
    snapped_points = 0

    for x, y in coords:
        total_points += 1
        p = Point(float(x), float(y))
        distance = p.distance(coastline_geom)

        if distance <= snap_tolerance:
            _, nearest_on_coast = nearest_points(p, coastline_geom)
            snapped_coords.append((float(nearest_on_coast.x), float(nearest_on_coast.y)))
            snapped_points += 1
        else:
            snapped_coords.append((float(x), float(y)))

    # Ensure ring closure remains valid. Note this *forces* closure rather than
    # fixing it: if the first vertex snapped and the last did not, the last is
    # overwritten (current section 9, limitation 10). Left as-is on purpose --
    # changing it moves output, and the snapping stage is due for replacement.
    if snapped_coords and snapped_coords[0] != snapped_coords[-1]:
        snapped_coords[-1] = snapped_coords[0]

    return snapped_coords, total_points, snapped_points


def collect_polygons(candidate_geom: Optional[BaseGeometry]) -> List[Polygon]:
    """Extract only Polygon parts from Polygon/MultiPolygon/collections."""
    if candidate_geom is None or candidate_geom.is_empty:
        return []
    if candidate_geom.geom_type == "Polygon":
        return [candidate_geom]
    if candidate_geom.geom_type == "MultiPolygon":
        return list(candidate_geom.geoms)
    if hasattr(candidate_geom, "geoms"):
        parts: List[Polygon] = []
        for g in candidate_geom.geoms:
            parts.extend(collect_polygons(g))
        return parts
    return []


def snap_geometry_to_coastline(
    geom: Optional[BaseGeometry],
    coastline_geom: Optional[BaseGeometry],
    snap_tolerance: float,
) -> Tuple[Optional[BaseGeometry], int, int]:
    """Snap polygon boundary vertices to coastline and preserve valid geometry."""
    total_points = 0
    snapped_points = 0

    if coastline_geom is None or geom is None or geom.is_empty:
        return geom, total_points, snapped_points

    def snap_polygon(poly: Polygon) -> Tuple[BaseGeometry, int, int]:
        poly_total = 0
        poly_snapped = 0

        ext_coords = list(poly.exterior.coords)
        snapped_ext, t_ext, s_ext = _snap_ring_coords_to_coastline(
            ext_coords, coastline_geom, snap_tolerance
        )
        poly_total += t_ext
        poly_snapped += s_ext

        snapped_interiors = []
        for interior in poly.interiors:
            int_coords = list(interior.coords)
            snapped_int, t_int, s_int = _snap_ring_coords_to_coastline(
                int_coords, coastline_geom, snap_tolerance
            )
            poly_total += t_int
            poly_snapped += s_int
            snapped_interiors.append(snapped_int)

        snapped_poly = Polygon(snapped_ext, snapped_interiors)

        # Keep polygon stable if snapping creates invalid geometry
        if not snapped_poly.is_valid:
            repaired = snapped_poly.buffer(0)
            if repaired.is_valid and not repaired.is_empty:
                snapped_poly = repaired
            else:
                return poly, poly_total, 0

        return snapped_poly, poly_total, poly_snapped

    if geom.geom_type == "Polygon":
        snapped_geom, total_points, snapped_points = snap_polygon(geom)
        return snapped_geom, total_points, snapped_points

    if geom.geom_type == "MultiPolygon":
        snapped_parts = []
        for poly in geom.geoms:
            snapped_geom_part, t, s = snap_polygon(poly)
            total_points += t
            snapped_points += s
            snapped_parts.extend(collect_polygons(snapped_geom_part))

        if not snapped_parts:
            return geom, total_points, 0
        if len(snapped_parts) == 1:
            return snapped_parts[0], total_points, snapped_points
        return MultiPolygon(snapped_parts), total_points, snapped_points

    # Non-polygon geometries are left unchanged
    return geom, total_points, snapped_points


def estimate_pixel_diagonal_from_features(
    pixel_feature_collections: List[dict],
) -> Optional[float]:
    """Estimate pixel-space diagonal from all feature bounds.

    Note this keys off *feature* bounds rather than image size, so a map whose
    zones cluster in one corner gets a much smaller tolerance than the same map
    with spread-out zones (current section 9, limitation 9). Once the framing
    box and image dimensions are both available end to end this should key off
    the image instead.
    """
    minx = float("inf")
    miny = float("inf")
    maxx = float("-inf")
    maxy = float("-inf")
    found_any = False

    for fc in pixel_feature_collections:
        if fc.get("type") != "FeatureCollection":
            continue
        for feat in fc.get("features", []):
            geom_data = feat.get("geometry")
            if not geom_data:
                continue
            try:
                geom = shape(geom_data)
            except Exception:
                continue
            if geom is None or geom.is_empty:
                continue
            gx_min, gy_min, gx_max, gy_max = geom.bounds
            minx = min(minx, gx_min)
            miny = min(miny, gy_min)
            maxx = max(maxx, gx_max)
            maxy = max(maxy, gy_max)
            found_any = True

    if not found_any:
        return None

    width_px = max(0.0, maxx - minx)
    height_px = max(0.0, maxy - miny)
    diagonal_px = math.sqrt(width_px * width_px + height_px * height_px)
    if diagonal_px <= 0:
        return None
    return diagonal_px
