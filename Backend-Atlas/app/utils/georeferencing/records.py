"""Structured per-run record for a georeferencing run.

Written next to ``report.json`` as ``run_record.json``. Three reasons it exists
on day one rather than being retrofitted:

* You cannot debug an IoU regression from an IoU number. If 0.94 becomes 0.71,
  the record says which stage moved it.
* A gate is only tunable if its inputs are logged **even when it passes**.
* It is the dataset the offline tuning track consumes (roadmap section 8).

Nothing here is on the hot path: building a record must never be able to fail a
run, so every accessor is defensive and ``write`` swallows its own errors.
"""

import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RUN_RECORD_FILENAME = "run_record.json"
RECORD_SCHEMA_VERSION = "1"


@dataclass
class GateCheck:
    """One named check, logged whether or not it applied.

    Logging inapplicable and passing checks is the point: which check actually
    discriminates real failures is a corpus-level question (roadmap section 5),
    and it can only be answered by aggregating runs where the check passed too.
    """

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
