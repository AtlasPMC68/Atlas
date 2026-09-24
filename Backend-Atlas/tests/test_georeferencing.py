"""Unit tests for the georeferencing package (Steps 0-1).

These deliberately avoid cv2 and the Celery task: they cover the model
interface, the honest units, and the two new inputs (framing box, water picks).
"""

import math

import numpy as np
import pytest

from app.utils.georeferencing import (
    DEFAULT_GEOREF_CONFIG,
    AffineModel,
    CityRef,
    ControlPoint,
    GateCheck,
    RunRecord,
    build_georef_inputs,
    control_point_weights,
    count_by_source,
    mercator_scale_factor,
    parse_control_points,
    parse_control_points_field,
    parse_georef_inputs,
    parse_frame_bounds,
    parse_frame_bounds_entry,
    reference_latitude,
    select_control_points,
    webmercator_meters_to_km,
)
from app.utils.imposed_colors import (
    KIND_WATER,
    KIND_ZONE,
    imposed_colors_to_config_entries,
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

    def test_rmse_is_measured_with_redundancy(self):
        noisy = DST.copy()
        noisy[0, 0] += 10.0
        model = AffineModel.fit(SRC, noisy)
        assert model.redundancy == 2
        assert model.rmse_3857 is not None
        assert model.rmse_3857 > 0.0

    def test_weights_pull_the_fit_towards_the_trusted_point(self):
        noisy = DST.copy()
        noisy[0] += np.array([40.0, 0.0])

        uniform = AffineModel.fit(SRC, noisy)
        weights = np.array([100.0, 1.0, 1.0, 1.0])
        weighted = AffineModel.fit(SRC, noisy, weights=weights)

        residual_uniform = uniform.residuals_3857[0]
        residual_weighted = weighted.residuals_3857[0]
        assert residual_weighted < residual_uniform

    def test_rejects_mismatched_weight_length(self):
        with pytest.raises(ValueError):
            AffineModel.fit(SRC, DST, weights=np.ones(2))

    def test_requires_three_points(self):
        with pytest.raises(ValueError):
            AffineModel.fit(SRC[:2], DST[:2])

    def test_serialize_round_trips(self):
        model = AffineModel.fit(SRC, DST)
        restored = AffineModel.deserialize(model.serialize())
        assert np.allclose(restored.matrix, model.matrix)


def _sift(x=1.0, y=2.0, lon=-70.0, lat=45.0):
    return ControlPoint.sift((x, y), (lon, lat))


def _city(x=10.0, y=20.0, lon=-71.2, lat=46.8, geonameid=6325494, name="Québec"):
    return ControlPoint.from_city((x, y), (lon, lat), geonameid, name)


class TestControlPoint:
    """A discriminated union on ``source``, enforced at construction."""

    def test_a_city_point_carries_its_city(self):
        point = _city()
        assert point.source == "city"
        assert point.city == CityRef(geonameid=6325494, name="Québec")

    def test_a_sift_point_carries_none(self):
        assert _sift().city is None

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

    @pytest.mark.parametrize(
        "geonameid, name",
        [(0, "X"), (-3, "X"), (True, "X"), ("12", "X"), (12, ""), (12, "  ")],
    )
    def test_a_city_needs_a_real_id_and_name(self, geonameid, name):
        with pytest.raises(ValueError):
            CityRef(geonameid=geonameid, name=name)

    @pytest.mark.parametrize(
        "pixel, geo",
        [
            ((1.0, float("nan")), (-70.0, 45.0)),
            ((1.0, 2.0), (-200.0, 45.0)),
            ((1.0, 2.0), (-70.0, 95.0)),
            ((1.0,), (-70.0, 45.0)),
            ((True, 2.0), (-70.0, 45.0)),
        ],
    )
    def test_bad_coordinates_are_refused(self, pixel, geo):
        with pytest.raises(ValueError):
            ControlPoint(pixel=pixel, geo=geo, source="sift")

    def test_coordinates_are_normalised_to_float_tuples(self):
        point = ControlPoint.sift([1, 2], [-70, 45])
        assert point.pixel == (1.0, 2.0) and isinstance(point.pixel[0], float)
        assert point.geo == (-70.0, 45.0)

    @pytest.mark.parametrize("point", [_sift(), _city()])
    def test_dict_round_trip(self, point):
        assert ControlPoint.from_dict(point.to_dict()) == point

    def test_the_wire_format_has_no_sigma(self):
        """Sigma is a model setting looked up by source, not an observation."""
        assert "sigmaPx" not in _sift().to_dict()
        assert set(_city().to_dict()) == {"source", "pixel", "geo", "city"}

    def test_parse_names_the_bad_entry(self):
        good = _sift().to_dict()
        with pytest.raises(ValueError, match="control point 1"):
            parse_control_points([good, {**good, "source": "city"}])

    def test_parse_requires_a_list(self):
        with pytest.raises(ValueError):
            parse_control_points({"source": "sift"})

    def test_weights_are_inverse_variance_by_source(self):
        config = DEFAULT_GEOREF_CONFIG.with_overrides(
            gcp_sigma_px_sift=5.0, gcp_sigma_px_city=20.0
        )
        weights = control_point_weights([_sift(), _city()], config)
        assert np.allclose(weights, [1 / 25.0, 1 / 400.0])

    def test_sources_are_weighted_alike_by_default(self):
        weights = control_point_weights([_sift(), _city()])
        assert weights[0] == weights[1]


class TestSourceSelection:
    def test_selects_by_source_and_keeps_order(self):
        points = [_sift(1), _city(2), _sift(3)]
        assert [p.pixel[0] for p in select_control_points(points, ["sift"])] == [1, 3]
        assert [p.pixel[0] for p in select_control_points(points, ["city"])] == [2]
        assert select_control_points(points, ["sift", "city"]) == points

    def test_counts_include_zeros(self):
        assert count_by_source([_sift(), _sift()]) == {"sift": 2, "city": 0}


class TestControlPointsField:
    """The ``control_points`` form field, shared by both upload routes."""

    def test_absent_means_no_points(self):
        assert parse_control_points_field(None) == []
        assert parse_control_points_field("") == []

    def test_mixed_sources_parse(self):
        import json

        raw = json.dumps([_sift(1).to_dict(), _sift(2).to_dict(), _city().to_dict()])
        points = parse_control_points_field(raw)
        assert [p.source for p in points] == ["sift", "sift", "city"]

    def test_fewer_than_three_points_are_refused(self):
        import json

        with pytest.raises(ValueError, match="at least 3"):
            parse_control_points_field(json.dumps([_sift().to_dict()] * 2))

    def test_invalid_json_is_refused(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_control_points_field("[{")


class TestHonestUnits:
    def test_mercator_inflates_with_latitude(self):
        assert mercator_scale_factor(0.0) == pytest.approx(1.0)
        assert mercator_scale_factor(56.0) == pytest.approx(1.788, abs=0.01)

    def test_km_conversion_undoes_the_inflation(self):
        # 1000 "metres" of EPSG:3857 at 56N is ~559 m on the ground.
        km = webmercator_meters_to_km(1000.0, 56.0)
        assert km == pytest.approx(1.0 / mercator_scale_factor(56.0), abs=1e-6)
        assert km < 0.6

    def test_reference_latitude_prefers_the_framing_box(self):
        bounds = {"west": -80.0, "south": 44.0, "east": -56.0, "north": 62.0}
        assert reference_latitude(bounds, [(-70.0, 10.0)]) == pytest.approx(53.0)

    def test_reference_latitude_falls_back_to_control_points(self):
        assert reference_latitude(None, [(-70.0, 40.0), (-71.0, 50.0)]) == pytest.approx(
            45.0
        )

    def test_reference_latitude_is_none_without_either(self):
        assert reference_latitude(None, []) is None


class TestFrameBounds:
    def test_parses_a_valid_box(self):
        parsed = parse_frame_bounds(
            '{"west": -80, "south": 44, "east": -56, "north": 62}'
        )
        assert parsed == {"west": -80.0, "south": 44.0, "east": -56.0, "north": 62.0}

    def test_absent_is_none_not_an_error(self):
        assert parse_frame_bounds(None) is None
        assert parse_frame_bounds("") is None
        assert parse_frame_bounds_entry(None) is None

    @pytest.mark.parametrize(
        "payload",
        [
            '{"west": -80}',
            '{"west": -80, "south": 70, "east": -56, "north": 62}',
            '{"west": -80, "south": 44, "east": -56, "north": 200}',
            "not json",
            "[1, 2]",
        ],
    )
    def test_rejects_bad_payloads(self, payload):
        with pytest.raises(ValueError):
            parse_frame_bounds(payload)


class TestImposedColorKinds:
    def test_entries_without_a_kind_are_zones(self):
        """Every payload written before `kind` existed meant zones."""
        _, _, _, kinds = parse_imposed_colors_entries(
            [{"x": 0.3, "y": 0.2, "name": "Quebec", "radius": 20}]
        )
        assert kinds == [KIND_ZONE]

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

    def test_split_returns_none_when_nothing_matches(self):
        positions, names, radii, kinds = parse_imposed_colors_entries(
            [{"x": 0.3, "y": 0.2, "name": "Quebec", "radius": 20}]
        )
        assert split_imposed_colors_by_kind(
            positions, names, radii, kinds, KIND_WATER
        ) == (None, None, None)

    def test_config_entries_round_trip_the_kind(self):
        entries = [
            {"x": 0.3, "y": 0.2, "name": "Quebec", "radius": 20, "kind": "zone"},
            {"x": 0.8, "y": 0.9, "name": "Atlantique", "radius": 15, "kind": "water"},
        ]
        parsed = parse_imposed_colors_entries(entries)
        assert imposed_colors_to_config_entries(*parsed) == entries

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

    def test_round_trips_every_input(self):
        frame = {"west": -80.0, "south": 44.0, "east": -56.0, "north": 62.0}
        colors = [{"x": 0.3, "y": 0.2, "name": "Quebec", "radius": 20, "kind": "zone"}]

        payload = build_georef_inputs(self._control_points(), frame, colors)
        points, bounds, imposed = parse_georef_inputs(payload)

        assert points == self._control_points()
        assert points[2].city.name == "Québec"
        assert bounds == frame
        assert imposed == colors

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

    def test_is_none_when_there_is_nothing_to_store(self):
        assert build_georef_inputs(None, None, None) is None

    def test_partial_inputs_are_kept(self):
        payload = build_georef_inputs(self._control_points(), None, None)
        points, bounds, imposed = parse_georef_inputs(payload)
        assert len(points) == 3
        assert bounds is None
        assert imposed is None

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            {},
            "not a dict",
            {"georef": {"controlPoints": [{"nope": 1}]}},
            {"georef": {"frameBounds": {"west": -80}}},
            {"colors": {"imposed": "not a list"}},
        ],
    )
    def test_parsing_is_tolerant(self, payload):
        """Recovering inputs is not validating a request: salvage, never raise."""
        points, bounds, imposed = parse_georef_inputs(payload)
        assert points == []
        assert bounds is None
        assert imposed is None


class TestRunRecord:
    def test_phases_accumulate(self):
        record = RunRecord()
        with record.phase("fit"):
            pass
        with record.phase("fit"):
            pass
        assert "fit" in record.timing_ms
        assert record.timing_ms["fit"] >= 0.0

    def test_gates_are_logged_even_when_they_pass(self):
        record = RunRecord()
        record.add_gate(GateCheck(name="gcp_disagreement", value=1.0, threshold=2.0))
        record.add_gate(
            GateCheck(name="water_iou", applicable=False, passed=True, value=None)
        )
        assert len(record.gates) == 2
        assert record.all_gates_passed
        assert record.failed_gate_names == []

    def test_failed_gates_are_named(self):
        record = RunRecord()
        record.add_gate(
            GateCheck(name="transform_sanity", value=9.0, threshold=1.0, passed=False)
        )
        assert not record.all_gates_passed
        assert record.failed_gate_names == ["transform_sanity"]

    def test_write_is_json_serializable(self, tmp_path):
        record = RunRecord(run_id="t/c")
        record.set_inputs(controlPointCount=7)
        record.set_model("stage2_affine", AffineModel.fit(SRC, DST).serialize())
        record.set_errors(gcpRmseKm=None)
        path = record.write(str(tmp_path))
        assert path is not None

        import json

        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        assert payload["runId"] == "t/c"
        assert payload["inputs"]["controlPointCount"] == 7
        assert payload["models"]["stage2_affine"]["name"] == "affine"

    def test_write_never_raises_on_a_bad_directory(self):
        record = RunRecord()
        assert record.write("\0invalid") is None


def test_affine_matches_the_previous_hand_rolled_fit():
    """The package split must not move a single coordinate.

    Reproduces the pre-split least-squares construction and checks the fitted
    matrix is identical.
    """
    pixel = [(127.3, 672.9), (898.4, 1602.9), (893.0, 1448.0), (179.8, 226.1)]
    geo = [(-78.78, 56.30), (-64.53, 45.80), (-64.76, 47.85), (-77.88, 60.69)]

    r_earth = 6378137.0

    def old_mercator(lon, lat):
        x = math.radians(lon) * r_earth
        lat = max(min(lat, 89.9), -89.9)
        y = math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) * r_earth
        return x, y

    src = np.array(pixel, dtype=float)
    dst = np.array([old_mercator(*g) for g in geo], dtype=float)

    n = len(src)
    design = np.zeros((2 * n, 6))
    target = np.zeros(2 * n)
    for i in range(n):
        x, y = src[i]
        X, Y = dst[i]
        design[2 * i] = [x, y, 1, 0, 0, 0]
        target[2 * i] = X
        design[2 * i + 1] = [0, 0, 0, x, y, 1]
        target[2 * i + 1] = Y
    a, b, tx, c, d, ty = np.linalg.lstsq(design, target, rcond=None)[0]
    expected = np.array([[a, b, tx], [c, d, ty], [0.0, 0.0, 1.0]])

    from app.utils.georeferencing import fit_affine_from_control_points

    model = fit_affine_from_control_points(
        [ControlPoint.sift(p, g) for p, g in zip(pixel, geo)]
    )
    assert np.allclose(model.matrix, expected, rtol=0, atol=0)
