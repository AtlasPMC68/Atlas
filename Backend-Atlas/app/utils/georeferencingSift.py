import math
from typing import List, Tuple, Dict, Any
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
    """Convert WebMercator (EPSG:3857) to WGS84 lon/lat."""
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


def build_affine_from_point_pairs(
    pixel_points: List[XY],
    geo_points_lonlat: List[LonLat],
) -> np.ndarray:
    """Build affine transformation matrix from matched point pairs.
    
    Uses least-squares fitting to compute the 2D affine transformation that
    best maps pixel coordinates to geographic coordinates (via WebMercator).
    
    Args:
        pixel_points: List of (x, y) pixel coordinates
        geo_points_lonlat: List of (lon, lat) geographic coordinates
        
    Returns:
        3x3 affine transformation matrix
        
    Raises:
        ValueError: If inputs are invalid or insufficient points provided
    """
    try:
        if len(pixel_points) < 3 or len(geo_points_lonlat) < 3:
            raise ValueError("At least 3 point pairs are required for affine transformation")
        
        if len(pixel_points) != len(geo_points_lonlat):
            raise ValueError(
                f"Mismatch in point counts: {len(pixel_points)} pixel points "
                f"vs {len(geo_points_lonlat)} geo points"
            )
        
        logger.info(f"Building affine transform from {len(pixel_points)} point pairs")
        
        # Convert geographic coordinates to WebMercator
        geo_xy_points = [_lonlat_to_webmercator(lon, lat) for lon, lat in geo_points_lonlat]
        
        src = np.array(pixel_points, dtype=float)
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
        
        logger.info(f"Least squares - rank: {rank}, residuals: {residuals}")
        
        if residuals.size > 0:
            rmse = np.sqrt(residuals[0] / (2 * n))
            logger.info(f"RMSE of fit: {rmse:.2f} meters")
        
        if len(params) != 6:
            raise ValueError(f"Expected 6 parameters, got {len(params)}")
        
        a, b_coef, tx, c, d, ty = params
        
        M = np.array([
            [a, b_coef, tx],
            [c, d, ty],
            [0, 0, 1]
        ], dtype=float)
        
        logger.info("Affine matrix computed successfully")
        return M
        
    except Exception as e:
        logger.error(f"Error building affine transform: {str(e)}", exc_info=True)
        raise


def build_tps_from_point_pairs(
    pixel_points: List[XY],
    geo_points_lonlat: List[LonLat],
) -> ThinPlateSpline2D:
    """Build Thin-Plate Spline transformation from matched point pairs.
    
    TPS provides non-linear warping which can better handle distortions
    in historical maps. Recommended for 7+ point pairs.
    
    Args:
        pixel_points: List of (x, y) pixel coordinates
        geo_points_lonlat: List of (lon, lat) geographic coordinates
        
    Returns:
        ThinPlateSpline2D object
        
    Raises:
        ValueError: If inputs are invalid or insufficient points provided
    """
    try:
        if len(pixel_points) < 3 or len(geo_points_lonlat) < 3:
            raise ValueError("At least 3 point pairs are required for TPS")
        
        if len(pixel_points) != len(geo_points_lonlat):
            raise ValueError(
                f"Mismatch in point counts: {len(pixel_points)} pixel points "
                f"vs {len(geo_points_lonlat)} geo points"
            )
        
        logger.info(f"Building TPS transform from {len(pixel_points)} point pairs")
        
        # Convert geographic coordinates to WebMercator
        geo_xy_points = [_lonlat_to_webmercator(lon, lat) for lon, lat in geo_points_lonlat]
        
        src = np.array(pixel_points, dtype=float)
        dst = np.array(geo_xy_points, dtype=float)
        
        tps = ThinPlateSpline2D(src, dst)
        logger.info("TPS transform computed successfully")
        
        return tps
        
    except Exception as e:
        logger.error(f"Error building TPS transform: {str(e)}", exc_info=True)
        raise


def georeference_features_with_sift_points(
    pixel_feature_collections: List[Dict[str, Any]],
    pixel_points: List[XY],
    geo_points_lonlat: List[LonLat],
    use_tps: bool = False,
) -> List[Dict[str, Any]]:
    """Georeference pixel-space features using SIFT-matched point pairs.
    
    This function transforms feature collections from pixel coordinates to
    geographic coordinates (EPSG:4326) using either affine or TPS transformation.
    
    Args:
        pixel_feature_collections: List of GeoJSON FeatureCollections in pixel space
        pixel_points: List of (x, y) pixel coordinates from SIFT matching
        geo_points_lonlat: List of (lon, lat) geographic coordinates from SIFT matching
        use_tps: If True, use Thin-Plate Spline (recommended for 7+ points).
                 If False, use affine transformation (faster, works with 3+ points)
    
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

        logger.info(
            f"Georeferencing {len(pixel_feature_collections)} feature collections "
            f"using {len(pixel_points)} point pairs with {'TPS' if use_tps else 'affine'} transform"
        )
        
        # Build transformation
        if use_tps:
            if len(pixel_points) < 7:
                logger.warning(
                    f"Only {len(pixel_points)} points provided. "
                    f"TPS works better with 7+ points. Consider using affine instead."
                )
            tps = build_tps_from_point_pairs(pixel_points, geo_points_lonlat)
            transform_func = tps
        else:
            affine_matrix = build_affine_from_point_pairs(pixel_points, geo_points_lonlat)
            
            def affine_transform(x, y):
                """Apply affine transform: pixel coords -> WebMercator"""
                x_arr = np.asarray(x, dtype=float).ravel()
                y_arr = np.asarray(y, dtype=float).ravel()
                
                # Homogeneous coords
                pts = np.vstack([x_arr, y_arr, np.ones_like(x_arr)])
                transformed = affine_matrix @ pts
                
                X = transformed[0, :]
                Y = transformed[1, :]
                
                return X.reshape(np.asarray(x).shape), Y.reshape(np.asarray(y).shape)
            
            transform_func = affine_transform

        def _to_3857(x, y, z=None):
            """Apply transformation to get WebMercator coordinates"""
            X, Y = transform_func(x, y)
            if z is None:
                return X, Y
            return X, Y, z

        def _to_lonlat(x, y, z=None):
            """Convert WebMercator to lon/lat"""
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
                props["transform_method"] = "TPS" if use_tps else "affine"

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
        logger.error(f"Error in georeference_features_with_sift_points: {str(e)}", exc_info=True)
        raise
