"""Unit tests for Step 4: chamfer, ICP, gates and the recovery ladder.

None of this needs cv2 -- `align.py`, `gates.py` and `recovery.py` consume the
arrays `evidence.py` produced, and do their own gradients with scipy. The tests
therefore build small synthetic worlds instead of reading a map, which also
makes the behaviour being pinned explicit: a known transform is perturbed, and
alignment has to recover it.
"""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from app.utils.georeferencing import (
    AffineModel,
    ControlPoint,
    DEFAULT_GEOREF_CONFIG,
    RunRecord,
)
from app.utils.georeferencing.align import (
    CurveSamples,
    build_user_field,
    fit_chamfer,
    find_correspondences,
    icp_refine,
    tukey_loss,
    _params_from_model,
    _to_pixel,
)
from app.utils.georeferencing.gates import (
    evaluate_gates,
    failed_names,
    gates_passed,
    gcp_rms_px,
    similarity_of,
    water_mask_iou,
)
from app.utils.georeferencing.records import GateCheck
from app.utils.georeferencing.recovery import AlignmentResult, _perturb, align

WIDTH, HEIGHT = 300, 240


# --------------------------------------------------------------------------
# A synthetic world: a known affine, a curve, and an edge map drawn from it
# --------------------------------------------------------------------------


def _truth_model() -> AffineModel:
    """A plain scale + translation, pixel -> 'EPSG:3857'."""
    matrix = np.array(
        [[1000.0, 0.0, -8.0e6], [0.0, -1000.0, 7.0e6], [0.0, 0.0, 1.0]]
    )
    return AffineModel(matrix=matrix)


def _curve_pixels() -> np.ndarray:
    """A wiggly curve in pixel space -- a stand-in coastline."""
    x = np.arange(30.0, 270.0, 1.0)
    y = 120.0 + 40.0 * np.sin(x / 26.0)
    return np.column_stack([x, y])


def _world() -> tuple:
    """Return (truth, samples, evidence-like object) that agree exactly."""
    truth = _truth_model()
    pixels = _curve_pixels()

    X, Y = truth(pixels[:, 0], pixels[:, 1])
    xy = np.column_stack([X, Y])

    # The normal step: one pixel perpendicular to the curve, pushed to world.
    tangent = np.gradient(pixels, axis=0)
    norm = np.hypot(tangent[:, 0], tangent[:, 1])
    nx, ny = -tangent[:, 1] / norm, tangent[:, 0] / norm
    Xn, Yn = truth(pixels[:, 0] + nx, pixels[:, 1] + ny)
    samples = CurveSamples(xy=xy, xy_normal=np.column_stack([Xn, Yn]))

    # Draw densely along the curve, the way `reference._draw_polyline` does.
    # Stepping x by one pixel leaves gaps wherever the curve is steeper than
    # 45 degrees, and a gappy raster gives unusable gradient orientations.
    weight = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    dense_x = np.arange(30.0, 269.0, 0.2)
    dense_y = 120.0 + 40.0 * np.sin(dense_x / 26.0)
    cols = np.clip(dense_x.astype(int), 0, WIDTH - 1)
    rows = np.clip(dense_y.astype(int), 0, HEIGHT - 1)
    weight[rows, cols] = 1.0

    evidence = SimpleNamespace(
        edge_weight=weight,
        text_mask=np.zeros((HEIGHT, WIDTH), dtype=bool),
        water=np.zeros((HEIGHT, WIDTH), dtype=bool),
    )
    return truth, samples, evidence


def _control_points_from(model: AffineModel, pixels) -> list:
    from app.utils.georeferencing.projection import webmercator_to_lonlat

    points = []
    for px, py in pixels:
        X, Y = model(np.array([px]), np.array([py]))
        lon, lat = webmercator_to_lonlat(float(X[0]), float(Y[0]))
        points.append(ControlPoint.sift((px, py), (lon, lat)))
    return points


class TestTukey:
    def test_derivative_reaches_exactly_zero(self):
        """The whole reason for Tukey over Huber: past the cutoff, a sample
        contributes nothing at all rather than merely less."""
        rho = tukey_loss(np.array([0.0, 0.5, 1.0, 2.0, 100.0]))
        assert rho[1][0] == pytest.approx(0.5)
        assert rho[1][2] == 0.0
        assert rho[1][4] == 0.0

    def test_is_bounded(self):
        rho = tukey_loss(np.array([1.0, 10.0, 1e6]))
        assert np.allclose(rho[0], 1.0 / 6.0)

    def test_is_monotone_on_inliers(self):
        rho = tukey_loss(np.linspace(0.0, 1.0, 25))
        assert np.all(np.diff(rho[0]) >= -1e-12)


class TestUserField:
    def test_suppressed_edges_read_as_further_away(self):
        """Straight-line suppression has to survive into the distance field;
        thresholding the weight map would throw it away."""
        weight = np.zeros((50, 50), dtype=np.float32)
        weight[25, 10] = 1.0  # strong
        weight[25, 40] = 0.15  # suppressed
        evidence = SimpleNamespace(edge_weight=weight, text_mask=None, water=None)
        field = build_user_field(evidence, DEFAULT_GEOREF_CONFIG)

        assert field.distance_px[25, 10] == pytest.approx(0.0)
        assert field.distance_px[25, 40] == pytest.approx(
            DEFAULT_GEOREF_CONFIG.straight_line_distance_penalty_px
        )

    def test_validity_is_zero_under_text_and_one_away_from_it(self):
        weight = np.zeros((60, 60), dtype=np.float32)
        weight[30, :] = 1.0
        text = np.zeros((60, 60), dtype=bool)
        text[20:40, 20:40] = True
        evidence = SimpleNamespace(edge_weight=weight, text_mask=text, water=None)
        field = build_user_field(evidence, DEFAULT_GEOREF_CONFIG)

        assert field.validity[30, 30] < 0.05
        assert field.validity[5, 5] > 0.95

    def test_validity_is_smooth_at_the_boundary(self):
        """A hard 0/1 mask makes the objective discontinuous as samples cross."""
        weight = np.ones((40, 40), dtype=np.float32)
        text = np.zeros((40, 40), dtype=bool)
        text[:, 20:] = True
        evidence = SimpleNamespace(edge_weight=weight, text_mask=text, water=None)
        field = build_user_field(evidence, DEFAULT_GEOREF_CONFIG)
        row = field.validity[20]
        assert 0.0 < row[20] < 1.0
        assert np.all(np.diff(row[15:26]) <= 1e-6)

    def test_empty_edges_do_not_explode(self):
        evidence = SimpleNamespace(
            edge_weight=np.zeros((20, 20), dtype=np.float32),
            text_mask=None,
            water=None,
        )
        field = build_user_field(evidence, DEFAULT_GEOREF_CONFIG)
        assert not field.edge.any()
        assert np.isfinite(field.distance_px).all()


class TestChamfer:
    def test_recovers_a_translation(self):
        truth, samples, evidence = _world()
        field = build_user_field(evidence, DEFAULT_GEOREF_CONFIG)
        control_points = _control_points_from(
            truth, [(60.0, 100.0), (150.0, 140.0), (240.0, 110.0)]
        )

        start = _perturb(truth, 12.0, -9.0, 0.0)
        assert gcp_rms_px(start, control_points) > 5.0

        result = fit_chamfer(start, control_points, samples, field, DEFAULT_GEOREF_CONFIG)
        assert gcp_rms_px(result.model, control_points) < gcp_rms_px(
            start, control_points
        )

    def test_probe_ignores_control_points_entirely(self):
        """The probe must be independent, or the primary gate is circular."""
        truth, samples, evidence = _world()
        field = build_user_field(evidence, DEFAULT_GEOREF_CONFIG)
        real = _control_points_from(truth, [(60.0, 100.0), (150.0, 140.0), (240.0, 110.0)])
        nonsense = _control_points_from(
            _perturb(truth, 900.0, 900.0, 0.0),
            [(60.0, 100.0), (150.0, 140.0), (240.0, 110.0)],
        )

        start = _perturb(truth, 6.0, 4.0, 0.0)
        a = fit_chamfer(start, real, samples, field, DEFAULT_GEOREF_CONFIG, use_gcps=False)
        b = fit_chamfer(
            start, nonsense, samples, field, DEFAULT_GEOREF_CONFIG, use_gcps=False
        )
        assert np.allclose(a.model.matrix, b.model.matrix)

    def test_no_samples_is_not_a_crash(self):
        truth, _samples, evidence = _world()
        field = build_user_field(evidence, DEFAULT_GEOREF_CONFIG)
        empty = CurveSamples(xy=np.zeros((0, 2)), xy_normal=np.zeros((0, 2)))
        result = fit_chamfer(truth, [], empty, field, DEFAULT_GEOREF_CONFIG)
        assert result.model is truth
        assert not result.converged


class TestNormalSearchICP:
    def test_finds_correspondences_on_the_true_transform(self):
        truth, samples, evidence = _world()
        field = build_user_field(evidence, DEFAULT_GEOREF_CONFIG)
        index, targets, weight = find_correspondences(
            _params_from_model(truth), samples, field, 20.0, DEFAULT_GEOREF_CONFIG
        )
        assert index.size > 0.5 * len(samples)
        assert targets.shape == (index.size, 2)
        assert np.all(weight >= 0.0)

    def test_orientation_filter_rejects_a_crossing_line(self):
        """The point of the stage: a border crossing a coast is 'nearby edge
        pixels' to a chamfer, and must not be matched by ICP."""
        truth, samples, evidence = _world()

        # Replace the coastline with a single perpendicular bar: it is close to
        # the reference curve but oriented across it.
        weight = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        weight[:, 150] = 1.0
        crossing = SimpleNamespace(
            edge_weight=weight, text_mask=None, water=None
        )
        field = build_user_field(crossing, DEFAULT_GEOREF_CONFIG)

        index, _targets, _w = find_correspondences(
            _params_from_model(truth), samples, field, 30.0, DEFAULT_GEOREF_CONFIG
        )
        # Only the few samples whose own normal happens to align with the bar
        # may match; the bulk must be rejected.
        assert index.size < 0.25 * len(samples)

    def test_tolerance_controls_how_much_is_accepted(self):
        truth, samples, evidence = _world()
        weight = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        weight[:, 150] = 1.0
        field = build_user_field(
            SimpleNamespace(edge_weight=weight, text_mask=None, water=None),
            DEFAULT_GEOREF_CONFIG,
        )
        strict = DEFAULT_GEOREF_CONFIG.with_overrides(
            icp_orientation_tolerance_deg=5.0
        )
        loose = DEFAULT_GEOREF_CONFIG.with_overrides(
            icp_orientation_tolerance_deg=89.0
        )
        few, _t, _w = find_correspondences(
            _params_from_model(truth), samples, field, 30.0, strict
        )
        many, _t2, _w2 = find_correspondences(
            _params_from_model(truth), samples, field, 30.0, loose
        )
        assert few.size < many.size

    def test_refine_improves_or_holds(self):
        truth, samples, evidence = _world()
        field = build_user_field(evidence, DEFAULT_GEOREF_CONFIG)
        control_points = _control_points_from(truth, [(60.0, 100.0), (240.0, 110.0)])
        start = _perturb(truth, 5.0, 3.0, 0.0)
        result = icp_refine(
            start, control_points, samples, field, DEFAULT_GEOREF_CONFIG
        )
        assert result.detail["correspondences"] > 0
        assert gcp_rms_px(result.model, control_points) <= gcp_rms_px(
            start, control_points
        ) + 1e-6


class TestGates:
    def _phase(self, converged=True, inliers=0.8):
        from app.utils.georeferencing.align import PhaseResult

        return PhaseResult(
            model=_truth_model(),
            converged=converged,
            inlier_fraction=inliers,
            cost=1.0,
            iterations=10,
        )

    def _layers(self, water=None):
        from app.utils.georeferencing.reference import ReferenceGrid

        grid = ReferenceGrid(
            west=-80.0, south=40.0, east=-60.0, north=55.0, width=50, height=40
        )
        return SimpleNamespace(
            grid=grid,
            water=np.zeros((40, 50), dtype=bool) if water is None else water,
            has_water=water is not None and water.any(),
        )

    def test_all_checks_are_returned_even_when_inapplicable(self):
        truth, _s, evidence = _world()
        checks = evaluate_gates(
            truth, truth, None, [], self._layers(), evidence, self._phase()
        )
        names = [c.name for c in checks]
        assert "probe_gcp_disagreement" in names
        assert "water_mask_iou" in names
        assert any(not c.applicable for c in checks)
        assert gates_passed(checks)

    def test_a_distant_probe_fails_the_primary_gate(self):
        truth, _s, evidence = _world()
        control_points = _control_points_from(truth, [(60.0, 100.0), (240.0, 110.0)])
        bad_probe = _perturb(truth, 500.0, 0.0, 0.0)
        checks = evaluate_gates(
            truth, truth, bad_probe, control_points, self._layers(), evidence,
            self._phase(),
        )
        assert "probe_gcp_disagreement" in failed_names(checks)
        assert not gates_passed(checks)

    def test_scale_drift_is_caught(self):
        truth, _s, evidence = _world()
        blown = AffineModel(matrix=truth.matrix.copy())
        blown.matrix[:2, :2] *= 2.0
        checks = evaluate_gates(
            blown, truth, None, [], self._layers(), evidence, self._phase()
        )
        assert "scale_drift" in failed_names(checks)

    def test_rotation_drift_is_caught(self):
        truth, _s, evidence = _world()
        turned = _perturb(truth, 0.0, 0.0, 40.0)
        checks = evaluate_gates(
            turned, truth, None, [], self._layers(), evidence, self._phase()
        )
        assert "rotation_drift" in failed_names(checks)

    def test_a_mirror_is_caught(self):
        truth, _s, evidence = _world()
        mirrored = AffineModel(matrix=truth.matrix.copy())
        mirrored.matrix[0, 0] *= -1.0
        checks = evaluate_gates(
            mirrored, truth, None, [], self._layers(), evidence, self._phase()
        )
        assert "transform_determinant" in failed_names(checks)

    def test_inlier_collapse_is_caught(self):
        truth, _s, evidence = _world()
        checks = evaluate_gates(
            truth, truth, None, [], self._layers(), evidence,
            self._phase(inliers=0.01),
        )
        assert "inlier_fraction" in failed_names(checks)

    def test_chamfer_residual_is_never_a_gate(self):
        """A fit locked onto the wrong feature has a *low* residual, so the
        residual can only ever be a diagnostic."""
        truth, _s, evidence = _world()
        checks = evaluate_gates(
            truth, truth, None, [], self._layers(), evidence, self._phase()
        )
        assert not any("residual" in c.name or "chamfer" in c.name for c in checks)

    def test_water_gate_is_inapplicable_without_water(self):
        truth, _s, evidence = _world()
        checks = evaluate_gates(
            truth, truth, None, [], self._layers(), evidence, self._phase()
        )
        water = next(c for c in checks if c.name == "water_mask_iou")
        assert not water.applicable
        assert water.passed


class TestWaterIou:
    def test_none_when_either_side_is_dry(self):
        truth, _s, evidence = _world()
        layers = SimpleNamespace(grid=None, water=None, has_water=False)
        assert water_mask_iou(truth, layers, evidence) is None


class TestRecoveryLadder:
    def test_falls_back_to_the_baseline_without_evidence(self):
        truth, _s, _e = _world()
        empty_evidence = SimpleNamespace(
            edge_weight=np.zeros((HEIGHT, WIDTH), dtype=np.float32),
            text_mask=None,
            water=None,
        )
        layers = SimpleNamespace(
            grid=None,
            water=np.zeros((4, 4), dtype=bool),
            has_water=False,
            curve_mask=lambda **kw: np.zeros((4, 4), dtype=bool),
            sample_curve_points_with_normals=lambda **kw: (
                np.zeros(0),
                np.zeros(0),
                np.zeros(0),
                np.zeros(0),
            ),
            coverage=lambda: {},
        )
        record = RunRecord()
        result = align(truth, [], layers, empty_evidence, record=record)
        assert result.model is truth
        assert result.method == "gcp_only"
        assert result.rung == 7
        assert not result.used_curve_evidence

    def test_perturb_moves_the_model_in_pixel_space(self):
        truth = _truth_model()
        moved = _perturb(truth, 10.0, 0.0, 0.0)
        X0, _ = truth(np.array([0.0]), np.array([0.0]))
        X1, _ = moved(np.array([-10.0]), np.array([0.0]))
        assert float(X1[0]) == pytest.approx(float(X0[0]))

    def test_result_reports_whether_curve_evidence_was_used(self):
        truth = _truth_model()
        assert AlignmentResult(truth, "joint", 0).used_curve_evidence
        assert AlignmentResult(truth, "joint_gcp_weighted", 3).used_curve_evidence
        assert not AlignmentResult(truth, "gcp_only", 7).used_curve_evidence


class TestStagedEvidence:
    """Coastline first, then lakes; rivers off by default."""

    class _FakeLayers:
        def __init__(self):
            self.calls = []

        def curve_mask(self, use_coastline=True, use_lakes=True, use_rivers=True):
            self.calls.append((use_coastline, use_lakes, use_rivers))
            return np.zeros((4, 4), dtype=bool)

        def sample_curve_points_with_normals(self, **kw):
            z = np.zeros(0)
            return z, z, z, z

    def test_rivers_are_off_by_default(self):
        assert DEFAULT_GEOREF_CONFIG.use_rivers_for_alignment is False
        assert DEFAULT_GEOREF_CONFIG.use_lakes_for_alignment is True

    def test_default_sampling_excludes_rivers(self):
        from app.utils.georeferencing.align import build_curve_samples

        layers = self._FakeLayers()
        build_curve_samples(layers, DEFAULT_GEOREF_CONFIG)
        assert layers.calls == [(True, True, False)]

    def test_coastline_stage_excludes_lakes_and_rivers(self):
        from app.utils.georeferencing.align import build_curve_samples

        layers = self._FakeLayers()
        build_curve_samples(
            layers, DEFAULT_GEOREF_CONFIG,
            use_coastline=True, use_lakes=False, use_rivers=False,
        )
        assert layers.calls == [(True, False, False)]

    def test_coarse_schedule_is_wider_than_the_fine_one(self):
        """The coarse stage has to reach a coastline that starts far away."""
        c = DEFAULT_GEOREF_CONFIG
        assert c.coarse_blur_px[0] > c.anneal_blur_px[0] * 4
        assert c.coarse_cutoff_px[0] > c.anneal_cutoff_px[0] * 4


class TestEngagementGate:
    """A fit that never moved passes every sanity check, because nothing
    drifted. This gate is the only thing that notices."""

    def _phase(self):
        from app.utils.georeferencing.align import PhaseResult

        return PhaseResult(
            model=_truth_model(), converged=True, inlier_fraction=0.8,
            cost=1.0, iterations=10,
        )

    def _layers(self):
        return SimpleNamespace(
            grid=None, water=np.zeros((4, 4), dtype=bool), has_water=False
        )

    def test_a_fit_that_did_not_move_fails(self):
        truth, _s, evidence = _world()
        checks = evaluate_gates(
            truth, truth, None, [], self._layers(), evidence, self._phase(),
            baseline_chamfer_px=40.0, aligned_chamfer_px=40.0,
        )
        assert "curve_fit_engaged" in failed_names(checks)

    def test_a_fit_that_improved_passes(self):
        truth, _s, evidence = _world()
        checks = evaluate_gates(
            truth, truth, None, [], self._layers(), evidence, self._phase(),
            baseline_chamfer_px=40.0, aligned_chamfer_px=12.0,
        )
        assert "curve_fit_engaged" not in failed_names(checks)
        assert gates_passed(checks)

    def test_a_fit_that_got_worse_fails(self):
        truth, _s, evidence = _world()
        checks = evaluate_gates(
            truth, truth, None, [], self._layers(), evidence, self._phase(),
            baseline_chamfer_px=40.0, aligned_chamfer_px=55.0,
        )
        assert "curve_fit_engaged" in failed_names(checks)

    def test_inapplicable_without_residuals(self):
        truth, _s, evidence = _world()
        checks = evaluate_gates(
            truth, truth, None, [], self._layers(), evidence, self._phase()
        )
        check = next(c for c in checks if c.name == "curve_fit_engaged")
        assert not check.applicable
        assert check.passed

    def test_magnitude_alone_is_still_never_a_gate(self):
        """A huge residual that improved is fine; a tiny one that did not is not.
        The gate is about engagement, not correctness."""
        truth, _s, evidence = _world()
        huge_but_improved = evaluate_gates(
            truth, truth, None, [], self._layers(), evidence, self._phase(),
            baseline_chamfer_px=900.0, aligned_chamfer_px=400.0,
        )
        tiny_but_stuck = evaluate_gates(
            truth, truth, None, [], self._layers(), evidence, self._phase(),
            baseline_chamfer_px=2.0, aligned_chamfer_px=2.0,
        )
        assert "curve_fit_engaged" not in failed_names(huge_but_improved)
        assert "curve_fit_engaged" in failed_names(tiny_but_stuck)


class TestNonRegression:
    def test_alignment_is_off_by_default(self):
        """Turning it on is the experiment, not the baseline. Step 4 must not
        change production output until the evidence says it should."""
        assert DEFAULT_GEOREF_CONFIG.enable_curve_alignment is False
