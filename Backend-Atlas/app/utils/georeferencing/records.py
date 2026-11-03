"""Structured per-run record for a georeferencing run."""

import json
import logging
import math
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RUN_RECORD_FILENAME = "run_record.json"
#: 2: ``models`` holds ``gcp_affine`` (the GCP-only baseline, always),
#: ``aligned_affine`` (when alignment used the curves) and ``applied`` (what
#: the features were placed with). Version 1 wrote the applied model under
#: ``stage2_affine`` and a ``chosen`` duplicate, and never the baseline.
RECORD_SCHEMA_VERSION = "2"


@dataclass
class GateCheck:
    """One named check, logged whether or not it applied."""

    name: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    applicable: bool = True
    passed: bool = True
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunRecord:
    """Everything one alignment run knew, decided and measured."""

    schema_version: str = RECORD_SCHEMA_VERSION
    run_id: Optional[str] = None
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # GCPs (+ source, sigma), framing box, pipette picks, reference layer versions
    inputs: Dict[str, Any] = field(default_factory=dict)
    # affine after Stage 2, affine after chamfer, chosen model + parameters
    models: Dict[str, Any] = field(default_factory=dict)
    gates: List[Dict[str, Any]] = field(default_factory=list)
    # GCP residuals, chamfer residual, IoU per zone
    errors: Dict[str, Any] = field(default_factory=dict)
    timing_ms: Dict[str, float] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    # --- population ---------------------------------------------------------

    def set_inputs(self, **values: Any) -> "RunRecord":
        self.inputs.update(values)
        return self

    def set_model(self, key: str, value: Any) -> "RunRecord":
        self.models[key] = value
        return self

    def set_errors(self, **values: Any) -> "RunRecord":
        self.errors.update(values)
        return self

    def set_config(self, config: Any) -> "RunRecord":
        if hasattr(config, "to_dict"):
            self.config = config.to_dict()
        elif isinstance(config, dict):
            self.config = dict(config)
        return self

    def add_gate(self, check: GateCheck) -> "RunRecord":
        self.gates.append(check.to_dict())
        return self

    def note(self, message: str) -> "RunRecord":
        self.notes.append(message)
        return self

    @property
    def all_gates_passed(self) -> bool:
        return all(g.get("passed", True) for g in self.gates if g.get("applicable"))

    @property
    def failed_gate_names(self) -> List[str]:
        return [
            str(g.get("name"))
            for g in self.gates
            if g.get("applicable") and not g.get("passed", True)
        ]

    @contextmanager
    def phase(self, name: str):
        """Time a phase and record it in milliseconds."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.timing_ms[name] = round(
                self.timing_ms.get(name, 0.0) + elapsed_ms, 3
            )

    # --- output -------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "runId": self.run_id,
            "startedAt": self.started_at,
            "inputs": self.inputs,
            "models": self.models,
            "gates": self.gates,
            "errors": self.errors,
            "timingMs": self.timing_ms,
            "config": self.config,
            "notes": self.notes,
        }

    def write(self, directory: str, filename: str = RUN_RECORD_FILENAME) -> Optional[str]:
        """Write the record into *directory*. Never raises."""
        try:
            os.makedirs(directory, exist_ok=True)
            path = os.path.join(directory, filename)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False, default=str)
            return path
        except Exception as e:  # pragma: no cover - diagnostics must not break runs
            logger.warning(f"Failed to write georef run record to {directory}: {e}")
            return None


#: Evidence statistics read from ``inputs.userEvidence``, under their own names.
_EVIDENCE_SIGNALS = (
    "edgeFraction",
    "waterEdgeFilterKept",
    "waterFraction",
    "coastLinePairedFraction",
    "coastLineMergedFraction",
    "coastLineFlankGapPx",
)


def record_signals(record: Dict[str, Any]) -> Dict[str, Any]:
    """What a run did and what it could see, flat: the blind side of a results
    table. Read the same way from real and synthetic runs, so their signals
    compare (georeferencing-synthetic.md §7.3). A key the record
    lacks (an older run) is None."""
    inputs = record.get("inputs") or {}
    errors = record.get("errors") or {}
    alignment = inputs.get("alignment") or {}
    evidence = inputs.get("userEvidence") or {}
    post = errors.get("postAlignment") or {}
    bend = errors.get("coastBend") or {}
    inland = errors.get("inlandCorrection") or {}
    checks = errors.get("checkPoints") or {}
    by_source = inputs.get("controlPointsBySource") or {}
    layout = inputs.get("controlPointLayout") or {}
    loo = errors.get("affineLeaveOneOut") or {}
    image_size = inputs.get("imageSize") or []
    gcp_affine = (record.get("models") or {}).get("gcp_affine") or {}
    row: Dict[str, Any] = {
        "appliedModel": ((record.get("models") or {}).get("applied") or {}).get("name"),
        "alignmentMethod": alignment.get("method"),
        "alignmentSkipped": alignment.get("skipped"),
        "failedChecks": ",".join(alignment.get("failedChecks") or []) or None,
        "postAlignmentApplied": post.get("applied"),
        "coastBendApplied": bend.get("applied"),
        "coastBendSkippedBecause": bend.get("skippedBecause"),
        "coastBendMaxPx": bend.get("maxCorrectionPx"),
        "coastBendCorrespondences": bend.get("correspondences"),
        "coastBendCoastShare": bend.get("coastShare"),
        "coastBendChamferBeforePx": bend.get("chamferBeforePx"),
        "coastBendChamferAfterPx": bend.get("chamferAfterPx"),
        "inlandApplied": inland.get("applied"),
        "bendFallbackApplied": (errors.get("bendFallback") or {}).get("applied"),
        "inlandSkippedBecause": inland.get("skippedBecause"),
        "inlandPoints": inland.get("inlandPoints"),
        "inlandMaxShiftPx": inland.get("maxShiftPx"),
        "snapToleranceMeters": inputs.get("snapToleranceMeters"),
        "snapMisfitPx": inputs.get("snapMisfitPx"),
        "gcpRmseKm": errors.get("gcpRmseKm"),
        "gcpRmseKind": errors.get("gcpRmseKind"),
        "controlPointCount": inputs.get("controlPointCount"),
        "siftCount": by_source.get("sift"),
        "cityCount": by_source.get("city"),
        "hullShare": layout.get("hullShare"),
        "nearestGapMedianRatio": layout.get("nearestGapMedianRatio"),
        "nearestGapMaxRatio": layout.get("nearestGapMaxRatio"),
        "emptyRadiusRatio": layout.get("emptyRadiusRatio"),
        "looAffineRmsPx": loo.get("rmsPx"),
        "looAffineMaxPx": loo.get("maxPx"),
        "looAffineMaxOverMedian": loo.get("maxOverMedian"),
        "imageDiagonalPx": round(math.hypot(*image_size), 1) if len(image_size) == 2 else None,
        "coastlineSamples": alignment.get("coastlineSamples"),
        "coastlineCoverage": (inputs.get("referenceCoverage") or {}).get("coastline"),
        "metersPerPixel": gcp_affine.get("metersPerPixel"),
        "referenceLatitude": inputs.get("referenceLatitude"),
        "baselineGcpRmsPx": alignment.get("baselineGcpRmsPx"),
        "alignedGcpRmsPx": alignment.get("alignedGcpRmsPx"),
        "coastDisplacementPx": alignment.get("coastDisplacementPx"),
        "baselineChamferPx": alignment.get("baselineChamferPx"),
        "alignedChamferPx": alignment.get("alignedChamferPx"),
        "inlierFraction": alignment.get("inlierFraction"),
        "correspondences": alignment.get("correspondences"),
        **{key: evidence.get(key) for key in _EVIDENCE_SIGNALS},
        "predictedIou": (errors.get("predictedQuality") or {}).get("iou"),
        "predictedMedianKm": (errors.get("predictedQuality") or {}).get("mapMedianKm"),
        "checkCount": checks.get("count"),
        "checkRmseKm": checks.get("rmseKm"),
        "checkRmseKmGcpAffine": (checks.get("byModel") or {}).get("gcp_affine"),
    }
    for gate in record.get("gates") or []:
        row[f"gate.{gate.get('name')}"] = gate.get("value")
    return row
