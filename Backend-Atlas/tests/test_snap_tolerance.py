"""The coastline snap tolerance is one share of the image diagonal, in metres,
with no clamps."""

import math
from types import SimpleNamespace

from app.utils.georeferencing.config import DEFAULT_GEOREF_CONFIG
from app.utils.georeferencing.pipeline import snap_tolerance_m_for


def test_it_is_the_ratio_of_the_image_diagonal_with_no_cap():
    model = SimpleNamespace(meters_per_pixel=7_500.0)
    tolerance = snap_tolerance_m_for(model, (602, 375), DEFAULT_GEOREF_CONFIG)
    ratio = DEFAULT_GEOREF_CONFIG.coastline_snap_ratio_of_diagonal
    assert math.isclose(tolerance, math.hypot(602, 375) * ratio * 7_500.0)
