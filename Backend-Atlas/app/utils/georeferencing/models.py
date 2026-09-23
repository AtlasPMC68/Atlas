"""Alignment models: fit / apply / inverse / serialize.

One interface per model, so that later stages can swap affine for
affine+stretch for FFD without rewriting every call site.

Three interface decisions look over-engineered for an affine fitted to seven
points, and each is here because retrofitting it later would touch every call
site:

* **The model has an inverse.** Chamfer alignment (plan section 8) pushes
  reference samples *into* pixel space; the previous ``AffineTransformation``
  was pixel -> EPSG:3857 only.
* **``fit()`` takes a per-point weight vector**, not a scalar. Uniform here.
  Stage 7 weights control points by ``1/sigma^2``, and sigma differs per source.
* **``fit()`` takes a regularizer object**, not a scalar lambda. ``None`` here.
  Stage 7 uses a spatially varying lambda(x) field, not a constant.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

import numpy as np

from .config import (
    DEFAULT_GEOREF_CONFIG,
    GCP_SOURCES,
    SOURCE_CITY,
    SOURCE_SIFT,
    GeorefConfig,
)
from .projection import LonLat, XY, lonlat_to_webmercator


@dataclass(frozen=True)
class CityRef:
    """The gazetteer city a control point was matched to.

    ``geonameid`` is the GeoNames id, stable across GeoNames-derived datasets,
    which is what tells two spellings of one city ("Quebec", "Kebek") apart
    from two different cities. ``name`` is the gazetteer's name, so run records
    and overlays say which city a residual belongs to.
    """

    geonameid: int
    name: str

    def __post_init__(self) -> None:
        if isinstance(self.geonameid, bool) or not isinstance(self.geonameid, int):
            raise ValueError(f"city id must be an integer, got {self.geonameid!r}")
        if self.geonameid <= 0:
            raise ValueError(f"city id must be positive, got {self.geonameid}")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("city name must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.geonameid, "name": self.name}


@dataclass(frozen=True)
class ControlPoint:
    """One pixel <-> geo pair, and where it came from.

    A discriminated union on ``source``: a ``city`` point always carries its
    ``CityRef`` and a ``sift`` point never has one. Enforced at construction,
    so no consumer ever handles a city without a name or a keypoint with one.

    Positional uncertainty is deliberately *not* stored here. It is a model
    setting, looked up from ``GeorefConfig`` by source when fitting
    (``gcp_sigma_px``), so it can change without rewriting stored clicks.
    """

    pixel: XY
    geo: LonLat
    source: str
    city: Optional[CityRef] = None

    def __post_init__(self) -> None:
        if self.source not in GCP_SOURCES:
            raise ValueError(
                f"Unknown control point source {self.source!r};"
                f" expected one of {list(GCP_SOURCES)}"
            )
        if self.source == SOURCE_CITY and not isinstance(self.city, CityRef):
            raise ValueError("A city control point needs the city it was matched to")
        if self.source != SOURCE_CITY and self.city is not None:
            raise ValueError(f"A {self.source} control point cannot carry a city")

        pixel = _finite_pair(self.pixel, "pixel")
        lon, lat = _finite_pair(self.geo, "geo")
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError(f"geo out of range: lon={lon}, lat={lat}")
        # Frozen, so normalise to plain float tuples through object.__setattr__.
        object.__setattr__(self, "pixel", pixel)
        object.__setattr__(self, "geo", (lon, lat))

    @classmethod
    def sift(cls, pixel: Sequence[float], geo: Sequence[float]) -> "ControlPoint":
        """A coastline keypoint the user matched on their map. ``geo`` is (lon, lat)."""
        return cls(pixel=pixel, geo=geo, source=SOURCE_SIFT)

    @classmethod
    def from_city(
        cls,
        pixel: Sequence[float],
        geo: Sequence[float],
        geonameid: int,
        name: str,
    ) -> "ControlPoint":
        """A gazetteer city the user located on their map. ``geo`` is (lon, lat)."""
        return cls(
            pixel=pixel,
            geo=geo,
            source=SOURCE_CITY,
            city=CityRef(geonameid=geonameid, name=name),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "source": self.source,
            "pixel": {"x": self.pixel[0], "y": self.pixel[1]},
            "geo": {"lon": self.geo[0], "lat": self.geo[1]},
        }
        if self.city is not None:
            payload["city"] = self.city.to_dict()
        return payload

    @classmethod
    def from_dict(cls, entry: Any) -> "ControlPoint":
        """Inverse of ``to_dict``. Strict: raises ValueError on anything else.

        The one wire format for control points: the upload routes, the Celery
        task arguments, dev-test ``config.json`` and ``maps.georef_inputs``.
        """
        if not isinstance(entry, dict):
            raise ValueError(f"control point must be an object, got {entry!r}")
        pixel = entry.get("pixel")
        geo = entry.get("geo")
        if not isinstance(pixel, dict) or not isinstance(geo, dict):
            raise ValueError("control point needs 'pixel' {x, y} and 'geo' {lon, lat}")
        try:
            xy = (pixel["x"], pixel["y"])
            lonlat = (geo["lon"], geo["lat"])
        except KeyError as e:
            raise ValueError(f"control point is missing {e}")

        city = entry.get("city")
        city_ref = None
        if city is not None:
            if not isinstance(city, dict) or "id" not in city or "name" not in city:
                raise ValueError("control point 'city' must be {id, name}")
            city_ref = CityRef(geonameid=city["id"], name=city["name"])

        return cls(pixel=xy, geo=lonlat, source=entry.get("source"), city=city_ref)


def _finite_pair(value: Any, label: str) -> Tuple[float, float]:
    try:
        a, b = value
        pair = (_as_float(a), _as_float(b))
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be two numbers, got {value!r}")
    if not all(math.isfinite(v) for v in pair):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return pair


def _as_float(value: Any) -> float:
    # bool is an int subclass; a True coordinate is always a caller bug.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"not a number: {value!r}")
    return float(value)


def parse_control_points(entries: Any) -> List[ControlPoint]:
    """A JSON list of control points, as ``ControlPoint.to_dict`` writes them.

    Raises:
        ValueError: naming the offending index, on anything malformed.
    """
    if not isinstance(entries, list):
        raise ValueError("control points must be a JSON array")
    points: List[ControlPoint] = []
    for i, entry in enumerate(entries):
        try:
            points.append(ControlPoint.from_dict(entry))
        except ValueError as e:
            raise ValueError(f"control point {i}: {e}")
    return points


def select_control_points(
    control_points: Sequence[ControlPoint], sources: Sequence[str]
) -> List[ControlPoint]:
    """The points whose source is in *sources*, in their original order."""
    wanted = set(sources)
    return [cp for cp in control_points if cp.source in wanted]


def count_by_source(control_points: Sequence[ControlPoint]) -> Dict[str, int]:
    """Point count per known source, zeros included, for records and the UI."""
    counts = {source: 0 for source in GCP_SOURCES}
    for cp in control_points:
        counts[cp.source] += 1
    return counts


def gcp_sigma_px(source: str, config: GeorefConfig = DEFAULT_GEOREF_CONFIG) -> float:
    """Expected positional error, in image pixels, of a point from *source*."""
    if source == SOURCE_CITY:
        return float(config.gcp_sigma_px_city)
    return float(config.gcp_sigma_px_sift)


def control_point_weights(
    control_points: Sequence[ControlPoint],
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> np.ndarray:
    """``1/sigma^2`` weights, sigma looked up per source from *config*."""
    sigmas = np.array(
        [max(gcp_sigma_px(cp.source, config), 1e-6) for cp in control_points],
        dtype=float,
    )
    return 1.0 / (sigmas**2)


class Regularizer(Protocol):
    """Penalty added to the least-squares system.

    ``None`` throughout the proof of concept. Stage 7 replaces the scalar lambda
    with a spatially varying field, hence an object rather than a float.
    """

    def augment(
        self, design: np.ndarray, target: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:  # pragma: no cover - interface only
        ...


@dataclass
class AffineModel:
    """Pixel -> EPSG:3857 affine, with least-squares fit and an inverse.

    Affine gives translation, non-uniform scale, rotation and shear -- the
    degrees of freedom a scanned, slightly rotated, slightly stretched paper map
    needs. It deliberately replaced a thin-plate spline: TPS interpolates every
    control point exactly but extrapolates wildly outside their convex hull,
    which distorted map corners badly.

    Pixel Y grows downward while northing grows upward; nothing flips it
    explicitly -- the fit simply learns a negative ``d``.
    """

    name = "affine"
    dof = 6

    matrix: np.ndarray
    n_points: int = 0
    residuals_3857: np.ndarray = field(default_factory=lambda: np.zeros(0))

    # --- fitting ------------------------------------------------------------

    @classmethod
    def fit(
        cls,
        src_xy: np.ndarray,
        dst_xy: np.ndarray,
        weights: Optional[np.ndarray] = None,
        regularizer: Optional[Regularizer] = None,
    ) -> "AffineModel":
        """Least-squares fit of ``dst = M @ src``.

        Args:
            src_xy: (n, 2) source coordinates, pixel space.
            dst_xy: (n, 2) target coordinates, EPSG:3857.
            weights: optional (n,) per-point weights. Uniform when omitted.
            regularizer: optional penalty; unused in the proof of concept.
        """
        src_xy = np.asarray(src_xy, dtype=float)
        dst_xy = np.asarray(dst_xy, dtype=float)

        if src_xy.shape != dst_xy.shape:
            raise ValueError("src_xy and dst_xy must have same shape")
        if src_xy.ndim != 2 or src_xy.shape[1] != 2:
            raise ValueError("src_xy and dst_xy must be (n, 2) arrays")
        if src_xy.shape[0] < 3:
            raise ValueError("At least 3 control points are required for affine")

        n = src_xy.shape[0]

        # Two rows per point:
        #   X = a*x + b*y + tx   ->  [x, y, 1, 0, 0, 0]
        #   Y = c*x + d*y + ty   ->  [0, 0, 0, x, y, 1]
        design = np.zeros((2 * n, 6))
        target = np.zeros(2 * n)

        design[0::2, 0] = src_xy[:, 0]
        design[0::2, 1] = src_xy[:, 1]
        design[0::2, 2] = 1.0
        design[1::2, 3] = src_xy[:, 0]
        design[1::2, 4] = src_xy[:, 1]
        design[1::2, 5] = 1.0
        target[0::2] = dst_xy[:, 0]
        target[1::2] = dst_xy[:, 1]

        if weights is not None:
            w = np.asarray(weights, dtype=float).ravel()
            if w.shape[0] != n:
                raise ValueError("weights must have one entry per control point")
            if np.any(w < 0):
                raise ValueError("weights must be non-negative")
            # Weighted least squares by row scaling: both rows of a point share
            # its weight, and sqrt(w) on the residual is w on the squared one.
            row_scale = np.repeat(np.sqrt(w), 2)
            design = design * row_scale[:, None]
            target = target * row_scale

        if regularizer is not None:
            design, target = regularizer.augment(design, target)

        params, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
        a, b, tx, c, d, ty = params

        matrix = np.array([[a, b, tx], [c, d, ty], [0.0, 0.0, 1.0]], dtype=float)
        model = cls(matrix=matrix, n_points=n)
        model.residuals_3857 = model._residual_distances(src_xy, dst_xy)
        return model

    def measure_against(self, control_points: Sequence["ControlPoint"]) -> None:
        """Attach control-point residuals to a model that was not fitted here.

        Step 4 hands back a model produced by the chamfer/ICP optimiser rather
        than by ``fit``, so it arrives with no residuals and would otherwise
        report its error as unknown.
        """
        if not control_points:
            return
        src = np.array([cp.pixel for cp in control_points], dtype=float)
        dst = np.array(
            [
                lonlat_to_webmercator(lon, lat)
                for lon, lat in (cp.geo for cp in control_points)
            ],
            dtype=float,
        )
        self.n_points = len(control_points)
        self.residuals_3857 = self._residual_distances(src, dst)

    def _residual_distances(self, src_xy: np.ndarray, dst_xy: np.ndarray) -> np.ndarray:
        """Per-point distance between predicted and target position, in 3857 m."""
        X, Y = self(src_xy[:, 0], src_xy[:, 1])
        return np.hypot(X - dst_xy[:, 0], Y - dst_xy[:, 1])

    # --- error reporting ----------------------------------------------------

    @property
    def redundancy(self) -> int:
        """Observations minus parameters. Zero means the fit is exact by
        construction and its residual carries no information."""
        return 2 * self.n_points - self.dof

    @property
    def rmse_3857(self) -> Optional[float]:
        """RMS control-point residual in EPSG:3857 metres, or None when the fit
        has no redundancy.

        With exactly 3 control points the affine passes through every point
        exactly, so a residual of 0 means "no evidence", not "perfect fit". The
        previous code reported that 0 as confidence (current section 9,
        limitation 2); returning None instead forces callers to say "unknown".
        """
        if self.redundancy <= 0 or self.residuals_3857.size == 0:
            return None
        return float(np.sqrt(np.mean(self.residuals_3857**2)))

    @property
    def meters_per_pixel(self) -> float:
        """Average EPSG:3857 metres per image pixel, from the linear block."""
        a, b = float(self.matrix[0, 0]), float(self.matrix[0, 1])
        c, d = float(self.matrix[1, 0]), float(self.matrix[1, 1])
        return (float(np.hypot(a, c)) + float(np.hypot(b, d))) / 2.0

    @property
    def determinant(self) -> float:
        return float(np.linalg.det(self.matrix[:2, :2]))

    # --- applying -----------------------------------------------------------

    def __call__(self, x, y) -> Tuple[np.ndarray, np.ndarray]:
        """Transform pixel coordinates to EPSG:3857, vectorised."""
        shape = np.asarray(x).shape
        x_arr = np.asarray(x, dtype=float).ravel()
        y_arr = np.asarray(y, dtype=float).ravel()

        pts = np.vstack([x_arr, y_arr, np.ones_like(x_arr)])
        transformed = self.matrix @ pts
        return transformed[0, :].reshape(shape), transformed[1, :].reshape(shape)

    def as_shapely_transform(self):
        """Callback for ``shapely.ops.transform``: pixel -> EPSG:3857."""

        def _transform(x, y, z=None):
            X, Y = self(x, y)
            if z is None:
                return X, Y
            return X, Y, z

        return _transform

    def inverse(self) -> "AffineModel":
        """The EPSG:3857 -> pixel model.

        Needed by chamfer alignment, which samples the reference coastline and
        pushes it into pixel space to read the user-side distance transform.
        """
        if abs(self.determinant) < 1e-12:
            raise ValueError("Affine is singular and cannot be inverted")
        return AffineModel(matrix=np.linalg.inv(self.matrix))

    # --- serialization ------------------------------------------------------

    def serialize(self) -> Dict[str, Any]:
        """Persistable form, so a re-run or a later feature edit reuses the fit
        instead of refitting (current section 9, limitation 4)."""
        return {
            "name": self.name,
            "dof": self.dof,
            "matrix": [[float(v) for v in row] for row in self.matrix],
            "nPoints": int(self.n_points),
            "redundancy": int(self.redundancy),
            "rmse3857": self.rmse_3857,
            "metersPerPixel": float(self.meters_per_pixel),
            "determinant": self.determinant,
        }

    @classmethod
    def deserialize(cls, payload: Dict[str, Any]) -> "AffineModel":
        if payload.get("name") not in (None, cls.name):
            raise ValueError(f"Not an affine model payload: {payload.get('name')}")
        return cls(
            matrix=np.array(payload["matrix"], dtype=float),
            n_points=int(payload.get("nPoints", 0)),
        )


def fit_affine_from_control_points(
    control_points: Sequence[ControlPoint],
    use_sigma_weights: bool = False,
    regularizer: Optional[Regularizer] = None,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> AffineModel:
    """Fit pixel -> EPSG:3857 from control-point records.

    ``use_sigma_weights`` stays off by default: the baseline treats every
    point alike, whatever its source. ``config`` supplies the per-source sigma
    when it is turned on.
    """
    if len(control_points) < 3:
        raise ValueError(
            "At least 3 point pairs are required for affine transformation"
        )

    src = np.array([cp.pixel for cp in control_points], dtype=float)
    dst = np.array(
        [lonlat_to_webmercator(lon, lat) for lon, lat in (cp.geo for cp in control_points)],
        dtype=float,
    )
    weights = (
        control_point_weights(control_points, config) if use_sigma_weights else None
    )
    return AffineModel.fit(src, dst, weights=weights, regularizer=regularizer)
