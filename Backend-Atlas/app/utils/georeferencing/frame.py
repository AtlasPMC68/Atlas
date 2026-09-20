"""The framing box: the world area the user drew before matching keypoints.

``worldAreaBounds`` has always existed in ``ImportView.vue`` and has always been
sent to ``/projects/coastline-keypoints``; it was simply never forwarded to
``/upload`` (current section 9, limitation 3). It is the working extent for
every reference layer built in Step 2, so it now travels with the upload and is
persisted into the dev-test ``config.json``.

Shared by the production and dev-test routes so both stay in sync, in the same
way ``imposed_colors.py`` is.
"""

import json
import math
from json import JSONDecodeError
from typing import Any, Dict, Optional

FrameBounds = Dict[str, float]

_REQUIRED_KEYS = ("west", "south", "east", "north")


def parse_frame_bounds(raw: Optional[str]) -> Optional[FrameBounds]:
    """Parse a raw ``frame_bounds`` JSON string. ``None`` when absent.

    Raises:
        ValueError: If the payload is present but not a valid bounds object.
    """
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except JSONDecodeError as e:
        raise ValueError(f"frame_bounds is not valid JSON: {e}")

    return parse_frame_bounds_entry(parsed)


def parse_frame_bounds_entry(entry: Any) -> Optional[FrameBounds]:
    """Same as ``parse_frame_bounds`` but for an already decoded object."""
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise ValueError("frame_bounds must be a JSON object")
    if not set(_REQUIRED_KEYS).issubset(entry.keys()):
        raise ValueError(
            "frame_bounds must be a JSON object with west, south, east, north"
        )

    try:
        bounds = {key: float(entry[key]) for key in _REQUIRED_KEYS}
    except (TypeError, ValueError):
        raise ValueError("frame_bounds values must be numbers")

    if not all(math.isfinite(value) for value in bounds.values()):
        raise ValueError("frame_bounds values must be finite numbers")

    if not (-90.0 <= bounds["south"] <= 90.0 and -90.0 <= bounds["north"] <= 90.0):
        raise ValueError("frame_bounds latitudes must be within [-90, 90]")
    if bounds["south"] >= bounds["north"]:
        raise ValueError("frame_bounds south must be below north")

    # Longitudes may legitimately wrap the antimeridian (west > east), so the
    # only check here is that they are in range.
    if not all(-180.0 <= bounds[key] <= 180.0 for key in ("west", "east")):
        raise ValueError("frame_bounds longitudes must be within [-180, 180]")

    return bounds


def frame_bounds_to_config_entry(
    bounds: Optional[FrameBounds],
) -> Optional[Dict[str, float]]:
    """Serialisable form, so a dev-test case re-runs with the same extent."""
    if not bounds:
        return None
    return {key: float(bounds[key]) for key in _REQUIRED_KEYS}
