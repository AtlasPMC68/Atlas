"""The gates: named checks that decide whether an aligned model may ship.

Plan section 8.2. Three available signals with distinct roles:

    chamfer residual      diagnostic only -- **never** a gate, because a fit
                          locked onto the wrong feature has a *low* residual by
                          construction
    probe GCP disagreement  primary gate, always available -- the probe fit never
                          sees the control points, so measuring it against them
                          is genuinely independent of the curve objective
    water-mask IoU        secondary gate, when a water mask exists -- area
                          overlap is a different measurement from curve
                          distance, so it catches different failures

Every check is returned whether or not it applied, and all of them are logged
every run. Which check actually discriminates real failures is a corpus-level
question (roadmap section 5), and it can only be answered by aggregating runs
where the check passed too.
"""

import logging
import math
from typing import Any, List, Optional, Sequence

import numpy as np

from .align import _gcp_arrays, _params_from_model, _to_pixel, PhaseResult
from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .models import AffineModel, ControlPoint
from .projection import R_EARTH
from .records import GateCheck

logger = logging.getLogger(__name__)


def gcp_rms_px(model: AffineModel, control_points: Sequence[ControlPoint]) -> float:
    """RMS distance, in image pixels, from a model's prediction to each GCP."""
    if not control_points:
        return float("nan")
    pixel, merc, _sigma = _gcp_arrays(control_points)
    sx, sy = _to_pixel(_params_from_model(model), merc)
    return float(np.sqrt(np.mean((sx - pixel[:, 0]) ** 2 + (sy - pixel[:, 1]) ** 2)))


def similarity_of(model: AffineModel) -> tuple:
    """(scale, rotation in degrees, determinant) of the linear block."""
    a, b = float(model.matrix[0, 0]), float(model.matrix[0, 1])
    c, d = float(model.matrix[1, 0]), float(model.matrix[1, 1])
    determinant = a * d - b * c
    scale = math.sqrt(abs(determinant))
    rotation = math.degrees(math.atan2(c, a))
    return scale, rotation, determinant


def water_mask_iou(model: AffineModel, layers: Any, evidence: Any) -> Optional[float]:
    """Overlap of the user's water mask with the reference water, warped in.

    Compared against ``layers.water`` -- ocean *and* lake surfaces -- never
    against ocean alone. A blue pipette selects both, while the reference
    ``land`` raster counts lake interiors as land, so comparing against ocean
    alone scores a correct alignment as wrong: measured, harmless where the
    framing box has coast (IoU 0.97) and total where it does not (0.00, lakes
    being the only water there). A box without coastline is exactly where
    alignment is weakest and this gate matters most.

    Returns None when either side has no water, which makes the gate
    inapplicable rather than failed.
    """
    user_water = np.asarray(getattr(evidence, "water", None))
    if user_water.ndim != 2 or not user_water.any():
        return None
    if not getattr(layers, "has_water", False):
        return None

    height, width = user_water.shape
    cols = np.arange(width, dtype=float) + 0.5
    rows = np.arange(height, dtype=float) + 0.5
    px, py = np.meshgrid(cols, rows)

    # image pixels -> EPSG:3857 -> lon/lat -> reference raster
    X, Y = model(px.ravel(), py.ravel())
    lon = np.degrees(X / R_EARTH)
    lat = np.degrees(2.0 * np.arctan(np.exp(Y / R_EARTH)) - np.pi / 2.0)
    rx, ry = layers.grid.to_pixel(lon, lat)

    inside = (
        (rx >= 0) & (rx < layers.grid.width) & (ry >= 0) & (ry < layers.grid.height)
    )
    reference = np.zeros(px.size, dtype=bool)
    ix = np.clip(rx.astype(int), 0, layers.grid.width - 1)
    iy = np.clip(ry.astype(int), 0, layers.grid.height - 1)
    reference[inside] = layers.water[iy[inside], ix[inside]]
    reference = reference.reshape(height, width)

    union = int((user_water | reference).sum())
    if union == 0:
        return None
    return float(int((user_water & reference).sum()) / union)


def evaluate_gates(
    candidate: AffineModel,
    baseline: AffineModel,
    probe: Optional[AffineModel],
    control_points: Sequence[ControlPoint],
    layers: Any,
    evidence: Any,
    phase: PhaseResult,
    ground_meters_per_pixel: Optional[float] = None,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    baseline_chamfer_px: Optional[float] = None,
    aligned_chamfer_px: Optional[float] = None,
) -> List[GateCheck]:
    """Run every check. Returns them all, applicable or not."""
    checks: List[GateCheck] = []
    baseline_rms = gcp_rms_px(baseline, control_points)

    # --- primary -------------------------------------------------------------
    if probe is not None and control_points:
        probe_rms = gcp_rms_px(probe, control_points)
        threshold = max(baseline_rms * config.gate_probe_gcp_ratio, 1e-6)
        probe_km = None
        absolute_ok = True
        if ground_meters_per_pixel:
            probe_km = probe_rms * ground_meters_per_pixel / 1000.0
            absolute_ok = probe_km <= config.gate_probe_gcp_max_km
        checks.append(
            GateCheck(
                name="probe_gcp_disagreement",
                value=float(probe_rms),
                threshold=float(threshold),
                applicable=True,
                passed=bool(probe_rms <= threshold and absolute_ok),
                detail=(
                    f"curve-only fit misses held-out GCPs by {probe_rms:.1f}px"
                    + (f" ({probe_km:.1f}km)" if probe_km is not None else "")
                    + f"; GCP-only baseline {baseline_rms:.1f}px"
                ),
            )
        )
    else:
        checks.append(
            GateCheck(
                name="probe_gcp_disagreement",
                applicable=False,
                passed=True,
                detail="no probe fit or no control points",
            )
        )

    # --- secondary -----------------------------------------------------------
    iou = water_mask_iou(candidate, layers, evidence)
    checks.append(
        GateCheck(
            name="water_mask_iou",
            value=None if iou is None else float(iou),
            threshold=float(config.gate_water_iou_min),
            applicable=iou is not None,
            passed=True if iou is None else bool(iou >= config.gate_water_iou_min),
            detail=(
                "no water on one side or the other"
                if iou is None
                else "user water vs reference ocean + lakes"
            ),
        )
    )

    # --- transform sanity ----------------------------------------------------
    base_scale, base_rotation, base_det = similarity_of(baseline)
    scale, rotation, determinant = similarity_of(candidate)

    checks.append(
        GateCheck(
            name="transform_determinant",
            value=float(determinant),
            threshold=0.0,
            applicable=True,
            passed=bool(determinant * base_det > 0),
            detail="a sign flip is a mirror or a fold",
        )
    )

    drift = abs(scale / base_scale - 1.0) if base_scale else float("inf")
    checks.append(
        GateCheck(
            name="scale_drift",
            value=float(drift),
            threshold=float(config.gate_max_scale_drift),
            applicable=True,
            passed=bool(drift <= config.gate_max_scale_drift),
            detail=f"scale moved {drift * 100:.1f}% from the GCP-only affine",
        )
    )

    turn = abs((rotation - base_rotation + 180.0) % 360.0 - 180.0)
    checks.append(
        GateCheck(
            name="rotation_drift",
            value=float(turn),
            threshold=float(config.gate_max_rotation_deg),
            applicable=True,
            passed=bool(turn <= config.gate_max_rotation_deg),
            detail=f"rotated {turn:.1f} degrees from the GCP-only affine",
        )
    )

    # --- did the curve term engage at all? -----------------------------------
    # Note carefully what this is and is not. Residual *magnitude* is never a
    # gate: a fit locked onto the wrong feature scores well by construction.
    # This checks that the residual *improved*, which is a convergence question.
    # It exists because a fit that never moved passes every other check here --
    # scale drift zero, rotation zero, optimizer "converged" -- and so returns
    # the baseline wearing a success label. Without it, a map whose starting
    # transform was too far off for the chamfer to reach looks identical to one
    # that aligned perfectly.
    if (
        baseline_chamfer_px is not None
        and aligned_chamfer_px is not None
        and math.isfinite(baseline_chamfer_px)
        and math.isfinite(aligned_chamfer_px)
        and baseline_chamfer_px > 1e-6
    ):
        improvement = 1.0 - (aligned_chamfer_px / baseline_chamfer_px)
        checks.append(
            GateCheck(
                name="curve_fit_engaged",
                value=float(improvement),
                threshold=float(config.gate_min_chamfer_improvement),
                applicable=True,
                passed=bool(improvement >= config.gate_min_chamfer_improvement),
                detail=(
                    f"trimmed chamfer {baseline_chamfer_px:.1f}px -> "
                    f"{aligned_chamfer_px:.1f}px ({improvement:+.1%}); below the "
                    "threshold means the curve term never engaged, not that the "
                    "fit is wrong"
                ),
            )
        )
    else:
        checks.append(
            GateCheck(
                name="curve_fit_engaged",
                applicable=False,
                passed=True,
                detail="no chamfer residual available",
            )
        )

    # --- optimizer health ----------------------------------------------------
    checks.append(
        GateCheck(
            name="optimizer_converged",
            value=1.0 if phase.converged else 0.0,
            threshold=1.0,
            applicable=True,
            passed=bool(phase.converged),
            detail=f"{phase.iterations} function evaluations",
        )
    )
    checks.append(
        GateCheck(
            name="inlier_fraction",
            value=float(phase.inlier_fraction),
            threshold=float(config.gate_min_inlier_fraction),
            applicable=True,
            passed=bool(phase.inlier_fraction >= config.gate_min_inlier_fraction),
            detail=(
                "a collapse here means the fit rests on a handful of samples, or "
                "that orientation filtering matched almost nothing -- wrong-feature "
                "lock caught in the act"
            ),
        )
    )

    return checks


def gates_passed(checks: Sequence[GateCheck]) -> bool:
    """Both gates must pass, plus transform sanity and optimizer health."""
    return all(check.passed for check in checks if check.applicable)


def failed_names(checks: Sequence[GateCheck]) -> List[str]:
    return [c.name for c in checks if c.applicable and not c.passed]
