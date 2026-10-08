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
)
from app.utils.georeferencing.gates import (
    evaluate_gates,
    failed_names,
    gates_passed,
    gcp_rms_px,
)
from app.utils.georeferencing.recovery import _perturb, align

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


class TestNormalSearchICP:

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


#: The thresholds the gates were designed with. The defaults are neutralised
#: while the gates are evaluated from the run log (config.py), so tests that
#: check what a gate catches pass these explicitly.
DESIGNED_GATES = DEFAULT_GEOREF_CONFIG.with_overrides(
    gate_probe_gcp_ratio=2.0,
    gate_probe_gcp_max_km=150.0,
    gate_water_iou_min=0.7,
    gate_max_scale_drift=0.25,
    gate_max_rotation_deg=15.0,
    gate_min_inlier_fraction=0.2,
    gate_min_chamfer_improvement=0.02,
)


def _gated(*args, **kwargs):
    return evaluate_gates(*args, config=DESIGNED_GATES, **kwargs)


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
        checks = _gated(
            truth, truth, None, [], self._layers(), evidence, self._phase()
        )
        names = [c.name for c in checks]
        assert "probe_gcp_disagreement" in names
        assert "water_mask_iou" in names
        assert any(not c.applicable for c in checks)
        assert gates_passed(checks)


    def test_a_mirror_is_caught(self):
        truth, _s, evidence = _world()
        mirrored = AffineModel(matrix=truth.matrix.copy())
        mirrored.matrix[0, 0] *= -1.0
        checks = _gated(
            mirrored, truth, None, [], self._layers(), evidence, self._phase()
        )
        assert "transform_determinant" in failed_names(checks)


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


    def test_a_fit_that_got_worse_fails(self):
        truth, _s, evidence = _world()
        checks = _gated(
            truth, truth, None, [], self._layers(), evidence, self._phase(),
            baseline_chamfer_px=40.0, aligned_chamfer_px=55.0,
        )
        assert "curve_fit_engaged" in failed_names(checks)


# --------------------------------------------------------------------------
# The 2026-09-30 fixes 1 and 2 (dev-docs/georeferencing-history.md)
# --------------------------------------------------------------------------


def _samples_at(model: AffineModel, pixels: np.ndarray) -> CurveSamples:
    """Reference samples whose true position under *model* is *pixels*."""
    X, Y = model(pixels[:, 0], pixels[:, 1])
    tangent = np.gradient(pixels, axis=0)
    norm = np.hypot(tangent[:, 0], tangent[:, 1])
    nx, ny = -tangent[:, 1] / norm, tangent[:, 0] / norm
    Xn, Yn = model(pixels[:, 0] + nx, pixels[:, 1] + ny)
    return CurveSamples(xy=np.column_stack([X, Y]), xy_normal=np.column_stack([Xn, Yn]))


def _drawn_curve(dy: float = 0.0, x_end: float = 269.0) -> SimpleNamespace:
    """The `_world` curve drawn on the map, optionally displaced by *dy* px --
    a map whose coast is drawn somewhere its control points disagree with."""
    weight = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    dense_x = np.arange(30.0, x_end, 0.2)
    dense_y = 120.0 + dy + 40.0 * np.sin(dense_x / 26.0)
    weight[
        np.clip(dense_y.astype(int), 0, HEIGHT - 1),
        np.clip(dense_x.astype(int), 0, WIDTH - 1),
    ] = 1.0
    return SimpleNamespace(
        edge_weight=weight,
        text_mask=np.zeros((HEIGHT, WIDTH), dtype=bool),
        water=np.zeros((HEIGHT, WIDTH), dtype=bool),
    )


SPREAD = [(40.0, 30.0), (260.0, 40.0), (150.0, 210.0), (60.0, 200.0), (250.0, 190.0)]


class TestControlPointsKeepPulling:
    """One robust loss for both terms rejected any control point more than a
    pixel or two off in the fine stages: the joint fit was curve-only."""


    def test_control_points_far_beyond_the_curve_cutoff_still_pull(self):
        """No curve evidence at all, the start 40 px off: only the control
        points can move the fit, and they must."""
        truth = _truth_model()
        control_points = _control_points_from(truth, SPREAD)
        blind = SimpleNamespace(
            edge_weight=np.zeros((HEIGHT, WIDTH), dtype=np.float32),
            text_mask=None,
            water=None,
        )
        samples = _samples_at(truth, _curve_pixels())
        start = _perturb(truth, 40.0, -25.0, 0.0)

        result = fit_chamfer(
            start, control_points, samples, build_user_field(blind), DEFAULT_GEOREF_CONFIG
        )

        assert gcp_rms_px(start, control_points) > 40.0
        assert gcp_rms_px(result.model, control_points) < 0.5

    def test_the_joint_fit_is_not_the_curve_only_fit(self):
        """A coast drawn 25 px from where the control points put it. The probe
        (curve only) goes to the drawing; the joint fit must not simply follow
        it, or the control points carry no information.

        At equal term weights: this is about the loss rejecting the points, not
        about the balance. The default x10 coastline weight (config v19) moves
        the joint fit ~80% of the way to the drawing, by design."""
        truth = _truth_model()
        control_points = _control_points_from(truth, SPREAD)
        samples = _samples_at(truth, _curve_pixels())
        field = build_user_field(_drawn_curve(dy=25.0))
        config = DEFAULT_GEOREF_CONFIG.with_overrides(weight_curve=1.0)

        probe = fit_chamfer(truth, control_points, samples, field, config, use_gcps=False)
        joint = fit_chamfer(truth, control_points, samples, field, config)

        probe_rms = gcp_rms_px(probe.model, control_points)
        joint_rms = gcp_rms_px(joint.model, control_points)
        assert probe_rms > 15.0
        assert joint_rms < 0.5 * probe_rms


class TestOffImageSamples:
    """The framing box puts reference coastline off the map. Those samples used
    to read the distance field at the nearest border pixel."""


    def test_samples_off_the_image_cost_a_constant_and_pull_nowhere(self):
        """Off the map a sample is an outlier: the saturated Tukey cost, the
        same wherever the transform moves it. Not the distance at the border
        pixel (an attractor), and not zero (which rewards hiding it there)."""
        from app.utils.georeferencing.align import _residuals

        truth, _samples, evidence = _world()
        field = build_user_field(evidence)
        off_map = np.column_stack(
            [np.linspace(-400.0, -100.0, 50), np.linspace(-300.0, 600.0, 50)]
        )
        samples = _samples_at(truth, off_map)

        def residuals(model):
            return _residuals(
                _params_from_model(model), None, None, None,
                samples.xy, np.ones(len(samples)), field.distance_px,
                field.validity, None, 20.0,
            )

        here = residuals(truth)
        assert np.allclose(here, 20.0 / math.sqrt(3.0))
        assert np.allclose(residuals(_perturb(truth, 7.0, -5.0, 1.0)), here)

    def test_fractions_count_only_samples_in_view(self):
        """A perfect fit whose reference curve runs off the map is all inliers
        among what can be seen, not 'half the samples missed'."""
        truth = _truth_model()
        # Drawn to the image edge, so every sample in view has its coast.
        field = build_user_field(_drawn_curve(x_end=float(WIDTH)))
        x = np.arange(30.0, 570.0, 1.0)  # the image is 300 px wide
        long_curve = np.column_stack([x, 120.0 + 40.0 * np.sin(x / 26.0)])
        samples = _samples_at(truth, long_curve)

        chamfer = fit_chamfer(truth, [], samples, field, DEFAULT_GEOREF_CONFIG, use_gcps=False)
        icp = icp_refine(truth, [], samples, field, DEFAULT_GEOREF_CONFIG, use_gcps=False)

        # The fit stays put: hiding the coast off the map gains nothing, and
        # neither does squeezing off-map coast into view. Unfixed, the first
        # pushed every sample out of view and the second drifted 11 px with a
        # shear; what is left is a curve-only fit of a single raster curve,
        # weakly constrained along its own length.
        assert gcp_rms_px(chamfer.model, _control_points_from(truth, SPREAD)) < 3.0
        in_view = chamfer.detail["samplesInView"]
        assert 0.4 * len(samples) < in_view < 0.6 * len(samples)
        assert chamfer.inlier_fraction > 0.9
        # ICP over the samples that could match, not over every sample.
        matched, in_view = icp.detail["correspondences"], icp.detail["samplesInView"]
        assert icp.inlier_fraction == pytest.approx(matched / in_view)
        assert matched / len(samples) < 0.5 < icp.inlier_fraction
