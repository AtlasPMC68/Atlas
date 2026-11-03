"""The synthetic map generator (dev-docs/georeferencing-synthetic.md §3)."""

import ast
import copy
import dataclasses
import glob
import os

import cv2
import numpy as np
import pytest
import shapely
from shapely.geometry import Point, box

from app.utils.georef_synthetic import DEFORMATIONS, generate_case, generate_map, generate_twins
from app.utils.georef_synthetic.metrics import dense_samples
from app.utils.georef_synthetic.regions import Unit, image_rect, land_layers, to_pixels
from app.utils.georef_synthetic.render import drawn_layers, render_map
from app.utils.georef_synthetic.run import run_case
from app.utils.georef_synthetic.user import LayoutOptions
from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG
from app.utils.georef_synthetic.warps import (
    WarpOptions,
    EQUIRECTANGULAR,
    LAMBERT_CONIC,
    MERCATOR,
    LocalBump,
    Patchwork,
    Projection,
    SmoothField,
    Warp,
    draw_bump,
    draw_field,
    draw_patchwork,
    fit_affine,
)

SIZE = (1200, 800)


def _base(projection: Projection, rng: np.random.Generator) -> Warp:
    x_west, _ = projection.forward(projection.lon0 - 10.0, projection.lat0)
    x_east, _ = projection.forward(projection.lon0 + 10.0, projection.lat0)
    affine, params = fit_affine(projection, (projection.lon0, projection.lat0), float(x_east - x_west), SIZE, rng)
    return Warp(projection, affine, SIZE, (), params)


@pytest.mark.parametrize(
    "projection",
    [
        Projection(MERCATOR, 5.0, 45.0),
        Projection(EQUIRECTANGULAR, -70.0, 47.0),
        Projection(LAMBERT_CONIC, 130.0, 38.0, 31.0, 45.0),
        Projection(LAMBERT_CONIC, -60.0, -35.0, -42.0, -28.0),
    ],
)
def test_projection_inverse(projection):
    lon = projection.lon0 + np.linspace(-15.0, 15.0, 31)
    lat = np.clip(projection.lat0 + np.linspace(-12.0, 12.0, 31), -80.0, 80.0)
    back_lon, back_lat = projection.inverse(*projection.forward(lon, lat))
    np.testing.assert_allclose(back_lon, lon, atol=1e-9)
    np.testing.assert_allclose(back_lat, lat, atol=1e-9)


@pytest.mark.parametrize("families", [(), ("field",), ("shift",), ("scale",), ("field", "shift")])
def test_warp_round_trip(families):
    rng = np.random.default_rng(3)
    base = _base(Projection(LAMBERT_CONIC, 10.0, 50.0, 44.0, 56.0), rng)
    displacements = []
    for family in families:
        if family == "field":
            displacements.append(draw_field(rng, SIZE))
        else:
            bump = draw_bump(rng, SIZE, np.array([500.0, 300.0]))
            while bump.kind != family:
                bump = draw_bump(rng, SIZE, np.array([500.0, 300.0]))
            displacements.append(bump)
    warp = Warp(base.projection, base.affine, SIZE, tuple(displacements))
    assert warp.min_jacobian_determinant() > 0.0

    px, py = np.meshgrid(np.linspace(0, SIZE[0], 25), np.linspace(0, SIZE[1], 17))
    lon, lat = warp.inverse(px, py)
    back_x, back_y = warp.forward(lon, lat)
    np.testing.assert_allclose(back_x, px, atol=1e-3)
    np.testing.assert_allclose(back_y, py, atol=1e-3)


def test_the_affine_part_keeps_orientation():
    """North up, east right before the random rotation: a map is never mirrored."""
    warp = _base(Projection(MERCATOR, 0.0, 30.0), np.random.default_rng(0))
    x0, y0 = warp.forward(0.0, 30.0)
    x_east, _ = warp.forward(1.0, 30.0)
    _, y_north = warp.forward(0.0, 31.0)
    assert x_east > x0 and y_north < y0


def test_a_folding_warp_is_detected():
    centre = np.array([600.0, 400.0])
    folding = LocalBump("shift", centre, radius=40.0, shift=np.array([200.0, 0.0]))
    warp = Warp(Projection(MERCATOR, 0.0, 0.0), np.eye(2, 3), SIZE, (folding,))
    assert warp.min_jacobian_determinant() <= 0.0


def test_field_is_scaled_to_its_rms():
    rng = np.random.default_rng(7)
    field = draw_field(rng, SIZE)
    gx, gy = np.meshgrid(np.linspace(0, SIZE[0], 32), np.linspace(0, SIZE[1], 32))
    d = field.displacement(np.column_stack((gx.ravel(), gy.ravel())))
    rms = np.sqrt(np.mean(np.sum(d * d, axis=1)))
    assert rms == pytest.approx(field.rms_ratio * np.hypot(*SIZE), rel=1e-9)


def test_jacobians_match_finite_differences():
    rng = np.random.default_rng(11)
    terms = [draw_field(rng, SIZE), LocalBump("scale", np.array([400.0, 300.0]), 150.0, scale=0.25),
             LocalBump("shift", np.array([700.0, 500.0]), 120.0, shift=np.array([30.0, -20.0]))]
    q = rng.uniform(0, 1, size=(50, 2)) * SIZE
    eps = 1e-4
    for term in terms:
        numeric = np.stack(
            [(term.displacement(q + eps * e) - term.displacement(q - eps * e)) / (2 * eps) for e in np.eye(2)],
            axis=2,
        )
        np.testing.assert_allclose(term.jacobian(q), numeric, atol=1e-6)


def _halves(level, bbox, countries=None):
    """Two fake units, the west and east halves of the box: the generator's
    zone code without the borders/ files (gitignored)."""
    west, south, east, north = bbox
    middle = (west + east) / 2.0
    return [
        Unit("West", "WST", None, box(west, south, middle, north)),
        Unit("East", "EST", None, box(middle, south, east, north)),
    ]


def test_a_seed_always_gives_the_same_map():
    first = generate_map(4, units=_halves)
    second = generate_map(4, units=_halves)
    assert cv2.imencode(".png", first.image)[1].tobytes() == cv2.imencode(".png", second.image)[1].tobytes()
    assert first.to_dict() == second.to_dict()
    assert {z.name for z in first.zones} == {"West", "East"}


@pytest.fixture(scope="module")
def twins():
    return generate_twins(4, units=_halves)


def test_twins_share_everything_but_the_displacement(twins):
    none, field, local, stress = (twins[d] for d in DEFORMATIONS)
    assert none.warp.displacements == ()
    assert [type(d) for d in field.warp.displacements] == [SmoothField]
    assert [type(d) for d in local.warp.displacements] == [LocalBump]
    kinds = [type(d) for d in stress.warp.displacements]
    assert kinds[0] is SmoothField and kinds[-1] is Patchwork and set(kinds[1:-1]) == {LocalBump}
    for twin in (none, field, local, stress):
        assert twin.map_id == f"m00004-{twin.deformation}"
        assert twin.region == none.region
        assert twin.warp.projection == none.warp.projection
        assert np.array_equal(twin.warp.affine, none.warp.affine)
        assert twin.style == none.style
        # One framing box, so the same suggestions, where each twin shows them.
        assert twin.frame_bounds == none.frame_bounds
        shared = {(c["lon"], c["lat"]) for c in twin.sift_candidates} & {(c["lon"], c["lat"]) for c in none.sift_candidates}
        assert len(shared) >= 0.8 * min(len(twin.sift_candidates), len(none.sift_candidates))


def test_the_stress_twin_is_far_stronger_and_leaves_the_others_alone(twins):
    """Its own stream: the base twins are the same drawn with or without it."""
    stress = twins["stress"]
    assert stress.warp.min_jacobian_determinant(160) > 0.0
    assert 0.0 < stress.stress["strength"] <= 1.0
    strongest = max(twins[d].warp.non_affine_rms_px() for d in ("field", "local"))
    assert stress.warp.non_affine_rms_px() > 2.0 * strongest
    alone = generate_twins(4, units=_halves, deformations=("none",))
    assert list(alone) == ["none"]
    assert alone["none"].to_dict() == twins["none"].to_dict()
    assert np.array_equal(alone["none"].image, twins["none"].image)


def test_the_patchwork_jacobian_matches_its_displacement():
    rng = np.random.default_rng(0)
    patchwork = draw_patchwork(rng, (1200, 900))
    q = rng.uniform((0, 0), (1200, 900), size=(50, 2))
    h = 1e-3
    numeric = np.stack(
        [(patchwork.displacement(q + h * e) - patchwork.displacement(q - h * e)) / (2 * h) for e in np.eye(2)],
        axis=2,
    )
    assert np.allclose(patchwork.jacobian(q), numeric, atol=1e-6)


def test_a_layout_makes_the_same_draws_on_every_twin(twins):
    """The three base twins. The stress twin moves features far enough to
    change which suggestions it shows, so its layouts draw from other counts."""
    params = [generate_case(twins[d], 0).layout.params for d in ("none", "field", "local")]
    for p in params[1:]:
        assert p["radiusRatio"] == params[0]["radiusRatio"]
        assert p["noisePx"] == params[0]["noisePx"]
        assert p["siftRequested"] == params[0]["siftRequested"]
    assert twins["none"].generalisation.to_dict() == twins["field"].generalisation.to_dict()


@pytest.fixture(scope="module")
def generalised():
    return generate_map(4, units=_halves)


def test_a_generalised_coast_is_drawn_off_the_true_one(generalised):
    """Off by about its amplitude, nowhere by more than its reach; the fill
    and the line agree; the interior stays true."""
    gen = generalised.generalisation
    true_coast = drawn_layers(generalised.warp, generalised.visible, land_layers(), None).coastline
    drawn = generalised.layers.coastline
    samples = shapely.points([drawn.interpolate(t, normalized=True).coords[0] for t in np.linspace(0, 1, 2000)])
    off = shapely.distance(samples, true_coast)
    assert 0.2 * gen.amplitude_px < float(np.median(off)) < 3.0 * gen.amplitude_px
    assert float(np.percentile(off, 99)) < gen.reach_px
    fill_outline = generalised.layers.land_with_lakes.boundary
    assert float(np.max(shapely.distance(samples, fill_outline))) < 1e-6
    for zone in generalised.zones:
        # The drawn zone differs from the true one only along the coast.
        moved = zone.drawn.symmetric_difference(zone.pixel_geometry)
        assert moved.difference(true_coast.buffer(gen.reach_px)).area < 0.001 * zone.pixel_geometry.area


def test_a_user_clicks_a_coastal_feature_where_the_map_draws_it(generalised):
    coastal = [c for c in generalised.sift_candidates if c["feature"] == "coastline"]
    assert coastal
    drawn = shapely.points([c["drawnPixel"] for c in coastal])
    assert float(np.max(shapely.distance(drawn, generalised.layers.coastline))) < 1e-6
    # Only features the map draws are suggested: none is clicked on another.
    gen = generalised.generalisation
    shifted = shapely.points(gen.move(np.array([c["pixel"] for c in coastal])))
    assert float(np.max(shapely.distance(drawn, shifted))) <= gen.snap_px
    case = generate_case(generalised, 0, EXACT_CLICKS)
    for p in case.layout.points:
        if not p["bad"]:
            assert p["pixel"] == p["drawnPixel"]


def test_pixel_zones_are_the_true_zones_through_the_warp():
    synthetic = generate_map(4, units=_halves)
    rect = image_rect(synthetic.image_size)
    for zone in synthetic.zones:
        warped = to_pixels(zone.geometry, synthetic.warp, 0.01).intersection(rect)
        assert warped.symmetric_difference(zone.pixel_geometry).area < 0.01 * zone.pixel_geometry.area


UNDEFORMED = WarpOptions(
    projection_weights={MERCATOR: 1.0}, field_probability=0.0, bump_probability=0.0, coast_generalisation=False
)
EXACT_CLICKS = LayoutOptions(noise_px=(0.0, 0.0), bad_probability=0.0)
AFFINE_ONLY = DEFAULT_GEOREF_CONFIG.with_overrides(
    transform_model="affine", enable_curve_alignment=False, align_after_piecewise=False
)


@pytest.fixture(scope="module")
def undeformed_case():
    synthetic = generate_map(4, units=_halves, options=UNDEFORMED)
    return generate_case(synthetic, 0, EXACT_CLICKS), dense_samples(synthetic, 2000)


def test_an_undeformed_map_places_at_zero_km(undeformed_case):
    """Mercator, an affine, exact clicks: the affine fit is exact. Anything
    above ~0 means the generator and the pipeline disagree on a convention
    (pixel origin, axis direction, units, projection)."""
    case, samples = undeformed_case
    assert case.map.warp.families == ["mercator", "affine"]
    measured, record, _raw = run_case(case, AFFINE_ONLY, samples)
    assert measured["metrics"]["denseMeanKm"] < 0.05
    assert measured["metrics"]["rawMeanIou"] > 0.999
    assert measured["metrics"]["meanIou"] > 0.99
    # The same transform's zones, cleaned without and with snapping.
    assert measured["metrics"]["unsnappedMeanIou"] > 0.99
    assert measured["metrics"]["snappedMeanIou"] > 0.98
    # The check points take the same conventions through errors.checkPoints.
    checks = record["errors"]["checkPoints"]
    assert checks["count"] == len(case.layout.check_points) > 0
    assert checks["rmseKm"] < 0.05


def test_snapping_stretches_by_the_measured_misfit_leaves_an_exact_placement_as_it_is(undeformed_case):
    """With the coast already in place, the measured tolerance is the floor and
    snapping has nothing to correct: it must not cost IoU (§10.8)."""
    case, samples = undeformed_case
    config = AFFINE_ONLY.with_overrides(coastline_snap_measured=True, coastline_snap_stretches=True)
    measured, record, _raw = run_case(case, config, samples)
    metrics = measured["metrics"]
    assert record["inputs"]["snapMisfitPx"] < 2.0
    assert metrics["snappedMeanIou"] > metrics["unsnappedMeanIou"] - 0.002


def test_a_run_records_the_quality_inputs_and_scores_points(undeformed_case):
    """The quality estimator's inputs (georeferencing-synthetic.md §4.3): the
    layout and the affine's leave-one-out on every run, read into the run_
    columns, and with ``points`` that many dense samples with what the run
    knew there and their error."""
    case, samples = undeformed_case
    measured, record, _raw = run_case(case, DEFAULT_GEOREF_CONFIG, samples, points=40)
    run = measured["run"]
    assert 0.0 < run["hullShare"] <= 1.0
    assert run["emptyRadiusRatio"] > 0.0
    assert len(record["errors"]["affineLeaveOneOut"]["residualsPx"]) == run["controlPointCount"]
    assert run["imageDiagonalPx"] > 0

    rows = measured["points"]
    assert len(rows) == 40
    assert [r["pt_index"] for r in rows] == list(range(40))
    first = rows[0]
    assert first["pt_x"] == round(float(samples.px[0]), 2)
    for key in ("pt_nearestPointRatio", "pt_pointsNearby", "pt_insideHull", "pt_shiftFromAffinePx",
                "pt_coastDistanceRatio", "pt_nearbyLooPx", "gen_coastal", "m_errorKm", "m_errorPx"):
        assert key in first, key
    # Exact clicks on an undeformed map: placed to within a fraction of a pixel,
    # and the coast is in the frame, so its distance is known.
    assert max(r["m_errorPx"] for r in rows) < 1.0
    assert all(r["pt_coastDistanceRatio"] is not None for r in rows)


def test_check_points_are_placed_as_the_real_protocol_asks(undeformed_case):
    """Not a control point, not next to one, at most two outside the control
    points' hull, both kinds, clicked as the control points are."""
    from app.utils.georef_synthetic.user import CHECK_CITY, CHECK_OUTSIDE_HULL, CHECK_SIFT

    case, _samples = undeformed_case
    controls = np.array([p["truePixel"] for p in case.layout.points])
    gaps = np.hypot(*(controls[:, None] - controls[None, :]).transpose(2, 0, 1))
    np.fill_diagonal(gaps, np.inf)
    min_gap = float(np.median(gaps.min(axis=1))) / 3.0
    hull = shapely.MultiPoint([tuple(c) for c in controls]).convex_hull
    used = {(p["lon"], p["lat"]) for p in case.layout.points}
    checks = case.layout.check_points
    sources = [p["source"] for p in checks]
    assert 0 < sources.count("sift") <= CHECK_SIFT and sources.count("city") <= CHECK_CITY
    assert sum(not hull.covers(Point(*p["truePixel"])) for p in checks) <= CHECK_OUTSIDE_HULL
    for p in checks:
        assert (p["lon"], p["lat"]) not in used and not p["bad"]
        assert np.hypot(*(controls - p["truePixel"]).T).min() >= min_gap
        assert p["pixel"] == p["drawnPixel"]  # exact clicks


@pytest.mark.parametrize(
    "coast_width, coast_outline", [(0, False), (0, True), (1, True), (2, True), (3, True), (4, True)]
)
def test_alignment_keeps_an_undeformed_map_in_place(undeformed_case, coast_width, coast_outline):
    """Whatever the coast's drawn width: the evidence is the drawn line's
    centre, where the reference coastline is. On its sea-side flank, as before
    config v21, a 2 px coast moved this map by ~1.4 px
    (georeferencing-history.md, 2026-10-27). A plain colour change (width 0,
    no outline) is found to the pixel only: Canny marks one of the two pixels
    either side of the step, and nothing recentres a single edge, so ~0.7 px
    (georeferencing.md, limitations)."""
    case, samples = undeformed_case
    synthetic = copy.copy(case.map)
    style = dataclasses.replace(
        synthetic.style, coast_width=coast_width, coast_contrast=1.0, coast_outline=coast_outline
    )
    synthetic.image = render_map(synthetic.layers, synthetic.zones, synthetic.colours, style, synthetic.image_size)
    drawn = dataclasses.replace(case, map=synthetic)

    config = AFFINE_ONLY.with_overrides(enable_curve_alignment=True)
    measured, _record, _raw = run_case(drawn, config, samples)
    # 0.2-0.35 px measured with a line: the fit's own floor on this map, not a bias.
    bound = 0.4 if coast_width or coast_outline else 0.8
    assert measured["metrics"]["denseMeanKm"] / case.map.km_per_pixel < bound


def test_layouts_follow_the_import_and_stay_in_their_area(undeformed_case):
    """At least 3 SIFT pairs, as the import requires; every point inside the
    (possibly grown) circle; never only cities."""
    case, _samples = undeformed_case
    synthetic = case.map
    diagonal = np.hypot(*synthetic.image_size)
    for layout_index in range(12):
        layout = generate_case(synthetic, layout_index).layout
        params, points = layout.params, layout.points
        assert params["siftCount"] >= 3
        assert params["cityCount"] <= params["cityRequested"]
        radius = params["radiusRatioUsed"] * diagonal
        for p in points:
            assert np.hypot(p["truePixel"][0] - params["centrePx"][0], p["truePixel"][1] - params["centrePx"][1]) <= radius + 0.01


@pytest.mark.parametrize("inland", [False, True])
def test_a_refused_bend_falls_back_to_the_piecewise_step(undeformed_case, inland):
    """The bend in place of the piecewise step, made to refuse (a cap of
    nothing): with the fallback the map is placed as PROD places it, the
    piecewise step and the second alignment, and the inland correction does
    not run on top."""
    case, samples = undeformed_case
    config = DEFAULT_GEOREF_CONFIG.with_overrides(
        transform_model="affine",
        align_after_piecewise=False,
        coast_bend=True,
        coast_bend_max_ratio_of_diagonal=1e-9,
        coast_bend_inland=inland,
        coast_bend_fallback_piecewise=True,
    )
    _measured, record, _raw = run_case(case, config, samples)
    errors = record["errors"]
    assert errors["coastBend"]["applied"] is False
    assert errors["bendFallback"]["applied"] is True
    assert record["models"]["applied"]["name"] == "piecewise_affine"
    assert "inlandCorrection" not in errors


def test_protocol_layouts_spread_their_points_over_the_map(undeformed_case):
    """A protocol layout clicks at least 6 SIFT pairs and 3 cities where the
    map has them, over the whole map, and spreads them further than an open
    layout of the same map does."""
    case, _samples = undeformed_case
    synthetic = case.map

    def spread(points):
        """The share of the image the points' hull covers."""
        hull = shapely.MultiPoint([p["truePixel"] for p in points]).convex_hull
        return hull.area / float(np.prod(synthetic.image_size))

    protocol, open_ = [], []
    for layout_index in range(8):
        for share, out in ((1.0, protocol), (0.0, open_)):
            layout = generate_case(synthetic, layout_index, LayoutOptions(protocol_probability=share)).layout
            out.append(layout)
    for layout in protocol:
        params = layout.params
        assert params["family"] == "protocol" and params["radiusRatioUsed"] >= 1.0
        assert params["siftCount"] >= min(6, len(synthetic.sift_candidates))
        assert params["cityCount"] >= min(3, len(synthetic.city_candidates))
    assert all(layout.params["family"] == "open" for layout in open_)
    assert np.median([spread(l.points) for l in protocol]) > np.median([spread(l.points) for l in open_])


def test_a_sift_mismatch_lands_on_the_same_drawn_curve(undeformed_case):
    case, _samples = undeformed_case
    always = LayoutOptions(noise_px=(0.0, 0.0), bad_probability=1.0)
    layout = generate_case(case.map, 0, always).layout
    bad = layout.params["bad"]
    assert bad["kind"] == "sift_mismatch"
    point = layout.points[bad["index"]]
    curves = {"coastline": case.map.layers.coastline, "lake": case.map.layers.lakes.boundary}
    assert curves[point["feature"]].distance(Point(point["pixel"])) < 1e-6
    assert bad["displacementPx"] > 0


def test_layouts_are_seeded_apart_from_the_map(undeformed_case):
    case, _samples = undeformed_case
    again = generate_case(case.map, 0, EXACT_CLICKS)
    other = generate_case(case.map, 1, EXACT_CLICKS)
    assert again.to_dict() == case.to_dict()
    assert other.to_dict() != case.to_dict()


def test_the_pipeline_never_imports_the_generator():
    root = os.path.join(os.path.dirname(__file__), "..", "app", "utils", "georeferencing")
    for path in glob.glob(os.path.join(root, "*.py")):
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not any("georef_synthetic" in n for n in names), path
