"""Helpers shared by the georeferencing unit tests."""

import math

from app.utils.georeferencing.projection import LonLat, R_EARTH


def webmercator_to_lonlat(x: float, y: float) -> LonLat:
    """EPSG:3857 metres -> (lon, lat). The tests build their truth in 3857,
    the space the models fit in, and hand control points over as lon/lat."""
    lon = math.degrees(x / R_EARTH)
    lat = math.degrees(2.0 * math.atan(math.exp(y / R_EARTH)) - math.pi / 2.0)
    return lon, lat
