"""Curve alignment after the piecewise correction (``post_align``).

A synthetic map: a wavy coastline drawn in pixel space, and control points
clicked 6 px to the left of where the truth puts them, so the piecewise model
fitted to them sits 6 px off the coast. Aligning again in front of it should
pull it back toward the coast.

No cv2: the user field is built by hand from the drawn curve.
"""

import numpy as np
from scipy.ndimage import distance_transform_edt

from app.utils.georeferencing import (
    DEFAULT_GEOREF_CONFIG,
    AffineModel,
    ControlPoint,
    fit_affine_from_control_points,
    fit_piecewise_from_control_points,
    georeference_features,
)
from app.utils.georeferencing.align import CurveSamples, UserField
from app.utils.georeferencing.post_align import (
    AlignmentContext,
    align_after_piecewise,
    compose,
)
from tests.georef_helpers import webmercator_to_lonlat

WIDTH, HEIGHT = 400, 300
IMAGE = (0.0, 0.0, float(WIDTH), float(HEIGHT))
SCALE_M_PER_PX = 1000.0
ORIGIN_3857 = (-8_900_000.0, 6_000_000.0)
CLICK_OFFSET_PX = 6.0


def _truth(x, y):
    return ORIGIN_3857[0] + x * SCALE_M_PER_PX, ORIGIN_3857[1] - y * SCALE_M_PER_PX


def _coast_px(step=0.5):
    x = np.arange(40.0, 360.0, step)
    return x, 150.0 + 40.0 * np.sin(x / 30.0)


def _control_points():
    pixels = [(60, 60), (340, 70), (200, 150), (80, 250), (330, 240), (210, 40)]
    points = []
    for x, y in pixels:
        # Clicked to the left of the truth: the fit inherits the offset.
        X, Y = _truth(x + CLICK_OFFSET_PX, y)
        points.append(ControlPoint.sift((x, y), webmercator_to_lonlat(X, Y)))
    return points


def _context():
    x, y = _coast_px()
    edge = np.zeros((HEIGHT, WIDTH), dtype=bool)
    edge[np.round(y).astype(int), np.round(x).astype(int)] = True
    field = UserField(
        distance_px=distance_transform_edt(~edge),
        orientation=np.zeros((HEIGHT, WIDTH)),
        edge=edge,
        validity=np.ones((HEIGHT, WIDTH)),
        height=HEIGHT,
        width=WIDTH,
    )
    sx, sy = _coast_px(step=2.0)
    X, Y = _truth(sx, sy)
    xy = np.column_stack([X, Y])
    samples = CurveSamples(xy=xy, xy_normal=xy + np.array([0.0, SCALE_M_PER_PX]))
    return AlignmentContext(coast_samples=samples, fine_samples=samples, user_field=field)


CONFIG = DEFAULT_GEOREF_CONFIG.with_overrides(enable_icp=False, weight_curve=10.0)


def _piecewise():
    return fit_piecewise_from_control_points(
        _control_points(), extent=IMAGE, influence_radius_px=0.175 * np.hypot(WIDTH, HEIGHT)
    )


class TestCompose:
    def test_is_the_model_applied_after_the_affine(self):
        model = _piecewise()
        front = AffineModel(
            matrix=np.array([[1.01, 0.02, -4.0], [-0.01, 0.99, 3.0], [0.0, 0.0, 1.0]])
        )
        composed = compose(model, front)

        x = np.array([10.0, 120.0, 250.0, 390.0, -500.0])
        y = np.array([15.0, 200.0, 90.0, 290.0, 800.0])
        fx, fy = front(x, y)
        assert np.allclose(composed(x, y), model(fx, fy))

    def test_inverts_exactly(self):
        composed = compose(
            _piecewise(),
            AffineModel(matrix=np.array([[1.0, 0.0, -5.0], [0.0, 1.0, 2.0], [0, 0, 1.0]])),
        )
        x, y = np.array([30.0, 200.0, 370.0]), np.array([40.0, 150.0, 280.0])
        assert np.allclose(composed.inverse()(*composed(x, y)), (x, y))


class TestAlignAfterPiecewise:
    def test_pulls_the_map_back_onto_the_coast(self):
        model = _piecewise()
        record_errors = {}

        class _Record:
            def set_errors(self, **kwargs):
                record_errors.update(kwargs)

        aligned = align_after_piecewise(
            model, _control_points(), _context(), CONFIG, record=_Record()
        )

        stats = record_errors["postAlignment"]
        assert stats["applied"] is True
        assert stats["chamferAfterPx"] < stats["chamferBeforePx"]
        # Where a coast pixel lands, against where the truth puts it.
        x, y = _coast_px(step=20.0)
        before = np.hypot(*(np.subtract(model(x, y), _truth(x, y))))
        after = np.hypot(*(np.subtract(aligned(x, y), _truth(x, y))))
        assert after.mean() < before.mean()
        assert aligned.residuals_kind == "in_sample"

    def test_aligns_an_affine_too(self):
        affine = fit_affine_from_control_points(_control_points())
        record_errors = {}

        class _Record:
            def set_errors(self, **kwargs):
                record_errors.update(kwargs)

        aligned = align_after_piecewise(
            affine, _control_points(), _context(), CONFIG, record=_Record()
        )

        stats = record_errors["postAlignment"]
        assert stats["applied"] is True and stats["onModel"] == "affine"
        assert aligned.name == "affine"
        x, y = _coast_px(step=20.0)
        before = np.hypot(*(np.subtract(affine(x, y), _truth(x, y))))
        after = np.hypot(*(np.subtract(aligned(x, y), _truth(x, y))))
        assert after.mean() < before.mean()

    def test_keeps_the_model_without_evidence(self):
        model = _piecewise()
        empty = CurveSamples(xy=np.zeros((0, 2)), xy_normal=np.zeros((0, 2)))
        context = _context()
        context = AlignmentContext(
            coast_samples=empty, fine_samples=empty, user_field=context.user_field
        )
        assert align_after_piecewise(model, _control_points(), context, CONFIG) is model


class TestThroughThePipeline:
    FRAME = {"west": -82.0, "south": 44.0, "east": -72.0, "north": 50.0}
    ZONE = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[100, 100], [300, 110], [290, 250], [100, 100]]],
                },
            }
        ],
    }

    def _run(self, refine, model=None, control_points=None, **overrides):
        config = DEFAULT_GEOREF_CONFIG.with_overrides(
            snap_to_coastline=False,
            clip_to_land_mask=False,
            align_after_piecewise=True,
            **overrides,
        )
        return georeference_features(
            [self.ZONE],
            control_points or _control_points(),
            frame_bounds=self.FRAME,
            image_size=(WIDTH, HEIGHT),
            config=config,
            model=model,
            refine_piecewise=refine,
        )

    @staticmethod
    def _recording():
        calls = []

        def refine(model, record):
            calls.append(model.name)
            return model

        return calls, refine

    def test_refines_the_piecewise_model(self):
        calls, refine = self._recording()
        self._run(refine, transform_model="piecewise_affine")
        assert calls == ["piecewise_affine"]

    def test_aligns_the_gcp_affine_when_the_correction_is_refused(self):
        """Without it, piecewise -> align with a refused correction would ship
        the GCP-only affine, never aligned (Maghreb clustered, 2026-10-08)."""
        cps = _control_points()
        cps.append(cps[0])  # duplicate: the correction cannot be built
        calls, refine = self._recording()

        result = self._run(refine, control_points=cps, transform_model="piecewise_affine")

        assert result.record.to_dict()["errors"]["piecewiseApplied"] is False
        assert calls == ["affine"]

    def test_leaves_an_aligned_affine_alone(self):
        calls, refine = self._recording()
        aligned = AffineModel(
            matrix=np.array([[1000.0, 0.0, ORIGIN_3857[0]], [0.0, -1000.0, ORIGIN_3857[1]], [0, 0, 1.0]])
        )
        result = self._run(refine, model=aligned, transform_model="affine")

        assert calls == []
        stats = result.record.to_dict()["errors"]["postAlignment"]
        assert stats == {"applied": False, "skippedBecause": "no piecewise model, already aligned"}

    def test_says_when_it_has_no_inputs(self):
        result = self._run(None, transform_model="piecewise_affine")
        stats = result.record.to_dict()["errors"]["postAlignment"]
        assert stats == {"applied": False, "skippedBecause": "no alignment inputs"}

    def test_is_on_by_default(self):
        """B7b (config v19)."""
        assert DEFAULT_GEOREF_CONFIG.align_after_piecewise is True
        assert DEFAULT_GEOREF_CONFIG.weight_curve == 10.0
