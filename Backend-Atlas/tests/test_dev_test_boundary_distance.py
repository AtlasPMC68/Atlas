"""Boundary distance: how far, in km, the extracted zone boundary sits from the
expected one. See dev-docs/georeferencing-testing.md section 4."""

import math

import pytest
from shapely.geometry import box, mapping

from app.utils.dev_test_evaluator import (
    BOUNDARY_STEP_KM,
    EARTH_RADIUS_KM,
    boundary_distance_km,
)

KM_PER_DEG = math.radians(1.0) * EARTH_RADIUS_KM  # ~111.2 km at the equator


def _fc(*zones):
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": name}, "geometry": mapping(geom)}
            for name, geom in zones
        ],
    }


def test_a_uniform_inset_is_measured_in_km():
    """An inner square 0.1 degree inside the outer one, at the equator: every
    inner boundary point is 0.1 degree (~11.1 km) from the outer boundary."""
    outer = box(-1.0, -1.0, 1.0, 1.0)
    inner = box(-0.9, -0.9, 0.9, 0.9)
    d = boundary_distance_km(outer, inner)
    expected = 0.1 * KM_PER_DEG
    assert d["extractedToExpectedMeanKm"] == pytest.approx(expected, abs=0.3)
    # Outer corners are diagonal from the inner ones.
    assert d["maxKm"] == pytest.approx(expected * math.sqrt(2), abs=0.3)


def test_holes_do_not_count_as_misplaced_boundary():
    """A lake cut out of the middle of a zone is not a misplaced border: the
    outline is measured, and the hole is counted separately."""
    outer = box(-5.0, -5.0, 5.0, 5.0)
    holed = outer.difference(box(-1.0, -1.0, 1.0, 1.0))
    d = boundary_distance_km(outer, holed)
    assert d["maxKm"] <= BOUNDARY_STEP_KM / 2 + 1e-6
    assert d["extractedHoles"] == 1
    assert d["expectedHoles"] == 0


