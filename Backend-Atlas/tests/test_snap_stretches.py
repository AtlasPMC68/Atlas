"""Snapping stretches (``coastline_snap_stretches``) and the measured tolerance
(``coastline_snap_measured``): georeferencing-synthetic.md §10.8."""

import math
from types import SimpleNamespace

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

from app.utils.georeferencing.config import DEFAULT_GEOREF_CONFIG
from app.utils.georeferencing.pipeline import snap_tolerance_m_for
from app.utils.georeferencing.snapping import (
    CoastIndex,
    snap_geometry_to_coastline,
    snap_geometry_to_coastline_stretches,
)

TOLERANCE = 10.0


def _snap(zone, coast, min_run=20.0, tolerance=TOLERANCE):
    return snap_geometry_to_coastline_stretches(zone, CoastIndex.build(coast), tolerance, min_run, 45.0, 0.25)


def _straight_coast():
    return LineString([(x, 0.0) for x in range(-1000, 2001, 100)])


def test_a_shore_along_the_coast_moves_onto_it_and_the_rest_stays():
    zone = shapely.segmentize(Polygon([(0, 5), (1000, 5), (1000, 1005), (0, 1005)]), 50.0)
    snapped, total, moved = _snap(zone, _straight_coast())
    assert moved > 0 and total == len(zone.exterior.coords) - 1
    minx, miny, maxx, maxy = snapped.bounds
    assert math.isclose(miny, 0.0, abs_tol=1e-9)
    assert (minx, maxx, maxy) == (0.0, 1000.0, 1005.0)


def test_a_border_that_only_reaches_the_sea_is_left_alone():
    # The old snap moves the apex; a stretch of one vertex is no stretch.
    zone = Polygon([(500, 5), (1000, 1000), (0, 1000)])
    snapped, _, moved = _snap(zone, _straight_coast())
    assert moved == 0
    assert snapped.equals(zone)
    _, _, old_moved = snap_geometry_to_coastline(zone, _straight_coast(), TOLERANCE)
    assert old_moved > 0


def test_a_snapped_shore_follows_the_coast_between_its_vertices():
    # A coarse shore every 30 degrees along a finely drawn arc: the chords cut
    # 34 m inside the arc, the snapped shore follows it.
    arc = LineString([(1000 * math.cos(a), 1000 * math.sin(a)) for a in np.radians(np.arange(0, 181, 2))])
    shore = [(1003 * math.cos(a), 1003 * math.sin(a)) for a in np.radians(np.arange(0, 181, 30))]
    zone = Polygon(shore + [(-1003, 2000), (1003, 2000)])
    on_arc = [shapely.Point(1000 * math.cos(a), 1000 * math.sin(a)) for a in np.radians(np.arange(30, 151, 2))]

    snapped, _, _ = _snap(zone, arc)
    assert max(p.distance(snapped.exterior) for p in on_arc) < 1e-6
    vertex, _, _ = snap_geometry_to_coastline(zone, arc, TOLERANCE)
    assert max(p.distance(vertex.exterior) for p in on_arc) > 30


def test_an_island_drawn_slightly_off_snaps_whole():
    island = shapely.segmentize(Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)]), 100.0)
    zone = shapely.affinity.translate(island, 3.0, 3.0)
    snapped, total, moved = _snap(zone, island.exterior)
    assert moved == total > 0
    assert snapped.symmetric_difference(island).area < 1e-6


def test_a_zone_narrower_than_the_tolerance_does_not_fold_onto_the_coast():
    # Every vertex of a 30 m strip is within 50 m of the coast, the inland
    # border too: snapped whole, it would fold to a line.
    zone = shapely.segmentize(Polygon([(0, 5), (1000, 5), (1000, 35), (0, 35)]), 50.0)
    snapped, _, moved = _snap(zone, _straight_coast(), tolerance=50.0)
    assert moved == 0
    assert snapped.equals(zone)


def test_the_measured_tolerance_is_the_misfit_times_the_factor_between_floor_and_ratio():
    model = SimpleNamespace(meters_per_pixel=100.0)
    size = (1000, 750)
    config = DEFAULT_GEOREF_CONFIG.with_overrides(coastline_snap_measured=True)
    cap = math.hypot(*size) * config.coastline_snap_ratio_of_diagonal * 100.0
    factor, floor = config.coastline_snap_misfit_factor, config.coastline_snap_min_px

    assert math.isclose(snap_tolerance_m_for(model, size, config, 2.0), factor * 2.0 * 100.0)
    assert math.isclose(snap_tolerance_m_for(model, size, config, 0.1), floor * 100.0)
    assert math.isclose(snap_tolerance_m_for(model, size, config, 1e6), cap)
    # Nothing measured, or measuring off: the ratio of the diagonal.
    assert math.isclose(snap_tolerance_m_for(model, size, config, None), cap)
    assert math.isclose(snap_tolerance_m_for(model, size, config, float("nan")), cap)
    unmeasured = DEFAULT_GEOREF_CONFIG.with_overrides(coastline_snap_measured=False)
    assert math.isclose(snap_tolerance_m_for(model, size, unmeasured, 2.0), cap)
