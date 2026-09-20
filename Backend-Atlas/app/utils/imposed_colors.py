"""Parsing of the pipette (`imposed_colors`) payload sent by the frontend.

The payload is a JSON array of
`{"x": float, "y": float, "name": str, "radius": int, "kind": "zone" | "water"}`
entries, where x/y are normalised image coordinates in [0, 1]. It is shared by the
production upload route and the dev-test one so both stay in sync.

`kind` separates zone fill from water. They are pipetted separately because they
are routinely the same hue -- on the Leclerc map blue is Nouvelle-France while
the Atlantic is white. Colour alone cannot disambiguate them, and the user can in
one click. Entries without a `kind` are zones, which is what every payload
written before this field existed meant.
"""

import json
from json import JSONDecodeError
from typing import Any, List, Optional, Tuple

KIND_ZONE = "zone"
KIND_WATER = "water"
VALID_KINDS = (KIND_ZONE, KIND_WATER)

ImposedColors = Tuple[
    Optional[List[Tuple[float, float]]],  # click positions (normalised x, y)
    Optional[List[Optional[str]]],  # user-provided names
    Optional[List[int]],  # sampling radii in pixels
    Optional[List[str]],  # kind: "zone" or "water"
]


def parse_imposed_colors(raw: str | None) -> ImposedColors:
    """Parse a raw `imposed_colors` JSON string into positions, names, radii, kinds.

    Returns (None, None, None, None) when nothing was provided.

    Raises:
        ValueError: If the payload is not a valid list of click entries.
    """
    if not raw:
        return None, None, None, None

    try:
        parsed = json.loads(raw)
    except JSONDecodeError as e:
        raise ValueError(f"imposed_colors is not valid JSON: {e}")

    return parse_imposed_colors_entries(parsed)


def parse_imposed_colors_entries(entries: Any) -> ImposedColors:
    """Same as `parse_imposed_colors` but for an already decoded list."""
    if entries is None:
        return None, None, None, None
    if not isinstance(entries, list):
        raise ValueError("imposed_colors must be a JSON array")
    if not entries:
        return None, None, None, None

    click_positions: List[Tuple[float, float]] = []
    names: List[Optional[str]] = []
    radii: List[int] = []
    kinds: List[str] = []

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

        raw_kind = entry.get("kind")
        kind = str(raw_kind).strip().lower() if raw_kind is not None else KIND_ZONE
        if kind not in VALID_KINDS:
            raise ValueError(f"kind must be one of {VALID_KINDS}")

        click_positions.append((x, y))
        names.append(name or None)
        radii.append(radius)
        kinds.append(kind)

    return click_positions, names, radii, kinds


def split_imposed_colors_by_kind(
    click_positions: Optional[List[Tuple[float, float]]],
    names: Optional[List[Optional[str]]],
    radii: Optional[List[int]],
    kinds: Optional[List[str]],
    kind: str,
) -> Tuple[
    Optional[List[Tuple[float, float]]],
    Optional[List[Optional[str]]],
    Optional[List[int]],
]:
    """Keep only the picks of one `kind`, as three parallel lists.

    Returns (None, None, None) when nothing of that kind was picked, so the
    result drops straight into the `Optional[List]` arguments downstream.
    """
    if not click_positions:
        return None, None, None

    selected = [
        idx
        for idx in range(len(click_positions))
        if (kinds[idx] if kinds and idx < len(kinds) else KIND_ZONE) == kind
    ]
    if not selected:
        return None, None, None

    return (
        [click_positions[i] for i in selected],
        [(names[i] if names and i < len(names) else None) for i in selected],
        [(int(radii[i]) if radii and i < len(radii) else 20) for i in selected],
    )


def imposed_colors_to_config_entries(
    click_positions: Optional[List[Tuple[float, float]]],
    names: Optional[List[Optional[str]]],
    radii: Optional[List[int]],
    kinds: Optional[List[str]] = None,
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
                "kind": (kinds[idx] if kinds and idx < len(kinds) else KIND_ZONE),
            }
        )
    return entries
