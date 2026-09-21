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


class TestTextMask:
    def test_empty_without_regions(self):
        mask = build_text_mask((HEIGHT, WIDTH), None, 7)
        assert mask.shape == (HEIGHT, WIDTH)
        assert not mask.any()

    def test_covers_the_region(self):
        region = [[100, 100], [200, 100], [200, 140], [100, 140]]
        mask = build_text_mask((HEIGHT, WIDTH), [region], 0)
        assert mask[120, 150]
        assert not mask[10, 10]

    def test_dilation_grows_the_mask(self):
        region = [[100, 100], [200, 100], [200, 140], [100, 140]]
        tight = build_text_mask((HEIGHT, WIDTH), [region], 0)
        grown = build_text_mask((HEIGHT, WIDTH), [region], 8)
        assert grown.sum() > tight.sum()
        # Canny fires just outside a glyph, which is the point of dilating.
        assert grown[120, 201] and not tight[120, 201]

    def test_dilation_scales_with_image_size(self):
        """A fixed pixel count is proportionally huge on a small scan.

        Measured on a real 521x481 map, an absolute 7 px dilation helped push
        the text mask to 42% of the image, gutting the edge evidence. The
        dilation is now keyed off the diagonal so it means the same thing at any
        resolution.
        """
        region = [[10, 10], [60, 10], [60, 30], [10, 30]]
        small = build_text_mask((200, 240), [region], 8).sum()
        large = build_text_mask((1400, 1700), [region], 8).sum()
        # Same region, same nominal dilation: the big image must not dilate less.
        assert large > small

    def test_malformed_regions_are_skipped_not_fatal(self):
        mask = build_text_mask(
            (HEIGHT, WIDTH), [[[1, 2]], [["a", "b"], ["c", "d"]], None], 2
        )
        assert not mask.any()


class TestEdgeMap:
    def test_finds_edges(self):
        edges = build_edge_map(_with_neatline_and_coast())
        assert edges.any()

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

    def test_accepts_a_leading_axis_layout(self):
        found = np.array([[[10, 20, 30, 40], [50, 60, 70, 80]]], dtype=np.int32)
        assert normalize_hough_output(found) == self.EXPECTED

    def test_none_and_empty_are_no_lines(self):
        assert normalize_hough_output(None) == []
        assert normalize_hough_output(np.empty((0, 1, 4), dtype=np.int32)) == []


class TestStraightLineSuppression:
    def test_detects_a_long_straight_line(self):
        edges = build_edge_map(_with_neatline_and_coast())
        lines = detect_straight_lines(edges)
        assert lines, "the neatline should be found"

    def test_ignores_short_segments(self):
        image = _blank()
        cv2.line(image, (100, 100), (130, 100), (0, 0, 0), 2)
        edges = build_edge_map(image)
        assert detect_straight_lines(edges) == []

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

    def test_down_weights_rather_than_deletes(self):
        """A real coast can run straight for a while; erasing is too destructive."""
        image = _with_neatline_and_coast()
        edges = build_edge_map(image)
        weight = suppress_straight_lines(edges, detect_straight_lines(edges))
        assert (weight > 0).sum() == edges.sum()
        assert weight.min() >= 0.0
        assert weight.max() <= 1.0

    def test_no_lines_leaves_the_map_untouched(self):
        edges = build_edge_map(_with_neatline_and_coast())
        weight = suppress_straight_lines(edges, [])
        assert np.array_equal(weight, edges.astype(np.float32))


class TestWaterMask:
    @staticmethod
    def _sea_and_lake() -> np.ndarray:
        """Blue sea down the left edge, same-blue lake in the middle."""
        image = np.full((HEIGHT, WIDTH, 3), 230, dtype=np.uint8)
        image[:, :90] = (40, 90, 200)  # RGB: reaches the border, so it is ocean
        cv2.circle(image, (260, 150), 40, (40, 90, 200), -1)  # interior: a lake
        return image

    def test_no_picks_gives_an_empty_mask(self):
        mask = build_water_mask(self._sea_and_lake(), None)
        assert not mask.any()

    def test_picks_select_matching_pixels(self):
        image = self._sea_and_lake()
        mask = build_water_mask(image, [(0.1, 0.5)], [10])
        assert mask[150, 40]
        assert not mask[150, 380]

    def test_one_pick_finds_both_water_bodies(self):
        """Sea and lake are the same hue -- which is why kind is a user choice."""
        image = self._sea_and_lake()
        mask = build_water_mask(image, [(0.1, 0.5)], [10])
        assert mask[150, 40] and mask[150, 260]

    def test_out_of_range_picks_are_ignored(self):
        mask = build_water_mask(self._sea_and_lake(), [(5.0, 5.0)], [10])
        assert not mask.any()

    def test_splits_border_ocean_from_interior_lake(self):
        image = self._sea_and_lake()
        water = build_water_mask(image, [(0.1, 0.5)], [10])
        ocean, lakes = split_ocean_and_lakes(water)

        assert ocean[150, 40] and not lakes[150, 40]
        assert lakes[150, 260] and not ocean[150, 260]
        assert not (ocean & lakes).any()

    def test_split_of_empty_water_is_empty(self):
        empty = np.zeros((HEIGHT, WIDTH), dtype=bool)
        ocean, lakes = split_ocean_and_lakes(empty)
        assert not ocean.any() and not lakes.any()

    def test_specks_below_the_minimum_area_are_dropped(self):
        water = np.zeros((HEIGHT, WIDTH), dtype=bool)
        water[150:153, 200:203] = True  # 9 px, well under the threshold
        _, lakes = split_ocean_and_lakes(water)
        assert not lakes.any()


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

    def test_keeps_an_edge_on_the_shore(self):
        filtered, applied = filter_edges_near_water(
            self._column(100), self._water_left_of(100)
        )
        assert applied
        assert filtered[:, 100].all()

    def test_keeps_an_edge_a_couple_of_pixels_off_the_shore(self):
        """Canny can land a pixel or two either side of the true boundary."""
        margin = DEFAULT_GEOREF_CONFIG.edge_water_margin_px
        water = self._water_left_of(100)
        on_land, _ = filter_edges_near_water(self._column(100 + margin - 1), water)
        in_water, _ = filter_edges_near_water(self._column(100 - margin), water)
        assert on_land.any()
        assert in_water.any()

    def test_drops_an_edge_inland(self):
        filtered, _ = filter_edges_near_water(
            self._column(250), self._water_left_of(100)
        )
        assert not filtered.any()

    def test_drops_an_edge_in_open_water(self):
        """Graticules and routes drawn across the sea are surrounded by water."""
        filtered, _ = filter_edges_near_water(
            self._column(40), self._water_left_of(100)
        )
        assert not filtered.any()

    def test_no_water_leaves_edges_untouched(self):
        edges = self._column(250)
        filtered, applied = filter_edges_near_water(
            edges, np.zeros((HEIGHT, WIDTH), dtype=bool)
        )
        assert not applied
        assert np.array_equal(filtered, edges)

    def test_too_little_water_is_not_trusted(self):
        """A stray pick on a legend swatch must not delete every edge."""
        water = np.zeros((HEIGHT, WIDTH), dtype=bool)
        water[10:15, 10:15] = True
        edges = self._column(250)
        filtered, applied = filter_edges_near_water(edges, water)
        assert not applied
        assert np.array_equal(filtered, edges)

    def test_can_be_switched_off(self):
        config = DEFAULT_GEOREF_CONFIG.with_overrides(edge_water_filter=False)
        edges = self._column(250)
        filtered, applied = filter_edges_near_water(
            edges, self._water_left_of(100), config
        )
        assert not applied
        assert np.array_equal(filtered, edges)

    def test_end_to_end_drops_a_river_and_keeps_the_coast(self):
        image = TestWaterMask._sea_and_lake()
        cv2.line(image, (330, 20), (330, 280), (0, 0, 0), 2)  # an inland "river"
        evidence = build_user_evidence(
            image, water_click_positions=[(0.1, 0.5)], water_sampling_radii=[10]
        )
        assert evidence.stats["waterEdgeFilterApplied"]
        assert evidence.edges[:, 85:95].any(), "the sea's shore should survive"
        assert not evidence.edges[:, 320:340].any(), "the river should be gone"


class TestBuildUserEvidence:
    def test_bundles_everything(self):
        image = _with_neatline_and_coast()
        evidence = build_user_evidence(image)

        assert evidence.width == WIDTH and evidence.height == HEIGHT
        assert evidence.has_edges
        assert evidence.edge_weight.shape == (HEIGHT, WIDTH)
        assert evidence.stats["straightLineCount"] > 0
        assert evidence.stats["suppressedEdgePixels"] > 0

    def test_works_with_no_water_picks_at_all(self):
        """Leclerc's Atlantic is unpainted: there is simply no water evidence."""
        evidence = build_user_evidence(_with_neatline_and_coast())
        assert not evidence.has_water
        assert evidence.stats["waterFraction"] == 0.0
        assert not evidence.ocean.any() and not evidence.lakes.any()

    def test_works_with_no_text_regions(self):
        """The dev-test path skips text extraction entirely."""
        evidence = build_user_evidence(_with_neatline_and_coast(), text_regions=None)
        assert not evidence.text_mask.any()
        assert evidence.has_edges

    def test_water_picks_flow_through(self):
        image = TestWaterMask._sea_and_lake()
        evidence = build_user_evidence(
            image, water_click_positions=[(0.1, 0.5)], water_sampling_radii=[10]
        )
        assert evidence.has_water
        assert evidence.stats["oceanFraction"] > 0.0
        assert evidence.stats["lakeFraction"] > 0.0

    def test_accepts_a_grayscale_image(self):
        gray = cv2.cvtColor(_with_neatline_and_coast(), cv2.COLOR_BGR2GRAY)
        assert build_user_evidence(gray).has_edges
