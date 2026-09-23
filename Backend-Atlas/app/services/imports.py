"""An import in progress: what the user has entered, and whether it can run.

The user's entries live in ``map_imports.inputs`` as one JSON object, saved as
each step is confirmed so a reload finds them again:

    frameBounds     {west, south, east, north}          "Zone sur le monde"
    legend          {present, bounds}                   "Délimiter la légende"
    controlPoints   [ControlPoint.to_dict(), ...]       SIFT and city points
    colors          [{x, y, name, radius, kind, hex}]   the pipette picks
    options         {textExtraction, shapesExtraction}

``hex`` is only for the UI's swatches; extraction re-samples every pick.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.map import Map
from app.models.map_import import EXTRACTION_ACTIVE, MapImport
from app.models.project import Project
from app.utils.georeferencing import (
    SOURCE_SIFT,
    ControlPoint,
    count_by_source,
    parse_control_points,
    parse_frame_bounds_entry,
)
from app.utils.georeferencing.requirements import MIN_CONTROL_POINTS
from app.utils.imposed_colors import (
    KIND_WATER,
    KIND_ZONE,
    parse_imposed_colors_entries,
    split_imposed_colors_by_kind,
)
from app.utils.legend import LegendBounds, parse_legend_entry

INPUT_KEYS = ("frameBounds", "legend", "controlPoints", "colors", "options")

DEFAULT_OPTIONS = {"textExtraction": False, "shapesExtraction": False}

#: An import untouched this long is abandoned; the next import sweeps it.
STALE_IMPORT_AGE = timedelta(days=7)


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def _validate_colors(entries: Any) -> List[Dict[str, Any]]:
    parse_imposed_colors_entries(entries)  # raises on anything malformed
    colors: List[Dict[str, Any]] = []
    for entry in entries or []:
        hex_value = entry.get("hex")
        colors.append(
            {
                "x": float(entry["x"]),
                "y": float(entry["y"]),
                "name": (str(entry["name"]).strip() or None)
                if entry.get("name") is not None
                else None,
                "radius": int(float(entry.get("radius", 20))),
                "kind": str(entry.get("kind") or KIND_ZONE).strip().lower(),
                "hex": str(hex_value) if isinstance(hex_value, str) else None,
            }
        )
    return colors


def _validate_options(entry: Any) -> Dict[str, bool]:
    if not isinstance(entry, dict):
        raise ValueError("options must be an object")
    options = dict(DEFAULT_OPTIONS)
    for key in DEFAULT_OPTIONS:
        if key in entry:
            if not isinstance(entry[key], bool):
                raise ValueError(f"options.{key} must be a boolean")
            options[key] = entry[key]
    return options


def apply_inputs_patch(
    current: Dict[str, Any], patch: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate *patch* and merge it into *current*. ``None`` clears a key.

    A new framing box clears the control points unless the patch sets them
    too: the SIFT keypoints are drawn from the box, and the city search is
    limited to it, so points matched under the old box no longer belong.

    Raises:
        ValueError: on an unknown key or a malformed value.
    """
    unknown = set(patch) - set(INPUT_KEYS)
    if unknown:
        raise ValueError(f"unknown input(s): {', '.join(sorted(unknown))}")

    merged = dict(current or {})
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
            continue
        if key == "frameBounds":
            merged[key] = parse_frame_bounds_entry(value)
        elif key == "legend":
            _answered, bounds = parse_legend_entry(value)
            merged[key] = {"present": bounds is not None, "bounds": bounds}
        elif key == "controlPoints":
            points = parse_control_points(value)
            merged[key] = [cp.to_dict() for cp in points]
        elif key == "colors":
            merged[key] = _validate_colors(value)
        elif key == "options":
            merged[key] = _validate_options(value)

    frame_changed = merged.get("frameBounds") != (current or {}).get("frameBounds")
    if frame_changed and "controlPoints" not in patch:
        merged.pop("controlPoints", None)

    return merged


@dataclass(frozen=True)
class ImportInputs:
    """The stored inputs, parsed into what extraction consumes."""

    frame_bounds: Optional[Dict[str, float]]
    legend_answered: bool
    legend_bounds: Optional[LegendBounds]
    control_points: List[ControlPoint]
    zone_picks: Tuple[Optional[list], Optional[list], Optional[list]]
    water_picks: Tuple[Optional[list], Optional[list], Optional[list]]
    all_colors: List[Dict[str, Any]] = field(default_factory=list)
    options: Dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_OPTIONS))

    @property
    def enable_text_extraction(self) -> bool:
        return bool(self.options.get("textExtraction"))

    @property
    def enable_shapes_extraction(self) -> bool:
        return bool(self.options.get("shapesExtraction"))


def parse_import_inputs(inputs: Optional[Dict[str, Any]]) -> ImportInputs:
    """Read stored inputs. They were validated on the way in, so this raises
    only on a row edited by hand."""
    inputs = inputs or {}
    legend_answered, legend_bounds = parse_legend_entry(inputs.get("legend"))
    colors = inputs.get("colors") or []
    positions, names, radii, kinds = parse_imposed_colors_entries(colors or None)
    options = dict(DEFAULT_OPTIONS)
    options.update(inputs.get("options") or {})

    return ImportInputs(
        frame_bounds=parse_frame_bounds_entry(inputs.get("frameBounds")),
        legend_answered=legend_answered,
        legend_bounds=legend_bounds,
        control_points=parse_control_points(inputs.get("controlPoints") or []),
        zone_picks=split_imposed_colors_by_kind(
            positions, names, radii, kinds, KIND_ZONE
        ),
        water_picks=split_imposed_colors_by_kind(
            positions, names, radii, kinds, KIND_WATER
        ),
        all_colors=colors,
        options=options,
    )


def missing_inputs(inputs: ImportInputs) -> List[str]:
    """What the user still has to do before extraction can start, in French,
    one line per step, in checklist order."""
    missing: List[str] = []
    if not inputs.frame_bounds:
        missing.append("Zone sur le monde")
    if not inputs.legend_answered:
        missing.append("Délimiter la légende")
    if count_by_source(inputs.control_points)[SOURCE_SIFT] < MIN_CONTROL_POINTS:
        missing.append(f"Points SIFT (au moins {MIN_CONTROL_POINTS})")
    if not inputs.zone_picks[0]:
        missing.append("Couleurs à extraire (au moins une zone)")
    return missing


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------


async def get_owned_map(
    session: AsyncSession, map_id: UUID, user_id: UUID
) -> Optional[Map]:
    result = await session.execute(
        select(Map)
        .join(Project, Map.project_id == Project.id)
        .where(Map.id == map_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_import(
    session: AsyncSession, map_id: UUID, *, for_update: bool = False
) -> Optional[MapImport]:
    query = select(MapImport).where(MapImport.map_id == map_id)
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


def is_extraction_active(row: MapImport) -> bool:
    return row.extraction_state in EXTRACTION_ACTIVE


async def delete_stale_imports(session: AsyncSession) -> None:
    """Drop imports abandoned long ago. Not ones with an extraction on its way."""
    cutoff = datetime.utcnow() - STALE_IMPORT_AGE
    await session.execute(
        delete(MapImport).where(
            MapImport.updated_at < cutoff,
            MapImport.extraction_state.not_in(EXTRACTION_ACTIVE),
        )
    )
