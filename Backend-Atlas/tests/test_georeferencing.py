"""Unit tests for the georeferencing package (Steps 0-1).

These deliberately avoid cv2 and the Celery task: they cover the model
interface, the honest units, and the two new inputs (framing box, water picks).
"""

import math

import numpy as np
import pytest

from app.utils.georeferencing import (
    AffineModel,
    ControlPoint,
    GateCheck,
    RunRecord,
    build_georef_inputs,
    control_point_weights,
    mercator_scale_factor,
    parse_georef_inputs,
    parse_frame_bounds,
    parse_frame_bounds_entry,
    reference_latitude,
    sigma_px_for_source,
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


class TestControlPoint:
    def test_from_pairs_assigns_a_source_sigma(self):
        points = ControlPoint.from_pairs(
            [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)],
            [(-70.0, 45.0), (-71.0, 46.0), (-72.0, 47.0)],
            source="sift",
        )
        assert [p.source for p in points] == ["sift"] * 3
        assert all(p.sigma_px == sigma_px_for_source("sift") for p in points)

    def test_city_sigma_is_much_larger_than_keypoint_sigma(self):
        """Old maps place cities sloppily; a coastline keypoint is click-precise.
        The two must not share a weight."""
        assert sigma_px_for_source("city") > 3 * sigma_px_for_source("sift")

    def test_rejects_dicts(self):
        with pytest.raises(TypeError):
            ControlPoint.from_pairs([{"x": 1, "y": 2}], [{"lon": 1, "lat": 2}])

    def test_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError):
            ControlPoint.from_pairs([(1.0, 2.0)], [(1.0, 2.0), (3.0, 4.0)])

    def test_weights_are_inverse_variance(self):
        points = ControlPoint.from_pairs(
            [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)],
            [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)],
            source="sift",
        )
        expected = 1.0 / (sigma_px_for_source("sift") ** 2)
        assert np.allclose(control_point_weights(points), expected)


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
        return ControlPoint.from_pairs(
            [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)],
            [(-70.0, 45.0), (-71.0, 46.0), (-72.0, 47.0)],
            source="sift",
        )

    def test_round_trips_every_input(self):
        frame = {"west": -80.0, "south": 44.0, "east": -56.0, "north": 62.0}
        colors = [{"x": 0.3, "y": 0.2, "name": "Quebec", "radius": 20, "kind": "zone"}]

        payload = build_georef_inputs(self._control_points(), frame, colors)
        points, bounds, imposed = parse_georef_inputs(payload)

        assert [p.pixel for p in points] == [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
        assert [p.source for p in points] == ["sift"] * 3
        assert [p.sigma_px for p in points] == [sigma_px_for_source("sift")] * 3
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
        ControlPoint.from_pairs(pixel, geo, source="sift")
    )
    assert np.allclose(model.matrix, expected, rtol=0, atol=0)
