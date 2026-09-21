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

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

import numpy as np

from .projection import LonLat, XY, lonlat_to_webmercator

# Positional uncertainty in *image pixels*, by where the control point came from.
# A coastline keypoint's sigma is click precision; a city's is how wrong old maps
# place cities, which is the premise of the whole project. They differ by an
# order of magnitude, which is what makes a 1/sigma^2 weighting meaningful
# rather than decorative (plan section 9).
DEFAULT_SIGMA_PX_BY_SOURCE: Dict[str, float] = {
    "sift": 6.0,
    "manual": 8.0,
    "city": 40.0,
}
FALLBACK_SIGMA_PX = 8.0

GCP_SOURCES = tuple(DEFAULT_SIGMA_PX_BY_SOURCE)


def sigma_px_for_source(source: Optional[str]) -> float:
    return DEFAULT_SIGMA_PX_BY_SOURCE.get(source or "", FALLBACK_SIGMA_PX)


@dataclass(frozen=True)
class ControlPoint:
    """One user-supplied pixel <-> geo pair, with its provenance.

    ``sigma_px`` is a per-source constant until Stage 7 actually uses it for
    weighting; carrying it now costs nothing and saves a migration later.
    """

    pixel: XY
    geo: LonLat
    source: str = "manual"
    sigma_px: float = FALLBACK_SIGMA_PX

    @classmethod
    def make(
        cls,
        pixel: Sequence[float],
        geo: Sequence[float],
        source: str = "manual",
        sigma_px: Optional[float] = None,
    ) -> "ControlPoint":
        return cls(
            pixel=(float(pixel[0]), float(pixel[1])),
            geo=(float(geo[0]), float(geo[1])),
            source=source,
            sigma_px=(
                float(sigma_px) if sigma_px is not None else sigma_px_for_source(source)
            ),
        )

    @classmethod
    def from_pairs(
        cls,
        pixel_points: Sequence[Sequence[float]],
        geo_points_lonlat: Sequence[Sequence[float]],
        source: str = "sift",
    ) -> List["ControlPoint"]:
        """Build records from the two parallel arrays the routes still send.

        Raises:
            ValueError: on mismatched lengths.
            TypeError: when given dicts instead of (x, y) tuples.
        """
        if pixel_points and isinstance(pixel_points[0], dict):
            raise TypeError(
                f"pixel_points contains dicts, expected (x, y) tuples: {pixel_points[0]}"
            )
        if geo_points_lonlat and isinstance(geo_points_lonlat[0], dict):
            raise TypeError(
                "geo_points_lonlat contains dicts, expected (lon, lat) tuples: "
                f"{geo_points_lonlat[0]}"
            )
        if len(pixel_points) != len(geo_points_lonlat):
            raise ValueError(
                f"Mismatch in point counts: {len(pixel_points)} pixel points "
                f"vs {len(geo_points_lonlat)} geo points"
            )
        return [
            cls.make(px, geo, source=source)
            for px, geo in zip(pixel_points, geo_points_lonlat)
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pixel": {"x": self.pixel[0], "y": self.pixel[1]},
            "geo": {"lon": self.geo[0], "lat": self.geo[1]},
            "source": self.source,
            "sigmaPx": self.sigma_px,
        }


def control_point_weights(control_points: Sequence[ControlPoint]) -> np.ndarray:
    """``1/sigma^2`` weights. Not yet applied to the fit -- see module docstring."""
    sigmas = np.array(
        [max(float(cp.sigma_px), 1e-6) for cp in control_points], dtype=float
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
) -> AffineModel:
    """Fit pixel -> EPSG:3857 from control-point records.

    ``use_sigma_weights`` stays off by default: turning it on changes output,
    and Step 1 must leave output identical.
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
    weights = control_point_weights(control_points) if use_sigma_weights else None
    return AffineModel.fit(src, dst, weights=weights, regularizer=regularizer)
