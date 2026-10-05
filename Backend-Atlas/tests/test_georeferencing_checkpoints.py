"""Check points: held out of every fit, measured against the applied transform.

See dev-docs/georeferencing-testing.md section 3.
"""

import json

import pytest

from app.utils.extraction_steps import MapPlacement
from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG, ControlPoint
from app.utils.georeferencing.checkpoints import validate_check_points
from app.utils.georeferencing.projection import (
    webmercator_meters_to_km,
    webmercator_to_lonlat,
)

FRAME = {"west": -80.0, "south": 44.0, "east": -64.0, "north": 52.0}
SCALE_M_PER_PX = 1000.0
ORIGIN_3857 = (-8_900_000.0, 6_500_000.0)


def _truth(x, y, dx=0.0, dy=0.0):
    """The lon/lat a pixel truly maps to, optionally displaced by (dx, dy) px."""
    return webmercator_to_lonlat(
        ORIGIN_3857[0] + (x + dx) * SCALE_M_PER_PX,
        ORIGIN_3857[1] - (y + dy) * SCALE_M_PER_PX,
    )


CONTROL = [
    ControlPoint.sift((100.0, 100.0), _truth(100.0, 100.0)),
    ControlPoint.sift((500.0, 120.0), _truth(500.0, 120.0)),
    ControlPoint.sift((300.0, 320.0), _truth(300.0, 320.0)),
    ControlPoint.from_city((150.0, 300.0), _truth(150.0, 300.0), 6325494, "Québec"),
    ControlPoint.sift((480.0, 300.0), _truth(480.0, 300.0)),
]


def _check(x, y, geonameid, name, dx=0.0, dy=0.0):
    return ControlPoint.from_city((x, y), _truth(x, y, dx, dy), geonameid, name)


def _zone():
    ring = [[120.0, 120.0], [460.0, 130.0], [450.0, 300.0], [140.0, 290.0], [120.0, 120.0]]
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}
        ],
    }


def _placement(**overrides):
    config = DEFAULT_GEOREF_CONFIG.with_overrides(
        **{
            "snap_to_coastline": False,
            "clip_to_land_mask": False,
            "transform_model": "affine",
            **overrides,
        }
    )
    return MapPlacement(
        control_points=CONTROL,
        alignment=None,
        frame_bounds=FRAME,
        image_size=(600, 400),
        config=config,
    )


class TestValidation:

    def test_a_city_used_for_fitting_is_refused(self):
        with pytest.raises(ValueError, match="also a control point"):
            validate_check_points(CONTROL, [_check(260.0, 210.0, 6325494, "Québec")])


class TestMeasurement:

    def test_the_error_is_the_ground_distance_of_the_misplacement(self):
        """A city the map draws 20 px off: the affine places it 20 px of 3857
        metres away, which is that many ground km at this latitude."""
        drawn_off = _check(250.0, 200.0, 1, "A", dx=20.0)
        result = _placement().georeference([_zone()], check_points=[drawn_off])
        checks = result.record.to_dict()["errors"]["checkPoints"]
        expected = webmercator_meters_to_km(20 * SCALE_M_PER_PX, checks["referenceLatitude"])
        assert checks["points"][0]["errorKm"] == pytest.approx(expected, rel=1e-3)
        assert checks["points"][0]["name"] == "A"

    def test_check_points_never_change_the_fit(self):
        """The whole point: adding check points, however wrong, leaves the
        applied transform exactly as it was."""
        wild = [_check(250.0, 200.0, 1, "A", dx=80.0, dy=-60.0)]
        for model in ("affine", "piecewise_affine"):
            placement = _placement(transform_model=model)
            without = placement.georeference([_zone()])
            with_checks = placement.georeference([_zone()], check_points=wild)
            assert json.dumps(without.collections) == json.dumps(with_checks.collections)
            assert without.model.serialize() == with_checks.model.serialize()
