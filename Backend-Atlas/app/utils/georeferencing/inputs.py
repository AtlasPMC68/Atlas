"""The inputs a map was georeferenced from, in persistable form.

Georeferencing runs exactly once, at import. Until now the control points, the
framing box and the pipette picks existed only as arguments to the Celery task,
so once it returned they were gone -- and the only way to georeference a map
differently was to re-import it and re-click every point by hand.

Storing the *inputs* rather than the fitted transform is the useful direction:
with the inputs you can refit anything, including a better model later; with a
stored matrix you can only re-apply the same affine. Roadmap section 4.4's
active GCP suggestion refits by construction, so it needs these, not a matrix.

The shape deliberately mirrors the dev-test ``config.json`` (``georef`` +
``colors``) so a production map and a test case carry the same information.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from .frame import FrameBounds, frame_bounds_to_config_entry, parse_frame_bounds_entry
from .models import ControlPoint, parse_control_points
from .requirements import MIN_CONTROL_POINTS

# 2: control points carry a source and, for cities, the city; no sigma.
# 3: the legend answer ({present, bounds}) is stored beside the framing box.
GEOREF_INPUTS_VERSION = "3"


def parse_control_points_field(raw: Optional[str]) -> List[ControlPoint]:
    """The ``control_points`` form field of both upload routes.

    Shared, like ``imposed_colors.py`` and ``frame.py``, so the production and
    dev-test routes cannot drift apart. Empty when absent. At least
    ``MIN_CONTROL_POINTS`` when present, because an affine cannot be fitted
    from fewer and the task would only fail on it later.

    Raises:
        ValueError: on invalid JSON, a malformed point, or too few points.
    """
    if not raw:
        return []
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"control_points is not valid JSON: {e}")
    points = parse_control_points(entries)
    if points and len(points) < MIN_CONTROL_POINTS:
        raise ValueError(
            f"at least {MIN_CONTROL_POINTS} control points are needed, got {len(points)}"
        )
    return points


def build_georef_inputs(
    control_points: Optional[Sequence[ControlPoint]] = None,
    frame_bounds: Optional[FrameBounds] = None,
    imposed_colors: Optional[List[dict]] = None,
    legend: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Assemble the payload stored on ``maps.georef_inputs``.

    Returns None when there is nothing worth storing, so the column stays null
    for maps imported without georeferencing.

    Args:
        control_points: the pixel <-> geo pairs, with their source.
        frame_bounds: the world area the user framed.
        imposed_colors: pipette entries as ``imposed_colors_to_config_entries``
            returns them, zone and water alike.
        legend: the legend answer as ``legend_to_entry`` writes it. The
            legend is masked out of the alignment evidence, so a refit needs it.
    """
    if not control_points and not frame_bounds and not imposed_colors:
        return None

    return {
        "version": GEOREF_INPUTS_VERSION,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "georef": {
            "controlPoints": (
                [cp.to_dict() for cp in control_points] if control_points else None
            ),
            "frameBounds": frame_bounds_to_config_entry(frame_bounds),
            "legend": legend,
        },
        "colors": {
            "imposed": imposed_colors or None,
        },
    }


def parse_georef_inputs(
    payload: Optional[Dict[str, Any]],
) -> tuple[List[ControlPoint], Optional[FrameBounds], Optional[List[dict]]]:
    """Read a stored payload back into usable objects.

    Tolerant by design: a malformed or partial payload yields whatever parts are
    readable rather than raising, because the caller is recovering inputs, not
    validating a request.
    """
    if not isinstance(payload, dict):
        return [], None, None

    georef = payload.get("georef") if isinstance(payload.get("georef"), dict) else {}
    colors = payload.get("colors") if isinstance(payload.get("colors"), dict) else {}

    control_points: List[ControlPoint] = []
    for entry in georef.get("controlPoints") or []:
        try:
            control_points.append(ControlPoint.from_dict(entry))
        except ValueError:
            continue

    try:
        frame_bounds = parse_frame_bounds_entry(georef.get("frameBounds"))
    except ValueError:
        frame_bounds = None

    imposed = colors.get("imposed")
    if not isinstance(imposed, list):
        imposed = None

    return control_points, frame_bounds, imposed
