import math
from typing import List, Tuple, Dict, Any, Optional
import logging

import numpy as np
from scipy.interpolate import Rbf
from shapely.geometry import shape, mapping
from shapely.ops import transform


logger = logging.getLogger(__name__)

LonLat = Tuple[float, float]
XY = Tuple[float, float]


R_EARTH = 6378137.0


def _lonlat_to_webmercator(lon: float, lat: float) -> XY:
    """Convert WGS84 lon/lat to WebMercator (EPSG:3857).

    This avoids adding pyproj as a dependency.
    """
    x = math.radians(lon) * R_EARTH
    # Clamp latitude for numerical stability
    lat = max(min(lat, 89.9), -89.9)
    y = math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) * R_EARTH
    return x, y


def _webmercator_to_lonlat(x: float, y: float) -> LonLat:
    lon = math.degrees(x / R_EARTH)
    lat = math.degrees(2.0 * math.atan(math.exp(y / R_EARTH)) - math.pi / 2.0)
    return lon, lat

class ThinPlateSpline2D:
    """Simple 2D Thin-Plate Spline wrapper using scipy's Rbf.

    Maps (x, y) pixel coordinates -> (X, Y) projected coordinates.
    """

    def __init__(self, src_xy: np.ndarray, dst_xy: np.ndarray):
        if src_xy.shape != dst_xy.shape:
            raise ValueError("src_xy and dst_xy must have same shape")
        if src_xy.shape[0] < 3:
            raise ValueError("At least 3 control points are required for TPS")

        x = src_xy[:, 0]
        y = src_xy[:, 1]
        X = dst_xy[:, 0]
        Y = dst_xy[:, 1]

        # Thin-plate spline radial basis
        self._rbf_x = Rbf(x, y, X, function="thin_plate")
        self._rbf_y = Rbf(x, y, Y, function="thin_plate")

    def __call__(self, x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        X = self._rbf_x(x, y)
        Y = self._rbf_y(x, y)
        return X, Y


def build_affine_from_control_polylines_and_points(
    pixel_polyline: List[XY],
    geo_polyline_lonlat: List[LonLat],
    pixel_points: Optional[List[XY]] = None,
    geo_points_lonlat: Optional[List[LonLat]] = None,
) -> np.ndarray:
    """Build affine transform from control polylines and optional points.
    
    Uses least-squares fitting when additional control points are provided.
    """
    try:
        if len(pixel_polyline) < 2 or len(geo_polyline_lonlat) < 2:
            raise ValueError("Both polylines must contain at least 2 points")
        
        logger.info(f"Building affine transform with {len(pixel_polyline)} polyline points")
        
        # Collect all control point pairs
        src_points = list(pixel_polyline)
        geo_xy_points = [_lonlat_to_webmercator(lon, lat) for lon, lat in geo_polyline_lonlat]
        
        # Add extra control points if provided
        if pixel_points and geo_points_lonlat:
            logger.info(f"Adding {len(pixel_points)} additional control points")
            src_points.extend(pixel_points)
            geo_xy_points.extend([
                _lonlat_to_webmercator(lon, lat) for lon, lat in geo_points_lonlat
            ])
        
        src = np.array(src_points, dtype=float)
        dst = np.array(geo_xy_points, dtype=float)
        
        logger.info(f"Source points shape: {src.shape}, Destination points shape: {dst.shape}")
        
        # Solve for affine transformation using least squares
        # [X]   [a  b  tx] [x]
        # [Y] = [c  d  ty] [y]
        # [1]   [0  0   1] [1]
        
        n = src.shape[0]
        
        # Build matrices for least squares: dst = A @ params
        # For X: X = a*x + b*y + tx
        # For Y: Y = c*x + d*y + ty
        
        A = np.zeros((2*n, 6))
        b_vec = np.zeros(2*n)
        
        for i in range(n):
            x, y = src[i]
            X, Y = dst[i]
            
            # Row for X equation
            A[2*i] = [x, y, 1, 0, 0, 0]
            b_vec[2*i] = X
            
            # Row for Y equation  
            A[2*i + 1] = [0, 0, 0, x, y, 1]
            b_vec[2*i + 1] = Y
        
        # Solve least squares
        params, residuals, rank, s = np.linalg.lstsq(A, b_vec, rcond=None)
        
        logger.info(f"Least squares - rank: {rank}, residuals shape: {residuals.shape if residuals.size > 0 else 'empty'}")
        
        if len(params) != 6:
            raise ValueError(f"Expected 6 parameters, got {len(params)}")
        
        a, b_coef, tx, c, d, ty = params
        
        M = np.array([
            [a, b_coef, tx],
            [c, d, ty],
            [0, 0, 1]
        ], dtype=float)
        
        logger.info(f"Affine matrix computed successfully")
        return M
        
    except Exception as e:
        logger.error(f"Error building affine transform: {str(e)}", exc_info=True)
        raise


def georeference_pixel_features(
    pixel_feature_collections: List[Dict[str, Any]],
    pixel_polyline: List[XY],
    geo_polyline_lonlat: List[LonLat],
    pixel_points: Optional[List[XY]] = None,
    geo_points_lonlat: Optional[List[LonLat]] = None
) -> List[Dict[str, Any]]:
    """Apply affine-based georeferencing to pixel-space feature collections.

    Returns new FeatureCollections in EPSG:4326 (lon/lat).
    """
    try:
        if not pixel_feature_collections:
            logger.warning("No pixel feature collections provided")
            return []

        # Basic validation/logging to help debug unexpected input types
        if pixel_polyline and isinstance(pixel_polyline[0], dict):
            raise TypeError(f"pixel_polyline contains dicts, expected (x, y) pairs: first={pixel_polyline[0]}")
        if geo_polyline_lonlat and isinstance(geo_polyline_lonlat[0], dict):
            raise TypeError(f"geo_polyline_lonlat contains dicts, expected (lon, lat) pairs: first={geo_polyline_lonlat[0]}")

        logger.info(f"Georeferencing {len(pixel_feature_collections)} feature collections")
        affine_matrix = build_affine_from_control_polylines_and_points(
            pixel_polyline, geo_polyline_lonlat, pixel_points, geo_points_lonlat
        )

        def _affine_to_3857(x, y, z=None):
            """Apply affine transform: pixel coords -> WebMercator"""
            x_arr = np.asarray(x, dtype=float).ravel()
            y_arr = np.asarray(y, dtype=float).ravel()
            
            # Homogeneous coords
            pts = np.vstack([x_arr, y_arr, np.ones_like(x_arr)])
            transformed = affine_matrix @ pts
            
            X = transformed[0, :]
            Y = transformed[1, :]
            
            if z is None:
                return X.reshape(np.asarray(x).shape), Y.reshape(np.asarray(y).shape)
            return X.reshape(np.asarray(x).shape), Y.reshape(np.asarray(y).shape), z

        def _to_lonlat(x, y, z=None):
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

        for fc_idx, fc in enumerate(pixel_feature_collections):
            if fc.get("type") != "FeatureCollection":
                logger.warning(f"Skipping non-FeatureCollection at index {fc_idx}")
                continue
            new_features: List[Dict[str, Any]] = []
            for feat_idx, feat in enumerate(fc.get("features", [])):
                try:
                    geom = shape(feat.get("geometry"))
                except Exception as e:
                    logger.warning(f"Failed to parse geometry at feature {feat_idx}: {e}")
                    continue

                try:
                    geom_3857 = transform(_affine_to_3857, geom)
                    geom_wgs84 = transform(_to_lonlat, geom_3857)
                except Exception as e:
                    logger.error(f"Failed to transform feature {feat_idx}: {e}", exc_info=True)
                    continue

                props = dict(feat.get("properties", {}))
                props["is_pixel_space"] = False
                props["is_georeferenced"] = True
                props["crs"] = "EPSG:4326"

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

        logger.info(f"Successfully georeferenced {len(georef_collections)} collections")
        return georef_collections
        
    except Exception as e:
        logger.error(f"Error in georeference_pixel_features: {str(e)}", exc_info=True)
        raise
