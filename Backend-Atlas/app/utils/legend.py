"""The legend: the part of a map that is a key, not geography.

The user either draws a rectangle around it or says the map has none. Both are
answers; a map nobody asked about has no answer at all, and that difference is
what the dev-test requirements check reads.

The rectangle is in the image's own pixel space (natural width/height), as the
legend picker draws it. Every extractor ignores it:

    colors      its pixels are removed from the masks before zones are built
    shapes      shapes centred inside it are dropped
    text        OCR boxes centred inside it never become city points
    alignment   its edges and water are not evidence

It no longer *drives* anything: colours come from the pipette alone. Deriving
colours from legend swatches was removed with the import redesign.

Shared by the production and dev-test paths so both read it the same way, like
``imposed_colors.py`` and ``georeferencing/frame.py``.
"""

import math
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

LegendBounds = Dict[str, float]

_REQUIRED_KEYS = ("x", "y", "width", "height")


def parse_legend_bounds(entry: Any) -> LegendBounds:
    """Validate a decoded ``{x, y, width, height}`` rectangle.

    Raises:
        ValueError: If it is not an object with four finite numbers and a
            positive size.
    """
    if not isinstance(entry, dict) or not set(_REQUIRED_KEYS).issubset(entry.keys()):
        raise ValueError("legend bounds must be an object with x, y, width, height")

    try:
        bounds = {key: float(entry[key]) for key in _REQUIRED_KEYS}
    except (TypeError, ValueError):
        raise ValueError("legend bounds values must be numbers")

    if not all(math.isfinite(value) for value in bounds.values()):
        raise ValueError("legend bounds values must be finite numbers")
    if bounds["width"] <= 0 or bounds["height"] <= 0:
        raise ValueError("legend bounds width and height must be > 0")
    return bounds


def legend_to_entry(bounds: Optional[LegendBounds]) -> Dict[str, Any]:
    """The stored answer: a rectangle, or an explicit "no legend"."""
    if bounds is None:
        return {"present": False, "bounds": None}
    return {"present": True, "bounds": dict(bounds)}


def parse_legend_entry(entry: Any) -> Tuple[bool, Optional[LegendBounds]]:
    """Read a stored answer back. Returns ``(answered, bounds)``.

    ``(False, None)``: never answered. ``(True, None)``: the map has no legend.

    Raises:
        ValueError: If the entry exists but is malformed.
    """
    if entry is None:
        return False, None
    if not isinstance(entry, dict) or "present" not in entry:
        raise ValueError('legend must be {"present": bool, "bounds": {...} | null}')
    if not entry["present"]:
        return True, None
    return True, parse_legend_bounds(entry.get("bounds"))


def point_in_legend(x: float, y: float, bounds: Optional[LegendBounds]) -> bool:
    if not bounds:
        return False
    return (
        bounds["x"] <= x <= bounds["x"] + bounds["width"]
        and bounds["y"] <= y <= bounds["y"] + bounds["height"]
    )


def polygon_center_in_legend(
    points: Sequence[Sequence[float]], bounds: Optional[LegendBounds]
) -> bool:
    """Whether the centre of an OCR box (or any polygon) lies in the legend."""
    if not bounds or not points:
        return False
    try:
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
    except (TypeError, ValueError, IndexError):
        return False
    return point_in_legend(sum(xs) / len(xs), sum(ys) / len(ys), bounds)


def legend_mask(
    shape_hw: Tuple[int, int], bounds: Optional[LegendBounds]
) -> np.ndarray:
    """Boolean mask of the legend rectangle, clipped to the image."""
    height, width = int(shape_hw[0]), int(shape_hw[1])
    mask = np.zeros((height, width), dtype=bool)
    if not bounds:
        return mask

    x1 = max(0, int(math.floor(bounds["x"])))
    y1 = max(0, int(math.floor(bounds["y"])))
    x2 = min(width, int(math.ceil(bounds["x"] + bounds["width"])))
    y2 = min(height, int(math.ceil(bounds["y"] + bounds["height"])))
    if x2 > x1 and y2 > y1:
        mask[y1:y2, x1:x2] = True
    return mask
