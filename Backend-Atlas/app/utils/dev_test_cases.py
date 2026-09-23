"""Case kinds, and whether a stored case still satisfies the current algorithm.

Two things live here, and they answer two different questions a dev has about a
test case before running it.

**What is this case for?** A *regression* case has hand-drawn expected zones and
a score that gates the backend test suite. A *probe* case has neither: it exists
only to persist the clicks -- control points, framing box, pipette picks -- so
that a map can be re-extracted in seconds to look at where the zones landed.
Probes are how you iterate on alignment on a map you have not spent an hour
drawing ground truth for, which is most maps. They never fail CI, because there
is nothing for them to be wrong about.

The kind is *declared*, never inferred from a missing zones file. Inferring it
would mean a regression case whose ground truth went missing silently demotes
itself to a probe, and coverage disappears without anything going red.

**Can this case still run?** ``georeferencing/requirements.py`` declares what
the current algorithm needs; this module resolves that declaration against what
one case actually has on disk, and writes the answer to ``case_state.json`` so
it is visible without re-deriving it.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.utils.dev_test_assets import TEST_CASES_DIR, ZONES_DIR
from app.utils.dev_test_derived import DerivedState, inspect_text_regions
from app.utils.georeferencing import (
    DEFAULT_GEOREF_CONFIG,
    SOURCE_CITY,
    SOURCE_SIFT,
    GeorefConfig,
    count_by_source,
)
from app.utils.georeferencing.requirements import (
    MIN_CONTROL_POINTS,
    REQUIREMENTS_VERSION,
    RequirementsReport,
    check_requirements,
)

logger = logging.getLogger(__name__)

KIND_REGRESSION = "regression"
KIND_PROBE = "probe"
VALID_KINDS = (KIND_REGRESSION, KIND_PROBE)

CASE_STATE_FILENAME = "case_state.json"


def normalize_kind(value: Any, default: str = KIND_REGRESSION) -> str:
    """Coerce a stored or submitted kind, defaulting rather than raising.

    Cases written before kinds existed have none, and they are regressions --
    that is what every one of them was created to be.
    """
    if isinstance(value, str) and value.strip().lower() in VALID_KINDS:
        return value.strip().lower()
    return default


def _read_case_config(test_id: str, test_case_id: str) -> Dict[str, Any]:
    """The case's config.json, or an empty dict. Never raises."""
    path = os.path.join(TEST_CASES_DIR, test_id, test_case_id, "config.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_case_kind(
    test_id: str,
    test_case_id: str,
    *,
    test_metadata: Optional[Dict[str, Any]] = None,
    case_config: Optional[Dict[str, Any]] = None,
) -> str:
    """The kind in force for one case.

    The map sets the default -- a map with no ground truth drawn on it hosts
    probes -- and a case may override it. The override is what lets a deliberate
    known-bad experiment sit on a map that otherwise carries real regressions,
    instead of being deleted to keep the suite green.
    """
    if case_config is None:
        case_config = _read_case_config(test_id, test_case_id)

    if case_config.get("kind") is not None:
        return normalize_kind(case_config.get("kind"))

    if test_metadata is None:
        from app.utils.dev_test import load_test_metadata_entry

        test_metadata = load_test_metadata_entry(test_id)

    return normalize_kind((test_metadata or {}).get("kind"))


def has_expected_zones(test_id: str) -> bool:
    return os.path.exists(os.path.join(ZONES_DIR, f"{test_id}_zones.geojson"))


@dataclass(frozen=True)
class CaseState:
    """Everything known about a case before it runs."""

    test_id: str
    test_case_id: str
    kind: str
    requirements: RequirementsReport
    derived: List[DerivedState]
    has_expected_zones: bool
    #: What the case holds, whatever the run selects -- the result page uses it
    #: to offer only the source checkboxes that have points behind them.
    control_points_by_source: Dict[str, int]

    @property
    def scored(self) -> bool:
        """Whether this run produces a number that means anything."""
        return self.kind == KIND_REGRESSION and self.has_expected_zones

    @property
    def runnable(self) -> bool:
        return self.requirements.runnable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "testId": self.test_id,
            "testCaseId": self.test_case_id,
            "kind": self.kind,
            "scored": self.scored,
            "hasExpectedZones": self.has_expected_zones,
            "controlPointsBySource": self.control_points_by_source,
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "requirements": self.requirements.to_dict(),
            "derived": [d.to_dict() for d in self.derived],
        }

    def write(self, directory: Optional[str] = None) -> Optional[str]:
        """Persist beside ``report.json``. Never raises: this is a record."""
        target = directory or os.path.join(
            TEST_CASES_DIR, self.test_id, self.test_case_id
        )
        try:
            os.makedirs(target, exist_ok=True)
            path = os.path.join(target, CASE_STATE_FILENAME)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            return path
        except Exception as e:
            logger.warning(
                f"[DEV-TEST] Could not write case state for"
                f" {self.test_id}/{self.test_case_id}: {e}"
            )
            return None

    def summary_lines(self) -> List[str]:
        head = (
            f"{self.kind} case, requirements v{REQUIREMENTS_VERSION}, "
            + ("scored" if self.scored else "not scored")
        )
        return [head] + ["  " + line for line in self.requirements.lines()]


def build_case_state(
    *,
    test_id: str,
    test_case_id: str,
    inputs: Any,
    image_path: str,
    config: Optional[GeorefConfig] = None,
    case_config: Optional[Dict[str, Any]] = None,
    kind: Optional[str] = None,
) -> CaseState:
    """Resolve the current requirements against one case's stored inputs.

    ``inputs`` is a ``CaseExtractionInputs``. Derived artifacts are *inspected*
    here, never produced -- deciding whether a 135 s OCR run is warranted is the
    caller's business, not a side effect of asking what state a case is in.
    """
    cfg = config or DEFAULT_GEOREF_CONFIG
    resolved_kind = kind or resolve_case_kind(
        test_id, test_case_id, case_config=case_config
    )

    derived: List[DerivedState] = []
    by_source = count_by_source(inputs.control_points)
    usable = sum(by_source[source] for source in cfg.gcp_sources)
    presence: Dict[str, Any] = {
        # Counted over the sources this run uses: a case with 7 SIFT points and
        # 2 cities can run "SIFT only" but not "cities only".
        "controlPoints": (
            usable >= MIN_CONTROL_POINTS,
            f"{usable} point(s) from {', '.join(cfg.gcp_sources)}"
            f" (sift={by_source[SOURCE_SIFT]}, city={by_source[SOURCE_CITY]})",
        ),
        "cityControlPoints": by_source[SOURCE_CITY] > 0,
        "frameBounds": bool(inputs.frame_bounds),
        "zonePicks": bool(inputs.imposed_click_positions),
        "waterPicks": bool(inputs.water_click_positions),
    }

    if cfg.enable_curve_alignment:
        text_state = inspect_text_regions(test_id, image_path)
        derived.append(text_state)
        presence["textRegions"] = text_state.as_presence()

    return CaseState(
        test_id=test_id,
        test_case_id=test_case_id,
        kind=resolved_kind,
        requirements=check_requirements(presence, cfg),
        derived=derived,
        has_expected_zones=has_expected_zones(test_id),
        control_points_by_source=by_source,
    )


def load_case_state(test_id: str, test_case_id: str) -> Optional[Dict[str, Any]]:
    """The last written state for a case, or None.

    Read-only convenience for the UI. It is a record of the last run, not an
    authority: a checkout can change what a case has without anything re-running.
    """
    path = os.path.join(TEST_CASES_DIR, test_id, test_case_id, CASE_STATE_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None
