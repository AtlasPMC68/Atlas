"""Unit tests for user-side evidence (Step 3).

`evidence.py` is the one module in the georeferencing package that needs cv2, so
these are skipped where the image stack is absent. They run on synthetic images
rather than a real map: the behaviour being pinned is "a straight neatline gets
down-weighted and a wiggly coast does not", which a drawn test image states far
more clearly than a scan would.
"""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2", reason="evidence.py requires cv2")

from app.utils.georeferencing.config import DEFAULT_GEOREF_CONFIG  # noqa: E402
from app.utils.georeferencing.evidence import (  # noqa: E402
    build_edge_map,
    normalize_hough_output,
    build_text_mask,
    build_user_evidence,
    build_water_mask,
    detect_straight_lines,
    filter_edges_near_water,
    split_ocean_and_lakes,
    suppress_straight_lines,
)

WIDTH, HEIGHT = 400, 300


def _blank(value: int = 255) -> np.ndarray:
    return np.full((HEIGHT, WIDTH, 3), value, dtype=np.uint8)


def _with_neatline_and_coast() -> np.ndarray:
    """A long straight border plus a wiggly curve: a map in miniature."""
    image = _blank()
    # A neatline: long, straight, the thing suppression exists for.
    cv2.line(image, (20, 20), (380, 20), (0, 0, 0), 2)
    # A "coast": same length, but curved.
    xs = np.arange(30, 370)
    ys = (180 + 30 * np.sin(xs / 18.0)).astype(int)
    for x, y in zip(xs, ys):
        cv2.circle(image, (int(x), int(y)), 1, (0, 0, 0), -1)
    return image


class TestEdgeMap:

    def test_text_is_removed_from_the_edge_map(self):
        image = _blank()
        cv2.putText(image, "Quebec", (60, 150), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)

        without_mask = build_edge_map(image)
        region = [[40, 100], [320, 100], [320, 170], [40, 170]]
        text_mask = build_text_mask((HEIGHT, WIDTH), [region], 6)
        with_mask = build_edge_map(image, text_mask)

        assert without_mask.sum() > 0
        assert with_mask.sum() < without_mask.sum()
        assert not (with_mask & text_mask).any()


class TestHoughOutputShapes:
    """`HoughLinesP` returns (N, 1, 4) on OpenCV 4.x and (N, 4) on 5.0.

    `opencv-python-headless` was unpinned, so two images built weeks apart
    disagreed and the dev loop crashed while the test suite stayed green. The
    dependency is pinned now; this keeps the parser tolerant regardless.
    """

    EXPECTED = [(10, 20, 30, 40), (50, 60, 70, 80)]

    def test_accepts_the_opencv_4_layout(self):
        found = np.array([[[10, 20, 30, 40]], [[50, 60, 70, 80]]], dtype=np.int32)
        assert normalize_hough_output(found) == self.EXPECTED

    def test_accepts_the_opencv_5_layout(self):
        found = np.array([[10, 20, 30, 40], [50, 60, 70, 80]], dtype=np.int32)
        assert normalize_hough_output(found) == self.EXPECTED


class TestStraightLineSuppression:


    def test_suppresses_the_neatline_but_keeps_the_coast(self):
        """The whole point: straightness separates map furniture from geography."""
        image = _with_neatline_and_coast()
        edges = build_edge_map(image)
        weight = suppress_straight_lines(edges, detect_straight_lines(edges))

        neatline_band = weight[15:30, 50:350]
        coast_band = weight[140:220, 50:350]

        suppressed_on_neatline = np.isclose(
            neatline_band[neatline_band > 0], DEFAULT_GEOREF_CONFIG.straight_line_weight
        ).mean()
        kept_on_coast = np.isclose(coast_band[coast_band > 0], 1.0).mean()

        assert suppressed_on_neatline > 0.8
        assert kept_on_coast > 0.8


class TestWaterMask:
    @staticmethod
    def _sea_and_lake() -> np.ndarray:
        """Blue sea down the left edge, same-blue lake in the middle."""
        image = np.full((HEIGHT, WIDTH, 3), 230, dtype=np.uint8)
        image[:, :90] = (40, 90, 200)  # RGB: reaches the border, so it is ocean
        cv2.circle(image, (260, 150), 40, (40, 90, 200), -1)  # interior: a lake
        return image


    def test_splits_border_ocean_from_interior_lake(self):
        image = self._sea_and_lake()
        water = build_water_mask(image, [(0.1, 0.5)], [10])
        ocean, lakes = split_ocean_and_lakes(water)

        assert ocean[150, 40] and not lakes[150, 40]
        assert lakes[150, 260] and not ocean[150, 260]
        assert not (ocean & lakes).any()


class TestWaterEdgeFilter:
    """Edges survive only on the water/land boundary, within a small margin."""

    @staticmethod
    def _water_left_of(x: int) -> np.ndarray:
        water = np.zeros((HEIGHT, WIDTH), dtype=bool)
        water[:, :x] = True
        return water

    @staticmethod
    def _column(x: int) -> np.ndarray:
        edges = np.zeros((HEIGHT, WIDTH), dtype=bool)
        edges[:, x] = True
        return edges


    def test_end_to_end_drops_a_river_and_keeps_the_coast(self):
        image = TestWaterMask._sea_and_lake()
        cv2.line(image, (330, 20), (330, 280), (0, 0, 0), 2)  # an inland "river"
        evidence = build_user_evidence(
            image, water_click_positions=[(0.1, 0.5)], water_sampling_radii=[10]
        )
        assert evidence.stats["waterEdgeFilterApplied"]
        assert evidence.edges[:, 85:95].any(), "the sea's shore should survive"
        assert not evidence.edges[:, 320:340].any(), "the river should be gone"


