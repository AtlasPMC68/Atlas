"""What a run knows about how well it placed the map, blind: the inputs of the
quality estimator (georeferencing-synthetic.md §4.3).

Per map, the control points' layout and the affine's leave-one-out residuals,
recorded on every run. Per point, what the run knows at one pixel
(``point_features``), computed by the same function in production and in the
runners, so a model fitted on synthetic maps reads the same inputs on a real
one. Nothing here uses a truth.

The fitted models (``QUALITY_MODEL_PATH``) turn them into what the run
expects of itself, ``predict_quality``: recorded on every run, and fitted by
the scripts under the same definitions (``MAP_FEATURES``, ``POINT_FEATURES``,
``zone_features``).
"""

import functools
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import shape

from .control_points import ControlPoint
from .projection import lonlat_to_webmercator
from .records import record_signals

#: "Near" a pixel, as a share of the image diagonal: about the piecewise
#: correction's reach (``piecewise_influence_radius_ratio_of_diagonal``).
NEARBY_RATIO = 0.15
#: The coast "around" a pixel, as a share of the diagonal.
COAST_AROUND_RATIO = 0.05
#: Control points whose leave-one-out residuals describe a pixel.
LOO_NEIGHBOURS = 3
#: Grid across the image on which the largest gap between points is found.
EMPTY_GRID = 32
#: The fitted estimator production applies: Q4's error models and Q8's
#: success model (georeferencing-synthetic.md §10.10, §10.13), written from
#: their ``model.json`` by ``scripts/fit_georef_success.py --ship``.
QUALITY_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quality_model.json")
#: Pixels inside the zones at which the success model reads the point model.
ZONE_SAMPLES = 300


def _pixels(control_points: Sequence[ControlPoint]) -> np.ndarray:
    return np.array([cp.pixel for cp in control_points], dtype=float).reshape(-1, 2)


def _diagonal(image_size: Tuple[int, int]) -> float:
    return math.hypot(*image_size)


def _hull(pixels: np.ndarray) -> Any:
    """The points' convex hull; empty below 3 points or when they are aligned."""
    hull = shapely.MultiPoint(pixels).convex_hull if len(pixels) else shapely.Polygon()
    return hull if hull.geom_type == "Polygon" else shapely.Polygon()


def control_point_layout(
    control_points: Sequence[ControlPoint], image_size: Tuple[int, int]
) -> Dict[str, Any]:
    """How the control points cover the image: their hull's share of it, the
    gap from each point to its nearest neighbour, and the largest distance
    from anywhere in the image to the nearest point, as shares of the
    diagonal."""
    pixels = _pixels(control_points)
    width, height = image_size
    diagonal = _diagonal(image_size)
    out: Dict[str, Any] = {
        "hullShare": round(_hull(pixels).area / float(width * height), 4) if width * height else None,
        "nearestGapMedianRatio": None,
        "nearestGapMaxRatio": None,
        "emptyRadiusRatio": None,
    }
    if len(pixels) >= 2:
        gaps, _ = cKDTree(pixels).query(pixels, k=2)
        out["nearestGapMedianRatio"] = round(float(np.median(gaps[:, 1])) / diagonal, 4)
        out["nearestGapMaxRatio"] = round(float(gaps[:, 1].max()) / diagonal, 4)
    if len(pixels):
        xs, ys = np.meshgrid(np.linspace(0, width, EMPTY_GRID), np.linspace(0, height, EMPTY_GRID))
        empty, _ = cKDTree(pixels).query(np.column_stack([xs.ravel(), ys.ravel()]))
        out["emptyRadiusRatio"] = round(float(empty.max()) / diagonal, 4)
    return out


def affine_leave_one_out(
    control_points: Sequence[ControlPoint], meters_per_pixel: float
) -> Dict[str, Any]:
    """Each control point's residual under the control-point affine fitted
    without it, in pixels (closed form: the residual over one minus its
    leverage). Empty with 3 points or fewer, where leaving one out leaves
    nothing to check it against. ``residualsPx`` is in the order of the
    points; the dev tool and ``point_features`` read it."""
    out: Dict[str, Any] = {"residualsPx": [], "rmsPx": None, "maxPx": None, "maxOverMedian": None}
    n = len(control_points)
    if n <= 3 or not meters_per_pixel or not math.isfinite(meters_per_pixel):
        return out
    design = np.column_stack([_pixels(control_points), np.ones(n)])
    target = np.array([lonlat_to_webmercator(*cp.geo) for cp in control_points], dtype=float)
    pinv = np.linalg.pinv(design)
    residual = target - design @ (pinv @ target)
    leverage = np.einsum("ij,ji->i", design, pinv)
    held_out = np.full(n, np.nan)
    ok = leverage < 1.0 - 1e-9
    held_out[ok] = np.linalg.norm(residual[ok], axis=1) / (1.0 - leverage[ok]) / meters_per_pixel
    finite = held_out[np.isfinite(held_out)]
    out["residualsPx"] = [round(float(v), 3) if math.isfinite(v) else None for v in held_out]
    if finite.size:
        median = float(np.median(finite))
        out["rmsPx"] = round(float(np.sqrt(np.mean(finite**2))), 3)
        out["maxPx"] = round(float(finite.max()), 3)
        out["maxOverMedian"] = round(float(finite.max()) / median, 3) if median > 0 else None
    return out


@dataclass(frozen=True)
class CoastEvidence:
    """The reference coast as the applied model draws it in the image, and
    how far each of its samples is from a drawn edge (NaN where the field
    cannot see)."""

    xy: np.ndarray  # (M, 2) pixels
    misfit_px: np.ndarray  # (M,)


def coast_evidence(model: Any, context: Any) -> Optional[CoastEvidence]:
    """The coast samples of an alignment context through *model*'s inverse;
    None without a coast in the frame."""
    from .align import edge_distance_px
    from .post_align import _through

    if context is None or len(context.coast_samples) == 0:
        return None
    coast = _through(model.inverse(), context.coast_samples)
    xy = np.asarray(coast.xy, dtype=float)
    keep = np.all(np.isfinite(xy), axis=1)
    xy = xy[keep]
    return CoastEvidence(xy=xy, misfit_px=edge_distance_px(context.user_field, xy[:, 0], xy[:, 1]))


@dataclass(frozen=True)
class ZoneSizes:
    """The extracted zones in the image, before placement: what an error in
    pixels costs each one's IoU depends on its size."""

    shapes: Tuple[Any, ...]
    #: sqrt(area / pi): the radius of the disc of the same area.
    radius_px: np.ndarray
    #: 2 area / perimeter: the radius for a disc, about the width of a long
    #: thin zone, which a shift across it eats into.
    width_px: np.ndarray


def zone_sizes(pixel_zones: Sequence[Dict[str, Any]]) -> ZoneSizes:
    """Every polygon feature of the pixel-space FeatureCollections *pixel_zones*
    (what ``georeference`` places), with its size."""
    shapes = []
    for collection in pixel_zones:
        for feature in collection.get("features", []):
            geom = shape(feature["geometry"])
            if not geom.is_valid:
                geom = geom.buffer(0)
            if geom.area > 0:
                shapes.append(geom)
    area = np.array([g.area for g in shapes], dtype=float)
    perimeter = np.array([g.length for g in shapes], dtype=float)
    return ZoneSizes(
        shapes=tuple(shapes),
        radius_px=np.sqrt(area / math.pi),
        width_px=2.0 * area / np.maximum(perimeter, 1e-9),
    )


def zone_errors(sizes: ZoneSizes, pixels: np.ndarray, error_px: np.ndarray) -> np.ndarray:
    """Per zone, the median of *error_px* over the *pixels* (N, 2) inside it,
    or at the pixel nearest to it where none is."""
    pixels = np.asarray(pixels, dtype=float).reshape(-1, 2)
    error_px = np.asarray(error_px, dtype=float)
    out = np.full(len(sizes.shapes), np.nan)
    if not len(pixels):
        return out
    for i, zone in enumerate(sizes.shapes):
        inside = shapely.contains_xy(zone, pixels[:, 0], pixels[:, 1])
        if inside.any():
            out[i] = float(np.median(error_px[inside]))
        else:
            p = zone.representative_point()
            out[i] = float(error_px[np.argmin(np.hypot(pixels[:, 0] - p.x, pixels[:, 1] - p.y))])
    return out


def zone_sample_pixels(sizes: ZoneSizes, count: int, seed: int = 0) -> np.ndarray:
    """*count* pixels uniform over the zones' union (N, 2), from *seed*: where
    to ask ``point_features`` about the zones."""
    union = shapely.union_all(sizes.shapes) if sizes.shapes else shapely.Polygon()
    if union.is_empty:
        return np.zeros((0, 2))
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = union.bounds
    batch = min(200_000, max(4 * count, int(4 * count * (x1 - x0) * (y1 - y0) / union.area)))
    shapely.prepare(union)
    out = np.zeros((0, 2))
    for _ in range(20):
        xy = np.column_stack([rng.uniform(x0, x1, batch), rng.uniform(y0, y1, batch)])
        out = np.vstack([out, xy[shapely.contains_xy(union, xy[:, 0], xy[:, 1])]])
        if len(out) >= count:
            break
    return out[:count]


def disc_iou(error_px: np.ndarray, radius_px: np.ndarray) -> np.ndarray:
    """IoU of a disc of *radius_px* and the same disc shifted by *error_px*."""
    r = np.maximum(np.asarray(radius_px, dtype=float), 1e-9)
    d = np.minimum(np.asarray(error_px, dtype=float), 2.0 * r)
    overlap = 2.0 * r**2 * np.arccos(d / (2.0 * r)) - 0.5 * d * np.sqrt(np.maximum(4.0 * r**2 - d**2, 0.0))
    return overlap / (2.0 * math.pi * r**2 - overlap)


def point_features(
    pixels: np.ndarray,
    control_points: Sequence[ControlPoint],
    model: Any,
    baseline: Any,
    image_size: Tuple[int, int],
    coast: Optional[CoastEvidence] = None,
    loo_px: Optional[Sequence[Optional[float]]] = None,
) -> Dict[str, np.ndarray]:
    """What the run knows at each pixel of *pixels* (N, 2), one array per
    input. Distances are shares of the image diagonal; NaN where an input
    cannot be computed (no coast in the frame, no leave-one-out).

    - ``nearestPointRatio``, ``pointsNearby``, ``insideHull``: the control
      points around it.
    - ``shiftFromAffinePx``: how far the applied model puts it from where the
      control-point affine (*baseline*) does, in the baseline's pixels: what
      the alignment, the bend or the piecewise step changed there.
    - ``coastDistanceRatio``, ``coastMisfitPx``: the reference coast as the
      model draws it, and the median distance from its samples within
      ``COAST_AROUND_RATIO`` to a drawn edge: how well the coast fits around.
    - ``nearbyLooPx``: the leave-one-out residuals (``affine_leave_one_out``)
      of the nearest control points, weighted by inverse distance.
    """
    pixels = np.asarray(pixels, dtype=float).reshape(-1, 2)
    n = len(pixels)
    diagonal = _diagonal(image_size)
    points = _pixels(control_points)
    tree = cKDTree(points)

    nearest, _ = tree.query(pixels)
    nearby = np.array([len(i) for i in tree.query_ball_point(pixels, NEARBY_RATIO * diagonal)])
    hull = _hull(points)
    inside = shapely.intersects_xy(hull, pixels[:, 0], pixels[:, 1]) if not hull.is_empty else np.zeros(n, bool)

    mx, my = model(pixels[:, 0], pixels[:, 1])
    bx, by = baseline(pixels[:, 0], pixels[:, 1])
    shift = np.hypot(np.asarray(mx) - np.asarray(bx), np.asarray(my) - np.asarray(by)) / baseline.meters_per_pixel

    coast_distance = np.full(n, np.nan)
    coast_misfit = np.full(n, np.nan)
    if coast is not None and len(coast.xy):
        coast_tree = cKDTree(coast.xy)
        coast_distance, _ = coast_tree.query(pixels)
        coast_distance = coast_distance / diagonal
        for i, around in enumerate(coast_tree.query_ball_point(pixels, COAST_AROUND_RATIO * diagonal)):
            seen = coast.misfit_px[around]
            seen = seen[np.isfinite(seen)]
            if seen.size:
                coast_misfit[i] = float(np.median(seen))

    nearby_loo = np.full(n, np.nan)
    loo = np.array([np.nan if v is None else v for v in (loo_px or [])], dtype=float)
    if loo.size == len(points) and np.isfinite(loo).any():
        known = np.isfinite(loo)
        k = min(LOO_NEIGHBOURS, int(known.sum()))
        distance, index = cKDTree(points[known]).query(pixels, k=k)
        distance, index = distance.reshape(n, k), index.reshape(n, k)
        weight = 1.0 / np.maximum(distance, 1.0)
        nearby_loo = (loo[known][index] * weight).sum(axis=1) / weight.sum(axis=1)

    return {
        "nearestPointRatio": nearest / diagonal,
        "pointsNearby": nearby.astype(float),
        "insideHull": inside.astype(float),
        "shiftFromAffinePx": shift,
        "coastDistanceRatio": coast_distance,
        "coastMisfitPx": coast_misfit,
        "nearbyLooPx": nearby_loo,
    }


# --------------------------------------------------------------------------
# The fitted models
# --------------------------------------------------------------------------

Row = Dict[str, Any]


def _num(value: Any) -> float:
    if value in (None, "", "None"):
        return math.nan
    if value in ("True", "False"):
        return float(value == "True")
    try:
        return float(value)
    except ValueError:
        return math.nan


def _log(value: float, offset: float = 0.0) -> float:
    return math.log(value + offset) if math.isfinite(value) and value + offset > 0 else math.nan


def _log1p(value: float) -> float:
    return _log(value, 1.0)


def _g(row: Row, key: str) -> float:
    return _num(row.get(key))


#: Per-map inputs, from a run's ``record_signals`` under ``run_`` and its km
#: per pixel as ``kmpp`` (``run_row``). Distances are in the map's pixels:
#: "blind", read the same on a map of any scale.
MAP_FEATURES: Dict[str, Callable[[Row], float]] = {
    "logPoints": lambda r: _log(_g(r, "run_controlPointCount")),
    "cityShare": lambda r: _g(r, "run_cityCount") / _g(r, "run_controlPointCount"),
    "logGcpRmsePx": lambda r: _log1p(_g(r, "run_gcpRmseKm") / r["kmpp"]),
    "logLooRmsPx": lambda r: _log1p(_g(r, "run_looAffineRmsPx")),
    "logLooMaxPx": lambda r: _log1p(_g(r, "run_looAffineMaxPx")),
    "logLooMaxOverMedian": lambda r: _log(_g(r, "run_looAffineMaxOverMedian")),
    "hullShare": lambda r: _g(r, "run_hullShare"),
    "emptyRadiusRatio": lambda r: _g(r, "run_emptyRadiusRatio"),
    "nearestGapMedianRatio": lambda r: _g(r, "run_nearestGapMedianRatio"),
    "nearestGapMaxRatio": lambda r: _g(r, "run_nearestGapMaxRatio"),
    "coastlineCoverage": lambda r: _g(r, "run_coastlineCoverage"),
    "logCoastlineSamples": lambda r: _log1p(_g(r, "run_coastlineSamples")),
    "bendApplied": lambda r: float(r.get("run_appliedModel") == "coast_bend"),
    "piecewiseApplied": lambda r: float(r.get("run_appliedModel") == "piecewise_affine"),
    "logBendMaxPx": lambda r: _log1p(_g(r, "run_coastBendMaxPx")),
    "logSnapMisfitPx": lambda r: _log1p(_g(r, "run_snapMisfitPx")),
    "logBaselineChamferPx": lambda r: _log1p(_g(r, "run_baselineChamferPx")),
    "logAlignedChamferPx": lambda r: _log1p(_g(r, "run_alignedChamferPx")),
    "inlierFraction": lambda r: _g(r, "run_inlierFraction"),
    "logCoastDisplacementPx": lambda r: _log1p(_g(r, "run_coastDisplacementPx")),
    "logBaselineGcpRmsPx": lambda r: _log1p(_g(r, "run_baselineGcpRmsPx")),
    "logAlignedGcpRmsPx": lambda r: _log1p(_g(r, "run_alignedGcpRmsPx")),
    "logKmPerPx": lambda r: _log(r["kmpp"]),
    "logDiagonalPx": lambda r: _log(_g(r, "run_imageDiagonalPx")),
}

#: Per-point inputs, from ``point_features`` under ``pt_``, on arrays. The
#: map's predicted median and p90 (``MAP_PREDICTIONS``) come before them.
POINT_FEATURES: Dict[str, Callable[[Dict[str, np.ndarray]], np.ndarray]] = {
    "logNearestRatio": lambda p: np.log(p["pt_nearestPointRatio"] + 1e-3),
    "logPointsNearby": lambda p: np.log1p(p["pt_pointsNearby"]),
    "insideHull": lambda p: p["pt_insideHull"],
    "logShiftPx": lambda p: np.log1p(p["pt_shiftFromAffinePx"]),
    "logCoastDistanceRatio": lambda p: np.log(p["pt_coastDistanceRatio"] + 1e-3),
    "logCoastMisfitPx": lambda p: np.log1p(p["pt_coastMisfitPx"]),
    "logNearbyLooPx": lambda p: np.log1p(p["pt_nearbyLooPx"]),
}
POINT_COLUMNS = ["pt_" + k for k in ("nearestPointRatio", "pointsNearby", "insideHull", "shiftFromAffinePx",
                                     "coastDistanceRatio", "coastMisfitPx", "nearbyLooPx")]
MAP_PREDICTIONS = ("mapMedian", "mapP90")

#: The zone inputs of the success model (``zone_features``).
ZONE_FEATURES = (
    "logZoneRadiusMedian", "logZoneRadiusP10", "logZoneWidthMedian", "logZoneWidthP10", "logZoneCount",
    "logErrorOverRadius", "logErrorOverWidth", "logZoneErrorOverWidth", "discIouRadius", "discIouWidth",
)


def run_row(record: Dict[str, Any]) -> Row:
    """A run record as ``MAP_FEATURES`` read it."""
    row: Row = {f"run_{k}": v for k, v in record_signals(record).items()}
    row["kmpp"] = _g(row, "run_metersPerPixel") * math.cos(math.radians(_g(row, "run_referenceLatitude"))) / 1000.0
    return row


def zone_features(sizes: ZoneSizes, pixels: np.ndarray, point_log_px: np.ndarray, map_median: float) -> Dict[str, float]:
    """The zone inputs of one run: *point_log_px* is the point model (log
    blind pixels) at *pixels*, pixels inside the zones."""
    out = {k: math.nan for k in ZONE_FEATURES}
    if not len(sizes.shapes):
        return out
    r, w = sizes.radius_px, sizes.width_px
    out.update(
        logZoneRadiusMedian=math.log(float(np.median(r))),
        logZoneRadiusP10=math.log(float(np.percentile(r, 10))),
        logZoneWidthMedian=math.log(float(np.median(w))),
        logZoneWidthP10=math.log(float(np.percentile(w, 10))),
        logZoneCount=math.log(len(r)),
        logErrorOverRadius=map_median - math.log(float(np.median(r))),
        logErrorOverWidth=map_median - math.log(float(np.median(w))),
    )
    if len(pixels):
        e = zone_errors(sizes, pixels, np.exp(point_log_px))
        out.update(
            logZoneErrorOverWidth=math.log(float(np.mean(e / w))),
            discIouRadius=float(np.mean(disc_iou(e, r))),
            discIouWidth=float(np.mean(disc_iou(e, w))),
        )
    return out


class Design:
    """The columns of a model: an intercept, then each chosen input with its
    missing values filled with the fit rows' mean, and, where the fit rows
    miss it, whether it was missing (no coast nearby is information)."""

    def __init__(self, names: Sequence[str], fill: Sequence[float], flag: Sequence[bool]):
        self.names, self.fill, self.flag = list(names), list(fill), list(flag)

    @classmethod
    def fit(cls, F: np.ndarray, names: Sequence[str], cols: Sequence[int], rows: np.ndarray) -> "Design":
        fill, flag = [], []
        for j in cols:
            x = F[rows, j]
            known = x[np.isfinite(x)]
            fill.append(float(known.mean()) if known.size else 0.0)
            flag.append(bool(known.size < x.size))
        return cls([names[j] for j in cols], fill, flag)

    def __call__(self, F: np.ndarray, names: Sequence[str]) -> np.ndarray:
        out = [np.ones(len(F))]
        for name, fill, flag in zip(self.names, self.fill, self.flag):
            x = F[:, list(names).index(name)]
            missing = ~np.isfinite(x)
            out.append(np.where(missing, fill, x))
            if flag:
                out.append(missing.astype(float))
        return np.column_stack(out)

    def to_json(self) -> Dict[str, Any]:
        return {"inputs": self.names, "fill": self.fill, "missingFlag": self.flag}


class QualityModel:
    """The models of a ``quality_model.json``: Q4's error over the map and at
    a pixel, in log blind pixels, and Q8's snapped IoU."""

    PARTS = ("mapMedian", "mapP90", "pointMedian", "success")

    def __init__(self, path: str = QUALITY_MODEL_PATH):
        with open(path, encoding="utf-8") as f:
            model = json.load(f)
        self.version = model["version"]
        self.parts = {
            k: (Design(model[k]["inputs"], model[k]["fill"], model[k]["missingFlag"]), np.array(model[k]["coefficients"]))
            for k in self.PARTS
        }

    def _apply(self, key: str, F: np.ndarray, names: Sequence[str]) -> np.ndarray:
        design, beta = self.parts[key]
        return design(F, names) @ beta

    def map(self, row: Row) -> Tuple[float, float]:
        """The median and p90 over the map, from ``run_row``."""
        names = list(MAP_FEATURES)
        F = np.array([[MAP_FEATURES[n](row) for n in names]], dtype=float)
        return float(self._apply("mapMedian", F, names)[0]), float(self._apply("mapP90", F, names)[0])

    def points(self, map_median: float, map_p90: float, features: Dict[str, np.ndarray]) -> np.ndarray:
        """The median at each pixel of ``point_features``."""
        raw = {f"pt_{k}": np.asarray(v, dtype=float) for k, v in features.items()}
        with np.errstate(divide="ignore", invalid="ignore"):
            columns = [f(raw) for f in POINT_FEATURES.values()]
        n = len(columns[0])
        F = np.column_stack([np.full(n, map_median), np.full(n, map_p90), *columns])
        return self._apply("pointMedian", F, [*MAP_PREDICTIONS, *POINT_FEATURES])

    def iou(self, inputs: Dict[str, float]) -> float:
        """The snapped IoU, from inputs by name: ``MAP_FEATURES``,
        ``MAP_PREDICTIONS`` and ``zone_features``."""
        names = list(inputs)
        F = np.array([[inputs[n] for n in names]], dtype=float)
        return float(1.0 - np.exp(self._apply("success", F, names)[0]))


@functools.lru_cache(maxsize=1)
def default_quality_model() -> QualityModel:
    return QualityModel()


def predict_quality(
    record: Dict[str, Any],
    pixel_zones: Sequence[Dict[str, Any]],
    control_points: Sequence[ControlPoint],
    model: Any,
    baseline: Any,
    image_size: Tuple[int, int],
    context: Any = None,
    quality_model: Optional[QualityModel] = None,
) -> Dict[str, Any]:
    """What a placed run expects of itself, blind: the median error over the
    map (Q4), and the snapped IoU of *pixel_zones* (Q8), from the error the
    point model predicts at ``ZONE_SAMPLES`` pixels inside them, over each
    zone's width (georeferencing-synthetic.md §10.13). *record* is the run's
    as placed, *context* its ``AlignmentContext`` (None without a coast);
    ``iou`` is None without a zone."""
    quality = quality_model or default_quality_model()
    row = run_row(record)
    map_median, map_p90 = quality.map(row)
    kmpp = row["kmpp"]
    sizes = zone_sizes(pixel_zones)
    pixels = zone_sample_pixels(sizes, ZONE_SAMPLES)
    out: Dict[str, Any] = {
        "modelVersion": quality.version,
        "mapMedianPx": round(math.exp(map_median), 3),
        "mapMedianKm": round(math.exp(map_median) * kmpp, 3) if math.isfinite(kmpp) else None,
        "zones": len(sizes.shapes),
        "iou": None,
    }
    if not len(pixels):
        return out
    loo = ((record.get("errors") or {}).get("affineLeaveOneOut") or {}).get("residualsPx")
    features = point_features(
        pixels, control_points, model, baseline, image_size,
        coast=coast_evidence(model, context), loo_px=loo,
    )
    zones = zone_features(sizes, pixels, quality.points(map_median, map_p90, features), map_median)
    inputs = {**{n: f(row) for n, f in MAP_FEATURES.items()}, "mapMedian": map_median, "mapP90": map_p90, **zones}
    out.update(
        iou=round(quality.iou(inputs), 4),
        zoneErrorOverWidth=round(math.exp(zones["logZoneErrorOverWidth"]), 4),
        zoneWidthMedianPx=round(math.exp(zones["logZoneWidthMedian"]), 2),
    )
    return out
