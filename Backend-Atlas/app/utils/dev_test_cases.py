"""Case kinds, and whether a stored case still satisfies the current algorithm. """

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
    """The kind in force for one case."""

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
        return not self.requirements.blocked

    def to_dict(self) -> Dict[str, Any]:
        return {
            "testId": self.test_id,
            "testCaseId": self.test_case_id,
            "kind": self.kind,
            "scored": self.scored,
            "hasExpectedZones": self.has_expected_zones,
            "controlPointsBySource": self.control_points_by_source,
            "runnable": self.runnable,
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
    """Resolve the current requirements against one case's stored inputs."""

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
        "checkPoints": (
            len(inputs.check_points) > 0,
            f"{len(inputs.check_points)} point(s)",
        ),
        "frameBounds": bool(inputs.frame_bounds),
        "zonePicks": bool(inputs.zone_picks[0]),
        # An answer, not a rectangle: "no legend" satisfies it.
        "legend": bool(inputs.legend_answered),
        "waterPicks": bool(inputs.water_picks[0]),
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
    """The last written state for a case, or None."""
    
    path = os.path.join(TEST_CASES_DIR, test_id, test_case_id, CASE_STATE_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None
