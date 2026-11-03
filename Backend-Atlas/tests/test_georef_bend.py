"""The coast bend (app/utils/georeferencing/bend.py): its fit recovers a
smooth correction, sees only the part across a coast, the bent model inverts
and round-trips, the weighting gives the control points more say the more of
them there are, the stage bends a drawn coast onto the reference, and the
inland correction pulls only the control points far from the coast."""

from types import SimpleNamespace

import numpy as np

from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG
from app.utils.georeferencing.affine import AffineModel
from app.utils.georeferencing.align import CurveSamples, build_user_field
from app.utils.georeferencing.bend import (
    BendBasis,
    CoastBendModel,
    InlandCorrectionModel,
    across_observations,
    bend_to_coast,
    coast_share,
    correct_inland,
    full_observations,
    solve_bend,
)
from app.utils.georeferencing.control_points import ControlPoint
from app.utils.georeferencing.piecewise import deserialize_model
from app.utils.georeferencing.projection import webmercator_arrays_to_lonlat
from app.utils.georeferencing.records import RunRecord

SIZE = (400, 300)


def _field(p: np.ndarray) -> np.ndarray:
    return np.column_stack((
        3.0 + 0.01 * p[:, 0] + 8.0 * np.exp(-((p[:, 0] - 120) ** 2 + (p[:, 1] - 90) ** 2) / (2 * 60.0**2)),
        -2.0 + 6.0 * np.sin(p[:, 0] / 90.0),
    ))


def test_full_observations_recover_a_smooth_correction():
    rng = np.random.default_rng(0)
    basis = BendBasis(SIZE, 12)
    p = rng.uniform((0, 0), SIZE, (2000, 2))
    coef = solve_bend(basis, [(1.0, full_observations(basis(p), _field(p)))], 1e-6)
    q = rng.uniform((50, 50), (350, 250), (500, 2))
    assert np.abs(basis.apply(q, coef) - _field(q)).max() < 0.2


def test_a_straight_coast_sees_only_the_correction_across_it():
    basis = BendBasis(SIZE, 6)
    coast = np.column_stack((np.linspace(20, 380, 200), np.full(200, 150.0)))
    normals = np.tile((0.0, 1.0), (200, 1))
    slide = solve_bend(basis, [(1.0, across_observations(basis(coast), np.tile((5.0, 0.0), (200, 1)), normals))], 1e-3)
    push = solve_bend(basis, [(1.0, across_observations(basis(coast), np.tile((0.0, 5.0), (200, 1)), normals))], 1e-3)
    on_coast = basis(coast[40:160])
    assert np.abs(on_coast @ slide).max() < 1e-3
    assert np.allclose((on_coast @ push)[:, 1], 5.0, atol=0.1)


def test_the_jacobian_matches_the_correction():
    rng = np.random.default_rng(1)
    basis = BendBasis(SIZE, 6)
    coef = rng.normal(0, 3, (basis.size, 2))
    p = rng.uniform((0, 0), SIZE, (50, 2))
    h = 1e-4
    numeric = np.stack(
        [(basis.apply(p + d, coef) - basis.apply(p - d, coef)) / (2 * h) for d in (np.array([h, 0]), np.array([0, h]))],
        axis=2,
    )
    assert np.allclose(basis.jacobian(p, coef), numeric, atol=1e-6)


def _bent() -> CoastBendModel:
    base = AffineModel(matrix=np.array([[1000.0, 20.0, 5e5], [-10.0, -1000.0, 6e6], [0, 0, 1]]))
    basis = BendBasis(SIZE, 6)
    coef = np.zeros((basis.size, 2))
    coef[3:] = np.random.default_rng(2).normal(0, 2, (basis.size - 3, 2))
    return CoastBendModel(base, SIZE, 6, coef)


def test_the_bent_model_inverts_and_round_trips():
    model = _bent()
    p = np.random.default_rng(3).uniform((0, 0), SIZE, (200, 2))
    X, Y = model(p[:, 0], p[:, 1])
    qx, qy = model.inverse()(X, Y)
    assert np.allclose(np.column_stack((qx, qy)), p, atol=1e-6)
    again = deserialize_model(model.serialize())
    assert isinstance(again, CoastBendModel)
    assert np.allclose(np.column_stack(again(p[:, 0], p[:, 1])), np.column_stack((X, Y)))


def test_the_weighting_follows_the_counts():
    config = DEFAULT_GEOREF_CONFIG
    matches = np.ones(700)

    shares = [coast_share(config, matches, n, spacing=2.0) for n in (3, 10, 20)]
    sharper = coast_share(config.with_overrides(coast_bend_gcp_sigma_px=2.0), matches, 10, 2.0)
    correlated = coast_share(config.with_overrides(coast_bend_coast_correlation_px=60.0), matches, 10, 2.0)

    assert shares[0] > shares[1] > shares[2]
    assert round(shares[1], 2) == 0.93
    assert sharper < shares[1] and correlated < shares[1]


def test_the_stage_bends_a_drawn_coast_onto_the_reference():
    """The map draws a straight coast as a wave of 8 px; the model before the
    bend is the identity, so the reference coast is the straight line."""
    w, h = SIZE
    weight = np.zeros((h, w), dtype=np.float32)
    xs = np.arange(w)
    wave = lambda x: 150.0 + 8.0 * np.sin(x / 50.0)  # noqa: E731
    weight[np.round(wave(xs)).astype(int), xs] = 1.0
    user_field = build_user_field(SimpleNamespace(edge_weight=weight, text_mask=None))
    line = np.column_stack((np.linspace(10, w - 10, 400), np.full(400, 150.0)))
    context = SimpleNamespace(
        coast_samples=CurveSamples(xy=line, xy_normal=line + (0.0, 1.0)), user_field=user_field
    )
    identity = AffineModel(matrix=np.eye(3))
    corners = np.array([[20.0, 20.0], [380.0, 30.0], [200.0, 280.0]])
    lon, lat = webmercator_arrays_to_lonlat(corners[:, 0], corners[:, 1])
    points = [ControlPoint.sift(tuple(p), (a, b)) for p, a, b in zip(corners, lon, lat)]
    config = DEFAULT_GEOREF_CONFIG.with_overrides(
        coast_bend=True, coast_bend_knots_across=12
    )
    record = RunRecord()

    bent = bend_to_coast(identity, points, context, SIZE, config, record)

    assert record.to_dict()["errors"]["coastBend"]["applied"], record.to_dict()["errors"]["coastBend"]
    drawn = np.column_stack((xs[60:340].astype(float), wave(xs[60:340])))
    _, y = bent(drawn[:, 0], drawn[:, 1])
    assert np.abs(y - 150.0).max() < 1.5
    assert np.abs(drawn[:, 1] - 150.0).max() > 7.0


def test_the_inland_correction_pulls_only_the_points_far_from_the_coast():
    """A coast along y = 150 on the left half; the identity model is 6 px off
    at an inland point and 6 px off at one on the coast. Only the inland one
    is corrected, most of the way, and the correction fades before the coast."""
    line = np.column_stack((np.linspace(10, 200, 200), np.full(200, 150.0)))
    context = SimpleNamespace(coast_samples=CurveSamples(xy=line, xy_normal=line + (0.0, 1.0)))
    identity = AffineModel(matrix=np.eye(3))
    clicked = np.array([[350.0, 40.0], [100.0, 152.0]])
    true = clicked + (6.0, 4.0)
    lon, lat = webmercator_arrays_to_lonlat(true[:, 0], true[:, 1])
    points = [ControlPoint.sift(tuple(p), (a, b)) for p, a, b in zip(clicked, lon, lat)]
    config = DEFAULT_GEOREF_CONFIG.with_overrides(coast_bend_inland=True)
    record = RunRecord()

    model = correct_inland(identity, points, context, SIZE, config, record)

    stats = record.to_dict()["errors"]["inlandCorrection"]
    assert stats["applied"] and stats["inlandPoints"] == 1, stats
    X, Y = model(clicked[:, 0], clicked[:, 1])
    moved = np.column_stack((X, Y)) - clicked
    assert np.allclose(moved[0], (6.0, 4.0), atol=1.0)
    assert np.linalg.norm(moved[1]) < 0.5
    assert isinstance(model, InlandCorrectionModel)
    again = deserialize_model(model.serialize())
    qx, qy = again.inverse()(X, Y)
    assert np.allclose(np.column_stack((qx, qy)), clicked, atol=1e-6)

