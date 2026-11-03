"""The quality estimator's blind inputs (georeferencing/quality.py)."""

import math

import numpy as np

from app.utils.georeferencing.affine import AffineModel, fit_affine_from_control_points
from app.utils.georeferencing.control_points import ControlPoint
from app.utils.georeferencing.projection import lonlat_to_webmercator, webmercator_arrays_to_lonlat
from app.utils.georeferencing.quality import (
    CoastEvidence,
    affine_leave_one_out,
    control_point_layout,
    QualityModel,
    disc_iou,
    point_features,
    predict_quality,
    zone_errors,
    zone_sample_pixels,
    zone_sizes,
)

SIZE = (400, 300)
#: 1 km per pixel, north up, from (0, 0) at the origin of EPSG:3857.
MATRIX = np.array([[1000.0, 0.0, 0.0], [0.0, -1000.0, 0.0], [0.0, 0.0, 1.0]])


def _point(x, y, dx=0.0, dy=0.0):
    """A click at (x, y) whose ground position is where (x + dx, y + dy) is."""
    X, Y = MATRIX[:2] @ [x + dx, y + dy, 1.0]
    lon, lat = webmercator_arrays_to_lonlat(np.array([X]), np.array([Y]))
    return ControlPoint(pixel=(x, y), geo=(float(lon[0]), float(lat[0])), source="sift")


def _grid(offsets=None):
    offsets = offsets or {}
    return [_point(x, y, *offsets.get(i, (0.0, 0.0))) for i, (x, y) in enumerate(
        [(50, 50), (200, 40), (350, 60), (60, 250), (210, 260), (340, 240)]
    )]


def test_the_layout_measures_cover_and_gaps():
    layout = control_point_layout(_grid(), SIZE)
    assert 0.4 < layout["hullShare"] < 0.6
    assert 0.0 < layout["nearestGapMedianRatio"] <= layout["nearestGapMaxRatio"] < 0.5
    # The farthest spot from every point is a corner or the middle of an edge.
    assert 0.05 < layout["emptyRadiusRatio"] < 0.3

    clustered = control_point_layout([_point(10, 10), _point(20, 10), _point(15, 20)], SIZE)
    assert clustered["hullShare"] < 0.01
    assert clustered["emptyRadiusRatio"] > 0.9


def test_the_leave_one_out_is_the_refit_without_the_point():
    points = _grid({4: (6.0, -3.0), 1: (0.5, 0.2)})
    loo = affine_leave_one_out(points, 1000.0)

    for i, held in enumerate(points):
        rest = fit_affine_from_control_points(points[:i] + points[i + 1:])
        x, y = rest(np.array([held.pixel[0]]), np.array([held.pixel[1]]))
        expected = math.hypot(*(np.array([x[0], y[0]]) - lonlat_to_webmercator(*held.geo))) / 1000.0
        assert math.isclose(loo["residualsPx"][i], expected, rel_tol=1e-3, abs_tol=1e-3)
    assert loo["maxPx"] == max(loo["residualsPx"])
    assert loo["residualsPx"].index(loo["maxPx"]) == 4


def test_the_leave_one_out_needs_more_than_three_points():
    assert affine_leave_one_out(_grid()[:3], 1000.0)["residualsPx"] == []
    exact = affine_leave_one_out(_grid(), 1000.0)
    assert exact["maxPx"] < 1e-6


def test_point_features_read_the_points_the_model_and_the_coast():
    points = _grid()
    baseline = AffineModel(matrix=MATRIX, n_points=len(points))
    moved = AffineModel(matrix=MATRIX @ np.array([[1, 0, 3.0], [0, 1, 4.0], [0, 0, 1]]), n_points=len(points))
    pixels = np.array([[200.0, 150.0], [200.0, 5.0], [50.0, 50.0]])
    coast = CoastEvidence(xy=np.array([[200.0, 140.0], [205.0, 140.0]]), misfit_px=np.array([2.0, 4.0]))

    f = point_features(pixels, points, moved, baseline, SIZE, coast=coast, loo_px=[1.0, 1.0, 1.0, 9.0, 9.0, 9.0])

    assert np.allclose(f["shiftFromAffinePx"], 5.0)
    assert f["nearestPointRatio"][2] == 0.0
    assert list(f["insideHull"]) == [1.0, 0.0, 1.0]
    assert math.isclose(f["coastDistanceRatio"][0], 10.0 / math.hypot(*SIZE))
    assert f["coastMisfitPx"][0] == 3.0  # both samples within reach of the centre
    assert math.isnan(f["coastMisfitPx"][1])  # none near the top edge
    # Above the top row, the three nearest points are that row, whose residuals are 1.
    assert math.isclose(f["nearbyLooPx"][1], 1.0)


def test_point_features_without_coast_or_leave_one_out_are_nan():
    points = _grid()
    model = AffineModel(matrix=MATRIX, n_points=len(points))
    f = point_features(np.array([[100.0, 100.0]]), points, model, model, SIZE)
    assert f["shiftFromAffinePx"][0] == 0.0
    assert math.isnan(f["coastDistanceRatio"][0])
    assert math.isnan(f["nearbyLooPx"][0])


def _square(x0, y0, side):
    ring = [[x0, y0], [x0 + side, y0], [x0 + side, y0 + side], [x0, y0 + side], [x0, y0]]
    return {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}


def test_zone_sizes_are_a_disc_radius_and_a_width():
    strip = {"type": "Feature", "properties": {}, "geometry": {
        "type": "Polygon", "coordinates": [[[0, 0], [300, 0], [300, 10], [0, 10], [0, 0]]]}}
    sizes = zone_sizes([{"type": "FeatureCollection", "features": [_square(0, 0, 100), strip]}])
    assert np.allclose(sizes.radius_px, [math.sqrt(1e4 / math.pi), math.sqrt(3e3 / math.pi)])
    # 2 area / perimeter: half the side of a square, about the width of a strip.
    assert np.allclose(sizes.width_px, [50.0, 6000.0 / 620.0])


def test_zone_errors_read_the_pixels_inside_or_the_nearest():
    sizes = zone_sizes([{"type": "FeatureCollection", "features": [_square(0, 0, 100), _square(300, 0, 10)]}])
    pixels = np.array([[10.0, 10.0], [50.0, 50.0], [90.0, 90.0], [200.0, 5.0]])
    errors = zone_errors(sizes, pixels, np.array([1.0, 2.0, 9.0, 7.0]))
    assert errors.tolist() == [2.0, 7.0]


def test_disc_iou_runs_from_one_to_zero():
    iou = disc_iou(np.array([0.0, 5.0, 10.0, 20.0, 50.0]), np.array([10.0] * 5))
    assert iou[0] == 1.0 and iou[3] == 0.0 and iou[4] == 0.0
    assert 1.0 > iou[1] > iou[2] > 0.0


def test_zone_samples_fall_inside_the_zones():
    sizes = zone_sizes([{"type": "FeatureCollection", "features": [_square(0, 0, 10), _square(500, 500, 10)]}])
    pixels = zone_sample_pixels(sizes, 50, seed=1)
    assert pixels.shape == (50, 2)
    inside = ((pixels <= 10) | ((pixels >= 500) & (pixels <= 510))).all(axis=1)
    assert inside.all()
    assert np.array_equal(pixels, zone_sample_pixels(sizes, 50, seed=1))


def _placed():
    points = _grid()
    baseline = fit_affine_from_control_points(points)
    record = {
        "models": {"gcp_affine": baseline.serialize()},
        "inputs": {"referenceLatitude": 0.0, "controlPointCount": len(points)},
        "errors": {"affineLeaveOneOut": affine_leave_one_out(points, baseline.meters_per_pixel)},
    }
    return record, points, baseline


def test_the_shipped_quality_model_predicts_a_lower_iou_for_smaller_zones():
    record, points, baseline = _placed()
    QualityModel()  # the shipped file loads

    def predicted(side):
        zones = [{"type": "FeatureCollection", "features": [_square(100, 100, side), _square(250, 150, side)]}]
        return predict_quality(record, zones, points, baseline, baseline, SIZE)

    large, small = predicted(80), predicted(8)
    assert large["zones"] == 2 and large["mapMedianKm"] > 0
    assert 0.0 < small["iou"] < large["iou"] <= 1.0
    assert small["zoneWidthMedianPx"] < large["zoneWidthMedianPx"]


def test_quality_without_zones_has_no_iou():
    record, points, baseline = _placed()
    out = predict_quality(record, [], points, baseline, baseline, SIZE)
    assert out["zones"] == 0 and out["iou"] is None and out["mapMedianPx"] > 0
