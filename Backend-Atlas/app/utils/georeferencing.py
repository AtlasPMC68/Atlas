import math
from typing import List, Tuple, Dict, Any, Optional

import numpy as np
from scipy.interpolate import Rbf
from shapely.geometry import shape, mapping
from shapely.ops import transform


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


def _resample_polyline(points: List[XY], n_samples: int) -> np.ndarray:
    """Resample a polyline to n_samples points using arc-length parameterization.

    points: list of (x, y)
    returns: array of shape (n_samples, 2)
    """
    if len(points) < 2:
        raise ValueError("Polyline must contain at least 2 points")

    pts = np.asarray(points, dtype=float)
    diffs = np.diff(pts, axis=0)
    seg_lengths = np.hypot(diffs[:, 0], diffs[:, 1])
    cumdist = np.concatenate([[0.0], np.cumsum(seg_lengths)])

    if cumdist[-1] == 0:
        # Degenerate polyline; all points identical
        return np.repeat(pts[:1], n_samples, axis=0)

    target_dist = np.linspace(0.0, cumdist[-1], n_samples)
    resampled = np.empty((n_samples, 2), dtype=float)

    j = 0
    for i, td in enumerate(target_dist):
        while j < len(cumdist) - 2 and td > cumdist[j + 1]:
            j += 1
        t0, t1 = cumdist[j], cumdist[j + 1]
        if t1 == t0:
            alpha = 0.0
        else:
            alpha = (td - t0) / (t1 - t0)
        resampled[i] = (1 - alpha) * pts[j] + alpha * pts[j + 1]

    return resampled


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


def build_affine_from_control_polylines(
    pixel_polyline: List[XY],
    geo_polyline_lonlat: List[LonLat],
) -> np.ndarray:
    """Build an affine transform (3x3 matrix) from control polylines.
    
    Computes scale, rotation, and translation based on the two polylines.
    Much more stable than TPS when you only have a single control line.
    
    Returns: 3x3 affine matrix for transforming [x, y, 1] -> [X, Y, 1]
    """
    if len(pixel_polyline) < 2 or len(geo_polyline_lonlat) < 2:
        raise ValueError("Both polylines must contain at least 2 points")
    
    # Convert to arrays
    src = np.array(pixel_polyline, dtype=float)
    geo_xy = np.array([
        _lonlat_to_webmercator(lon, lat) for lon, lat in geo_polyline_lonlat
    ], dtype=float)
    
    # Compute centroids
    src_center = src.mean(axis=0)
    dst_center = geo_xy.mean(axis=0)
    
    # Compute average scale based on line lengths
    src_diffs = np.diff(src, axis=0)
    dst_diffs = np.diff(geo_xy, axis=0)
    src_length = np.sum(np.hypot(src_diffs[:, 0], src_diffs[:, 1]))
    dst_length = np.sum(np.hypot(dst_diffs[:, 0], dst_diffs[:, 1]))
    scale = dst_length / src_length if src_length > 0 else 1.0
    
    # Compute rotation: angle from first to last point
    src_vec = src[-1] - src[0]
    dst_vec = geo_xy[-1] - geo_xy[0]
    src_angle = np.arctan2(src_vec[1], src_vec[0])
    dst_angle = np.arctan2(dst_vec[1], dst_vec[0])
    rotation = dst_angle - src_angle
    
    # Build affine matrix: translate to origin, rotate, scale, translate to destination
    cos_r = np.cos(rotation)
    sin_r = np.sin(rotation)
    
    # Affine: [X, Y, 1] = M @ [x, y, 1]
    # M combines: translate(-src_center), rotate, scale, translate(dst_center)
    M = np.array([
        [scale * cos_r, -scale * sin_r, 0],
        [scale * sin_r,  scale * cos_r, 0],
        [0, 0, 1]
    ], dtype=float)
    
    # Apply translation
    offset = dst_center - scale * np.array([
        cos_r * src_center[0] - sin_r * src_center[1],
        sin_r * src_center[0] + cos_r * src_center[1]
    ])
    M[0, 2] = offset[0]
    M[1, 2] = offset[1]
    
    return M


def georeference_pixel_features(
    pixel_feature_collections: List[Dict[str, Any]],
    pixel_polyline: List[XY],
    geo_polyline_lonlat: List[LonLat],
) -> List[Dict[str, Any]]:
    """Apply affine-based georeferencing to pixel-space feature collections.

    Returns new FeatureCollections in EPSG:4326 (lon/lat).
    """
    if not pixel_feature_collections:
        return []

    # Basic validation/logging to help debug unexpected input types
    if pixel_polyline and isinstance(pixel_polyline[0], dict):
        raise TypeError(f"pixel_polyline contains dicts, expected (x, y) pairs: first={pixel_polyline[0]}")
    if geo_polyline_lonlat and isinstance(geo_polyline_lonlat[0], dict):
        raise TypeError(f"geo_polyline_lonlat contains dicts, expected (lon, lat) pairs: first={geo_polyline_lonlat[0]}")

    affine_matrix = build_affine_from_control_polylines(pixel_polyline, geo_polyline_lonlat)

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
            lon, lat = _webmercator_to_lonlat(float(x_arr[i]), float(y_arr[i]))
            lons[i] = lon
            lats[i] = lat
        if z is None:
            return lons, lats
        return lons, lats, z

    georef_collections: List[Dict[str, Any]] = []

    for fc in pixel_feature_collections:
        if fc.get("type") != "FeatureCollection":
            continue
        new_features: List[Dict[str, Any]] = []
        for feat in fc.get("features", []):
            try:
                geom = shape(feat.get("geometry"))
            except Exception:
                continue

            geom_3857 = transform(_affine_to_3857, geom)
            geom_wgs84 = transform(_to_lonlat, geom_3857)

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

    return georef_collections
