import sys
import os
import math

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "ocr", "florence"))
from inference import _map_point_back


def test_map_point_back_0_deg():
    x, y = _map_point_back(100, 100, 200, 200, 200, 200, 0)
    assert math.isclose(x, 100)
    assert math.isclose(y, 100)


def test_map_point_back_90_deg():
    orig_w, orig_h = 100, 200
    new_w, new_h = 200, 100
    x, y = _map_point_back(0, 0, orig_w, orig_h, new_w, new_h, 90)
    assert math.isclose(x, 100, abs_tol=1e-5)
    assert math.isclose(y, 0, abs_tol=1e-5)


def test_map_point_back_negative_coords():
    x, y = _map_point_back(-50, -50, 100, 100, 100, 100, 0)
    assert math.isclose(x, -50)
    assert math.isclose(y, -50)
