"""Parsing of the pipette (`imposed_colors`) payload sent by the frontend.

The payload is a JSON array of `{"x": float, "y": float, "name": str, "radius": int}`
entries, where x/y are normalised image coordinates in [0, 1]. It is shared by the
production upload route and the dev-test one so both stay in sync.
"""

import json
from json import JSONDecodeError
from typing import Any, List, Optional, Tuple

ImposedColors = Tuple[
    Optional[List[Tuple[float, float]]],  # click positions (normalised x, y)
    Optional[List[Optional[str]]],  # user-provided names
    Optional[List[int]],  # sampling radii in pixels
]


def parse_imposed_colors(raw: str | None) -> ImposedColors:
    """Parse a raw `imposed_colors` JSON string into positions, names and radii.

    Returns (None, None, None) when nothing was provided.

    Raises:
        ValueError: If the payload is not a valid list of click entries.
    """
    if not raw:
        return None, None, None

    try:
        parsed = json.loads(raw)
    except JSONDecodeError as e:
        raise ValueError(f"imposed_colors is not valid JSON: {e}")

    return parse_imposed_colors_entries(parsed)


def parse_imposed_colors_entries(entries: Any) -> ImposedColors:
    """Same as `parse_imposed_colors` but for an already decoded list."""
    if entries is None:
        return None, None, None
    if not isinstance(entries, list):
        raise ValueError("imposed_colors must be a JSON array")
    if not entries:
        return None, None, None

    click_positions: List[Tuple[float, float]] = []
    names: List[Optional[str]] = []
    radii: List[int] = []

    for entry in entries:
        if not isinstance(entry, dict) or "x" not in entry or "y" not in entry:
            raise ValueError('Each entry must be {"x": float, "y": float, "name": "..."}')

        try:
            x, y = float(entry["x"]), float(entry["y"])
        except (TypeError, ValueError):
            raise ValueError("x and y must be floats")
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError("x and y must be normalised floats in [0, 1]")

        radius_raw = entry.get("radius", 20)
        try:
            radius = int(float(radius_raw))
        except (TypeError, ValueError):
            raise ValueError("radius must be an int in [1, 200]")
        if radius < 1 or radius > 200:
            raise ValueError("radius must be an int in [1, 200]")

        raw_name = entry.get("name")
        name = str(raw_name).strip() if raw_name is not None else ""

        click_positions.append((x, y))
        names.append(name or None)
        radii.append(radius)

    return click_positions, names, radii


def imposed_colors_to_config_entries(
    click_positions: Optional[List[Tuple[float, float]]],
    names: Optional[List[Optional[str]]],
    radii: Optional[List[int]],
) -> Optional[List[dict]]:
    """Rebuild the serialisable entry list so a dev-test case can be re-run."""
    if not click_positions:
        return None

    entries: List[dict] = []
    for idx, (x, y) in enumerate(click_positions):
        entries.append(
            {
                "x": float(x),
                "y": float(y),
                "name": (names[idx] if names and idx < len(names) else None),
                "radius": int(radii[idx]) if radii and idx < len(radii) else 20,
            }
        )
    return entries
