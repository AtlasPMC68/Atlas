import math
from typing import List, Tuple, Dict, Any, Optional
import logging

import numpy as np
from scipy.interpolate import Rbf
from shapely.geometry import shape, mapping
from shapely.ops import transform
import cv2


logger = logging.getLogger(__name__)

LonLat = Tuple[float, float]
XY = Tuple[float, float]

R_EARTH = 6378137.0


class TransformationResult:
    """Container for transformation matrix and quality metrics."""
    def __init__(
        self, 
        matrix: np.ndarray, 
        transform_type: str,
        inliers_mask: Optional[np.ndarray] = None,
        reprojection_error: Optional[float] = None
    ):
        self.matrix = matrix
        self.transform_type = transform_type
        self.inliers_mask = inliers_mask
        self.reprojection_error = reprojection_error
        self.num_inliers = np.sum(inliers_mask) if inliers_mask is not None else None


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


def build_homography_from_point_pairs(
    pixel_points: List[XY],
    geo_points_lonlat: List[LonLat],
    use_ransac: bool = True,
    ransac_threshold: float = 5.0,
) -> TransformationResult:
    """Build homography transformation from matched point pairs with RANSAC.
    
    Homography (8 DOF) handles perspective distortion better than affine (6 DOF).
    RANSAC automatically filters outliers from SIFT matching.
    
    Args:
        pixel_points: List of (x, y) pixel coordinates from SIFT
        geo_points_lonlat: List of (lon, lat) geographic coordinates
        use_ransac: Whether to use RANSAC for outlier rejection
        ransac_threshold: Maximum allowed reprojection error (meters) for RANSAC inliers
        
    Returns:
        TransformationResult with 3x3 homography matrix and quality metrics
        
    Raises:
        ValueError: If inputs are invalid or insufficient points provided
    """
    try:
        min_points = 4  # Homography requires minimum 4 points
        if len(pixel_points) < min_points or len(geo_points_lonlat) < min_points:
            raise ValueError(f"At least {min_points} point pairs are required for homography")
        
        if len(pixel_points) != len(geo_points_lonlat):
            raise ValueError(
                f"Mismatch in point counts: {len(pixel_points)} pixel points "
                f"vs {len(geo_points_lonlat)} geo points"
            )
        
        logger.info(f"Building homography transform from {len(pixel_points)} point pairs")
        
        # Convert geographic coordinates to WebMercator
        geo_xy_points = [_lonlat_to_webmercator(lon, lat) for lon, lat in geo_points_lonlat]
        
        src_pts = np.array(pixel_points, dtype=np.float32).reshape(-1, 1, 2)
        dst_pts = np.array(geo_xy_points, dtype=np.float32).reshape(-1, 1, 2)
        
        # Compute homography with or without RANSAC
        if use_ransac and len(pixel_points) >= 4:
            H, mask = cv2.findHomography(
                src_pts, 
                dst_pts, 
                cv2.RANSAC, 
                ransac_threshold
            )
            inliers_mask = mask.ravel().astype(bool) if mask is not None else None
            num_inliers = np.sum(inliers_mask) if inliers_mask is not None else 0
            
            logger.info(
                f"RANSAC homography: {num_inliers}/{len(pixel_points)} inliers "
                f"({100*num_inliers/len(pixel_points):.1f}%)"
            )
            
            if num_inliers < min_points:
                logger.warning(f"Only {num_inliers} inliers found, falling back to all points")
                H, _ = cv2.findHomography(src_pts, dst_pts, 0)
                inliers_mask = None
        else:
            H, _ = cv2.findHomography(src_pts, dst_pts, 0)
            inliers_mask = None
        
        if H is None:
            raise ValueError("Failed to compute homography")
        
        # Calculate reprojection error
        reprojection_error = _calculate_reprojection_error(src_pts, dst_pts, H, inliers_mask)
        logger.info(f"Reprojection error: {reprojection_error:.2f} meters")
        
        result = TransformationResult(
            matrix=H,
            transform_type="homography",
            inliers_mask=inliers_mask,
            reprojection_error=reprojection_error
        )
        
        logger.info("Homography matrix computed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Error building homography transform: {str(e)}", exc_info=True)
        raise


def build_affine_from_point_pairs(
    pixel_points: List[XY],
    geo_points_lonlat: List[LonLat],
    use_ransac: bool = True,
    ransac_threshold: float = 5.0,
) -> TransformationResult:
    """Build affine transformation from matched point pairs with optional RANSAC.
    
    Affine (6 DOF) handles rotation, scale, translation, and shear.
    Simpler than homography but doesn't handle perspective distortion.
    
    Args:
        pixel_points: List of (x, y) pixel coordinates from SIFT
        geo_points_lonlat: List of (lon, lat) geographic coordinates
        use_ransac: Whether to use RANSAC for outlier rejection
        ransac_threshold: Maximum allowed reprojection error (meters) for RANSAC inliers
        
    Returns:
        TransformationResult with 3x3 affine matrix and quality metrics
        
    Raises:
        ValueError: If inputs are invalid or insufficient points provided
    """
    try:
        min_points = 3  # Affine requires minimum 3 points
        if len(pixel_points) < min_points or len(geo_points_lonlat) < min_points:
            raise ValueError(f"At least {min_points} point pairs are required for affine transformation")
        
        if len(pixel_points) != len(geo_points_lonlat):
            raise ValueError(
                f"Mismatch in point counts: {len(pixel_points)} pixel points "
                f"vs {len(geo_points_lonlat)} geo points"
            )
        
        logger.info(f"Building affine transform from {len(pixel_points)} point pairs")
        
        # Convert geographic coordinates to WebMercator
        geo_xy_points = [_lonlat_to_webmercator(lon, lat) for lon, lat in geo_points_lonlat]
        
        src_pts = np.array(pixel_points, dtype=np.float32)
        dst_pts = np.array(geo_xy_points, dtype=np.float32)
        
        # Compute affine with or without RANSAC
        if use_ransac and len(pixel_points) >= 3:
            M, inliers_mask = cv2.estimateAffinePartial2D(
                src_pts,
                dst_pts,
                method=cv2.RANSAC,
                ransacReprojThreshold=ransac_threshold
            )
            
            if M is None:
                logger.warning("RANSAC affine failed, using all points")
                M = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.LMEDS)[0]
                inliers_mask = None
            else:
                inliers_mask = inliers_mask.ravel().astype(bool) if inliers_mask is not None else None
                num_inliers = np.sum(inliers_mask) if inliers_mask is not None else len(pixel_points)
                logger.info(
                    f"RANSAC affine: {num_inliers}/{len(pixel_points)} inliers "
                    f"({100*num_inliers/len(pixel_points):.1f}%)"
                )
        else:
            M = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.LMEDS)[0]
            inliers_mask = None
        
        if M is None:
            raise ValueError("Failed to compute affine transformation")
        
        # Convert 2x3 affine to 3x3 matrix
        M_3x3 = np.vstack([M, [0, 0, 1]])
        
        # Calculate reprojection error
        src_homogeneous = np.column_stack([src_pts, np.ones(len(src_pts))])
        reprojected = (M_3x3 @ src_homogeneous.T).T[:, :2]
        
        if inliers_mask is not None:
            errors = np.linalg.norm(reprojected[inliers_mask] - dst_pts[inliers_mask], axis=1)
        else:
            errors = np.linalg.norm(reprojected - dst_pts, axis=1)
        
        reprojection_error = np.mean(errors)
        logger.info(f"Reprojection error: {reprojection_error:.2f} meters")
        
        result = TransformationResult(
            matrix=M_3x3,
            transform_type="affine",
            inliers_mask=inliers_mask,
            reprojection_error=reprojection_error
        )
        
        logger.info("Affine matrix computed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Error building affine transform: {str(e)}", exc_info=True)
        raise


def _calculate_reprojection_error(
    src_pts: np.ndarray,
    dst_pts: np.ndarray,
    H: np.ndarray,
    inliers_mask: Optional[np.ndarray] = None
) -> float:
    """Calculate mean reprojection error for homography."""
    src_pts_reshaped = src_pts.reshape(-1, 2)
    dst_pts_reshaped = dst_pts.reshape(-1, 2)
    
    # Project source points using homography
    src_homogeneous = np.column_stack([src_pts_reshaped, np.ones(len(src_pts_reshaped))])
    reprojected_homogeneous = (H @ src_homogeneous.T).T
    reprojected = reprojected_homogeneous[:, :2] / reprojected_homogeneous[:, 2:3]
    
    # Calculate errors
    errors = np.linalg.norm(reprojected - dst_pts_reshaped, axis=1)
    
    if inliers_mask is not None:
        errors = errors[inliers_mask]
    
    return float(np.mean(errors))


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
    use_homography: bool = True,
    use_ransac: bool = True,
) -> List[Dict[str, Any]]:
    """Georeference pixel-space features using SIFT-matched point pairs.
    
    This function transforms feature collections from pixel coordinates to
    geographic coordinates (EPSG:4326) using homography, affine, or TPS transformation.
    
    Recommended configurations:
    - 4-6 SIFT points: use_homography=True, use_ransac=True (default)
    - 3 SIFT points: use_homography=False (affine only)
    - 7+ SIFT points with high distortion: use_tps=True
    
    Args:
        pixel_feature_collections: List of GeoJSON FeatureCollections in pixel space
        pixel_points: List of (x, y) pixel coordinates from SIFT matching
        geo_points_lonlat: List of (lon, lat) geographic coordinates from SIFT matching
        use_tps: If True, use Thin-Plate Spline (handles non-linear distortion, 7+ points)
        use_homography: If True, use homography (8 DOF, handles perspective, 4+ points).
                       If False, use affine (6 DOF, simpler, 3+ points)
        use_ransac: If True, automatically filter outliers with RANSAC
    
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

        # Choose transformation method
        transform_method = "TPS" if use_tps else ("homography" if use_homography else "affine")
        logger.info(
            f"Georeferencing {len(pixel_feature_collections)} feature collections "
            f"using {len(pixel_points)} point pairs with {transform_method} transform"
        )
        
        # Build transformation
        if use_tps:
            if len(pixel_points) < 7:
                logger.warning(
                    f"Only {len(pixel_points)} points provided. "
                    f"TPS works better with 7+ points. Consider using homography/affine instead."
                )
            tps = build_tps_from_point_pairs(pixel_points, geo_points_lonlat)
            transform_func = tps
            transform_result = None
        else:
            # Use homography (better for perspective) or affine
            if use_homography and len(pixel_points) >= 4:
                transform_result = build_homography_from_point_pairs(
                    pixel_points, 
                    geo_points_lonlat,
                    use_ransac=use_ransac
                )
            else:
                if use_homography and len(pixel_points) < 4:
                    logger.warning(f"Only {len(pixel_points)} points - falling back to affine")
                transform_result = build_affine_from_point_pairs(
                    pixel_points,
                    geo_points_lonlat,
                    use_ransac=use_ransac
                )
            
            transformation_matrix = transform_result.matrix
            
            def matrix_transform(x, y):
                """Apply transformation matrix: pixel coords -> WebMercator"""
                x_arr = np.asarray(x, dtype=float).ravel()
                y_arr = np.asarray(y, dtype=float).ravel()
                
                # Homogeneous coords
                pts = np.vstack([x_arr, y_arr, np.ones_like(x_arr)])
                transformed = transformation_matrix @ pts
                
                # For homography, divide by w coordinate
                if transform_result.transform_type == "homography":
                    X = transformed[0, :] / transformed[2, :]
                    Y = transformed[1, :] / transformed[2, :]
                else:
                    X = transformed[0, :]
                    Y = transformed[1, :]
                
                return X.reshape(np.asarray(x).shape), Y.reshape(np.asarray(y).shape)
            
            transform_func = matrix_transform

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
                props["transform_method"] = transform_method
                
                # Add quality metrics if available (convert numpy types to Python types for JSON)
                if transform_result is not None:
                    if transform_result.reprojection_error is not None:
                        props["reprojection_error_m"] = float(round(transform_result.reprojection_error, 2))
                    if transform_result.num_inliers is not None:
                        props["ransac_inliers"] = int(transform_result.num_inliers)

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
