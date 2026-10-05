"""Turning a colour mask into polygons, holes included.

The case that motivated these: on a map of Rupert's Land, Hudson Bay is a hole
inside the zone, and the extraction used to fill it. Every contour came back
from ``find_contours`` as an equal, unlabelled closed curve, so the bay's
boundary became a polygon of its own and the union swallowed the bay. The
zone then covered open water, and the ocean clip had to carve it back out --
which made that clip look far more important than it is.
"""

import numpy as np
from shapely.geometry import Point

from app.utils.color_extraction import mask_to_geometry


def _square(size=200, lo=20, hi=180):
    mask = np.zeros((size, size), dtype=bool)
    mask[lo:hi, lo:hi] = True
    return mask


class TestMaskToGeometry:
    def test_an_enclosed_bay_is_a_hole_not_part_of_the_zone(self):
        mask = _square()
        mask[70:130, 70:130] = False  # the bay

        geom = mask_to_geometry(mask)

        assert geom.geom_type == "Polygon"
        assert len(geom.interiors) == 1
        assert not geom.contains(Point(100, 100))
        # Filled, this would be ~25,600 px; the hole is ~3,600 of them.
        assert 21_000 < geom.area < 22_500


    def test_separate_regions_stay_separate(self):
        mask = np.zeros((100, 100), dtype=bool)
        mask[10:40, 10:40] = True
        mask[60:90, 60:90] = True

        assert mask_to_geometry(mask).geom_type == "MultiPolygon"


class TestTextAwareFill:
    """Labels are drawn *over* a zone, so their pixels belong to that zone.

    Without this, nearest-colour assignment drops every glyph and the zone
    comes out full of gaps that hole filling cannot reach: on a real map the
    letters touch the rivers and borders, so the gaps run to the image edge
    and are not holes at all.
    """

    @staticmethod
    def _scene():
        """One zone with a label written across it, as index/valid arrays."""
        best = np.zeros((120, 200), dtype=np.int64)
        valid = np.zeros((120, 200), dtype=bool)
        valid[20:100, 20:180] = True  # the zone
        # Two glyph strokes, unassigned, in the middle of it.
        valid[50:62, 70:74] = False
        valid[50:62, 90:94] = False
        box = [(60, 45), (110, 45), (110, 68), (60, 68)]
        return best, valid, box

    def test_glyphs_become_part_of_the_zone(self):
        from app.utils.color_extraction import relabel_text_pixels

        best, valid, box = self._scene()
        _best, filled, stats = relabel_text_pixels(best, valid, [box])

        assert stats["boxesFilled"] == 1
        assert stats["pixelsFilled"] > 0
        assert filled[50:62, 70:74].all()
        assert filled[50:62, 90:94].all()

    def test_a_label_over_open_water_is_left_alone(self):
        """"OCEAN ATLANTIQUE" has no zone around it, and filling it would
        invent land."""
        from app.utils.color_extraction import relabel_text_pixels

        best, valid, _box = self._scene()
        offshore = [(10, 105), (60, 105), (60, 118), (10, 118)]

        _best, filled, stats = relabel_text_pixels(best, valid, [offshore])

        assert stats["boxesFilled"] == 0
        assert not filled[105:118, 10:60].any()


class TestTextInpaint:
    """The ink of a label is erased from the image before classification.

    The case that motivated it: "TERRE-NEUVE" written across a small island,
    mostly over the sea. The label fill skips that box -- its ring is ocean,
    which is not a zone -- so the island stays hollow. Rebuilding the image
    lets each side of the coast come back as what surrounds it.
    """

    LAND = (0.85, 0.25, 0.25)
    SEA = (0.30, 0.65, 0.90)

    def _scene(self):
        """Land on the left, sea on the right, black strokes across the coast."""
        from app.utils.color_extraction import compute_lab

        rgb = np.zeros((120, 200, 3), dtype=np.float64)
        rgb[:, :100] = self.LAND
        rgb[:, 100:] = self.SEA
        for x in (70, 85, 110, 125):  # two strokes on land, two at sea
            rgb[50:70, x : x + 4] = 0.05
        rgb[58:62, 70:129] = 0.05  # a bar joining them across the coast
        box = [(62, 44), (136, 44), (136, 76), (62, 76)]
        lab = compute_lab(rgb)
        centers = compute_lab(np.array([[self.LAND]]))[0]
        return rgb, lab, centers, box

    def test_ink_on_land_becomes_land_and_ink_at_sea_becomes_sea(self):
        from app.utils.color_extraction import inpaint_text_ink

        rgb, lab, centers, box = self._scene()
        out, _lab, stats = inpaint_text_ink(rgb, lab, centers, [box])

        assert stats["boxesFilled"] == 1
        assert np.allclose(out[60, 72], self.LAND, atol=0.08)
        assert np.allclose(out[60, 112], self.SEA, atol=0.08)


class TestTextRepaintPalette:
    """Ink is what the ring around a box does not contain; it is repainted by
    a local vote among the ring's colours, never a blend."""

    RED = (0.85, 0.25, 0.25)
    DARK_RED = (0.45, 0.08, 0.08)
    SEA = (0.30, 0.65, 0.90)
    WHITE = (1.0, 1.0, 1.0)

    @staticmethod
    def _run(rgb, boxes, **kw):
        from app.utils.color_extraction import compute_lab, repaint_text_ink_palette

        return repaint_text_ink_palette(rgb, compute_lab(rgb), boxes, **kw)


    def test_a_letter_across_the_coast_is_split_not_blended(self):
        rgb = np.zeros((120, 200, 3))
        rgb[:, :100] = self.RED
        rgb[:, 100:] = self.SEA
        rgb[55:65, 70:130] = 0.05  # one bar straddling the coast
        box = [(62, 44), (138, 44), (138, 76), (62, 76)]

        out, _lab, _stats = self._run(rgb, [box])

        assert np.allclose(out[60, 75], self.RED, atol=0.05)
        assert np.allclose(out[60, 125], self.SEA, atol=0.05)
        # No violet anywhere along the bar: every repainted pixel is one of the two.
        bar = out[55:65, 70:130].reshape(-1, 3)
        near = np.minimum(
            np.abs(bar - self.RED).max(axis=1), np.abs(bar - self.SEA).max(axis=1)
        )
        assert (near < 0.05).all()


class TestSharedZoneBorders:
    """A border drawn between two zones matches neither colour. The zones grow
    into it at the same rate and meet mid-line, but only across a narrow gap
    between two *different* zones."""

    @staticmethod
    def _two_zones(gap_width):
        labels = np.full((60, 100), -1, dtype=np.int32)
        labels[:, :40] = 0
        labels[:, 40 + gap_width :] = 1
        return labels

    def test_a_drawn_border_is_closed_and_split_mid_line(self):
        from app.utils.color_extraction import fill_gaps_between_zones

        out, filled = fill_gaps_between_zones(self._two_zones(4), 2, max_gap_px=6)

        assert filled == 4 * 60
        assert (out >= 0).all()
        assert (out[:, 40:42] == 0).all() and (out[:, 42:44] == 1).all()


    def test_neighbouring_polygons_share_their_edge(self):
        """Pixel-edge polygons of adjacent zones touch with no gap and no
        overlap -- traced through pixel centres, they were a pixel apart."""
        from app.utils.color_extraction import mask_to_pixel_edge_geometry

        labels = self._two_zones(0)
        left = mask_to_pixel_edge_geometry(labels == 0)
        right = mask_to_pixel_edge_geometry(labels == 1)

        assert left.intersection(right).area == 0
        assert left.distance(right) == 0
        assert np.isclose(left.union(right).area, 60 * 100)

