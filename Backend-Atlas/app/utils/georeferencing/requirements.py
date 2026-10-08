"""What the *current* georeferencing algorithm needs from a stored test case."""

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
#   4  legend added, required as an answer (a rectangle or "no legend")
#   5  checkPoints added, optional
#   6  probes no longer replay without a legend answer
REQUIREMENTS_VERSION = "6"

#: An affine has six unknowns and each point gives two equations.
MIN_CONTROL_POINTS = 3


class RequirementKind(str, Enum):
    USER_INPUT = "user_input"
    DERIVED = "derived"


class RequirementLevel(str, Enum):
    """How badly the pipeline wants an input."""

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
    #: Missing, and only a human can supply it: "Compléter les entrées" on the
    #: case's result page reopens its steps with everything else kept.
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind.value,
            "level": self.level.value,
            "sinceStep": self.since_step,
            "summary": self.summary,
            "remedy": self.remedy,
            "producer": self.producer,
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
        " complete the case ('Compléter les entrées' on its result page) and add"
        " points: they come from a human matching keypoints and cities to the"
        " map and cannot be recovered from disk."
    ),
)

_CITY_CONTROL_POINTS = Requirement(
    key="cityControlPoints",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.OPTIONAL,
    since_step="5",
    summary="Cities the user named and located on the map.",
    remedy=(
        "Optional: a map may show no city the gazetteer knows. Complete the case"
        " ('Compléter les entrées') and name the cities on the map to compare"
        " SIFT, cities and both."
    ),
)

_CHECK_POINTS = Requirement(
    key="checkPoints",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.OPTIONAL,
    since_step="tests",
    summary=(
        "Held-out points (cities or SIFT pairs): never fitted, measured against"
        " the applied transform. The only placement error that is not in-sample."
    ),
    remedy=(
        "Optional, but the primary metric of the test plan: complete the case"
        " ('Modifier les entrées') and place at least 5 check points spread"
        " across the map -- 'Villes de vérification', or SIFT pairs ticked"
        " 'vérification' at the SIFT step. See dev-docs/georeferencing-testing.md."
    ),
)

_FRAME_BOUNDS = Requirement(
    key="frameBounds",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.REQUIRED,
    since_step="1",
    summary="The world area the user framed; the extent for every reference layer.",
    remedy=(
        "Complete the case ('Compléter les entrées' on its result page) and draw"
        " the world area; its control points and picks are kept. The framing box"
        " is the extent of every reference raster, so it decides which geography"
        " the alignment can match against at all. Deriving one from the control"
        " points is not a substitute: that box is systematically too tight,"
        " because the points sit inside the mapped area."
    ),
)

_ZONE_PICKS = Requirement(
    key="zonePicks",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.REQUIRED,
    since_step="0",
    summary="Pipette picks of kind 'zone'; without them nothing is extracted.",
    remedy=(
        "Complete the case ('Compléter les entrées' on its result page) and pick"
        " the colours. A case predating the pipette has no colours in its config"
        " and there is nothing to georeference."
    ),
)

_WATER_PICKS = Requirement(
    key="waterPicks",
    kind=RequirementKind.USER_INPUT,
    level=RequirementLevel.OPTIONAL,
    since_step="1",
    summary=(
        "Pipette picks of kind 'water'. They identify the map's coastline:"
        " curve alignment runs only with them."
    ),
    remedy=(
        "Optional: a map with an unpainted ocean, or no coast, genuinely has"
        " none. Without them the map is placed by its control points alone."
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
        "Complete the case ('Compléter les entrées' on its result page) and"
        " answer the legend step: draw the rectangle, or choose 'Pas de légende"
        " sur la carte'."
    ),
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
    """The requirements in force for *config*."""

    cfg = config or DEFAULT_GEOREF_CONFIG

    reqs: List[Requirement] = [
        _CONTROL_POINTS,
        _CITY_CONTROL_POINTS,
        _CHECK_POINTS,
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
    """A case is missing a user input that only a human can supply."""

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
    """Resolve the in-force requirements against what a case actually has."""
    
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
