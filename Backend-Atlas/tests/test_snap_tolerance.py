"""The coastline snap tolerance is one share of the image diagonal, in metres.

It used to be clamped four ways (3-40 px, then 200 m-50 km), with no
measurement behind any bound; on a map of half a continent the 50 km cap, not
the ratio, set the tolerance.
"""

import math
from types import SimpleNamespace

from app.utils.georeferencing.config import DEFAULT_GEOREF_CONFIG
from app.utils.georeferencing.pipeline import _resolve_snap_tolerance_m

MODEL = SimpleNamespace(meters_per_pixel=7_500.0)


def _zones(minx, miny, maxx, maxy):
    ring = [[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]
    return [
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}
            ],
        }
    ]


def test_it_is_the_ratio_of_the_image_diagonal_with_no_cap():
    tolerance = _resolve_snap_tolerance_m(
        MODEL, _zones(0, 0, 10, 10), DEFAULT_GEOREF_CONFIG, None, (602, 375)
    )
    expected = math.hypot(602, 375) * 0.01 * 7_500.0  # ~53 km: over the old 50 km cap
    assert math.isclose(tolerance, expected)


def test_zones_in_one_corner_do_not_shrink_it():
    corner = _resolve_snap_tolerance_m(
        MODEL, _zones(0, 0, 50, 50), DEFAULT_GEOREF_CONFIG, None, (602, 375)
    )
    spread = _resolve_snap_tolerance_m(
        MODEL, _zones(0, 0, 600, 370), DEFAULT_GEOREF_CONFIG, None, (602, 375)
    )
    assert corner == spread


def test_without_the_image_size_the_zones_extent_stands_in():
    tolerance = _resolve_snap_tolerance_m(
        MODEL, _zones(0, 0, 300, 400), DEFAULT_GEOREF_CONFIG, None, None
    )
    assert math.isclose(tolerance, 500 * 0.01 * 7_500.0)


def test_nothing_to_measure_means_no_snapping():
    assert _resolve_snap_tolerance_m(MODEL, [], DEFAULT_GEOREF_CONFIG, None, None) is None
