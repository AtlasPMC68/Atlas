import math
import json
import os
from functools import lru_cache
from typing import Dict, List, Optional, Tuple
import logging

import numpy as np
from shapely.geometry import shape, mapping, Point, Polygon, MultiPolygon
from shapely.ops import transform, unary_union, nearest_points
from shapely.geometry.base import BaseGeometry

from app.utils.coastline_land_mask import (
    clip_zone_to_land_mask,
    load_land_mask_from_coastline_and_ocean_points,
)

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEOJSON_DIR = os.path.join(BASE_DIR, "..", "geojson")

LonLat = Tuple[float, float]
XY = Tuple[float, float]
JSONDict = Dict[str, object]

R_EARTH = 6378137.0
DEBUG = False


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


def _load_coastline_geometry(
    coastline_file: str = "ne_coastline.geojson",
)-> Optional[BaseGeometry]:
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

    # Ensure ring closure remains valid
    if snapped_coords and snapped_coords[0] != snapped_coords[-1]:
        snapped_coords[-1] = snapped_coords[0]

    return snapped_coords, total_points, snapped_points


def _snap_geometry_to_coastline(
    geom: Optional[BaseGeometry],
    coastline_geom: Optional[BaseGeometry],
    snap_tolerance: float,
) -> Tuple[Optional[BaseGeometry], int, int]:
    """Snap polygon boundary vertices to coastline and preserve valid geometry."""
    total_points = 0
    snapped_points = 0

    if coastline_geom is None or geom is None or geom.is_empty:
        return geom, total_points, snapped_points

    def _collect_polygons(candidate_geom: Optional[BaseGeometry]) -> List[Polygon]:
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
                parts.extend(_collect_polygons(g))
            return parts
        return []

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
            snapped_parts.extend(_collect_polygons(snapped_geom_part))

        if not snapped_parts:
            return geom, total_points, 0
        if len(snapped_parts) == 1:
            return snapped_parts[0], total_points, snapped_points
        return MultiPolygon(snapped_parts), total_points, snapped_points

    # Non-polygon geometries are left unchanged
    return geom, total_points, snapped_points


def _lonlat_to_webmercator(lon: float, lat: float) -> XY:
    x = math.radians(lon) * R_EARTH
    lat = max(min(lat, 89.9), -89.9)
    y = math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) * R_EARTH
    return x, y


def _webmercator_to_lonlat(x: float, y: float) -> LonLat:
    lon = math.degrees(x / R_EARTH)
    lat = math.degrees(2.0 * math.atan(math.exp(y / R_EARTH)) - math.pi / 2.0)
    return lon, lat


def _lonlat_arrays_to_webmercator(x, y, z=None):
    """Vectorized transform callback for Shapely: lon/lat (EPSG:4326) -> EPSG:3857."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)

    X = np.radians(x_arr) * R_EARTH
    lat_clamped = np.clip(y_arr, -89.9, 89.9)
    Y = np.log(np.tan(np.pi / 4.0 + np.radians(lat_clamped) / 2.0)) * R_EARTH

    if z is None:
        return X, Y
    return X, Y, z


def _estimate_affine_meters_per_pixel(affine: "AffineTransformation") -> float:
    """Estimate average meters-per-pixel from affine linear terms."""
    a = float(affine.matrix[0, 0])
    b = float(affine.matrix[0, 1])
    c = float(affine.matrix[1, 0])
    d = float(affine.matrix[1, 1])

    scale_x = math.sqrt(a * a + c * c)
    scale_y = math.sqrt(b * b + d * d)
    return (scale_x + scale_y) / 2.0


def _estimate_pixel_diagonal_from_features(
    pixel_feature_collections: List[JSONDict],
) -> Optional[float]:
    """Estimate pixel-space diagonal from all feature bounds."""
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


class AffineTransformation:
    """2D Affine transformation for pixel -> coordinate mapping.
    
    Affine handles rotation, scale, translation, and shear.
    Much more stable than TPS - no wild extrapolation issues.
    
    Transformation: [X, Y] = M @ [x, y, 1]
    where M is 3x3 affine matrix.
    """

    def __init__(self, src_xy: np.ndarray, dst_xy: np.ndarray):
        if src_xy.shape != dst_xy.shape:
            raise ValueError("src_xy and dst_xy must have same shape")
        if src_xy.shape[0] < 3:
            raise ValueError("At least 3 control points are required for affine")

        # Solve for affine transformation using least squares
        # [X]   [a  b  tx] [x]
        # [Y] = [c  d  ty] [y]
        # [1]   [0  0  1 ] [1]
        
        n = src_xy.shape[0]
        
        # Build matrices for least squares
        A = np.zeros((2*n, 6))
        b_vec = np.zeros(2*n)
        
        for i in range(n):
            x, y = src_xy[i]
            X, Y = dst_xy[i]
            
            # Row for X equation: X = a*x + b*y + tx
            A[2*i] = [x, y, 1, 0, 0, 0]
            b_vec[2*i] = X
            
            # Row for Y equation: Y = c*x + d*y + ty
            A[2*i + 1] = [0, 0, 0, x, y, 1]
            b_vec[2*i + 1] = Y
        
        # Solve least squares
        params, residuals, _, _ = np.linalg.lstsq(A, b_vec, rcond=None)
        
        a, b, tx, c, d, ty = params
        
        # Store as 3x3 matrix
        self.matrix = np.array([
            [a, b, tx],
            [c, d, ty],
            [0, 0, 1]
        ], dtype=float)
        
        # Calculate RMSE
        if residuals.size > 0:
            self.rmse = np.sqrt(residuals[0] / (2 * n))
        else:
            self.rmse = 0.0

    def __call__(self, x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Transform pixel coordinates to WebMercator coordinates."""
        x_arr = np.asarray(x, dtype=float).ravel()
        y_arr = np.asarray(y, dtype=float).ravel()
        
        # Homogeneous coordinates
        pts = np.vstack([x_arr, y_arr, np.ones_like(x_arr)])
        transformed = self.matrix @ pts
        
        X = transformed[0, :]
        Y = transformed[1, :]
        
        return X.reshape(np.asarray(x).shape), Y.reshape(np.asarray(y).shape)


def georeference_features_with_sift_points(
    pixel_feature_collections: List[JSONDict],
    pixel_points: List[XY],
    geo_points_lonlat: List[LonLat],
    snap_to_coastline: bool = True,
    clip_to_land_mask: bool = True,
    land_coverage_threshold: float = 0.01,
    coastline_snap_ratio_of_diagonal: float = 0.01,
    coastline_snap_tolerance_px: Optional[float] = None,
) -> List[JSONDict]:
    """Georeference pixel-space features using affine transformation.
    
    Establishes a pixel -> coordinate relationship using affine transformation.
    Affine is stable and predictable - no wild extrapolation distortion.
    
    Args:
        pixel_feature_collections: List of GeoJSON FeatureCollections in pixel space
        pixel_points: List of (x, y) pixel coordinates from SIFT matching
        geo_points_lonlat: List of (lon, lat) geographic coordinates
        snap_to_coastline: Whether to snap nearby zone boundary points to coastline
        clip_to_land_mask: Whether to clip transformed zones to land and remove ocean portions
        land_coverage_threshold: Minimum land coverage (0..1) required to keep a zone
        coastline_snap_ratio_of_diagonal: Ratio of pixel diagonal used as default tolerance
        coastline_snap_tolerance_px: Explicit pixel tolerance override (if provided)
    
    Returns:
        List of georeferenced FeatureCollections in EPSG:4326
        
    Raises:
        ValueError: If inputs are invalid
        TypeError: If point format is incorrect
    """
    try:
        if not pixel_feature_collections:
            logger.warning("No pixel feature collections provided")
            return []

        # Validate input types
        if pixel_points and isinstance(pixel_points[0], dict):
            raise TypeError(f"pixel_points contains dicts, expected (x, y) tuples: {pixel_points[0]}")
        if geo_points_lonlat and isinstance(geo_points_lonlat[0], dict):
            raise TypeError(f"geo_points_lonlat contains dicts, expected (lon, lat) tuples: {geo_points_lonlat[0]}")

        if len(pixel_points) < 3 or len(geo_points_lonlat) < 3:
            raise ValueError("At least 3 point pairs are required for affine transformation")
        
        if len(pixel_points) != len(geo_points_lonlat):
            raise ValueError(
                f"Mismatch in point counts: {len(pixel_points)} pixel points "
                f"vs {len(geo_points_lonlat)} geo points"
            )
        
        # Convert geographic coordinates to WebMercator
        geo_xy_points = [_lonlat_to_webmercator(lon, lat) for lon, lat in geo_points_lonlat]
        
        src = np.array(pixel_points, dtype=float)
        dst = np.array(geo_xy_points, dtype=float)
        
        # Build affine transformation: pixel -> WebMercator
        affine = AffineTransformation(src, dst)
        coastline_geom_3857 = None
        land_mask_3857 = None
        meters_per_pixel = None
        diagonal_px = None
        snap_tolerance_px = None
        snap_tolerance_m = None

        if snap_to_coastline:
            coastline_geom_wgs84 = _load_coastline_geometry()
            if coastline_geom_wgs84 is not None:
                coastline_geom_3857 = transform(
                    _lonlat_arrays_to_webmercator,
                    coastline_geom_wgs84,
                )

        snapping_enabled = snap_to_coastline and coastline_geom_3857 is not None

        if clip_to_land_mask:
            land_mask_wgs84 = load_land_mask_from_coastline_and_ocean_points()
            if land_mask_wgs84 is not None:
                land_mask_3857 = transform(_lonlat_arrays_to_webmercator, land_mask_wgs84)
            else:
                logger.warning("Land/ocean mask unavailable; ocean clipping will be skipped.")

        if snapping_enabled:
            min_snap_px = 3.0
            max_snap_px = 40.0
            min_snap_m = 200.0
            max_snap_m = 50_000.0

            meters_per_pixel = _estimate_affine_meters_per_pixel(affine)
            diagonal_px = _estimate_pixel_diagonal_from_features(pixel_feature_collections)

            if coastline_snap_tolerance_px is None:
                if diagonal_px is not None:
                    snap_tolerance_px = diagonal_px * coastline_snap_ratio_of_diagonal
                else:
                    snap_tolerance_px = 8.0
            else:
                snap_tolerance_px = float(coastline_snap_tolerance_px)

            snap_tolerance_px = max(min_snap_px, snap_tolerance_px)
            snap_tolerance_px = min(max_snap_px, snap_tolerance_px)

            snap_tolerance_m = snap_tolerance_px * meters_per_pixel
            snap_tolerance_m = max(min_snap_m, snap_tolerance_m)
            snap_tolerance_m = min(max_snap_m, snap_tolerance_m)

        total_boundary_points = 0
        total_snapped_points = 0

        def _to_3857(x, y, z=None):
            """Apply affine: pixel -> WebMercator"""
            X, Y = affine(x, y)
            if z is None:
                return X, Y
            return X, Y, z

        def _to_lonlat(x, y, z=None):
            """Convert WebMercator -> lon/lat"""
            x_arr = np.asarray(x, dtype=float)
            y_arr = np.asarray(y, dtype=float)
            lons = np.empty_like(x_arr)
            lats = np.empty_like(y_arr)
            for i in range(x_arr.size):
                lon, lat = _webmercator_to_lonlat(float(x_arr.flat[i]), float(y_arr.flat[i]))
                lons.flat[i] = lon
                lats.flat[i] = lat
            if z is None:
                return lons, lats
            return lons, lats, z

        georef_collections: List[JSONDict] = []

        for _, fc in enumerate(pixel_feature_collections):
            if fc.get("type") != "FeatureCollection":
                continue
                
            new_features: List[JSONDict] = []
            
            for feat_idx, feat in enumerate(fc.get("features", [])):
                try:
                    geom = shape(feat.get("geometry"))
                except Exception as e:
                    logger.warning(f"Failed to parse geometry at feature {feat_idx}: {e}")
                    continue

                props = dict(feat.get("properties", {}))

                try:
                    # Transform: pixel -> WebMercator
                    geom_3857 = transform(_to_3857, geom)
                except Exception as e:
                    logger.error(f"Failed to transform feature {feat_idx}: {e}", exc_info=True)
                    continue

                if snapping_enabled:
                    geom_3857, total_pts, snapped_pts = _snap_geometry_to_coastline(
                        geom_3857,
                        coastline_geom_3857,
                        snap_tolerance_m,
                    )
                    total_boundary_points += total_pts
                    total_snapped_points += snapped_pts

                if clip_to_land_mask and land_mask_3857 is not None:
                    clipped_geom = clip_zone_to_land_mask(
                        geom_3857,
                        land_mask_3857,
                        land_coverage_threshold=land_coverage_threshold,
                    )
                    if clipped_geom is None:
                        continue

                    geom_3857 = clipped_geom

                try:
                    # Convert WebMercator -> WGS84 (after optional snapping)
                    geom_wgs84 = transform(_to_lonlat, geom_3857)
                except Exception as e:
                    logger.error(
                        f"Failed to convert transformed geometry to lon/lat at feature {feat_idx}: {e}",
                        exc_info=True,
                    )
                    continue

                # Update properties
                props["is_pixel_space"] = False
                props["is_georeferenced"] = True
                props["crs"] = "EPSG:4326"
                props["transform_method"] = "affine"
                props["rmse_meters"] = float(round(affine.rmse, 2))

                new_features.append(
                    {
                        "type": "Feature",
                        "properties": props,
                        "geometry": mapping(geom_wgs84),
                    }
                )

            if new_features:
                georef_collections.append(
                    {
                        "type": "FeatureCollection",
                        "features": new_features,
                    }
                )

        return georef_collections
        
    except Exception as e:
        logger.error(f"Error in georeference_features_with_sift_points: {str(e)}", exc_info=True)
        raise
