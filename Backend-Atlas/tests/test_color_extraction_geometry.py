"""Turning a colour mask into polygons, holes included."""

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

