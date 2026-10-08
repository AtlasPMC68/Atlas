"""Check points: held-out pixel <-> lon/lat pairs that judge the applied transform.

A check point is clicked like a control point and never fitted. They travel as
their own list, never inside ``control_points``, so no stage that fits -- the
baseline affine, the alignment's GCP term, the gates, the piecewise pins, the
source selection -- can see one by mistake. Only this module reads them, after
the run, to measure the transform that actually placed the zones.

That is the error the control-point residuals cannot give: those are measured
on the points the model was fitted to, and an interpolating model passes
through its points exactly. See dev-docs/georeferencing-testing.md section 3.
"""

from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from shapely.geometry import MultiPoint, Point
from shapely.ops import transform

from .control_points import ControlPoint
from .projection import (
    lonlat_arrays_to_webmercator,
    lonlat_to_webmercator,
    reference_latitude,
    webmercator_arrays_to_lonlat,
    webmercator_meters_to_km,
)
from .snapping import load_coastline_geometry

#: Two clicks closer than this, in image pixels, are the same click.
SAME_CLICK_PX = 1.0


def validate_check_points(
    control_points: Sequence[ControlPoint], check_points: Sequence[ControlPoint]
) -> None:
    """Refuse a check point that is also a control point.

    Same city, or the same clicked pixel: either way it would be in the fit,
    and its "held-out" error would be an in-sample residual.

    Raises:
        ValueError: naming the offending check point.
    """
    fitted_cities = {cp.city.geonameid for cp in control_points if cp.city is not None}
    fitted_pixels = np.array([cp.pixel for cp in control_points], dtype=float).reshape(-1, 2)

    for i, check in enumerate(check_points):
        label = check.city.name if check.city is not None else f"#{i}"
        if check.city is not None and check.city.geonameid in fitted_cities:
            raise ValueError(
                f"check point {i} ({label}) is also a control point: a check"
                " point must be held out of the fit"
            )
        if fitted_pixels.size:
            gap = np.hypot(*(fitted_pixels - np.asarray(check.pixel)).T)
            if float(gap.min()) < SAME_CLICK_PX:
                raise ValueError(
                    f"check point {i} ({label}) is on a control point's pixel:"
                    " a check point must be held out of the fit"
                )

    check_cities = [cp.city.geonameid for cp in check_points if cp.city is not None]
    if len(check_cities) != len(set(check_cities)):
        raise ValueError("the same city is used as a check point twice")


def _errors_km(
    model: Any, check_points: Sequence[ControlPoint], ref_lat: float
) -> np.ndarray:
    pixels = np.array([cp.pixel for cp in check_points], dtype=float)
    X, Y = model(pixels[:, 0], pixels[:, 1])
    truth = np.array(
        [lonlat_to_webmercator(lon, lat) for lon, lat in (cp.geo for cp in check_points)],
        dtype=float,
    )
    distance_3857 = np.hypot(np.ravel(X) - truth[:, 0], np.ravel(Y) - truth[:, 1])
    return np.array([webmercator_meters_to_km(float(d), ref_lat) for d in distance_3857])


def _rms(values: np.ndarray) -> Optional[float]:
    values = values[np.isfinite(values)]
    return round(float(np.sqrt(np.mean(values**2))), 3) if values.size else None


@lru_cache(maxsize=1)
def _coastline_3857():
    coast = load_coastline_geometry()
    return None if coast is None else transform(lonlat_arrays_to_webmercator, coast)


def _placement(
    check: ControlPoint,
    control_points: Sequence[ControlPoint],
    hull: Any,
    ref_lat: float,
) -> Dict[str, Any]:
    """Where a check point sits relative to what the fit is built from.

    A transform's error depends on it: near a control point an interpolating
    model is pinned, inside their hull it interpolates, outside it
    extrapolates; near the coast, alignment has evidence, inland it has none.
    Recorded per point so results can be read by placement afterwards.
    """
    pixel = np.asarray(check.pixel, dtype=float)
    fitted = np.array([cp.pixel for cp in control_points], dtype=float).reshape(-1, 2)
    nearest_px = float(np.hypot(*(fitted - pixel).T).min()) if fitted.size else None

    coast_km = None
    coast = _coastline_3857()
    if coast is not None:
        x, y = lonlat_to_webmercator(*check.geo)
        coast_km = round(webmercator_meters_to_km(Point(x, y).distance(coast), ref_lat), 1)

    return {
        "nearestControlPx": None if nearest_px is None else round(nearest_px, 1),
        "insideControlHull": bool(hull is not None and hull.covers(Point(*pixel))),
        "coastDistanceKm": coast_km,
    }


def measure_check_points(
    check_points: Sequence[ControlPoint],
    applied_model: Any,
    *,
    frame_bounds: Dict[str, float],
    baseline_model: Any = None,
    control_points: Sequence[ControlPoint] = (),
) -> Optional[Dict[str, Any]]:
    """Error of the applied transform at each check point, in ground km.

    Returns the ``errors.checkPoints`` block of the run record, or None when
    there is nothing to measure. ``baseline_model`` (the GCP-only affine) is
    measured on the same points so every run says what it gained or lost
    against the floor on held-out points.
    """
    if not check_points or applied_model is None:
        return None

    ref_lat = reference_latitude(frame_bounds)

    errors = _errors_km(applied_model, check_points, ref_lat)
    baseline_errors = (
        _errors_km(baseline_model, check_points, ref_lat)
        if baseline_model is not None
        else None
    )
    hull = (
        MultiPoint([cp.pixel for cp in control_points]).convex_hull
        if len(control_points) >= 3
        else None
    )
    pixels = np.array([cp.pixel for cp in check_points], dtype=float)
    X, Y = applied_model(pixels[:, 0], pixels[:, 1])
    lon, lat = webmercator_arrays_to_lonlat(np.ravel(X), np.ravel(Y))

    points: List[Dict[str, Any]] = []
    for i, cp in enumerate(check_points):
        points.append(
            {
                "source": cp.source,
                "name": cp.city.name if cp.city is not None else None,
                "pixel": {"x": cp.pixel[0], "y": cp.pixel[1]},
                "geo": {"lon": cp.geo[0], "lat": cp.geo[1]},
                "predicted": {"lon": float(lon[i]), "lat": float(lat[i])},
                "errorKm": round(float(errors[i]), 3),
                "gcpAffineErrorKm": (
                    None if baseline_errors is None else round(float(baseline_errors[i]), 3)
                ),
                **_placement(cp, control_points, hull, ref_lat),
            }
        )

    by_model = {"applied": _rms(errors)}
    if baseline_errors is not None:
        by_model["gcp_affine"] = _rms(baseline_errors)

    inside = np.array([p["insideControlHull"] for p in points], dtype=bool)
    by_placement = {
        "insideControlHull": {"count": int(inside.sum()), "rmseKm": _rms(errors[inside])},
        "outsideControlHull": {"count": int((~inside).sum()), "rmseKm": _rms(errors[~inside])},
    }

    finite = errors[np.isfinite(errors)]
    return {
        "count": len(check_points),
        "appliedModel": getattr(applied_model, "name", None),
        "rmseKm": _rms(finite),
        "medianKm": round(float(np.median(finite)), 3) if finite.size else None,
        "maxKm": round(float(finite.max()), 3) if finite.size else None,
        "referenceLatitude": ref_lat,
        "byModel": by_model,
        "byPlacement": by_placement,
        "points": points,
    }
