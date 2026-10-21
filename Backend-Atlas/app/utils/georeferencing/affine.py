"""The affine model, pixel -> EPSG:3857: fit, apply, inverse, serialize."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .control_points import ControlPoint, control_point_weights
from .projection import lonlat_to_webmercator


@dataclass
class AffineModel:
    """Pixel -> EPSG:3857 affine, with least-squares fit and an inverse."""

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
    ) -> "AffineModel":
        """Least-squares fit of ``dst = M @ src``.

        Args:
            src_xy: (n, 2) source coordinates, pixel space.
            dst_xy: (n, 2) target coordinates, EPSG:3857.
            weights: optional (n,) per-point weights. Uniform when omitted.
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

        params, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
        a, b, tx, c, d, ty = params

        matrix = np.array([[a, b, tx], [c, d, ty], [0.0, 0.0, 1.0]], dtype=float)
        model = cls(matrix=matrix, n_points=n)
        model.residuals_3857 = model._residual_distances(src_xy, dst_xy)
        return model

    def measure_against(self, control_points: Sequence["ControlPoint"]) -> None:
        """Attach control-point residuals to a model that was not fitted here."""

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
        """RMS control-point residual in EPSG:3857 metres."""

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
        """The EPSG:3857 -> pixel model."""

        if abs(self.determinant) < 1e-12:
            raise ValueError("Affine is singular and cannot be inverted")
        return AffineModel(matrix=np.linalg.inv(self.matrix))

    # --- serialization ------------------------------------------------------

    def serialize(self) -> Dict[str, Any]:
        """Persistable form, so a re-run or a later feature edit reuses the fit
        instead of refitting (the original code never kept it)."""
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
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> AffineModel:
    """Fit pixel -> EPSG:3857 from control-point records."""
    
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
    return AffineModel.fit(src, dst, weights=weights)
