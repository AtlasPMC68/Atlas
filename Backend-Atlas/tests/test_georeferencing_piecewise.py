"""The piecewise-affine model and its use from the pipeline.

The properties worth pinning down are the ones that motivated the design: it
interpolates the control points, it stops being anything but the affine away
from them, it is continuous across triangle edges (the seam worry), and it
refuses inputs that would fold the map.

No cv2 and no Celery here, like the rest of the georeferencing unit tests.
"""

import numpy as np
import pytest

from app.utils.georeferencing import (
    DEFAULT_GEOREF_CONFIG,
    ControlPoint,
    PiecewiseAffineModel,
    fit_piecewise_from_control_points,
    georeference_features,
)
from app.utils.georeferencing.projection import lonlat_to_webmercator
from tests.georef_helpers import webmercator_to_lonlat

IMAGE = (0.0, 0.0, 600.0, 400.0)

# The truth is built in EPSG:3857 rather than in lon/lat, because that is the
# space the models fit in: northing is not linear in latitude, so a map that
# looks linear in degrees is *not* affine here and the correction would have
# real Mercator curvature to chew on, which is not what these tests are about.
SCALE_M_PER_PX = 1000.0
ORIGIN_3857 = (-8_900_000.0, 6_000_000.0)


def _target_3857(x, y, dx=0.0, dy=0.0):
    return (
        ORIGIN_3857[0] + (x + dx) * SCALE_M_PER_PX,
        ORIGIN_3857[1] - (y + dy) * SCALE_M_PER_PX,
    )


def _control_points(offsets=None):
    """Six points on a map an affine fits exactly, optionally nudged off it.

    `offsets` displaces a point in pixel-equivalents of 3857 metres, which is
    what gives the local correction something to do.
    """
    pixels = [
        (100.0, 100.0),
        (500.0, 120.0),
        (300.0, 200.0),
        (150.0, 320.0),
        (480.0, 300.0),
        (320.0, 60.0),
    ]
    points = []
    for i, (x, y) in enumerate(pixels):
        dx, dy = (offsets or {}).get(i, (0.0, 0.0))
        X, Y = _target_3857(x, y, dx, dy)
        points.append(ControlPoint.sift((x, y), webmercator_to_lonlat(X, Y)))
    return points


def _expected_3857(cp):
    return np.array(lonlat_to_webmercator(cp.geo[0], cp.geo[1]))


class TestInterpolationAndFallback:
    def test_hits_every_local_control_point_exactly(self):
        cps = _control_points({1: (14.0, -9.0), 3: (-11.0, 6.0)})
        model = fit_piecewise_from_control_points(cps, extent=IMAGE)

        for cp in cps:
            X, Y = model(cp.pixel[0], cp.pixel[1])
            assert np.allclose([X, Y], _expected_3857(cp), atol=1e-6)

    def test_is_the_plain_affine_outside_the_frame(self):
        cps = _control_points({2: (20.0, 20.0)})
        model = fit_piecewise_from_control_points(cps, extent=IMAGE)

        # Well outside the padded frame, so nothing extrapolates: this is the
        # failure that made the original TPS unusable.
        far_x, far_y = np.array([-5000.0, 9000.0]), np.array([-4000.0, 7000.0])
        assert np.allclose(model(far_x, far_y), model.base(far_x, far_y))


class TestContinuity:
    def test_no_seam_across_a_shared_triangle_edge(self):
        """The whole point of sharing vertices: approaching an edge from either
        side gives the same position, so zones are never cut apart."""
        cps = _control_points({0: (18.0, -12.0), 4: (-15.0, 9.0)})
        model = fit_piecewise_from_control_points(cps, extent=IMAGE)

        # Midpoint of an interior edge of the triangulation, approached from
        # both sides along the edge normal.
        a, b = model.verts_in[0], model.verts_in[2]
        mid = (a + b) / 2.0
        edge = b - a
        normal = np.array([-edge[1], edge[0]])
        normal = normal / np.hypot(*normal)

        eps = 1e-4
        left = model(*(mid + normal * eps))
        right = model(*(mid - normal * eps))
        assert np.allclose(left, right, atol=1e-3)


class TestRefusals:
    def test_a_folding_point_set_is_rejected(self):
        """Two points whose geo positions swap relative order fold the map:
        the mapping stops being one-to-one and the inverse is ambiguous."""
        cps = _control_points()
        swapped = list(cps)
        swapped[2] = ControlPoint.sift(cps[2].pixel, cps[4].geo)
        swapped[4] = ControlPoint.sift(cps[4].pixel, cps[2].geo)
        with pytest.raises(ValueError, match="fold the map"):
            fit_piecewise_from_control_points(swapped, extent=IMAGE)


class TestThroughThePipeline:
    """What a run actually goes through: the model chosen in the config."""

    FRAME = {"west": -82.0, "south": 44.0, "east": -72.0, "north": 50.0}

    @staticmethod
    def _zone(ring):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                }
            ],
        }

    def _run(self, cps, zone, transform_model="piecewise_affine"):
        config = DEFAULT_GEOREF_CONFIG.with_overrides(
            snap_to_coastline=False, clip_to_land_mask=False, transform_model=transform_model
        )
        return georeference_features(
            [zone], cps, frame_bounds=self.FRAME, image_size=(600, 400), config=config
        )

    def test_a_refused_correction_falls_back_instead_of_failing_the_run(self):
        cps = _control_points()
        cps.append(cps[0])  # duplicate: the correction cannot be built
        zone = self._zone([[120.0, 120.0], [460.0, 130.0], [450.0, 300.0], [120.0, 120.0]])

        result = self._run(cps, zone)

        assert result.model.name == "affine"
        errors = result.record.to_dict()["errors"]
        assert errors["piecewiseApplied"] is False
        assert "Duplicate" in errors["piecewiseRefusedBecause"]
        assert result.collections[0]["features"]

    def test_leave_one_out_refits_the_affine_for_every_fold(self):
        """The held-out point must not shape the affine it is measured against
        (the 2026-09-30 fix 3, dev-docs/georeferencing-history.md)."""
        cps = _control_points({1: (15.0, 10.0), 4: (-9.0, 12.0)})
        zone = self._zone([[120.0, 120.0], [460.0, 130.0], [450.0, 300.0], [120.0, 120.0]])
        result = self._run(cps, zone)

        src = np.array([cp.pixel for cp in cps], dtype=float)
        dst = np.array([_expected_3857(cp) for cp in cps], dtype=float)
        # No base handed in: every fold refits the affine without its point.
        honest = PiecewiseAffineModel.fit(
            src,
            dst,
            extent=IMAGE,
            anchor_margin=DEFAULT_GEOREF_CONFIG.piecewise_anchor_margin,
        )

        assert result.model.residuals_kind == "leave_one_out"
        assert np.allclose(result.model.residuals_3857, honest.residuals_3857)
        assert result.record.to_dict()["errors"]["gcpRmseKind"] == "leave_one_out"

    def test_long_edges_are_densified_before_a_piecewise_warp(self):
        cps = _control_points({2: (20.0, 15.0)})
        triangle = self._zone([[60.0, 60.0], [560.0, 70.0], [300.0, 380.0], [60.0, 60.0]])

        piecewise = self._run(cps, triangle)
        affine = self._run(cps, triangle, transform_model="affine")

        def vertex_count(result):
            geometry = result.collections[0]["features"][0]["geometry"]
            return len(geometry["coordinates"][0])

        assert vertex_count(affine) == 4
        assert vertex_count(piecewise) > 100
        assert piecewise.record.to_dict()["inputs"]["densifyStepPx"] > 0
