"""The piecewise-affine model and its use from the pipeline."""

import numpy as np
import pytest

from app.utils.georeferencing import (
    DEFAULT_GEOREF_CONFIG,
    ControlPoint,
    PiecewiseAffineModel,
    fit_piecewise_from_control_points,
    georeference_features,
)
from app.utils.georeferencing.config import TRANSFORM_MODELS
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


class TestLocalRegularization:
    """``local``: a correction fades out within the radius of its point."""

    RADIUS_PX = 100.0

    @staticmethod
    def _left_points():
        # (100, 100), (300, 200), (150, 320), (320, 60): nothing on the right
        # third of the image, and two of them nudged so there is a correction.
        cps = _control_points({2: (20.0, -15.0), 3: (-18.0, 12.0)})
        return [cps[i] for i in (0, 2, 3, 5)]

    def test_still_hits_every_control_point_exactly(self):
        cps = self._left_points()
        model = fit_piecewise_from_control_points(
            cps, extent=IMAGE, influence_radius_px=self.RADIUS_PX
        )

        for cp in cps:
            X, Y = model(cp.pixel[0], cp.pixel[1])
            assert np.allclose([X, Y], _expected_3857(cp), atol=1e-6)

    def test_a_region_without_a_point_keeps_the_base(self):
        cps = self._left_points()
        far = (np.array([560.0]), np.array([250.0]))  # ~265 px from the nearest

        plain = fit_piecewise_from_control_points(cps, extent=IMAGE)
        local = fit_piecewise_from_control_points(
            cps, extent=IMAGE, influence_radius_px=self.RADIUS_PX
        )

        # Without the regularization the corrections of the points on the left
        # reach this far; with it, the region is placed by the affine alone.
        assert not np.allclose(plain(*far), plain.base(*far))
        assert np.allclose(local(*far), local.base(*far))

    def test_no_anchor_lands_within_the_radius_of_a_point(self):
        cps = self._left_points()
        model = fit_piecewise_from_control_points(
            cps, extent=IMAGE, influence_radius_px=self.RADIUS_PX
        )

        src = np.array([cp.pixel for cp in cps])
        extra = model.verts_in[len(cps) + 8 :]  # after the points and the frame
        assert len(extra) > 0
        gaps = np.hypot(extra[:, None, 0] - src[:, 0], extra[:, None, 1] - src[:, 1])
        assert gaps.min() >= self.RADIUS_PX

    def test_none_adds_no_anchors(self):
        cps = self._left_points()
        model = fit_piecewise_from_control_points(cps, extent=IMAGE)
        assert len(model.verts_in) == len(cps) + 8

    def test_through_the_pipeline(self):
        config = DEFAULT_GEOREF_CONFIG.with_overrides(
            snap_to_coastline=False,
            clip_to_land_mask=False,
            transform_model="piecewise_affine",
            piecewise_regularization="local",
        )
        zone = TestThroughThePipeline._zone(
            [[120.0, 120.0], [460.0, 130.0], [450.0, 300.0], [120.0, 120.0]]
        )
        result = georeference_features(
            [zone],
            self._left_points(),
            frame_bounds=TestThroughThePipeline.FRAME,
            image_size=(600, 400),
            config=config,
        )

        errors = result.record.to_dict()["errors"]
        assert errors["piecewiseApplied"] is True
        assert errors["piecewiseRegularization"] == "local"
        assert errors["piecewiseInfluenceRadiusPx"] == pytest.approx(
            DEFAULT_GEOREF_CONFIG.piecewise_influence_radius_ratio_of_diagonal
            * np.hypot(600.0, 400.0)
        )
        assert result.model.residuals_kind == "leave_one_out"

    def test_is_the_default(self):
        """B7b's correction (config v19)."""
        assert DEFAULT_GEOREF_CONFIG.piecewise_regularization == "local"
        assert DEFAULT_GEOREF_CONFIG.piecewise_influence_radius_ratio_of_diagonal == 0.175


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
        # The unregularised model: these tests are about the correction itself.
        config = DEFAULT_GEOREF_CONFIG.with_overrides(
            snap_to_coastline=False,
            clip_to_land_mask=False,
            transform_model=transform_model,
            piecewise_regularization="none",
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


class TestAutoTransformModel:
    """``auto``: the affine unless its GCP misfit is over the threshold."""

    ZONE = TestThroughThePipeline._zone(
        [[120.0, 120.0], [460.0, 130.0], [450.0, 300.0], [120.0, 120.0]]
    )

    def _run(self, cps, ratio=None):
        config = DEFAULT_GEOREF_CONFIG.with_overrides(
            snap_to_coastline=False,
            clip_to_land_mask=False,
            transform_model="auto",
            auto_piecewise_rmse_ratio_of_diagonal=ratio,
        )
        return georeference_features(
            [self.ZONE],
            cps,
            frame_bounds=TestThroughThePipeline.FRAME,
            image_size=(600, 400),
            config=config,
        )

    def test_is_an_option_not_the_default(self):
        """B7b applies the correction on every map; ``auto`` stays selectable."""
        assert DEFAULT_GEOREF_CONFIG.transform_model == "piecewise_affine"
        assert "auto" in TRANSFORM_MODELS

    def test_keeps_the_affine_when_it_fits(self):
        result = self._run(_control_points())

        assert result.model.name == "affine"
        errors = result.record.to_dict()["errors"]
        assert errors["autoChoseModel"] == "affine"
        assert errors["autoAffineRmsePx"] == pytest.approx(0.0, abs=1e-6)
        assert "piecewiseApplied" not in errors

    def test_switches_to_piecewise_over_the_threshold(self):
        cps = _control_points({1: (15.0, 10.0), 4: (-9.0, 12.0)})
        # ~0.7 px: well under the few pixels these offsets leave.
        result = self._run(cps, ratio=0.001)

        errors = result.record.to_dict()["errors"]
        assert errors["autoAffineRmsePx"] > errors["autoThresholdPx"]
        assert result.model.name == "piecewise_affine"
        assert errors["autoChoseModel"] == "piecewise_affine"

    def test_threshold_scales_with_the_image_diagonal(self):
        result = self._run(_control_points(), ratio=0.02)
        # 600 x 400 -> diagonal ~721 px.
        assert result.record.to_dict()["errors"]["autoThresholdPx"] == pytest.approx(
            0.02 * np.hypot(600.0, 400.0)
        )

    def test_a_raised_threshold_keeps_the_affine(self):
        cps = _control_points({1: (15.0, 10.0), 4: (-9.0, 12.0)})
        assert self._run(cps, ratio=1.0).model.name == "affine"

    def test_three_points_keep_the_affine(self):
        """An exact fit is no evidence of distortion, so it never switches."""
        result = self._run(_control_points({1: (15.0, 10.0)})[:3], ratio=1e-9)

        assert result.model.name == "affine"
        errors = result.record.to_dict()["errors"]
        assert errors["autoAffineRmsePx"] is None
        assert errors["autoChoseModel"] == "affine"
