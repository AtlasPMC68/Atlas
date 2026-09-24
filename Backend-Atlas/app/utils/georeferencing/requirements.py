"""What the *current* georeferencing algorithm needs from a stored test case.

The georeferencing pipeline changes shape, not just constants: Step 1 added a
framing box, Step 1/3 added a separate water pipette, Step 4 made an OCR text
mask load-bearing. A case authored before any of those carries inputs that were
sufficient then and are not sufficient now, and nothing on disk says so -- the
case simply runs with less evidence than the algorithm expects and quietly
reports a worse number.

This module is the declaration that fixes that. Every input the pipeline
consumes is listed once, with the thing that actually matters about it: whether
a missing one can be *recovered*.

Two kinds, and the distinction is the whole point:

``USER_INPUT``
    Came from a human clicking something. A case authored before the water
    pipette existed cannot grow water picks by re-running anything; the only
    repair is a person creating a new case. So a missing required user input is
    an **error**, not a refresh.

``DERIVED``
    Extracted from the map by a step that is *not* part of georeferencing and
    does not change while georeferencing is tuned -- OCR text regions being the
    one that matters, at ~135 s per map on CPU. A missing derived artifact is
    recomputed once, persisted beside the map, and reused forever after. It is
    an expense, never a blocker.

Requirements are a function of the config, not a constant: the text mask is
required only when curve alignment is on, which is exactly why the regression
suite (alignment off) does not pay for OCR.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig

# Bump whenever a requirement is added, removed, or changes level. A case whose
# stored state was checked under an older version is re-checked, never trusted.
#   1  controlPoints, frameBounds (degraded), zonePicks, waterPicks, textRegions
#   2  frameBounds promoted to required; the degraded level removed entirely
#   3  controlPoints counts only the sources the run uses (at least 3);
#      cityControlPoints added, optional
#   4  legend added, required as an answer (a rectangle or "no legend");
#      the first requirement a run can execute without (blocks_execution)
REQUIREMENTS_VERSION = "4"

#: An affine has six unknowns and each point gives two equations.
MIN_CONTROL_POINTS = 3


class RequirementKind(str, Enum):
    USER_INPUT = "user_input"
    DERIVED = "derived"


class RequirementLevel(str, Enum):
    """How badly the pipeline wants an input.

    There is deliberately **no middle level** for "runs, but through a fallback
    that makes the result weaker". That level existed and ``frameBounds`` was
    filed under it, which was wrong: the framing box is the extent of every
    reference raster, so deriving one silently changes which geography the
    alignment can match against. An input the pipeline reads is either required
    or genuinely optional. A comfortable middle is how a case ends up running
    under-specified and reporting a worse number for a reason unrelated to
    whatever was being measured.
    """

    #: No run at all without it.
    REQUIRED = "required"
    #: Genuinely absent on some maps; its absence disables a capability.
    OPTIONAL = "optional"


class RequirementStatus(str, Enum):
    SATISFIED = "satisfied"
    #: Present but produced from inputs the case no longer has.
    STALE = "stale"
    #: Missing, recoverable by re-running the producing step.
    REFRESHABLE = "refreshable"
    #: Missing, and only a human can supply it. The case must be recreated.
    BLOCKED = "blocked"
    #: Missing, and genuinely optional. A capability is simply not exercised.
    ABSENT = "absent"


@dataclass(frozen=True)
class Requirement:
    """One input the pipeline consumes, and what to do when it is not there."""

    key: str
    kind: RequirementKind
    level: RequirementLevel
    #: Plan step that introduced it, so a case's age maps to what it can miss.
    since_step: str
    summary: str
    #: What a dev should actually do about it. Read verbatim in error messages.
    remedy: str
    #: For DERIVED requirements: the step that produces it.
    producer: Optional[str] = None
    #: Whether the pipeline cannot execute at all without it. A required input
    #: that only *changes* the result (the legend) is False: a scored case
    #: still fails on it, since its number would not be comparable, but a probe
    #: replays without it and says so.
    blocks_execution: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind.value,
            "level": self.level.value,
            "sinceStep": self.since_step,
            "summary": self.summary,
            "remedy": self.remedy,
            "producer": self.producer,
            "blocksExecution": self.blocks_execution,
        }


_CONTROL_POINTS = Requirement(
    key="controlPoints",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.REQUIRED,
    since_step="0",
    summary=(
        "Pixel <-> lon/lat pairs clicked by the user, at least"
        f" {MIN_CONTROL_POINTS} among the sources this run uses."
    ),
    remedy=(
        "If the case has enough points from another source, select it. Otherwise"
        " recreate the case: the control points come from a human matching"
        " keypoints and cities to the map and cannot be recovered from disk."
    ),
)

_CITY_CONTROL_POINTS = Requirement(
    key="cityControlPoints",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.OPTIONAL,
    since_step="5",
    summary="Cities the user named and located on the map.",
    remedy=(
        "Optional: a map may show no city the gazetteer knows. Recreate the case"
        " and name the cities on the map to compare SIFT, cities and both."
    ),
)

_FRAME_BOUNDS = Requirement(
    key="frameBounds",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.REQUIRED,
    since_step="1",
    summary="The world area the user framed; the extent for every reference layer.",
    remedy=(
        "Recreate the case and draw the world area. The framing box is the"
        " extent of every reference raster, so it decides which geography the"
        " alignment can match against at all. Deriving one from the control"
        " points is not a substitute: that box is systematically too tight,"
        " because the points sit inside the mapped area. Your drawn expected"
        " zones are per-map and are not lost -- only this case's clicks are."
    ),
)

_ZONE_PICKS = Requirement(
    key="zonePicks",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.REQUIRED,
    since_step="0",
    summary="Pipette picks of kind 'zone'; without them nothing is extracted.",
    remedy=(
        "Recreate the case. A case predating the pipette has no colours in its"
        " config and there is nothing to georeference."
    ),
)

_WATER_PICKS = Requirement(
    key="waterPicks",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.OPTIONAL,
    since_step="1",
    summary="Pipette picks of kind 'water', used for the water-mask gate.",
    remedy=(
        "Optional: a map with an unpainted ocean genuinely has none. Without"
        " them the water gate reports applicable=false and is never exercised."
    ),
)

_LEGEND = Requirement(
    key="legend",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.REQUIRED,
    since_step="6",
    summary=(
        "The legend rectangle, or an explicit 'no legend'. Masked out of the"
        " colour masks and the alignment evidence, so it changes the zones."
    ),
    remedy=(
        "Recreate the case and answer the legend step: draw the rectangle, or"
        " choose 'Pas de légende sur la carte'. A probe case replays without it"
        " and reports it missing; a scored case cannot, because its number"
        " would not be comparable to one taken with the legend masked."
    ),
    blocks_execution=False,
)

_TEXT_REGIONS = Requirement(
    key="textRegions",
    kind=RequirementKind.DERIVED,
    level=RequirementLevel.REQUIRED,
    since_step="3",
    summary=(
        "OCR label boxes, masked out of the edge map and carried as the"
        " validity mask. Roughly half the edge pixels on a labelled map are"
        " place names, so this is most of the evidence, not optional noise."
    ),
    remedy=(
        "Re-run OCR once (~135 s/map on CPU); it is cached beside the map for"
        " every case on it. Text extraction is not part of georeferencing and"
        " does not change while georeferencing is tuned."
    ),
    producer="text_extraction",
)


def georef_requirements(
    config: Optional[GeorefConfig] = None,
) -> Tuple[Requirement, ...]:
    """The requirements in force for *config*.

    Config-dependent on purpose. The text mask is load-bearing only when curve
    alignment runs, which is why the regression suite -- alignment off by
    design, so it keeps measuring the GCP-only floor -- never pays for OCR.
    """
    cfg = config or DEFAULT_GEOREF_CONFIG

    reqs: List[Requirement] = [
        _CONTROL_POINTS,
        _CITY_CONTROL_POINTS,
        _FRAME_BOUNDS,
        _ZONE_PICKS,
        _LEGEND,
    ]
    if cfg.enable_curve_alignment:
        reqs.append(_TEXT_REGIONS)
        reqs.append(_WATER_PICKS)
    return tuple(reqs)


@dataclass(frozen=True)
class RequirementState:
    """One requirement, resolved against one case."""

    requirement: Requirement
    status: RequirementStatus
    detail: Optional[str] = None

    @property
    def key(self) -> str:
        return self.requirement.key

    @property
    def blocks_run(self) -> bool:
        return self.status is RequirementStatus.BLOCKED

    @property
    def needs_refresh(self) -> bool:
        return self.status in (
            RequirementStatus.REFRESHABLE,
            RequirementStatus.STALE,
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = self.requirement.to_dict()
        payload["status"] = self.status.value
        payload["detail"] = self.detail
        return payload


class MissingUserInputError(RuntimeError):
    """A case is missing a user input that only a human can supply.

    Raised rather than worked around: silently running a case with less
    evidence than the algorithm expects reports a worse number for a reason
    that has nothing to do with the algorithm, which is precisely the failure
    this module exists to prevent.
    """

    def __init__(self, states: Iterable["RequirementState"], case_label: str = ""):
        self.states = list(states)
        self.case_label = case_label
        lines = [
            f"{case_label or 'case'} cannot run against the current"
            f" georeferencing algorithm (requirements v{REQUIREMENTS_VERSION})."
        ]
        for state in self.states:
            lines.append(
                f"  - {state.key} (added at step {state.requirement.since_step}):"
                f" {state.detail or 'missing'}"
            )
            lines.append(f"    {state.requirement.remedy}")
        super().__init__("\n".join(lines))


_STATUS_MARKERS = {
    RequirementStatus.SATISFIED: "ok",
    RequirementStatus.STALE: "STALE",
    RequirementStatus.REFRESHABLE: "REFRESH",
    RequirementStatus.BLOCKED: "BLOCKED",
    RequirementStatus.ABSENT: "absent",
}


@dataclass(frozen=True)
class RequirementsReport:
    """Every requirement resolved against one case, and what follows from it."""

    version: str
    states: Tuple[RequirementState, ...]

    @property
    def blocked(self) -> Tuple[RequirementState, ...]:
        return tuple(s for s in self.states if s.blocks_run)

    @property
    def blocks_execution(self) -> Tuple[RequirementState, ...]:
        """Blocked requirements the pipeline cannot execute without."""
        return tuple(s for s in self.blocked if s.requirement.blocks_execution)

    @property
    def refreshable(self) -> Tuple[RequirementState, ...]:
        return tuple(s for s in self.states if s.needs_refresh)

    @property
    def runnable(self) -> bool:
        return not self.blocked

    def raise_if_blocked(self, case_label: str = "") -> None:
        if self.blocked:
            raise MissingUserInputError(self.blocked, case_label)

    def lines(self) -> List[str]:
        """One human-readable line per requirement, for the dev loop."""
        return [
            "%-9s %-18s %s"
            % (
                _STATUS_MARKERS[state.status],
                state.key,
                state.detail or state.requirement.summary,
            )
            for state in self.states
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "runnable": self.runnable,
            "blocked": [s.key for s in self.blocked],
            "refreshable": [s.key for s in self.refreshable],
            "requirements": [s.to_dict() for s in self.states],
        }


def _state_for(
    requirement: Requirement, present: bool, detail: Optional[str]
) -> RequirementState:
    if present:
        # A derived artifact that exists but no longer matches its inputs is
        # worse than one that is absent: absent is obvious, stale is a silently
        # wrong number. Same treatment either way -- recompute it.
        if detail and str(detail).startswith("stale:"):
            return RequirementState(requirement, RequirementStatus.STALE, detail)
        return RequirementState(requirement, RequirementStatus.SATISFIED, detail)

    if requirement.kind is RequirementKind.DERIVED:
        # Recoverable by construction: re-run the producing step.
        return RequirementState(
            requirement,
            RequirementStatus.REFRESHABLE,
            detail or f"not cached; {requirement.producer} will be re-run once",
        )

    if requirement.level is RequirementLevel.REQUIRED:
        return RequirementState(requirement, RequirementStatus.BLOCKED, detail)
    return RequirementState(requirement, RequirementStatus.ABSENT, detail)


def check_requirements(
    presence: Dict[str, Any],
    config: Optional[GeorefConfig] = None,
) -> RequirementsReport:
    """Resolve the in-force requirements against what a case actually has.

    ``presence`` maps a requirement key to either a bool, or a
    ``(present, detail)`` pair when there is something worth saying about it --
    a derived artifact that exists but was produced from a different image, for
    instance. A detail starting with ``stale:`` marks a present-but-unusable
    artifact.
    """
    states: List[RequirementState] = []

    for requirement in georef_requirements(config):
        raw = presence.get(requirement.key, False)
        if isinstance(raw, tuple):
            present = bool(raw[0])
            detail = raw[1] if len(raw) > 1 else None
        else:
            present, detail = bool(raw), None

        states.append(_state_for(requirement, present, detail))

    return RequirementsReport(version=REQUIREMENTS_VERSION, states=tuple(states))
