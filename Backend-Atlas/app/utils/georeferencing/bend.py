"""The map bent to its coast after alignment: a smooth correction in pixels
(roadmap §3, georeferencing-synthetic.md §10.4–10.5). On by default since
config v22 (``coast_bend``), with the piecewise step where it refuses.

The applied model becomes ``M(p + c(p))``: ``M`` is the model alignment left
(affine or piecewise), ``c`` an affine part plus Gaussians on a grid of knots,
fitted by ridge least squares. Each coastline sample says only how far the
coast is drawn across itself (the normal-search correspondences of ICP); the
control points say where they were clicked. The search is redone after each
fit, with the radius shrinking, as ICP does.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import numpy as np
from scipy.spatial import cKDTree

from .affine import AffineModel
from .align import CurveSamples, _sample_bilinear, find_correspondences
from .config import GeorefConfig
from .control_points import ControlPoint
from .piecewise import RESIDUAL_IN_SAMPLE, PiecewiseAffineModel
from .projection import lonlat_to_webmercator
from .records import RunRecord

logger = logging.getLogger(__name__)

#: What can be bent: whatever alignment and the piecewise step left.
Model = Union[AffineModel, PiecewiseAffineModel]

#: Ridge on the affine part of ``c`` by default: only enough to keep a
#: straight coast's slide along itself determined.
AFFINE_RIDGE = 1e-8
#: Newton steps to find where the bend draws a point (``p + c(p) = q``).
INVERSE_ITERATIONS = 12
#: Rows of the basis evaluated at once: a densified zone can have 10^5 vertices.
CHUNK = 20_000
#: The grid the fold check and the size of the correction are read on.
CHECK_GRID = 64
#: Reweighting passes per search: the robust weights from the fit just made.
REWEIGHTS = 2
_IDENTITY = np.array([1.0, 0.0, 0.0, 0.0, 1.0, 0.0])


# --- the basis and its fit ----------------------------------------------------


class BendBasis:
    """``c(p) = [p / scale, 1, g_k(p)] @ coef``: an affine part, then Gaussians
    on a grid of knots ``knots_across`` across the long side, as wide as their
    spacing. ``knots_across=0`` is the affine part alone."""

    def __init__(self, size: Tuple[int, int], knots_across: int):
        w, h = size
        self.scale = math.hypot(w, h)
        if knots_across:
            self.sigma = max(w, h) / knots_across
            xs = np.arange(-0.5, w / self.sigma + 1.0) * self.sigma
            ys = np.arange(-0.5, h / self.sigma + 1.0) * self.sigma
            gx, gy = np.meshgrid(xs, ys)
            self.centres = np.column_stack((gx.ravel(), gy.ravel()))
        else:
            self.sigma = 1.0
            self.centres = np.zeros((0, 2))

    @property
    def size(self) -> int:
        return 3 + len(self.centres)

    def _gaussians(self, p: np.ndarray) -> np.ndarray:
        c = self.centres
        d2 = (p * p).sum(axis=1)[:, None] + (c * c).sum(axis=1)[None, :] - 2.0 * p @ c.T
        return np.exp(-np.maximum(d2, 0.0) / (2.0 * self.sigma**2))

    def __call__(self, p: np.ndarray) -> np.ndarray:
        out = np.empty((len(p), self.size))
        out[:, :2] = p / self.scale
        out[:, 2] = 1.0
        if len(self.centres):
            out[:, 3:] = self._gaussians(p)
        return out

    def apply(self, p: np.ndarray, coef: np.ndarray) -> np.ndarray:
        """``c(p)``, (N, 2), a chunk of rows at a time."""
        out = np.empty((len(p), 2))
        for start in range(0, len(p), CHUNK):
            out[start : start + CHUNK] = self(p[start : start + CHUNK]) @ coef
        return out

    def jacobian(self, p: np.ndarray, coef: np.ndarray) -> np.ndarray:
        """``dc/dp``, (N, 2, 2)."""
        jac = np.zeros((len(p), 2, 2))
        jac += (coef[:2].T / self.scale)[None, :, :]
        if len(self.centres):
            g = self._gaussians(p)  # (N, K)
            offset = p[:, None, :] - self.centres[None, :, :]  # (N, K, 2)
            grad = -g[:, :, None] * offset / self.sigma**2
            jac += np.einsum("nkj,ki->nij", grad, coef[3:])
        return jac


def normal_equations(
    phi: np.ndarray, directions: np.ndarray, values: np.ndarray, weights: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """One observation per row: ``directions[i] . c(p_i) = values[i]``, at
    weight ``weights[i]``. The parameters are ``[coef_x; coef_y]``."""
    design = np.hstack((phi * directions[:, :1], phi * directions[:, 1:]))
    scaled = design * weights[:, None]
    return design.T @ scaled, scaled.T @ values


def full_observations(
    phi: np.ndarray, u: np.ndarray, weights: Optional[np.ndarray] = None
) -> Tuple[np.ndarray, np.ndarray]:
    """Both components of each correction ``u``; the weights sum to 1 (equal
    when not given)."""
    n = len(u)
    w = np.full(n, 1.0 / n) if weights is None else weights / weights.sum()
    directions = np.vstack((np.tile((1.0, 0.0), (n, 1)), np.tile((0.0, 1.0), (n, 1))))
    return normal_equations(
        np.vstack((phi, phi)), directions, np.concatenate((u[:, 0], u[:, 1])), np.concatenate((w, w))
    )


def across_observations(
    phi: np.ndarray, u: np.ndarray, normals: np.ndarray, weights: Optional[np.ndarray] = None
) -> Tuple[np.ndarray, np.ndarray]:
    """Only each correction's component along its unit normal."""
    n = len(u)
    w = np.full(n, 1.0 / n) if weights is None else weights / weights.sum()
    return normal_equations(phi, normals, (u * normals).sum(axis=1), w)


def solve_bend(
    basis: BendBasis,
    parts: Sequence[Tuple[float, Tuple[np.ndarray, np.ndarray]]],
    ridge: float,
    affine_ridge: float = AFFINE_RIDGE,
) -> np.ndarray:
    """The coefficients, (basis.size, 2), for weighted sums of normal equations."""
    m = basis.size
    lhs = sum(share * a for share, (a, _) in parts)
    rhs = sum(share * b for share, (_, b) in parts)
    penalty = np.full(m, ridge)
    penalty[:3] = affine_ridge
    lhs = lhs + np.diag(np.concatenate((penalty, penalty)))
    params = np.linalg.solve(lhs, rhs)
    return np.column_stack((params[:m], params[m:]))


# --- the models --------------------------------------------------------------


class _PixelWarp:
    """``base(w(p))`` for a smooth warp ``w`` of the pixels. A subclass gives
    ``warp`` and its Jacobian, and the fields ``base``, ``image_size``,
    ``n_points``, ``residuals_3857`` and ``residuals_kind``."""

    def warp(self, p: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def warp_jacobian(self, p: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def unwarp(self, q: np.ndarray) -> np.ndarray:
        """The pixel the warp sends to *q*: Newton on ``w(p) = q``."""
        p = q - (self.warp(q) - q)
        for _ in range(INVERSE_ITERATIONS):
            residual = self.warp(p) - q
            if np.all(np.abs(residual) < 1e-6):
                break
            p = p - np.linalg.solve(self.warp_jacobian(p), residual[:, :, None])[:, :, 0]
        return p

    def __call__(self, x, y) -> Tuple[np.ndarray, np.ndarray]:
        shape = np.asarray(x).shape
        p = np.column_stack([np.asarray(x, dtype=float).ravel(), np.asarray(y, dtype=float).ravel()])
        q = self.warp(p)
        X, Y = self.base(q[:, 0], q[:, 1])
        return np.asarray(X).reshape(shape), np.asarray(Y).reshape(shape)

    def as_shapely_transform(self):
        def _transform(x, y, z=None):
            X, Y = self(x, y)
            return (X, Y) if z is None else (X, Y, z)

        return _transform

    def inverse(self) -> "_Unwarped":
        return _Unwarped(self)

    # --- error reporting, as the other models ---------------------------------

    def measure_against(self, control_points: Sequence[ControlPoint]) -> None:
        if not control_points:
            return
        src = np.array([cp.pixel for cp in control_points], dtype=float)
        dst = np.array([lonlat_to_webmercator(*cp.geo) for cp in control_points], dtype=float)
        X, Y = self(src[:, 0], src[:, 1])
        self.n_points = len(control_points)
        self.residuals_3857 = np.hypot(X - dst[:, 0], Y - dst[:, 1])
        self.residuals_kind = RESIDUAL_IN_SAMPLE

    @property
    def redundancy(self) -> int:
        return 2 * self.n_points - 6

    @property
    def rmse_3857(self) -> Optional[float]:
        r = self.residuals_3857[np.isfinite(self.residuals_3857)]
        return float(np.sqrt(np.mean(r**2))) if r.size else None

    @property
    def meters_per_pixel(self) -> float:
        return self.base.meters_per_pixel

    @property
    def determinant(self) -> float:
        return self.base.determinant

    # --- serialization ---------------------------------------------------------

    def _serialize_common(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "base": self.base.serialize(),
            "imageSize": [int(v) for v in self.image_size],
            "nPoints": int(self.n_points),
            "rmse3857": self.rmse_3857,
            "rmse3857Kind": self.residuals_kind,
            "residuals3857": [None if not np.isfinite(r) else float(r) for r in self.residuals_3857],
            "metersPerPixel": float(self.meters_per_pixel),
            "determinant": self.determinant,
        }

    def _read_residuals(self, payload: Dict[str, Any]) -> None:
        residuals = payload.get("residuals3857")
        if residuals is not None:
            self.residuals_3857 = np.array([np.nan if r is None else r for r in residuals], dtype=float)
            self.residuals_kind = payload.get("rmse3857Kind", RESIDUAL_IN_SAMPLE)


@dataclass
class CoastBendModel(_PixelWarp):
    """Pixel -> EPSG:3857: ``base(p + c(p))``."""

    name = "coast_bend"

    base: Model
    image_size: Tuple[int, int]
    knots_across: int
    coef: np.ndarray
    n_points: int = 0
    residuals_3857: np.ndarray = field(default_factory=lambda: np.zeros(0))
    residuals_kind: str = RESIDUAL_IN_SAMPLE

    def __post_init__(self) -> None:
        self.coef = np.asarray(self.coef, dtype=float)
        self.basis = BendBasis(tuple(self.image_size), int(self.knots_across))

    def warp(self, p: np.ndarray) -> np.ndarray:
        """``p + c(p)``."""
        return p + self.basis.apply(p, self.coef)

    def warp_jacobian(self, p: np.ndarray) -> np.ndarray:
        return self.basis.jacobian(p, self.coef) + np.eye(2)[None]

    def serialize(self) -> Dict[str, Any]:
        return {**self._serialize_common(), "knotsAcross": int(self.knots_across), "coef": self.coef.tolist()}

    @classmethod
    def deserialize(cls, payload: Dict[str, Any]) -> "CoastBendModel":
        from .piecewise import deserialize_model

        if payload.get("name") != cls.name:
            raise ValueError(f"Not a coast-bend payload: {payload.get('name')}")
        model = cls(
            base=deserialize_model(payload["base"]),
            image_size=tuple(payload["imageSize"]),
            knots_across=int(payload["knotsAcross"]),
            coef=np.array(payload["coef"], dtype=float),
            n_points=int(payload.get("nPoints", 0)),
        )
        model._read_residuals(payload)
        return model


class _Unwarped:
    """EPSG:3857 -> pixel through a warped model."""

    def __init__(self, model: _PixelWarp):
        self.model = model
        self.base_inverse = model.base.inverse()

    def __call__(self, X, Y) -> Tuple[np.ndarray, np.ndarray]:
        shape = np.asarray(X).shape
        qx, qy = self.base_inverse(np.asarray(X, dtype=float).ravel(), np.asarray(Y, dtype=float).ravel())
        p = self.model.unwarp(np.column_stack((qx, qy)))
        return p[:, 0].reshape(shape), p[:, 1].reshape(shape)


# --- the fit -----------------------------------------------------------------


def _tukey_weight(r: np.ndarray, cutoff: float) -> np.ndarray:
    z = np.clip(r / cutoff, 0.0, 1.0)
    return (1.0 - z * z) ** 2


def _chamfer_px(points: np.ndarray, user_field: Any, cutoff: float) -> float:
    """Mean truncated distance to the drawn coast at *points*, where it can be seen."""
    d = _sample_bilinear(user_field.distance_px, points[:, 0], points[:, 1])
    v = _sample_bilinear(user_field.validity, points[:, 0], points[:, 1]) > 0.5
    return float(np.minimum(d[v], cutoff).mean()) if v.any() else float("nan")


def _sample_spacing(points: np.ndarray) -> float:
    """The median distance from each coast sample to its nearest other one, px."""
    if len(points) < 2:
        return float("nan")
    distance, _ = cKDTree(points).query(points, k=2)
    return float(np.median(distance[:, 1]))


def coast_share(config: GeorefConfig, coast_weight: np.ndarray, gcp_count: int, spacing: float) -> float:
    """The coast's share of the weight, the control points having the rest.

    Each scalar observation weighs 1/σ²: a control point is two of them, a
    coast match one, discounted to the share of an independent observation
    that its spacing is of the correlation length (neighbouring matches along
    a coast are not independent)."""
    independent = min(1.0, spacing / config.coast_bend_coast_correlation_px) if np.isfinite(spacing) else 1.0
    coast = float(coast_weight.sum()) * independent / config.coast_bend_coast_sigma_px**2
    gcp = 2.0 * gcp_count / config.coast_bend_gcp_sigma_px**2
    return coast / (coast + gcp) if coast + gcp > 0 else 1.0


def bend_to_coast(
    model: Model,
    control_points: Sequence[ControlPoint],
    context: Any,
    image_size: Tuple[int, int],
    config: GeorefConfig,
    record: Optional[RunRecord] = None,
) -> Union[Model, CoastBendModel]:
    """Bend *model* to the drawn coast; *model* itself where a safeguard
    refuses (the pipeline then falls back to the piecewise step,
    ``coast_bend_fallback_piecewise``)."""

    record = record or RunRecord()
    stats: Dict[str, Any] = {"applied": False, "onModel": model.name}
    samples, user_field = context.coast_samples, context.user_field
    if len(samples) == 0 or not user_field.edge.any():
        stats["skippedBecause"] = "no coastline samples or no user edges"
        record.set_errors(coastBend=stats)
        return model

    # Everything happens in the frame of *model*'s pixels: s is where *model*
    # draws each reference sample, and c moves the drawn map onto it.
    inverse = model.inverse()
    s = np.column_stack(inverse(samples.xy[:, 0], samples.xy[:, 1]))
    tip = np.column_stack(inverse(samples.xy_normal[:, 0], samples.xy_normal[:, 1]))
    normal = tip - s
    length = np.linalg.norm(normal, axis=1)
    ok = np.isfinite(length) & (length > 1e-9)
    s, normal = s[ok], normal[ok] / length[ok, None]

    basis = BendBasis(image_size, config.coast_bend_knots_across)
    gcp_pixel = np.array([cp.pixel for cp in control_points], dtype=float)
    merc = np.array([lonlat_to_webmercator(*cp.geo) for cp in control_points], dtype=float)
    gcp_u = np.column_stack(inverse(merc[:, 0], merc[:, 1])) - gcp_pixel
    gcp = full_observations(basis(gcp_pixel), gcp_u)
    spacing = _sample_spacing(s)
    share = float("nan")

    bent = CoastBendModel(model, image_size, config.coast_bend_knots_across, np.zeros((basis.size, 2)))
    before = _chamfer_px(s, user_field, config.icp_cutoff_px)
    matched = 0
    for radius in config.coast_bend_search_radius_px:
        drawn = bent.unwarp(s)  # where the current bend draws each sample
        index, targets, confidence = find_correspondences(
            _IDENTITY, CurveSamples(xy=drawn, xy_normal=drawn + normal), user_field, radius, config
        )
        matched = int(index.size)
        if matched < config.icp_min_correspondences:
            break
        n_i = normal[index]
        u = s[index] - targets
        phi = basis(targets)
        # Robust weights, as ICP's Tukey: the cutoff follows the search radius
        # down, so the first, wide searches can still pull.
        cutoff = max(float(config.icp_cutoff_px), float(radius))
        residual = np.abs(((drawn[index] - targets) * n_i).sum(axis=1))
        coef = bent.coef
        for _ in range(REWEIGHTS):
            weight = confidence * _tukey_weight(residual, cutoff)
            if weight.sum() <= 0:
                break
            share = coast_share(config, weight, len(control_points), spacing)
            coef = solve_bend(
                basis,
                [(share, across_observations(phi, u, n_i, weight)), (1.0 - share, gcp)],
                config.coast_bend_ridge,
                config.coast_bend_affine_ridge,
            )
            residual = np.abs(((basis.apply(targets, coef) - u) * n_i).sum(axis=1))
        bent = CoastBendModel(model, image_size, config.coast_bend_knots_across, coef)
    stats.update(correspondences=matched, coastShare=share, sampleSpacingPx=spacing)
    if not np.any(bent.coef):
        stats["skippedBecause"] = f"too few correspondences ({matched})"
        record.set_errors(coastBend=stats)
        return model

    # --- safeguards: each falls back to *model* ---------------------------------
    w, h = image_size
    xs, ys = np.meshgrid(np.linspace(0, w, CHECK_GRID), np.linspace(0, h, CHECK_GRID))
    grid = np.column_stack((xs.ravel(), ys.ravel()))
    correction = np.linalg.norm(basis.apply(grid, bent.coef), axis=1)
    min_det = float(np.min(np.linalg.det(basis.jacobian(grid, bent.coef) + np.eye(2)[None])))
    after = _chamfer_px(bent.unwarp(s), user_field, config.icp_cutoff_px)
    cap = config.coast_bend_max_ratio_of_diagonal * math.hypot(w, h)
    stats.update(
        chamferBeforePx=before,
        chamferAfterPx=after,
        maxCorrectionPx=float(correction.max()),
        rmsCorrectionPx=float(np.sqrt(np.mean(correction**2))),
        minJacobianDet=min_det,
    )
    if min_det <= 0:
        stats["skippedBecause"] = "the bend folds the map"
    elif correction.max() > cap:
        stats["skippedBecause"] = f"the bend moves the map more than {cap:.0f} px"
    elif not np.isfinite(after) or (np.isfinite(before) and after > before):
        stats["skippedBecause"] = "the coastline chamfer got worse"
    else:
        bent.measure_against(control_points)
        stats["applied"] = True
        record.set_errors(coastBend=stats)
        return bent
    record.set_errors(coastBend=stats)
    return model
