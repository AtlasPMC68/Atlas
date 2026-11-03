"""The SIFT keypoint suggestions (sift_key_points_finder.py)."""

import numpy as np
import shapely
from shapely.geometry import Point

from app.utils.georeferencing.reference import (
    COASTLINE_FILE,
    LAKES_FILE,
    ReferenceGrid,
    load_reference_linework,
)
from app.utils.sift_key_points_finder import (
    LINE_WIDTH_PX,
    NUMBER_OF_KEYPOINTS,
    find_coastline_keypoints,
    render_linework,
)

#: Portugal to Morocco: one suggestion before the mask was widened (2026-10-27).
IBERIA = {"west": -14.62, "south": 31.68, "east": -3.78, "north": 42.37}
#: The Gulf of St Lawrence: a coast that leaves the frame and comes back.
ST_LAWRENCE = {"west": -70.0, "south": 45.0, "east": -58.0, "north": 51.0}


def test_a_regional_frame_gets_a_full_set_of_suggestions():
    assert find_coastline_keypoints(IBERIA)["total"] == NUMBER_OF_KEYPOINTS


def test_suggestions_lie_on_the_reference_curves():
    result = find_coastline_keypoints(ST_LAWRENCE)
    layers = {
        "coastline": load_reference_linework(COASTLINE_FILE),
        "lake": load_reference_linework(LAKES_FILE),
    }
    assert result["total"] >= 10
    for kp in result["keypoints"]:
        point = Point(kp["geo"]["lng"], kp["geo"]["lat"])
        assert layers[kp["feature"]].distance(point) < 1e-6, kp


def test_nothing_is_drawn_away_from_the_coast():
    """Lines are clipped to the frame, never joined across it. A line joined
    across a gap would light pixels tens to hundreds of px from any coast; the
    drawn line itself, anti-aliased and thickened at corners, stays within ~4."""
    grid = ReferenceGrid.from_bounds(ST_LAWRENCE, 1024, 768)
    render, lines = render_linework(load_reference_linework(COASTLINE_FILE), grid)
    rows, cols = np.nonzero(render)
    distances = shapely.distance(lines, shapely.points(cols, rows))
    assert distances.max() < 2 * LINE_WIDTH_PX
