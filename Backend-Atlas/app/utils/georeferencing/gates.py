"""Alignment: fit the coastline, check the result, keep it or fall back."""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .affine import AffineModel
from .align import (
    PhaseResult,
    _gcp_arrays,
    _params_from_model,
    _to_pixel,
    build_curve_samples,
    build_user_field,
    chamfer_residual_px,
    fit_chamfer,
    icp_refine,
    sample_displacement_px,
)
from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .control_points import ControlPoint
from .projection import R_EARTH
from .records import GateCheck, RunRecord

logger = logging.getLogger(__name__)

METHOD_JOINT = "joint"
METHOD_GCP_ONLY = "gcp_only"


# --------------------------------------------------------------------------
# Measurements
# --------------------------------------------------------------------------


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
    """Overlap of the user's water mask with the reference water, warped in."""

    user_water = np.asarray(evidence.water)
    if not getattr(layers, "has_water", False) or not user_water.any():
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


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def evaluate_gates(
    candidate: AffineModel,
    baseline: AffineModel,
    control_points: Sequence[ControlPoint],
    layers: Any,
    evidence: Any,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    baseline_chamfer_px: Optional[float] = None,
    aligned_chamfer_px: Optional[float] = None,
    ground_meters_per_pixel: Optional[float] = None,
) -> List[GateCheck]:
    """Run the four checks. Returns all of them, applicable or not."""
    checks: List[GateCheck] = []

    # --- not mirrored --------------------------------------------------------
    _s, _r, base_det = similarity_of(baseline)
    _s, _r, determinant = similarity_of(candidate)
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

    # --- the coastline fit did not get worse ---------------------------------
    # Residual *magnitude* is never a check: a fit locked onto the wrong
    # feature scores well by construction. This checks the residual did not
    # rise, which only a fit that went somewhere it should not can do.
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
                    f"{aligned_chamfer_px:.1f}px ({improvement:+.1%})"
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

    # --- the water still lines up --------------------------------------------
    # Area overlap is a different measurement from curve distance, so it
    # catches what the chamfer cannot: a fit that matched a coast-like line
    # but put the sea on the wrong side of it.
    base_iou = water_mask_iou(baseline, layers, evidence)
    aligned_iou = water_mask_iou(candidate, layers, evidence)
    if base_iou is not None and aligned_iou is not None:
        floor = base_iou - config.gate_water_iou_max_drop
        checks.append(
            GateCheck(
                name="water_agreement",
                value=float(aligned_iou),
                threshold=float(floor),
                applicable=True,
                passed=bool(aligned_iou >= floor),
                detail=(
                    f"water IoU {base_iou:.3f} with the control points alone,"
                    f" {aligned_iou:.3f} aligned"
                ),
            )
        )
    else:
        checks.append(
            GateCheck(
                name="water_agreement",
                applicable=False,
                passed=True,
                detail="no reference water in the framing box",
            )
        )

    # --- the user's clicks still hold ----------------------------------------
    # The fit trades the control points against the coastline, so it always
    # moves them a little; this only refuses a fit that moved them a lot.
    if control_points:
        base_rms = gcp_rms_px(baseline, control_points)
        aligned_rms = gcp_rms_px(candidate, control_points)
        shift = aligned_rms - base_rms
        limit = config.gate_max_gcp_shift_ratio_of_diagonal * math.hypot(
            evidence.width, evidence.height
        )
        km = (
            f" ({shift * ground_meters_per_pixel / 1000.0:.1f} km)"
            if ground_meters_per_pixel
            else ""
        )
        checks.append(
            GateCheck(
                name="control_points_held",
                value=float(shift),
                threshold=float(limit),
                applicable=True,
                passed=bool(shift <= limit),
                detail=(
                    f"control-point RMS {base_rms:.1f}px -> {aligned_rms:.1f}px,"
                    f" {shift:+.1f}px{km}"
                ),
            )
        )
    else:
        checks.append(
            GateCheck(
                name="control_points_held",
                applicable=False,
                passed=True,
                detail="no control points",
            )
        )

    return checks


def gates_passed(checks: Sequence[GateCheck]) -> bool:
    return all(check.passed for check in checks if check.applicable)


def failed_names(checks: Sequence[GateCheck]) -> List[str]:
    return [c.name for c in checks if c.applicable and not c.passed]


# --------------------------------------------------------------------------
# The attempt
# --------------------------------------------------------------------------


@dataclass
class AlignmentResult:
    """What alignment decided, and everything needed to explain it."""

    model: AffineModel
    method: str  # METHOD_JOINT | METHOD_GCP_ONLY
    gates: List[GateCheck] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    #: Why alignment never ran (a precondition), or None when it did.
    skipped: Optional[str] = None
    phase_models: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def used_curve_evidence(self) -> bool:
        return self.method != METHOD_GCP_ONLY


def skipped_alignment(
    baseline: AffineModel, reason: str, record: Optional[RunRecord] = None
) -> AlignmentResult:
    """The control-point affine, with the precondition that stopped alignment."""
    if record is not None:
        record.note(f"alignment skipped: {reason}")
    return AlignmentResult(model=baseline, method=METHOD_GCP_ONLY, skipped=reason)


def fit_stages(
    start: AffineModel,
    control_points: Sequence[ControlPoint],
    coast_samples: Any,
    fine_samples: Any,
    user_field: Any,
    config: GeorefConfig,
    gcp_targets: Optional[np.ndarray] = None,
) -> Tuple[AffineModel, PhaseResult, AffineModel]:
    """Coastline chamfer, then coastline + lakes, then ICP."""

    if config.enable_chamfer:
        coarse = fit_chamfer(
            start,
            control_points,
            coast_samples,
            user_field,
            config,
            use_gcps=True,
            blur_schedule=config.coarse_blur_px,
            cutoff_schedule=config.coarse_cutoff_px,
            gcp_targets=gcp_targets,
        )
        fine = fit_chamfer(
            coarse.model,
            control_points,
            fine_samples,
            user_field,
            config,
            use_gcps=True,
            blur_schedule=config.anneal_blur_px,
            cutoff_schedule=config.anneal_cutoff_px,
            gcp_targets=gcp_targets,
        )
        coarse_model, candidate, phase = coarse.model, fine.model, fine
    else:
        # ICP alone, straight from the control-point affine: no basin of
        # attraction, so it only works when the clicks already put the coast
        # within ICP's search radius.
        coarse_model, candidate = start, start
        phase = PhaseResult(
            model=start, converged=True, inlier_fraction=0.0, cost=float("nan"), iterations=0
        )

    if config.enable_icp:
        refined = icp_refine(
            candidate,
            control_points,
            fine_samples,
            user_field,
            config,
            use_gcps=True,
            gcp_targets=gcp_targets,
        )
        if refined.detail.get("correspondences", 0) >= config.icp_min_correspondences:
            candidate, phase = refined.model, refined

    return candidate, phase, coarse_model


def align(
    baseline: AffineModel,
    control_points: Sequence[ControlPoint],
    layers: Any,
    evidence: Any,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    record: Optional[RunRecord] = None,
    ground_meters_per_pixel: Optional[float] = None,
) -> AlignmentResult:
    """Fit the coastline from the control-point affine, check it, decide."""
    
    record = record or RunRecord()

    # Coastline on its own for the coarse stage, then lakes too when on.
    coast_samples = build_curve_samples(
        layers, config, use_coastline=True, use_lakes=False
    )
    fine_samples = build_curve_samples(layers, config)
    user_field = build_user_field(evidence, config)

    phase_models: Dict[str, Any] = {"gcp_affine": baseline.serialize()}
    stats: Dict[str, Any] = {
        "coastlineSamples": len(coast_samples),
        "fineSamples": len(fine_samples),
        "usesLakes": config.use_lakes_for_alignment,
        "usesChamfer": config.enable_chamfer,
        "usesIcp": config.enable_icp,
        "baselineGcpRmsPx": gcp_rms_px(baseline, control_points),
    }

    if len(coast_samples) == 0 or not user_field.edge.any():
        result = skipped_alignment(baseline, "no_coast_evidence", record)
        result.phase_models, result.stats = phase_models, stats
        return result

    baseline_chamfer = chamfer_residual_px(baseline, coast_samples, user_field)
    stats["baselineChamferPx"] = baseline_chamfer

    with record.phase("align_fit"):
        candidate, phase, coarse_model = fit_stages(
            baseline, control_points, coast_samples, fine_samples, user_field, config
        )
    phase_models["coarse"] = coarse_model.serialize()
    phase_models["aligned"] = candidate.serialize()

    residual = chamfer_residual_px(candidate, coast_samples, user_field)
    checks = evaluate_gates(
        candidate,
        baseline,
        control_points,
        layers,
        evidence,
        config,
        baseline_chamfer_px=baseline_chamfer,
        aligned_chamfer_px=residual,
        ground_meters_per_pixel=ground_meters_per_pixel,
    )
    for check in checks:
        record.add_gate(check)

    base_scale, base_rotation, _ = similarity_of(baseline)
    scale, rotation, _ = similarity_of(candidate)
    # Logged, not checked: how the fit got there and how far it moved.
    stats.update(
        {
            "alignedChamferPx": residual,
            "coastDisplacementPx": sample_displacement_px(baseline, candidate, coast_samples),
            "alignedGcpRmsPx": gcp_rms_px(candidate, control_points),
            "scaleDrift": abs(scale / base_scale - 1.0) if base_scale else None,
            "rotationDriftDeg": abs((rotation - base_rotation + 180.0) % 360.0 - 180.0),
            "optimizerConverged": bool(phase.converged),
            "inlierFraction": phase.inlier_fraction,
            "correspondences": phase.detail.get("correspondences"),
        }
    )

    if gates_passed(checks):
        record.set_model("aligned_affine", candidate.serialize())
        return AlignmentResult(
            model=candidate,
            method=METHOD_JOINT,
            gates=checks,
            phase_models=phase_models,
            stats=stats,
        )

    failed = failed_names(checks)
    logger.info(f"Alignment refused ({', '.join(failed)}); using the control-point affine")
    record.note("alignment refused, control-point affine used: " + ", ".join(failed))
    return AlignmentResult(
        model=baseline,
        method=METHOD_GCP_ONLY,
        gates=checks,
        failed_checks=failed,
        phase_models=phase_models,
        stats=stats,
    )
