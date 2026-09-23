"""Coarse chamfer alignment, normal-search ICP, and the gates.

Two phases (plan section 8.1). Both optimise the same six affine parameters, and
both express every residual in **user image pixels**, so one robust cutoff means
the same thing to the control-point term and to the curve term.

    Phase A -- chamfer.  Reference curve samples are pushed into pixel space and
                         read a distance field built from the user's edge map.
                         Annealed: the field starts heavily blurred for a wide
                         basin of attraction and sharpens as it converges.

    Phase B -- ICP.      Each reference sample searches along its own curve
                         normal for a user edge whose local orientation agrees
                         within a tolerance, producing explicit correspondences.
                         This is the only thing here that can tell a coastline
                         from a political border crossing it: to a chamfer
                         distance both are just "nearby edge pixels".

Nothing in this module needs cv2 -- it consumes the arrays `evidence.py` built,
and does its own gradients with scipy. That keeps it testable without the image
stack.

**The result is gated, never trusted.** A fit locked onto the wrong feature has
*low* chamfer residual by construction, so the residual can never be the check.
The primary gate is a probe fit that never sees the control points, measured
against them afterwards (section 10.3).
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates
from scipy.optimize import least_squares

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .models import AffineModel, ControlPoint, gcp_sigma_px
from .projection import lonlat_to_webmercator, webmercator_meters_to_km
from .records import GateCheck, RunRecord

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# The user-side field the curve term reads
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UserField:
    """Everything the objective samples at a projected reference point."""

    distance_px: np.ndarray
    orientation: np.ndarray  # radians, direction across the edge, in [0, pi)
    edge: np.ndarray
    validity: np.ndarray  # 0 where we cannot see, 1 where we can
    height: int
    width: int

    def blurred_distance(self, sigma_px: float) -> np.ndarray:
        if sigma_px <= 0:
            return self.distance_px
        return gaussian_filter(self.distance_px, sigma=float(sigma_px))


def build_user_field(
    evidence: Any,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> UserField:
    """Build the distance field, orientation field and validity mask.

    Two distance transforms, combined as ``min(D_strong, D_weak + penalty)``.
    Straight-line suppression leaves edges at a reduced weight rather than
    deleting them, and `distance_transform_edt` only takes a binary input;
    thresholding would throw the suppression away, so a suppressed edge instead
    behaves as though it were `penalty` pixels further off.

    Validity is the complement of the text mask, blurred. Where a label was
    removed we do not know what the geography does, and the honest answer is
    "no data" rather than "the nearest edge is 60 px away" -- see plan section
    7b. Blurred rather than hard, so the objective stays smooth as samples cross
    the boundary during optimisation.
    """
    weight = np.asarray(evidence.edge_weight, dtype=np.float32)
    edges = weight > 0
    strong = weight >= 1.0

    if not edges.any():
        logger.warning("User edge map is empty; curve alignment has nothing to read")
        big = np.full(weight.shape, 1e6, dtype=np.float32)
        return UserField(
            distance_px=big,
            orientation=np.zeros_like(big),
            edge=edges,
            validity=np.zeros_like(big),
            height=weight.shape[0],
            width=weight.shape[1],
        )

    distance_all = distance_transform_edt(~edges).astype(np.float32)
    if strong.any():
        distance_strong = distance_transform_edt(~strong).astype(np.float32)
        distance = np.minimum(
            distance_strong,
            distance_all + float(config.straight_line_distance_penalty_px),
        )
    else:
        distance = distance_all + float(config.straight_line_distance_penalty_px)

    # Orientation of the edge structure, from the gradient of a blurred edge
    # map. The gradient points across the edge, which is what ICP compares.
    blurred = gaussian_filter(weight, sigma=2.0)
    gy, gx = np.gradient(blurred)
    orientation = np.mod(np.arctan2(gy, gx), np.pi).astype(np.float32)

    text_mask = np.asarray(getattr(evidence, "text_mask", None))
    if text_mask.ndim == 2 and text_mask.any():
        validity = gaussian_filter((~text_mask).astype(np.float32), sigma=2.0)
        validity = np.clip(validity, 0.0, 1.0).astype(np.float32)
    else:
        validity = np.ones_like(distance, dtype=np.float32)

    return UserField(
        distance_px=distance,
        orientation=orientation,
        edge=edges,
        validity=validity,
        height=weight.shape[0],
        width=weight.shape[1],
    )


def _sample_bilinear(field: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Bilinear lookup at floating pixel positions, edge-clamped."""
    coords = np.vstack([y.ravel(), x.ravel()])
    out = map_coordinates(field, coords, order=1, mode="nearest")
    return out.reshape(x.shape)


# --------------------------------------------------------------------------
# Robust loss
# --------------------------------------------------------------------------


def tukey_loss(z: np.ndarray) -> np.ndarray:
    """Tukey biweight for `scipy.optimize.least_squares`, normalised to c = 1.

    Pass the real cutoff as ``f_scale``; scipy evaluates this at ``(f/f_scale)**2``.

    Tukey rather than Huber because schematic maps carry huge outlier fractions:
    a large share of a drawn outline can be invented. Huber down-weights
    outliers and still lets them pull; Tukey's derivative reaches exactly zero,
    so beyond the cutoff a sample contributes nothing at all. scipy has no
    built-in Tukey, and its `cauchy` is redescending but never reaches zero,
    which defeats the point.
    """
    z = np.asarray(z, dtype=float)
    inlier = z <= 1.0
    u = np.where(inlier, z, 1.0)

    rho = np.empty((3, z.size), dtype=float)
    rho[0] = np.where(inlier, (1.0 - (1.0 - u) ** 3) / 6.0, 1.0 / 6.0)
    rho[1] = np.where(inlier, 0.5 * (1.0 - u) ** 2, 0.0)
    rho[2] = np.where(inlier, -(1.0 - u), 0.0)
    return rho


# --------------------------------------------------------------------------
# Problem setup
# --------------------------------------------------------------------------


@dataclass
class CurveSamples:
    """Reference curve points, in EPSG:3857, with a normal step."""

    xy: np.ndarray  # (n, 2)
    xy_normal: np.ndarray  # (n, 2), one reference pixel along the curve normal

    def __len__(self) -> int:
        return int(self.xy.shape[0])


def build_curve_samples(
    layers: Any,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    use_coastline: bool = True,
    use_lakes: Optional[bool] = None,
    use_rivers: Optional[bool] = None,
) -> CurveSamples:
    """Reference curve samples, projected to EPSG:3857.

    Which layers count as evidence is a choice, not a given: alignment runs
    coastline-first and admits lakes afterwards, and rivers are off by default
    (see `GeorefConfig.use_rivers_for_alignment`).
    """
    if use_lakes is None:
        use_lakes = config.use_lakes_for_alignment
    if use_rivers is None:
        use_rivers = config.use_rivers_for_alignment

    mask = layers.curve_mask(
        use_coastline=use_coastline, use_lakes=use_lakes, use_rivers=use_rivers
    )
    lon, lat, dlon, dlat = layers.sample_curve_points_with_normals(
        spacing_px=config.curve_sample_spacing_px,
        max_points=config.curve_max_samples,
        mask=mask,
    )
    if lon.size == 0:
        empty = np.zeros((0, 2))
        return CurveSamples(xy=empty, xy_normal=empty)

    keep = np.hypot(dlon, dlat) > 0
    lon, lat, dlon, dlat = lon[keep], lat[keep], dlon[keep], dlat[keep]

    xy = np.array([lonlat_to_webmercator(a, b) for a, b in zip(lon, lat)])
    xy_n = np.array(
        [lonlat_to_webmercator(a, b) for a, b in zip(lon + dlon, lat + dlat)]
    )
    return CurveSamples(xy=xy, xy_normal=xy_n)


def _params_from_model(model: AffineModel) -> np.ndarray:
    m = model.matrix
    return np.array([m[0, 0], m[0, 1], m[0, 2], m[1, 0], m[1, 1], m[1, 2]], float)


def _model_from_params(params: np.ndarray, n_points: int = 0) -> AffineModel:
    a, b, tx, c, d, ty = params
    matrix = np.array([[a, b, tx], [c, d, ty], [0.0, 0.0, 1.0]], dtype=float)
    return AffineModel(matrix=matrix, n_points=n_points)


def _to_pixel(params: np.ndarray, xy: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Push EPSG:3857 coordinates into image pixels, i.e. apply the inverse."""
    a, b, tx, c, d, ty = params
    det = a * d - b * c
    if abs(det) < 1e-12:
        raise ValueError("Singular affine during alignment")
    X = xy[:, 0] - tx
    Y = xy[:, 1] - ty
    return (d * X - b * Y) / det, (-c * X + a * Y) / det


def _gcp_arrays(
    control_points: Sequence[ControlPoint],
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    pixel = np.array([cp.pixel for cp in control_points], dtype=float)
    merc = np.array(
        [lonlat_to_webmercator(lon, lat) for lon, lat in (c.geo for c in control_points)]
    )
    sigma = np.array(
        [max(gcp_sigma_px(cp.source, config), 1e-6) for cp in control_points]
    )
    return pixel, merc, sigma


# --------------------------------------------------------------------------
# Phase A -- chamfer
# --------------------------------------------------------------------------


def _residuals(
    params: np.ndarray,
    gcp_pixel: Optional[np.ndarray],
    gcp_merc: Optional[np.ndarray],
    gcp_weight: Optional[np.ndarray],
    samples: Optional[np.ndarray],
    sample_weight: Optional[np.ndarray],
    distance: Optional[np.ndarray],
    validity: Optional[np.ndarray],
    correspondences: Optional[np.ndarray] = None,
) -> np.ndarray:
    parts: List[np.ndarray] = []

    if gcp_pixel is not None and gcp_pixel.shape[0]:
        sx, sy = _to_pixel(params, gcp_merc)
        w = np.sqrt(gcp_weight)
        parts.append(((sx - gcp_pixel[:, 0]) * w).ravel())
        parts.append(((sy - gcp_pixel[:, 1]) * w).ravel())

    if samples is not None and samples.shape[0]:
        sx, sy = _to_pixel(params, samples)
        if correspondences is not None:
            # Phase B: explicit point-to-point correspondences.
            w = np.sqrt(sample_weight)
            parts.append(((sx - correspondences[:, 0]) * w).ravel())
            parts.append(((sy - correspondences[:, 1]) * w).ravel())
        else:
            # Phase A: read the distance field, scaled by how much we can see.
            d = _sample_bilinear(distance, sx, sy)
            v = _sample_bilinear(validity, sx, sy)
            parts.append((d * v * np.sqrt(sample_weight)).ravel())

    if not parts:
        return np.zeros(1)
    return np.concatenate(parts)


def chamfer_residual_px(
    model: AffineModel,
    samples: CurveSamples,
    user_field: UserField,
    trim: float = 0.7,
) -> float:
    """Mean distance from projected reference samples to the nearest user edge.

    Trimmed, because a schematic map legitimately has a large outlier tail and
    the untrimmed mean would be dominated by coastline the user simply never
    drew. Used to answer "did the curve term engage at all" -- never to argue a
    fit is *correct*, since a fit locked onto the wrong feature scores well here
    by construction.
    """
    if len(samples) == 0:
        return float("nan")
    sx, sy = _to_pixel(_params_from_model(model), samples.xy)
    inside = (
        (sx >= 0) & (sx < user_field.width) & (sy >= 0) & (sy < user_field.height)
    )
    if not inside.any():
        return float("nan")
    d = _sample_bilinear(user_field.distance_px, sx[inside], sy[inside])
    v = _sample_bilinear(user_field.validity, sx[inside], sy[inside])
    d = d[v > 0.5]
    if d.size == 0:
        return float("nan")
    keep = max(int(d.size * trim), 1)
    return float(np.sort(d)[:keep].mean())


def sample_displacement_px(
    before: AffineModel, after: AffineModel, samples: CurveSamples
) -> float:
    """Median distance the reference samples moved between two transforms."""
    if len(samples) == 0:
        return float("nan")
    bx, by = _to_pixel(_params_from_model(before), samples.xy)
    ax, ay = _to_pixel(_params_from_model(after), samples.xy)
    return float(np.median(np.hypot(ax - bx, ay - by)))


@dataclass
class PhaseResult:
    model: AffineModel
    converged: bool
    inlier_fraction: float
    cost: float
    iterations: int
    detail: Dict[str, Any] = field(default_factory=dict)


def fit_chamfer(
    initial: AffineModel,
    control_points: Sequence[ControlPoint],
    samples: CurveSamples,
    user_field: UserField,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    use_gcps: bool = True,
    gcp_weight_scale: float = 1.0,
    blur_schedule: Optional[Sequence[float]] = None,
    cutoff_schedule: Optional[Sequence[float]] = None,
) -> PhaseResult:
    """Phase A: annealed chamfer fit.

    ``use_gcps=False`` gives the probe fit of section 10.3 -- curve evidence
    alone, control points held out entirely so they remain an independent check.
    """
    blur = list(blur_schedule if blur_schedule is not None else config.anneal_blur_px)
    cutoffs = list(
        cutoff_schedule if cutoff_schedule is not None else config.anneal_cutoff_px
    )
    if len(cutoffs) != len(blur):
        cutoffs = (cutoffs * len(blur))[: len(blur)]

    n_samples = len(samples)
    if n_samples == 0:
        return PhaseResult(initial, False, 0.0, float("inf"), 0, {"reason": "no samples"})

    gcp_pixel = gcp_merc = gcp_w = None
    if use_gcps and control_points:
        gcp_pixel, gcp_merc, sigma = _gcp_arrays(control_points, config)
        # Normalise by count so seven control points are not drowned by
        # thousands of curve samples, then weight by 1/sigma**2 within the term.
        rel = (np.median(sigma) / sigma) ** 2
        gcp_w = (
            config.weight_gcp * gcp_weight_scale / max(len(control_points), 1)
        ) * rel

    sample_w = np.full(n_samples, config.weight_curve / n_samples)

    params = _params_from_model(initial)
    total_iterations = 0
    converged = False
    cost = float("inf")
    inlier_fraction = 0.0

    for level, (sigma_px, cutoff) in enumerate(zip(blur, cutoffs)):
        distance = user_field.blurred_distance(sigma_px)
        try:
            solution = least_squares(
                _residuals,
                params,
                args=(
                    gcp_pixel,
                    gcp_merc,
                    gcp_w,
                    samples.xy,
                    sample_w,
                    distance,
                    user_field.validity,
                ),
                loss=tukey_loss,
                f_scale=float(cutoff) * math.sqrt(config.weight_curve / n_samples),
                method="trf",
                max_nfev=config.max_iterations_per_level * 7,
            )
        except Exception as e:
            logger.warning(f"Chamfer level {level} failed: {e}")
            break

        params = solution.x
        total_iterations += int(solution.nfev)
        converged = bool(solution.success)
        cost = float(solution.cost)

        scaled = np.abs(solution.fun) / max(
            float(cutoff) * math.sqrt(config.weight_curve / n_samples), 1e-12
        )
        inlier_fraction = float((scaled <= 1.0).mean())

    model = _model_from_params(params, n_points=len(control_points))
    return PhaseResult(
        model=model,
        converged=converged,
        inlier_fraction=inlier_fraction,
        cost=cost,
        iterations=total_iterations,
        detail={"levels": len(blur)},
    )


# --------------------------------------------------------------------------
# Phase B -- normal-search ICP
# --------------------------------------------------------------------------


def find_correspondences(
    params: np.ndarray,
    samples: CurveSamples,
    user_field: UserField,
    radius_px: float,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Search along each reference normal for an orientation-matching edge.

    Returns ``(index, target_xy, weight)`` for the samples that matched.

    The orientation test is the reason this phase exists. A chamfer distance
    cannot tell a coastline from a political border crossing it -- both are just
    nearby edge pixels. Requiring the matched edge's local orientation to agree
    with the reference curve's rejects the crossing outright.
    """
    n = len(samples)
    if n == 0:
        return np.zeros(0, dtype=int), np.zeros((0, 2)), np.zeros(0)

    sx, sy = _to_pixel(params, samples.xy)
    nx_px, ny_px = _to_pixel(params, samples.xy_normal)
    dx, dy = nx_px - sx, ny_px - sy
    length = np.hypot(dx, dy)
    ok = length > 1e-9
    dx = np.where(ok, dx / np.where(ok, length, 1.0), 0.0)
    dy = np.where(ok, dy / np.where(ok, length, 1.0), 0.0)

    # The reference normal's own direction, as an angle across the curve.
    reference_angle = np.mod(np.arctan2(dy, dx), np.pi)
    tolerance = math.radians(config.icp_orientation_tolerance_deg)

    steps = np.arange(0.0, float(radius_px) + 1.0, 1.0)
    best_distance = np.full(n, np.inf)
    best_x = np.zeros(n)
    best_y = np.zeros(n)
    found = np.zeros(n, dtype=bool)

    for step in steps:
        for sign in (1.0, -1.0):
            if step == 0.0 and sign < 0:
                continue
            qx = sx + sign * step * dx
            qy = sy + sign * step * dy

            inside = (
                (qx >= 0) & (qx < user_field.width) & (qy >= 0) & (qy < user_field.height)
            )
            candidate = inside & ~found & ok
            if not candidate.any():
                continue

            ix = np.clip(qx.astype(int), 0, user_field.width - 1)
            iy = np.clip(qy.astype(int), 0, user_field.height - 1)

            on_edge = user_field.edge[iy, ix] & candidate
            if not on_edge.any():
                continue

            angle = user_field.orientation[iy, ix]
            delta = np.abs(angle - reference_angle)
            delta = np.minimum(delta, np.pi - delta)  # orientation, not direction
            aligned = on_edge & (delta <= tolerance)
            if not aligned.any():
                continue

            best_distance = np.where(aligned, step, best_distance)
            best_x = np.where(aligned, qx, best_x)
            best_y = np.where(aligned, qy, best_y)
            found = found | aligned

        if found.all():
            break

    index = np.flatnonzero(found)
    if index.size == 0:
        return index, np.zeros((0, 2)), np.zeros(0)

    tx = best_x[index]
    ty = best_y[index]
    ix = np.clip(tx.astype(int), 0, user_field.width - 1)
    iy = np.clip(ty.astype(int), 0, user_field.height - 1)

    # Confidence applied at correspondence time, before the robust loss sees it:
    # how much we can see there, and how much we trust that edge.
    weight = user_field.validity[iy, ix].astype(float)
    return index, np.column_stack([tx, ty]), weight


def icp_refine(
    initial: AffineModel,
    control_points: Sequence[ControlPoint],
    samples: CurveSamples,
    user_field: UserField,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    use_gcps: bool = True,
    gcp_weight_scale: float = 1.0,
) -> PhaseResult:
    """Phase B: iterate correspondence search and re-fit."""
    params = _params_from_model(initial)
    radii = list(config.icp_search_radius_px) or [20.0]

    gcp_pixel = gcp_merc = gcp_w = None
    if use_gcps and control_points:
        gcp_pixel, gcp_merc, sigma = _gcp_arrays(control_points, config)
        rel = (np.median(sigma) / sigma) ** 2
        gcp_w = (
            config.weight_gcp * gcp_weight_scale / max(len(control_points), 1)
        ) * rel

    matched = 0
    converged = False
    cost = float("inf")
    iterations = 0

    for iteration in range(int(config.icp_iterations)):
        radius = radii[min(iteration, len(radii) - 1)]
        index, targets, conf = find_correspondences(
            params, samples, user_field, radius, config
        )
        matched = int(index.size)
        if matched < int(config.icp_min_correspondences):
            logger.info(
                f"ICP stopped at iteration {iteration}: only {matched} correspondences"
            )
            break

        subset = samples.xy[index]
        weight = conf * (config.weight_curve / max(matched, 1))

        try:
            solution = least_squares(
                _residuals,
                params,
                args=(
                    gcp_pixel,
                    gcp_merc,
                    gcp_w,
                    subset,
                    weight,
                    None,
                    None,
                    targets,
                ),
                loss=tukey_loss,
                f_scale=float(config.icp_cutoff_px)
                * math.sqrt(config.weight_curve / max(matched, 1)),
                method="trf",
                max_nfev=config.max_iterations_per_level * 7,
            )
        except Exception as e:
            logger.warning(f"ICP iteration {iteration} failed: {e}")
            break

        params = solution.x
        converged = bool(solution.success)
        cost = float(solution.cost)
        iterations += int(solution.nfev)

    inlier_fraction = matched / max(len(samples), 1)
    return PhaseResult(
        model=_model_from_params(params, n_points=len(control_points)),
        converged=converged,
        inlier_fraction=inlier_fraction,
        cost=cost,
        iterations=iterations,
        detail={"correspondences": matched},
    )
