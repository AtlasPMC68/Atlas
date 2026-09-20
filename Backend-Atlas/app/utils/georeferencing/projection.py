"""Spherical WebMercator (EPSG:3857) helpers, and honest distance units.

The affine is fitted in a planar space because pixels are planar. WebMercator is
conformal, therefore locally isotropic: shape is already correct and only
*absolute scale* is wrong, by a factor of ``1/cos(phi)``. Everything that
reports a distance to a human must divide by that factor first --- see
``webmercator_meters_to_km``.

A local LAEA/TM projection is the principled version, but it needs ``pyproj``
and buys nothing at proof-of-concept scale.
"""

import math
from typing import Iterable, Optional, Sequence, Tuple

import numpy as np

R_EARTH = 6378137.0
MAX_MERCATOR_LAT = 89.9

LonLat = Tuple[float, float]
XY = Tuple[float, float]


def lonlat_to_webmercator(lon: float, lat: float) -> XY:
    x = math.radians(lon) * R_EARTH
    lat = max(min(lat, MAX_MERCATOR_LAT), -MAX_MERCATOR_LAT)
    y = math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) * R_EARTH
    return x, y


def webmercator_to_lonlat(x: float, y: float) -> LonLat:
    lon = math.degrees(x / R_EARTH)
    lat = math.degrees(2.0 * math.atan(math.exp(y / R_EARTH)) - math.pi / 2.0)
    return lon, lat


def lonlat_arrays_to_webmercator(x, y, z=None):
    """Vectorized transform callback for Shapely: EPSG:4326 -> EPSG:3857."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)

    X = np.radians(x_arr) * R_EARTH
    lat_clamped = np.clip(y_arr, -MAX_MERCATOR_LAT, MAX_MERCATOR_LAT)
    Y = np.log(np.tan(np.pi / 4.0 + np.radians(lat_clamped) / 2.0)) * R_EARTH

    if z is None:
        return X, Y
    return X, Y, z


def webmercator_arrays_to_lonlat(x, y, z=None):
    """Vectorized transform callback for Shapely: EPSG:3857 -> EPSG:4326.

    The per-point Python loop this replaces was the hot spot on dense
    color-extraction polygons (current §9, limitation 8).
    """
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)

    lon = np.degrees(x_arr / R_EARTH)
    lat = np.degrees(2.0 * np.arctan(np.exp(y_arr / R_EARTH)) - np.pi / 2.0)

    if z is None:
        return lon, lat
    return lon, lat, z


def mercator_scale_factor(latitude_deg: float) -> float:
    """``1/cos(phi)``: how much WebMercator inflates ground distance at *phi*."""
    lat = max(min(float(latitude_deg), MAX_MERCATOR_LAT), -MAX_MERCATOR_LAT)
    cos_phi = math.cos(math.radians(lat))
    if cos_phi <= 1e-9:
        return float("inf")
    return 1.0 / cos_phi


def webmercator_meters_to_km(distance_3857: float, latitude_deg: float) -> float:
    """Convert a WebMercator distance to real kilometres on the ground.

    A stated 1000 "metres" in EPSG:3857 is ~550 m on the ground at Quebec
    latitudes; this is the correction that makes reported numbers honest
    (current §9, limitation 1).
    """
    scale = mercator_scale_factor(latitude_deg)
    if not math.isfinite(scale) or scale <= 0:
        return float("nan")
    return float(distance_3857) / scale / 1000.0


def reference_latitude(
    frame_bounds: Optional[dict] = None,
    geo_points_lonlat: Optional[Sequence[LonLat]] = None,
) -> Optional[float]:
    """Latitude to correct distances at: the framing box centre when we have
    one, otherwise the mean control-point latitude, otherwise None."""
    if frame_bounds:
        try:
            south = float(frame_bounds["south"])
            north = float(frame_bounds["north"])
            return (south + north) / 2.0
        except (KeyError, TypeError, ValueError):
            pass

    lats = _finite_latitudes(geo_points_lonlat or [])
    if lats:
        return float(sum(lats) / len(lats))
    return None


def _finite_latitudes(geo_points_lonlat: Iterable[LonLat]) -> list:
    lats = []
    for point in geo_points_lonlat:
        try:
            lat = float(point[1])
        except (TypeError, ValueError, IndexError):
            continue
        if math.isfinite(lat):
            lats.append(lat)
    return lats
