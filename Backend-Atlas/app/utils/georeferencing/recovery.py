"""The alignment attempt, and the recovery ladder when its gates fail.

Plan section 10.2. Falling back to the GCP-only affine means having coastline
data and not using it, so failure is a **ladder of recoveries**, not a binary.
Every rung except the last still uses the coastline; descending means
progressively distrusting the *curve* evidence while the GCP evidence stays
constant.

Rung 3 is the important one: because `w_gcp` and `w_curve` are continuous,
"trust the coastline less" is a dial rather than a mode switch, and most
failures should be absorbed by turning it rather than by discarding the curve.

**Alignment is staged.** Coastline first, on its own, with a very wide annealing
schedule; then a finer stage that admits lakes; then ICP. Coastline is the most
distinctive structure on a map and the one a user is most likely to have drawn
faithfully, so it should set the transform before anything finer pulls on it.

Implemented here: rungs 1, 2, 3 and 7. Rungs 4 (reduce DOF to a similarity),
5 (restrict evidence to arcs near detected water) and 6 (regional acceptance)
are not implemented.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .align import (
    CurveSamples,
    PhaseResult,
    UserField,
    build_curve_samples,
    build_user_field,
    chamfer_residual_px,
    fit_chamfer,
    icp_refine,
    sample_displacement_px,
)
from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .gates import evaluate_gates, failed_names, gates_passed, gcp_rms_px
from .models import AffineModel, ControlPoint
from .records import GateCheck, RunRecord

logger = logging.getLogger(__name__)


@dataclass
class AlignmentResult:
    """What alignment decided, and everything needed to explain it."""

    model: AffineModel
    method: str  # "joint" | "joint_gcp_weighted" | "gcp_only"
    rung: int
    gates: List[GateCheck] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    probe_agreement_px: Optional[float] = None
    phase_models: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def used_curve_evidence(self) -> bool:
        return self.method != "gcp_only"


def _rung_settings(rung: int, config: GeorefConfig) -> Tuple[Dict[str, Any], str]:
    """Per-rung overrides for the joint fit, and the method name it produces."""
    if rung == 0:
        return {}, "joint"

    if rung == 1:
        # Re-anneal wider: the commonest failure is basin-of-attraction, and it
        # is fixable by starting smoother.
        return {"widen": 2.0}, "joint"

    if rung == 2:
        # Multi-start is handled by the caller, which perturbs the initial model.
        return {"multistart": True}, "joint"

    if rung == 3:
        # Raise the GCP weight so the curve can only refine within GCP tolerance.
        # A continuous dial, not a mode switch.
        return {"gcp_weight_scale": config.recovery_gcp_weight_boost}, "joint_gcp_weighted"

    return {}, "gcp_only"


def _perturbations(config: GeorefConfig) -> List[Tuple[float, float, float]]:
    """A small grid around the starting affine: (dx, dy, rotation degrees)."""
    t = config.recovery_multistart_translation_px
    r = config.recovery_multistart_rotation_deg
    return [
        (0.0, 0.0, 0.0),
        (t, 0.0, 0.0),
        (-t, 0.0, 0.0),
        (0.0, t, 0.0),
        (0.0, -t, 0.0),
        (0.0, 0.0, r),
        (0.0, 0.0, -r),
    ]


def _perturb(
    model: AffineModel, dx: float, dy: float, rotation_deg: float
) -> AffineModel:
    """Nudge a model in *pixel* space, so the grid means the same on any map."""
    theta = np.radians(rotation_deg)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    shift = np.array(
        [[cos_t, -sin_t, dx], [sin_t, cos_t, dy], [0.0, 0.0, 1.0]], dtype=float
    )
    return AffineModel(matrix=model.matrix @ shift, n_points=model.n_points)


def align(
    baseline: AffineModel,
    control_points: Sequence[ControlPoint],
    layers: Any,
    evidence: Any,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    record: Optional[RunRecord] = None,
    ground_meters_per_pixel: Optional[float] = None,
) -> AlignmentResult:
    """Fit the curve evidence, gate it, and climb down on failure.

    Args:
        baseline: the Stage 2 GCP-only affine. Also the floor we fall back to.
        control_points: the user's GCPs, with source and sigma.
        layers: `ReferenceLayers` for the framing box.
        evidence: `UserEvidence` for the map image.
        record: optional run record, populated in place.

    Returns:
        An `AlignmentResult` whose `model` is safe to use: either a gated
        alignment or the untouched baseline.
    """
    record = record or RunRecord()

    # Coastline on its own for the coarse stage.
    coast_samples = build_curve_samples(
        layers, config, use_coastline=True, use_lakes=False, use_rivers=False
    )
    # Then whatever else is switched on. Rivers are off by default.
    fine_samples = build_curve_samples(layers, config)

    user_field = build_user_field(evidence, config)

    phase_models: Dict[str, Any] = {"stage2_affine": baseline.serialize()}
    stats: Dict[str, Any] = {
        "coastlineSamples": len(coast_samples),
        "fineSamples": len(fine_samples),
        "usesLakes": config.use_lakes_for_alignment,
        "usesRivers": config.use_rivers_for_alignment,
        "baselineGcpRmsPx": gcp_rms_px(baseline, control_points),
    }

    if len(coast_samples) == 0 or not user_field.edge.any():
        record.note("no coastline samples or no user edges; alignment skipped")
        return AlignmentResult(
            model=baseline,
            method="gcp_only",
            rung=7,
            failed_checks=["no_evidence"],
            phase_models=phase_models,
            stats=stats,
        )

    baseline_chamfer = chamfer_residual_px(baseline, coast_samples, user_field)
    stats["baselineChamferPx"] = baseline_chamfer

    def _run(start: AffineModel, widen: float, gcp_weight_scale: float):
        """Coastline stage, then the fine stage, then ICP."""
        coarse = fit_chamfer(
            start,
            control_points,
            coast_samples,
            user_field,
            config,
            use_gcps=True,
            gcp_weight_scale=gcp_weight_scale,
            blur_schedule=tuple(b * widen for b in config.coarse_blur_px),
            cutoff_schedule=tuple(c * widen for c in config.coarse_cutoff_px),
        )

        fine = fit_chamfer(
            coarse.model,
            control_points,
            fine_samples,
            user_field,
            config,
            use_gcps=True,
            gcp_weight_scale=gcp_weight_scale,
            blur_schedule=tuple(b * widen for b in config.anneal_blur_px),
            cutoff_schedule=tuple(c * widen for c in config.anneal_cutoff_px),
        )

        candidate, phase = fine.model, fine
        if config.enable_icp:
            refined = icp_refine(
                fine.model,
                control_points,
                fine_samples,
                user_field,
                config,
                use_gcps=True,
                gcp_weight_scale=gcp_weight_scale,
            )
            if (
                refined.detail.get("correspondences", 0)
                >= config.icp_min_correspondences
            ):
                candidate, phase = refined.model, refined
        return candidate, phase, coarse.model

    # --- the probe: curve evidence alone, GCPs held out ----------------------
    # Its transform is discarded. Only its disagreement with the held-out GCPs
    # matters, and that is the primary gate. Passing it is not a reason to ship
    # it: the better estimator uses both sources.
    with record.phase("probe_fit"):
        probe_coarse = fit_chamfer(
            baseline,
            control_points,
            coast_samples,
            user_field,
            config,
            use_gcps=False,
            blur_schedule=config.coarse_blur_px,
            cutoff_schedule=config.coarse_cutoff_px,
        )
        probe = fit_chamfer(
            probe_coarse.model,
            control_points,
            fine_samples,
            user_field,
            config,
            use_gcps=False,
        )
    probe_rms = gcp_rms_px(probe.model, control_points)
    phase_models["probe_affine"] = probe.model.serialize()
    stats["probeGcpRmsPx"] = probe_rms

    last_gates: List[GateCheck] = []

    for rung in (0, 1, 2, 3):
        overrides, method = _rung_settings(rung, config)
        multistart = overrides.pop("multistart", False)
        gcp_weight_scale = overrides.pop("gcp_weight_scale", 1.0)
        widen = overrides.pop("widen", 1.0)

        starts = (
            [_perturb(baseline, *p) for p in _perturbations(config)]
            if multistart
            else [baseline]
        )

        best = None

        for start in starts:
            with record.phase(f"align_rung{rung}"):
                candidate, phase, coarse_model = _run(start, widen, gcp_weight_scale)

            residual = chamfer_residual_px(candidate, coast_samples, user_field)
            checks = evaluate_gates(
                candidate,
                baseline,
                probe.model,
                control_points,
                layers,
                evidence,
                phase,
                ground_meters_per_pixel,
                config,
                baseline_chamfer_px=baseline_chamfer,
                aligned_chamfer_px=residual,
            )
            if best is None or (gates_passed(checks) and not gates_passed(best[2])):
                best = (candidate, phase, checks, residual, coarse_model)
            if gates_passed(checks):
                break

        if best is None:
            continue

        candidate, phase, checks, residual, coarse_model = best
        last_gates = checks
        phase_models[f"rung{rung}_coarse"] = coarse_model.serialize()
        phase_models[f"rung{rung}"] = candidate.serialize()

        stats["alignedChamferPx"] = residual
        stats["coastDisplacementPx"] = sample_displacement_px(
            baseline, candidate, coast_samples
        )

        if gates_passed(checks):
            stats.update(
                {
                    "rung": rung,
                    "inlierFraction": phase.inlier_fraction,
                    "correspondences": phase.detail.get("correspondences"),
                    "alignedGcpRmsPx": gcp_rms_px(candidate, control_points),
                }
            )
            for check in checks:
                record.add_gate(check)
            record.set_model("chosen", candidate.serialize())
            return AlignmentResult(
                model=candidate,
                method=method,
                rung=rung,
                gates=checks,
                failed_checks=[],
                probe_agreement_px=probe_rms,
                phase_models=phase_models,
                stats=stats,
            )

        logger.info(
            f"Alignment rung {rung} failed gates: {', '.join(failed_names(checks))}"
        )

    # --- rung 7: the floor ---------------------------------------------------
    for check in last_gates:
        record.add_gate(check)
    record.note(
        "alignment fell back to the GCP-only affine: "
        + (", ".join(failed_names(last_gates)) or "no gate detail")
    )
    stats["rung"] = 7
    return AlignmentResult(
        model=baseline,
        method="gcp_only",
        rung=7,
        gates=last_gates,
        failed_checks=failed_names(last_gates),
        probe_agreement_px=probe_rms,
        phase_models=phase_models,
        stats=stats,
    )
