import math
from typing import List, Tuple, Dict, Any
import logging

import numpy as np
from shapely.geometry import shape, mapping
from shapely.ops import transform

logger = logging.getLogger(__name__)

LonLat = Tuple[float, float]
XY = Tuple[float, float]

R_EARTH = 6378137.0


def _lonlat_to_webmercator(lon: float, lat: float) -> XY:
    x = math.radians(lon) * R_EARTH
    lat = max(min(lat, 89.9), -89.9)
    y = math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) * R_EARTH
    return x, y


def _webmercator_to_lonlat(x: float, y: float) -> LonLat:
    lon = math.degrees(x / R_EARTH)
    lat = math.degrees(2.0 * math.atan(math.exp(y / R_EARTH)) - math.pi / 2.0)
    return lon, lat


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
    pixel_feature_collections: List[Dict[str, Any]],
    pixel_points: List[XY],
    geo_points_lonlat: List[LonLat],
) -> List[Dict[str, Any]]:
    """Georeference pixel-space features using affine transformation.
    
    Establishes a pixel -> coordinate relationship using affine transformation.
    Affine is stable and predictable - no wild extrapolation distortion.
    
    Args:
        pixel_feature_collections: List of GeoJSON FeatureCollections in pixel space
        pixel_points: List of (x, y) pixel coordinates from SIFT matching
        geo_points_lonlat: List of (lon, lat) geographic coordinates
    
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

        georef_collections: List[Dict[str, Any]] = []

        for _, fc in enumerate(pixel_feature_collections):
            if fc.get("type") != "FeatureCollection":
                continue
                
            new_features: List[Dict[str, Any]] = []
            
            for feat_idx, feat in enumerate(fc.get("features", [])):
                try:
                    geom = shape(feat.get("geometry"))
                except Exception as e:
                    logger.warning(f"Failed to parse geometry at feature {feat_idx}: {e}")
                    continue

                try:
                    # Transform: pixel -> WebMercator -> WGS84
                    geom_3857 = transform(_to_3857, geom)
                    geom_wgs84 = transform(_to_lonlat, geom_3857)
                except Exception as e:
                    logger.error(f"Failed to transform feature {feat_idx}: {e}", exc_info=True)
                    continue

                # Update properties
                props = dict(feat.get("properties", {}))
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
