"""Coarse chamfer alignment and normal-search ICP: the optimiser.

Two phases (dev-docs/georeferencing.md section 5.2). Both optimise the same six affine parameters, and
both express every residual in **user image pixels**. The two terms do not share
a loss: control points are plain least squares, and only the curve term is
robust (Tukey, cutoff in pixels). A shared loss used to reject the control
points in the fine stages -- see dev-docs/georeferencing-history.md, 2026-09-30.

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

**The result is checked, never trusted** (`gates.py`). A fit locked onto the
wrong feature has *low* chamfer residual by construction, so the residual's
size is never the check.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates
from scipy.optimize import least_squares

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .affine import AffineModel
from .control_points import ControlPoint, gcp_sigma_px
from .projection import lonlat_to_webmercator

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
    "no data" rather than "the nearest edge is 60 px away" -- see
    georeferencing-history.md, Steps 0-3. Blurred rather than hard, so the objective stays smooth as samples cross
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
    # Outside the image we cannot see either. Every lookup clamps to the
    # nearest pixel, so the border row and column are set to 0 and ramp up
    # inwards: a sample that leaves the image fades out smoothly instead of
    # reading the distance field at the border -- which made the image frame
    # an attractor for every reference point the framing box puts off-map.
    validity *= _border_ramp(validity.shape, BORDER_RAMP_PX)

    return UserField(
        distance_px=distance,
        orientation=orientation,
        edge=edges,
        validity=validity,
        height=weight.shape[0],
        width=weight.shape[1],
    )


#: Width, in pixels, of the ramp that takes validity from 0 on the image's
#: outermost pixels to 1 inside.
BORDER_RAMP_PX = 3.0


def _border_ramp(shape_hw: Tuple[int, int], width_px: float) -> np.ndarray:
    """0 on the outermost pixels, rising linearly to 1 at *width_px* inside."""
    height, width = shape_hw
    rows = np.arange(height, dtype=np.float32)
    cols = np.arange(width, dtype=np.float32)
    to_edge_y = np.minimum(rows, height - 1 - rows)
    to_edge_x = np.minimum(cols, width - 1 - cols)
    to_edge = np.minimum(to_edge_y[:, None], to_edge_x[None, :])
    return np.clip(to_edge / max(float(width_px), 1e-6), 0.0, 1.0).astype(np.float32)


def _sample_bilinear(field: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Bilinear lookup at floating pixel positions, edge-clamped."""
    coords = np.vstack([y.ravel(), x.ravel()])
    out = map_coordinates(field, coords, order=1, mode="nearest")
    return out.reshape(x.shape)


# --------------------------------------------------------------------------
# Robust loss
# --------------------------------------------------------------------------


def tukey_loss(z: np.ndarray) -> np.ndarray:
    """Tukey biweight, normalised to c = 1, in scipy's loss convention.

    Evaluated at ``z = (r/c)**2``; returns ``[rho, rho', rho'']``. Used through
    :func:`tukey_residual`, which applies it to the curve residuals only.

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


def tukey_residual(r: np.ndarray, cutoff_px: float) -> np.ndarray:
    """A residual whose square is the Tukey cost of *r* at *cutoff_px*.

    ``c * sqrt(2 * rho((r/c)**2))``: equal to ``|r|`` near zero, flat at
    ``c / sqrt(3)`` from the cutoff on, so beyond it a sample pulls on nothing.

    This is how the curve term gets its robust loss while the control-point
    term stays plain least squares. scipy's ``loss`` argument applies one loss
    with one ``f_scale`` to *every* residual; sized for thousands of curve
    samples, that scale rejected any control point more than a pixel or two
    off in the fine stages, so the "joint" fit was a curve-only fit in practice.
    """
    c = max(float(cutoff_px), 1e-9)
    r = np.asarray(r, dtype=float)
    rho = tukey_loss((r / c).ravel() ** 2)[0].reshape(r.shape)
    return c * np.sqrt(2.0 * np.maximum(rho, 0.0))


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
) -> CurveSamples:
    """Reference curve samples, projected to EPSG:3857.

    Which layers count as evidence is a choice, not a given: alignment runs
    coastline-first and admits lakes afterwards.
    """
    if use_lakes is None:
        use_lakes = config.use_lakes_for_alignment

    mask = layers.curve_mask(use_coastline=use_coastline, use_lakes=use_lakes)
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


def _gcp_term(
    control_points: Sequence[ControlPoint],
    config: GeorefConfig,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Control-point pixels, targets and per-point weights for the objective.

    Normalised by count so seven control points are not drowned by thousands
    of curve samples, then weighted by 1/sigma**2 within the term. The term is
    plain least squares (see `_residuals`), so these weights are what decides
    how hard the points pull -- the robust cutoff never reaches them.
    """
    pixel, merc, sigma = _gcp_arrays(control_points, config)
    rel = (np.median(sigma) / sigma) ** 2
    weight = (config.weight_gcp / max(len(control_points), 1)) * rel
    return pixel, merc, weight


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
    cutoff_px: float = 1.0,
) -> np.ndarray:
    """Residuals for ``least_squares`` with ``loss="linear"``.

    The control-point term is plain least squares: every point pulls in
    proportion to its error, however large. Only the curve term is robust,
    through :func:`tukey_residual` at *cutoff_px*. Its cost per sample is
    ``weight * (v * rho(d) + (1 - v) * rho_max)``: where validity ``v`` is 0
    (a label, off the image) the sample is treated as an outlier -- a flat
    cost that exerts no pull, as masked text calls for, without making the
    unseen regions a place the optimiser can hide samples for free.
    """
    parts: List[np.ndarray] = []

    if gcp_pixel is not None and gcp_pixel.shape[0]:
        sx, sy = _to_pixel(params, gcp_merc)
        w = np.sqrt(gcp_weight)
        parts.append(((sx - gcp_pixel[:, 0]) * w).ravel())
        parts.append(((sy - gcp_pixel[:, 1]) * w).ravel())

    if samples is not None and samples.shape[0]:
        sx, sy = _to_pixel(params, samples)
        w = np.sqrt(sample_weight)
        if correspondences is not None:
            # Phase B: point-to-point. Tukey applies to the distance, then the
            # scaled vector keeps its direction for the solver.
            dx = sx - correspondences[:, 0]
            dy = sy - correspondences[:, 1]
            r = np.hypot(dx, dy)
            scale = np.where(
                r > 1e-12, tukey_residual(r, cutoff_px) / np.maximum(r, 1e-12), 1.0
            )
            parts.append((dx * scale * w).ravel())
            parts.append((dy * scale * w).ravel())
        else:
            # Phase A: read the distance field where we can see. Where we
            # cannot (off the image, under a label) the sample costs what an
            # outlier costs: a constant, so it neither pulls the fit (the old
            # border clamp did) nor rewards it for hiding samples there (a
            # zero cost would make "push the coast off the map" the optimum).
            d = _sample_bilinear(distance, sx, sy)
            v = np.clip(_sample_bilinear(validity, sx, sy), 0.0, 1.0)
            seen = tukey_residual(d, cutoff_px)
            unseen = float(cutoff_px) / math.sqrt(3.0)
            parts.append((np.sqrt(v * seen**2 + (1.0 - v) * unseen**2) * w).ravel())

    if not parts:
        return np.zeros(1)
    return np.concatenate(parts)


def _samples_in_view(
    params: np.ndarray, samples: CurveSamples, user_field: "UserField"
) -> np.ndarray:
    """Which samples project somewhere we can see: inside the image, not
    under a label. The denominator of every per-sample fraction."""
    sx, sy = _to_pixel(params, samples.xy)
    return _sample_bilinear(user_field.validity, sx, sy) > 0.5


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
    blur_schedule: Optional[Sequence[float]] = None,
    cutoff_schedule: Optional[Sequence[float]] = None,
) -> PhaseResult:
    """Phase A: annealed chamfer fit.

    ``use_gcps=False`` fits the curve evidence alone, control points held out.
    The pipeline never does; tests use it to show the joint fit differs.
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
        gcp_pixel, gcp_merc, gcp_w = _gcp_term(control_points, config)

    params = _params_from_model(initial)
    total_iterations = 0
    converged = False
    cost = float("inf")
    inlier_fraction = 0.0
    in_view = 0

    for level, (sigma_px, cutoff) in enumerate(zip(blur, cutoffs)):
        distance = user_field.blurred_distance(sigma_px)
        # The evidence for this level is the samples in view at its start,
        # frozen for the solve -- the way ICP freezes its correspondences.
        # Letting the set change mid-solve biases the fit whatever an unseen
        # sample costs: at 0, pushing the coast off the map is free; at the
        # outlier cost, squeezing off-map coast into view pays. Frozen, an
        # active sample that leaves view costs the outlier constant and an
        # inactive one costs nothing, so neither move is rewarded. The term is
        # normalised by this count, so it does not weaken against the control
        # points just because the framing box puts coast off the map.
        active = _samples_in_view(params, samples, user_field)
        n_active = int(active.sum())
        sample_w = np.full(n_active, config.weight_curve / max(n_active, 1))
        try:
            solution = least_squares(
                _residuals,
                params,
                args=(
                    gcp_pixel,
                    gcp_merc,
                    gcp_w,
                    samples.xy[active],
                    sample_w,
                    distance,
                    user_field.validity,
                    None,
                    float(cutoff),
                ),
                loss="linear",
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

        # Share of the samples we can see that sit within the cutoff. Samples
        # off the image or under a label are neither inliers nor outliers.
        sx, sy = _to_pixel(params, samples.xy)
        seen = _samples_in_view(params, samples, user_field)
        in_view = int(seen.sum())
        if in_view:
            d = _sample_bilinear(distance, sx[seen], sy[seen])
            inlier_fraction = float((d <= float(cutoff)).mean())
        else:
            inlier_fraction = 0.0

    model = _model_from_params(params, n_points=len(control_points))
    return PhaseResult(
        model=model,
        converged=converged,
        inlier_fraction=inlier_fraction,
        cost=cost,
        iterations=total_iterations,
        detail={"levels": len(blur), "samplesInView": in_view},
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
) -> PhaseResult:
    """Phase B: iterate correspondence search and re-fit."""
    params = _params_from_model(initial)
    radii = list(config.icp_search_radius_px) or [20.0]

    gcp_pixel = gcp_merc = gcp_w = None
    if use_gcps and control_points:
        gcp_pixel, gcp_merc, gcp_w = _gcp_term(control_points, config)

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
                    float(config.icp_cutoff_px),
                ),
                loss="linear",
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

    # Matched over the samples that could have matched: correspondences are
    # only searched inside the image and off the labels, so counting the
    # coastline the framing box puts off the map would read as a collapse.
    in_view = int(_samples_in_view(params, samples, user_field).sum())
    inlier_fraction = matched / max(in_view, 1)
    return PhaseResult(
        model=_model_from_params(params, n_points=len(control_points)),
        converged=converged,
        inlier_fraction=float(min(inlier_fraction, 1.0)),
        cost=cost,
        iterations=iterations,
        detail={"correspondences": matched, "samplesInView": in_view},
    )
