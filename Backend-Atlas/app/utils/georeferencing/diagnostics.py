"""Per-control-point error, for deciding which clicks to keep.

A control point's *in-sample* residual is the wrong number to judge it by: an
affine spreads one bad click across all of them, so a mis-matched point both
hides itself and blames its neighbours. Leave-one-out asks the question that
actually matters -- "with this point excluded, how far off does the fit place
it?" -- and it is cheap here, because n is the number of clicks a human made.

This runs no pipeline: no OCR, no colour extraction, no reference rasters. It
is meant to answer "which of my points is wrong" in the time it takes to draw
a list, rather than in the two minutes a re-run costs.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .frame import FrameBounds
from .models import AffineModel, ControlPoint
from .projection import (
    lonlat_to_webmercator,
    reference_latitude,
    webmercator_meters_to_km,
)

logger = logging.getLogger(__name__)

#: A point whose leave-one-out error exceeds this multiple of the median is
#: called out as suspect. Relative, not absolute: what counts as far depends on
#: the map's scale, and a schematic map is wrong everywhere by tens of km.
SUSPECT_RATIO = 2.0

#: ...but the ratio alone flags noise when every point is good: on a cleanly
#: clicked map the median held-out error is near zero, and twice near-zero is
#: still near zero. So a suspect must also miss by more than clicking can
#: explain. In *image pixels*, because that is where the mistake was made --
#: a sift point carries sigma 6 px (``models.DEFAULT_SIGMA_PX_BY_SOURCE``), so
#: this is about 2.5 sigma.
SUSPECT_MIN_PX = 15.0


def _km(value: Optional[float], ref_lat: Optional[float]) -> Optional[float]:
    """EPSG:3857 metres to ground km, or None when neither is knowable."""
    if value is None or not np.isfinite(value) or ref_lat is None:
        return None
    return round(webmercator_meters_to_km(float(value), ref_lat), 1)


def load_last_run_model(record_path: str) -> Optional[Any]:
    """The transform a case's last run actually used, or None.

    Read from the run record rather than refitted, so a piecewise run reports
    the piecewise placement -- including the Step 4 alignment baked into it,
    which cannot be reproduced here because it needs the image.
    """
    try:
        with open(record_path, "r", encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None

    return _model_from_record(record)


def load_last_run_control_pixels(record_path: str) -> Optional[List[Tuple[float, float]]]:
    """The pixel clicks the last run actually fitted on, or None.

    A run made with points excluded was fitted on a subset, so measuring its
    model against every stored point would report an error the run never had
    -- worse, precisely when the point picker is being used to improve it.
    """
    try:
        with open(record_path, "r", encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None

    entries = (record.get("inputs") or {}).get("controlPoints")
    if not isinstance(entries, list):
        return None
    pixels: List[Tuple[float, float]] = []
    for entry in entries:
        pixel = (entry or {}).get("pixel") if isinstance(entry, dict) else None
        if not isinstance(pixel, dict):
            return None
        try:
            pixels.append((float(pixel["x"]), float(pixel["y"])))
        except (KeyError, TypeError, ValueError):
            return None
    return pixels


def _model_from_record(record: Dict[str, Any]) -> Optional[Any]:
    payload = (record.get("models") or {}).get("stage2_affine")
    if not isinstance(payload, dict):
        return None
    try:
        from .piecewise import deserialize_model

        return deserialize_model(payload)
    except Exception as e:  # pragma: no cover - a stale record must not 500
        logger.warning(f"Could not restore the last run's model: {e}")
        return None


def leave_one_out_models(
    control_points: Sequence[ControlPoint],
) -> List[Optional[AffineModel]]:
    """One affine per point, fitted without that point. None where impossible.

    The honest counterpart to the applied model when that model interpolates
    its own control points: a piecewise fit places every one of them exactly,
    so an arrow drawn from it has zero length and says nothing.
    """
    n = len(control_points)
    if n < 4:
        return [None] * n

    src = np.array([cp.pixel for cp in control_points], dtype=float)
    dst = np.array(
        [
            lonlat_to_webmercator(lon, lat)
            for lon, lat in (cp.geo for cp in control_points)
        ],
        dtype=float,
    )
    models: List[Optional[AffineModel]] = []
    for i in range(n):
        keep = np.arange(n) != i
        try:
            models.append(AffineModel.fit(src[keep], dst[keep]))
        except (ValueError, np.linalg.LinAlgError):
            models.append(None)
    return models


def control_point_diagnostics(
    control_points: Sequence[ControlPoint],
    frame_bounds: Optional[FrameBounds] = None,
    applied_model: Optional[Any] = None,
    applied_pixels: Optional[Sequence[Tuple[float, float]]] = None,
) -> Dict[str, Any]:
    """Per-point in-sample and leave-one-out error for an affine fit.

    Returns a JSON-ready dict. Distances are ground kilometres when a reference
    latitude is available, and None otherwise -- reporting raw EPSG:3857 metres
    as if they were ground distance is the inflation this package avoids
    everywhere else.

    Fewer than 4 points means no leave-one-out is possible: dropping one leaves
    the 3 an affine needs to fit exactly, so every held-out error would be
    measured against a fit with no freedom left.

    ``applied_model`` is the transform the case's last run used. When given,
    ``appliedKm`` reports how far that model actually placed each point, which
    is the number matching what the map shows. Leave-one-out stays an affine
    refit either way: it answers "can the points predict each other", and a
    model that interpolates them exactly cannot answer that about itself.

    ``applied_pixels`` are the clicks that run was fitted on. Points absent
    from it were excluded by hand, so they still get an ``appliedKm`` -- that
    is the useful number for deciding whether to bring one back -- but they
    are kept out of ``appliedRmseKm``, which reports what the run achieved.
    """
    points: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {
        "count": len(control_points),
        "affineRmseKm": None,
        "affineLooRmseKm": None,
        "appliedModel": getattr(applied_model, "name", None),
        "appliedRmseKm": None,
        "appliedPointCount": None,
        "excludedFromLastRun": [],
        "looAvailable": False,
        "referenceLatitude": None,
        "suspectIndices": [],
    }
    if len(control_points) < 3:
        return {"points": points, "summary": summary}

    src = np.array([cp.pixel for cp in control_points], dtype=float)
    dst = np.array(
        [
            lonlat_to_webmercator(lon, lat)
            for lon, lat in (cp.geo for cp in control_points)
        ],
        dtype=float,
    )
    ref_lat = reference_latitude(frame_bounds, [cp.geo for cp in control_points])
    summary["referenceLatitude"] = ref_lat

    fitted = AffineModel.fit(src, dst)
    in_sample = fitted.residuals_3857

    # How far the model that actually ran placed each point. For a piecewise
    # run this is ~0 at every local point by construction -- which is worth
    # showing, because it is exactly why it cannot be used to judge the fit.
    applied = None
    if applied_model is not None:
        try:
            ax, ay = applied_model(src[:, 0], src[:, 1])
            applied = np.hypot(ax - dst[:, 0], ay - dst[:, 1])
        except Exception as e:  # pragma: no cover - diagnostics must not fail
            logger.warning(f"Could not measure the applied model: {e}")
            applied = None

    # Which points that run was fitted on. Matched by click position rather
    # than by index: the record stores the surviving points, not their
    # original indices.
    used = np.ones(len(control_points), dtype=bool)
    if applied_pixels is not None:
        wanted = {(round(x, 6), round(y, 6)) for x, y in applied_pixels}
        used = np.array(
            [(round(cp.pixel[0], 6), round(cp.pixel[1], 6)) in wanted
             for cp in control_points]
        )
        summary["appliedPointCount"] = int(used.sum())
        summary["excludedFromLastRun"] = [
            i for i, was_used in enumerate(used) if not was_used
        ]

    n = len(control_points)
    loo = np.full(n, np.nan)
    if n >= 4:
        for i in range(n):
            keep = np.arange(n) != i
            try:
                model = AffineModel.fit(src[keep], dst[keep])
            except (ValueError, np.linalg.LinAlgError):
                continue
            x, y = model(src[i, 0], src[i, 1])
            loo[i] = float(np.hypot(x - dst[i, 0], y - dst[i, 1]))
        summary["looAvailable"] = bool(np.isfinite(loo).any())

    finite = loo[np.isfinite(loo)]
    median = float(np.median(finite)) if finite.size else None

    # Held-out error in pixels, which is the unit the click was made in and
    # the one `sigma_px` is expressed in. Both quantities are EPSG:3857, so
    # the ratio needs no latitude correction.
    meters_per_pixel = fitted.meters_per_pixel or 1.0

    for i, cp in enumerate(control_points):
        loo_value = float(loo[i]) if np.isfinite(loo[i]) else None
        loo_px = None if loo_value is None else loo_value / meters_per_pixel
        suspect = bool(
            loo_value is not None
            and median
            and loo_value > SUSPECT_RATIO * median
            and loo_px > SUSPECT_MIN_PX
        )
        if suspect:
            summary["suspectIndices"].append(i)
        points.append(
            {
                "index": i,
                "pixel": {"x": cp.pixel[0], "y": cp.pixel[1]},
                "geo": {"lon": cp.geo[0], "lat": cp.geo[1]},
                "source": cp.source,
                "inSampleKm": _km(float(in_sample[i]), ref_lat),
                "appliedKm": (
                    None if applied is None else _km(float(applied[i]), ref_lat)
                ),
                "usedInLastRun": bool(used[i]),
                "looKm": _km(loo_value, ref_lat),
                # Reported as well as km: km says how wrong the map is, pixels
                # say whether a human could have clicked that badly.
                "looPx": None if loo_px is None else round(loo_px, 1),
                "sigmaPx": cp.sigma_px,
                "suspect": suspect,
            }
        )

    summary["affineRmseKm"] = _km(fitted.rmse_3857, ref_lat)
    if applied is not None and applied.size and used.any():
        # Over the points that run was actually fitted on: including a point
        # it was told to ignore would report an error the run never had.
        summary["appliedRmseKm"] = _km(
            float(np.sqrt(np.mean(applied[used] ** 2))), ref_lat
        )
    if finite.size:
        summary["affineLooRmseKm"] = _km(
            float(np.sqrt(np.mean(finite**2))), ref_lat
        )
    return {"points": points, "summary": summary}
