"""The georeferencing package's core: the affine model, control points, units
and the inputs it is given. No cv2, no Celery task."""

import numpy as np
import pytest

from app.utils.georeferencing import (
    AffineModel,
    CityRef,
    ControlPoint,
    build_georef_inputs,
    mercator_scale_factor,
    parse_georef_inputs,
    select_control_points,
    webmercator_meters_to_km,
)
from app.utils.imposed_colors import (
    KIND_WATER,
    KIND_ZONE,
    parse_imposed_colors_entries,
    split_imposed_colors_by_kind,
)

# A pure scale + translation, so the expected transform is known exactly.
SRC = np.array([[0.0, 0.0], [100.0, 0.0], [0.0, 50.0], [100.0, 50.0]])
DST = np.array([[10.0, 20.0], [210.0, 20.0], [10.0, 120.0], [210.0, 120.0]])


class TestAffineModel:
    def test_recovers_an_exact_transform(self):
        model = AffineModel.fit(SRC, DST)
        X, Y = model(SRC[:, 0], SRC[:, 1])
        assert np.allclose(np.column_stack([X, Y]), DST)

    def test_inverse_round_trips(self):
        model = AffineModel.fit(SRC, DST)
        inverse = model.inverse()
        X, Y = model(np.array([7.0, 33.0]), np.array([11.0, 44.0]))
        x, y = inverse(X, Y)
        assert np.allclose(x, [7.0, 33.0])
        assert np.allclose(y, [11.0, 44.0])

    def test_rmse_is_none_without_redundancy(self):
        """Three points fit an affine exactly, so a zero residual is 'no
        evidence', not 'perfect fit'."""
        model = AffineModel.fit(SRC[:3], DST[:3])
        assert model.redundancy == 0
        assert model.rmse_3857 is None

    def test_requires_three_points(self):
        with pytest.raises(ValueError):
            AffineModel.fit(SRC[:2], DST[:2])


def _sift(x=1.0, y=2.0, lon=-70.0, lat=45.0):
    return ControlPoint.sift((x, y), (lon, lat))


def _city(x=10.0, y=20.0, lon=-71.2, lat=46.8, geonameid=6325494, name="Québec"):
    return ControlPoint.from_city((x, y), (lon, lat), geonameid, name)


class TestControlPoint:
    """A discriminated union on ``source``, enforced at construction."""

    def test_a_city_point_without_its_city_is_refused(self):
        with pytest.raises(ValueError, match="needs the city"):
            ControlPoint(pixel=(1.0, 2.0), geo=(-70.0, 45.0), source="city")

    def test_a_sift_point_with_a_city_is_refused(self):
        with pytest.raises(ValueError, match="cannot carry a city"):
            ControlPoint(
                pixel=(1.0, 2.0),
                geo=(-70.0, 45.0),
                source="sift",
                city=CityRef(geonameid=1, name="X"),
            )

    @pytest.mark.parametrize("source", ["manual", "", None, "SIFT"])
    def test_unknown_sources_are_refused(self, source):
        with pytest.raises(ValueError, match="Unknown control point source"):
            ControlPoint(pixel=(1.0, 2.0), geo=(-70.0, 45.0), source=source)

    @pytest.mark.parametrize("point", [_sift(), _city()])
    def test_dict_round_trip(self, point):
        assert ControlPoint.from_dict(point.to_dict()) == point


class TestSourceSelection:
    def test_selects_by_source_and_keeps_order(self):
        points = [_sift(1), _city(2), _sift(3)]
        assert [p.pixel[0] for p in select_control_points(points, ["sift"])] == [1, 3]
        assert [p.pixel[0] for p in select_control_points(points, ["city"])] == [2]
        assert select_control_points(points, ["sift", "city"]) == points


class TestHonestUnits:
    def test_mercator_inflates_with_latitude(self):
        assert mercator_scale_factor(0.0) == pytest.approx(1.0)
        assert mercator_scale_factor(56.0) == pytest.approx(1.788, abs=0.01)

    def test_km_conversion_undoes_the_inflation(self):
        # 1000 "metres" of EPSG:3857 at 56N is ~559 m on the ground.
        km = webmercator_meters_to_km(1000.0, 56.0)
        assert km == pytest.approx(1.0 / mercator_scale_factor(56.0), abs=1e-6)
        assert km < 0.6


class TestImposedColorKinds:
    def test_an_entry_without_a_kind_is_refused(self):
        with pytest.raises(ValueError, match="kind"):
            parse_imposed_colors_entries([{"x": 0.3, "y": 0.2, "name": "Quebec", "radius": 20}])

    def test_split_separates_zone_from_water(self):
        entries = [
            {"x": 0.3, "y": 0.2, "name": "Quebec", "radius": 20, "kind": "zone"},
            {"x": 0.8, "y": 0.9, "name": "Atlantique", "radius": 15, "kind": "water"},
        ]
        positions, names, radii, kinds = parse_imposed_colors_entries(entries)

        zones = split_imposed_colors_by_kind(positions, names, radii, kinds, KIND_ZONE)
        water = split_imposed_colors_by_kind(positions, names, radii, kinds, KIND_WATER)

        assert zones == ([(0.3, 0.2)], ["Quebec"], [20])
        assert water == ([(0.8, 0.9)], ["Atlantique"], [15])

    def test_rejects_an_unknown_kind(self):
        with pytest.raises(ValueError):
            parse_imposed_colors_entries([{"x": 0.1, "y": 0.1, "kind": "lava"}])


class TestGeorefInputs:
    """Georeferencing runs once, at import. Storing what it ran *from* is what
    makes a later re-run possible; storing the fitted matrix is not."""

    @staticmethod
    def _control_points():
        return [
            ControlPoint.sift((1.0, 2.0), (-70.0, 45.0)),
            ControlPoint.sift((3.0, 4.0), (-71.0, 46.0)),
            ControlPoint.from_city((5.0, 6.0), (-72.0, 47.0), 6325494, "Québec"),
        ]

    def test_round_tripped_points_refit_the_same_model(self):
        """The whole point: the stored inputs must reproduce the fit."""
        from app.utils.georeferencing import fit_affine_from_control_points

        original = self._control_points()
        restored, _, _ = parse_georef_inputs(build_georef_inputs(original))

        assert np.allclose(
            fit_affine_from_control_points(restored).matrix,
            fit_affine_from_control_points(original).matrix,
            rtol=0,
            atol=0,
        )


