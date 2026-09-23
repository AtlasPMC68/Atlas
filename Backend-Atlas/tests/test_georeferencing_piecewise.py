"""Unit tests for the piecewise-affine model and its use from the pipeline.

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
    AffineModel,
    ControlPoint,
    PiecewiseAffineModel,
    deserialize_model,
    fit_piecewise_from_control_points,
    georeference_features,
)
from app.utils.georeferencing.projection import (
    lonlat_to_webmercator,
    webmercator_to_lonlat,
)

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
        points.append(
            ControlPoint.make(
                pixel=(x, y), geo=webmercator_to_lonlat(X, Y), source="sift"
            )
        )
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

    def test_a_perfect_affine_map_is_left_alone(self):
        """No local distortion means no correction anywhere."""
        model = fit_piecewise_from_control_points(_control_points(), extent=IMAGE)

        grid_x, grid_y = np.meshgrid(np.linspace(0, 600, 13), np.linspace(0, 400, 9))
        # Millimetres, in metre units: what is left is the lon/lat round trip.
        assert np.allclose(
            model(grid_x, grid_y), model.base(grid_x, grid_y), atol=1e-3
        )
        assert float(model.corrections_3857.max()) < 1e-3

    def test_a_city_point_shapes_the_affine_but_does_not_pin_the_correction(self):
        """Interpolating exactly through a city would import the map's own
        error at that city into its whole neighbourhood."""
        cps = _control_points()
        # A city the map draws 30 km east and 20 km north of where it is.
        city_target = _target_3857(250.0, 250.0, 30.0, -20.0)
        cps.append(
            ControlPoint.make(
                pixel=(250.0, 250.0),
                geo=webmercator_to_lonlat(*city_target),
                source="city",
            )
        )
        model = fit_piecewise_from_control_points(cps, extent=IMAGE)

        assert model.n_local_points == 6
        X, Y = model(250.0, 250.0)
        # Not pinned to the city's own (wrong) position.
        assert np.hypot(X - city_target[0], Y - city_target[1]) > 5_000.0


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

    def test_inverse_round_trips(self):
        cps = _control_points({1: (12.0, 8.0)})
        model = fit_piecewise_from_control_points(cps, extent=IMAGE)
        inverse = model.inverse()

        x = np.array([120.0, 310.0, 455.0])
        y = np.array([140.0, 210.0, 295.0])
        back_x, back_y = inverse(*model(x, y))
        assert np.allclose(back_x, x, atol=1e-6)
        assert np.allclose(back_y, y, atol=1e-6)


class TestRefusals:
    def test_duplicate_control_points_are_rejected(self):
        cps = _control_points()
        cps.append(cps[0])
        with pytest.raises(ValueError, match="Duplicate control point"):
            fit_piecewise_from_control_points(cps, extent=IMAGE)

    def test_a_folding_point_set_is_rejected(self):
        """Two points whose geo positions swap relative order fold the map:
        the mapping stops being one-to-one and the inverse is ambiguous."""
        cps = _control_points()
        swapped = list(cps)
        swapped[2] = ControlPoint.make(
            pixel=cps[2].pixel, geo=cps[4].geo, source="sift"
        )
        swapped[4] = ControlPoint.make(
            pixel=cps[4].pixel, geo=cps[2].geo, source="sift"
        )
        with pytest.raises(ValueError, match="fold the map"):
            fit_piecewise_from_control_points(swapped, extent=IMAGE)


class TestErrorReporting:
    def test_reported_error_is_leave_one_out_not_the_zero_residual(self):
        cps = _control_points({3: (25.0, -18.0)})
        model = fit_piecewise_from_control_points(cps, extent=IMAGE)

        # In-sample, every local point is hit exactly, so a residual-based
        # number would say 0 and mean nothing.
        in_sample = model._residual_distances(
            np.array([cp.pixel for cp in cps], dtype=float),
            np.array([_expected_3857(cp) for cp in cps], dtype=float),
        )
        assert float(np.max(in_sample)) < 1e-6

        assert model.residuals_are_loo
        assert model.rmse_3857 is not None and model.rmse_3857 > 0.0

    def test_serialization_round_trips_through_the_dispatcher(self):
        cps = _control_points({0: (9.0, 4.0)})
        model = fit_piecewise_from_control_points(cps, extent=IMAGE)
        payload = model.serialize()

        restored = deserialize_model(payload)
        assert isinstance(restored, PiecewiseAffineModel)
        x = np.array([133.0, 420.0])
        y = np.array([175.0, 260.0])
        assert np.allclose(restored(x, y), model(x, y))
        assert payload["rmse3857Kind"] == "leave_one_out"

        # The same dispatcher must still return a plain affine for an affine.
        assert isinstance(
            deserialize_model(AffineModel.fit(
                np.array([cp.pixel for cp in cps], dtype=float),
                np.array([_expected_3857(cp) for cp in cps], dtype=float),
            ).serialize()),
            AffineModel,
        )


class TestPipelineIntegration:
    """The switch at the fit site, which is what a run actually goes through."""

    @staticmethod
    def _zone():
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[120.0, 120.0], [460.0, 130.0], [450.0, 300.0],
                             [140.0, 290.0], [120.0, 120.0]]
                        ],
                    },
                }
            ],
        }

    @staticmethod
    def _config(**overrides):
        return DEFAULT_GEOREF_CONFIG.with_overrides(
            snap_to_coastline=False, clip_to_land_mask=False, **overrides
        )

    def test_every_registered_model_can_actually_be_built(self):
        """A name offered in the dropdown that the pipeline cannot build would
        place the map with the baseline and say nothing about it."""
        from app.utils.georeferencing.config import TRANSFORM_MODELS

        cps = _control_points({1: (15.0, 10.0)})
        for name in TRANSFORM_MODELS:
            result = georeference_features(
                [self._zone()], cps, config=self._config(transform_model=name)
            )
            assert result.model.name == name

    def test_an_unknown_model_fails_loudly(self):
        with pytest.raises(ValueError, match="Unknown transform_model"):
            georeference_features(
                [self._zone()],
                _control_points(),
                config=self._config(transform_model="ffd_8x8"),
            )

    def test_off_by_default_keeps_the_affine(self):
        result = georeference_features(
            [self._zone()], _control_points({1: (15.0, 10.0)}), config=self._config()
        )
        assert result.model.name == "affine"
        feature = result.collections[0]["features"][0]
        assert feature["properties"]["transform_method"] == "affine"

    def test_switching_it_on_corrects_the_affine(self):
        cps = _control_points({1: (15.0, 10.0), 3: (-12.0, 7.0)})
        config = self._config(transform_model="piecewise_affine")
        result = georeference_features([self._zone()], cps, config=config)

        assert result.model.name == "piecewise_affine"
        assert result.record.to_dict()["errors"]["piecewiseApplied"] is True
        for cp in cps:
            X, Y = result.model(cp.pixel[0], cp.pixel[1])
            assert np.allclose([X, Y], _expected_3857(cp), atol=1e-6)

    def test_a_refused_correction_falls_back_instead_of_failing_the_run(self):
        cps = _control_points()
        cps.append(cps[0])  # duplicate: the correction cannot be built
        config = self._config(transform_model="piecewise_affine")

        result = georeference_features([self._zone()], cps, config=config)

        assert result.model.name == "affine"
        errors = result.record.to_dict()["errors"]
        assert errors["piecewiseApplied"] is False
        assert "Duplicate" in errors["piecewiseRefusedBecause"]
        assert result.collections[0]["features"]

    def test_it_corrects_a_model_handed_in_by_step_4(self):
        """Alignment's affine is a better base than the GCP-only one, so the
        correction has to apply on top of it rather than be skipped."""
        cps = _control_points({2: (16.0, -9.0)})
        src = np.array([cp.pixel for cp in cps], dtype=float)
        dst = np.array([_expected_3857(cp) for cp in cps], dtype=float)
        aligned = AffineModel.fit(src, dst)

        result = georeference_features(
            [self._zone()],
            cps,
            config=self._config(transform_model="piecewise_affine"),
            model=aligned,
        )

        assert result.model.name == "piecewise_affine"
        assert result.model.base is aligned

    def test_residuals_reach_the_record_as_json_safe_values(self):
        """A leave-one-out pass reports NaN when a refit was impossible, and
        NaN is not valid JSON for whoever reads the run record."""
        import json

        cps = _control_points({4: (13.0, 11.0)})
        result = georeference_features(
            [self._zone()], cps, config=self._config(transform_model="piecewise_affine")
        )

        payload = result.record.to_dict()
        json.dumps(payload, allow_nan=False)
        residuals = payload["errors"]["gcpResiduals3857"]
        assert len(residuals) == len(cps)
        assert all(r is None or isinstance(r, float) for r in residuals)


class TestControlPointDiagnostics:
    """The 'which click is wrong' answer, which drives the point picker."""

    @staticmethod
    def _grid(offsets=None):
        """Twelve points on an exact map, so one outlier stands out.

        Six points are too few for this: an affine fitted to five clean points
        plus one bad one is dragged proportionally, so the outlier's held-out
        error and its neighbours' grow together and the ratio never moves.
        Twelve dilutes the bad point enough for the comparison to mean
        something -- which is also true of a real case.
        """
        pixels = [
            (x, y) for y in (60.0, 180.0, 300.0) for x in (80.0, 220.0, 360.0, 500.0)
        ]
        points = []
        for i, (x, y) in enumerate(pixels):
            dx, dy = (offsets or {}).get(i, (0.0, 0.0))
            X, Y = _target_3857(x, y, dx, dy)
            points.append(
                ControlPoint.make(
                    pixel=(x, y), geo=webmercator_to_lonlat(X, Y), source="sift"
                )
            )
        return points

    @staticmethod
    def _diag(cps):
        from app.utils.georeferencing.diagnostics import control_point_diagnostics

        return control_point_diagnostics(cps)

    def test_leave_one_out_finds_the_bad_click(self):
        result = self._diag(self._grid({5: (80.0, -60.0)}))

        assert result["summary"]["looAvailable"] is True
        assert result["summary"]["suspectIndices"] == [5]
        worst = max(result["points"], key=lambda p: p["looKm"] or 0)
        assert worst["index"] == 5

    def test_in_sample_error_spreads_the_blame_but_loo_does_not(self):
        """Why the picker shows leave-one-out and not the fit's residual."""
        points = self._diag(self._grid({5: (80.0, -60.0)}))["points"]
        innocent = [p for p in points if p["index"] != 5]

        # The affine pushes the bad point's error onto every other point...
        assert all(p["inSampleKm"] > 1.0 for p in innocent)
        # ...while held out, the honest points are still placed well.
        assert max(p["looKm"] for p in innocent) < points[5]["looKm"] / 2

    def test_a_clean_set_has_no_suspects(self):
        """Twice a near-zero median is still near zero, so the ratio alone
        would flag floating-point noise on a perfectly clicked map."""
        result = self._diag(self._grid())

        assert result["summary"]["suspectIndices"] == []
        assert max(p["looKm"] for p in result["points"]) < 1.0
        assert max(p["looPx"] for p in result["points"]) < 1.0

    def test_a_point_off_by_less_than_a_click_is_not_suspect(self):
        """5 px is inside a sift point's own 6 px sigma."""
        result = self._diag(self._grid({5: (5.0, 0.0)}))

        assert result["summary"]["suspectIndices"] == []

    def test_three_points_report_no_leave_one_out(self):
        """Dropping one of three leaves an exact fit, so held-out error would
        be measured against a model with no freedom left."""
        result = self._diag(_control_points()[:3])

        assert result["summary"]["looAvailable"] is False
        assert all(p["looKm"] is None for p in result["points"])


class TestExcludingControlPoints:
    """Leaving a point out of a run without touching the stored case."""

    @staticmethod
    def _kwargs():
        return {
            "pixel_points": [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0)],
            "geo_points_lonlat": [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0)],
        }

    def test_drops_the_named_points_from_both_arrays(self):
        from app.utils.dev_test import drop_control_points

        kwargs = self._kwargs()
        assert drop_control_points(kwargs, [1]) == [1]
        assert kwargs["pixel_points"] == [(0.0, 0.0), (2.0, 2.0), (3.0, 3.0)]
        # The pairing is the whole point: both arrays must lose the same index.
        assert kwargs["geo_points_lonlat"] == [(0.0, 0.0), (2.0, 2.0), (3.0, 3.0)]

    def test_refuses_to_leave_fewer_than_three(self):
        from app.utils.dev_test import drop_control_points

        with pytest.raises(ValueError, match="fewer than the 3"):
            drop_control_points(self._kwargs(), [0, 1])

    def test_ignores_indices_that_no_longer_exist(self):
        """A page open while the case was re-clicked must not fail the run."""
        from app.utils.dev_test import drop_control_points

        kwargs = self._kwargs()
        assert drop_control_points(kwargs, [99]) == []
        assert len(kwargs["pixel_points"]) == 4


class TestLastRunModelReporting:
    """The panel's kilometres must describe the run that produced the map."""

    @staticmethod
    def _diag(cps, **kwargs):
        from app.utils.georeferencing.diagnostics import control_point_diagnostics

        return control_point_diagnostics(cps, **kwargs)

    def test_applied_error_uses_the_model_that_ran(self):
        cps = _control_points({1: (20.0, 0.0)})
        piecewise = fit_piecewise_from_control_points(cps, extent=IMAGE)

        result = self._diag(cps, applied_model=piecewise)

        assert result["summary"]["appliedModel"] == "piecewise_affine"
        # Piecewise interpolates its local points, so it places them exactly.
        # Reporting that as accuracy is the trap; the panel shows it next to
        # the leave-one-out number precisely so the two can be compared.
        assert max(p["appliedKm"] for p in result["points"]) < 0.1
        assert result["summary"]["affineLooRmseKm"] > 0.0

    def test_points_excluded_from_the_run_stay_out_of_its_rmse(self):
        """Otherwise the panel reports an error the run never had -- exactly
        when the picker is being used to improve it."""
        cps = _control_points({4: (120.0, -90.0)})
        kept = [cp for i, cp in enumerate(cps) if i != 4]
        model = AffineModel.fit(
            np.array([cp.pixel for cp in kept], dtype=float),
            np.array([_expected_3857(cp) for cp in kept], dtype=float),
        )

        result = self._diag(
            cps,
            applied_model=model,
            applied_pixels=[cp.pixel for cp in kept],
        )

        assert result["summary"]["excludedFromLastRun"] == [4]
        assert result["summary"]["appliedPointCount"] == 5
        assert result["points"][4]["usedInLastRun"] is False
        # The excluded point still reports how far off it is: that is the
        # number that says whether to bring it back.
        assert result["points"][4]["appliedKm"] > 10.0
        assert result["summary"]["appliedRmseKm"] < 1.0
