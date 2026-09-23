"""Draw where each control point *went*, on the map the user clicked.

One picture answers what a table of kilometres cannot: whether a bad point is
a mis-click (the arrow is short and the map is fine) or a mis-match (the arrow
is long and points at a different feature entirely).

Yellow dot   where the user clicked.
Red dot      where the transform puts that point's real-world position.
Arrow        from one to the other: its length is the error, in pixels, on the
             map's own scale.

Drawn with the model the run *actually used*, taken from its run record, so a
piecewise run shows the piecewise placement and not a freshly fitted affine.

This module needs cv2 and is therefore not re-exported from the package, for
the reason given in ``__init__``: importing it should not drag the image stack
into every consumer.
"""

import logging
from typing import Any, Optional, Sequence, Tuple

import cv2
import numpy as np

from .models import ControlPoint
from .projection import lonlat_to_webmercator, webmercator_arrays_to_lonlat

logger = logging.getLogger(__name__)

CLICK_COLOR = (0, 255, 255)  # BGR: yellow
TRUTH_COLOR = (255, 255, 0)  # BGR: cyan, for a point's real-world position
MODEL_COLOR = (0, 0, 255)  # BGR: red
ARROW_COLOR = (255, 255, 255)
SUSPECT_COLOR = (255, 0, 255)  # BGR: magenta, for a point flagged as suspect


def _scaled(image: np.ndarray, min_width: int = 1100) -> Tuple[np.ndarray, float]:
    """Upscale a small scan so dots and labels stay legible.

    A 602 px wide map cannot carry a readable label at every control point.
    Scaling the canvas rather than shrinking the annotations keeps the arrows
    proportional to the map, which is what the reader is judging.
    """
    height, width = image.shape[:2]
    if width >= min_width:
        return image.copy(), 1.0
    scale = min_width / float(width)
    resized = cv2.resize(
        image, (int(round(width * scale)), int(round(height * scale))),
        interpolation=cv2.INTER_NEAREST,
    )
    return resized, scale


def draw_control_point_overlay(
    image_bgr: np.ndarray,
    control_points: Sequence[ControlPoint],
    placed_pixels: Sequence[Optional[Tuple[float, float]]],
    errors_km: Optional[Sequence[Optional[float]]] = None,
    suspect_indices: Sequence[int] = (),
    caption: str = "",
) -> np.ndarray:
    """Return a BGR image annotating every control point.

    Args:
        image_bgr: the user's map, as OpenCV reads it.
        control_points: the clicks and their real-world positions.
        model: any fitted transform -- it only needs ``inverse()``, so affine
            and piecewise both work.
        errors_km: per-point ground error to label, when it is known.
        suspect_indices: points to mark in magenta.
        caption: one line drawn at the top, e.g. the model name and its RMS.
    """
    canvas, scale = _scaled(image_bgr if image_bgr.ndim == 3 else
                            cv2.cvtColor(image_bgr, cv2.COLOR_GRAY2BGR))

    suspects = set(int(i) for i in suspect_indices)
    font = cv2.FONT_HERSHEY_SIMPLEX

    for i, cp in enumerate(control_points):
        click = (int(round(cp.pixel[0] * scale)), int(round(cp.pixel[1] * scale)))

        target = placed_pixels[i] if i < len(placed_pixels) else None
        placed = None
        if target is not None and all(np.isfinite(v) for v in target):
            placed = (int(round(float(target[0]) * scale)),
                      int(round(float(target[1]) * scale)))

        if placed is not None:
            cv2.arrowedLine(canvas, click, placed, ARROW_COLOR, 2, tipLength=0.18)
            cv2.circle(canvas, placed, 5, MODEL_COLOR, -1)

        point_color = SUSPECT_COLOR if i in suspects else CLICK_COLOR
        cv2.circle(canvas, click, 6, point_color, -1)
        cv2.circle(canvas, click, 6, (0, 0, 0), 1)

        label = f"#{i}"
        if errors_km is not None and i < len(errors_km) and errors_km[i] is not None:
            label += f" {errors_km[i]:.0f}km"
        # Offset up-left of the click so the label never sits under the arrow.
        cv2.putText(canvas, label, (click[0] + 8, click[1] - 8), font, 0.45,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(canvas, label, (click[0] + 8, click[1] - 8), font, 0.45,
                    point_color, 1, cv2.LINE_AA)

    legend = [caption] if caption else []
    legend.append("jaune = clic   rouge = position selon la transformation")
    for row, text in enumerate(legend):
        y = 20 + row * 20
        cv2.putText(canvas, text, (10, y), font, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(canvas, text, (10, y), font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    return canvas


def draw_world_overlay(
    layers: Any,
    control_points: Sequence[ControlPoint],
    placed_3857: Sequence[Optional[Tuple[float, float]]],
    errors_km: Optional[Sequence[Optional[float]]] = None,
    suspect_indices: Sequence[int] = (),
    caption: str = "",
) -> np.ndarray:
    """The same points, seen from the world instead of from the map.

    The mirror image of ``draw_control_point_overlay``: there the arrow shows
    where a real place lands on the drawing, here it shows where a click on
    the drawing lands on the Earth. The second is the one to look at when
    asking whether a point was matched to the wrong feature, because the
    reference coastline is drawn underneath it.

    Yellow dot   the control point's true position (the keypoint's lon/lat).
    Red dot      where the transform sends the pixel the user clicked.
    """
    grid = layers.grid
    canvas = np.full((grid.height, grid.width, 3), 245, dtype=np.uint8)
    canvas[layers.land] = (226, 232, 226)  # land, faint
    canvas[layers.lakes.astype(bool)] = (200, 160, 110)
    canvas[layers.coastline.astype(bool)] = (120, 90, 60)

    suspects = set(int(i) for i in suspect_indices)
    font = cv2.FONT_HERSHEY_SIMPLEX

    for i, cp in enumerate(control_points):
        tx, ty = grid.to_pixel(cp.geo[0], cp.geo[1])
        truth = (int(round(float(tx))), int(round(float(ty))))

        target = placed_3857[i] if i < len(placed_3857) else None
        if target is not None and all(np.isfinite(v) for v in target):
            lon, lat = webmercator_arrays_to_lonlat(
                np.array([target[0]]), np.array([target[1]])
            )
            px, py = grid.to_pixel(lon[0], lat[0])
            placed = (int(round(float(px))), int(round(float(py))))
            cv2.arrowedLine(canvas, truth, placed, (60, 60, 60), 2, tipLength=0.15)
            cv2.circle(canvas, placed, 5, MODEL_COLOR, -1)

        point_color = SUSPECT_COLOR if i in suspects else TRUTH_COLOR
        cv2.circle(canvas, truth, 6, point_color, -1)
        cv2.circle(canvas, truth, 6, (0, 0, 0), 1)

        label = f"#{i}"
        if errors_km is not None and i < len(errors_km) and errors_km[i] is not None:
            label += f" {errors_km[i]:.0f}km"
        cv2.putText(canvas, label, (truth[0] + 8, truth[1] - 8), font, 0.45,
                    (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(canvas, label, (truth[0] + 8, truth[1] - 8), font, 0.45,
                    (20, 20, 20), 1, cv2.LINE_AA)

    legend = [caption] if caption else []
    legend.append("cyan = position reelle   rouge = ou le clic atterrit")
    for row, text in enumerate(legend):
        y = 20 + row * 20
        cv2.putText(canvas, text, (10, y), font, 0.5, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(canvas, text, (10, y), font, 0.5, (20, 20, 20), 1, cv2.LINE_AA)

    return canvas


def side_by_side(left: np.ndarray, right: np.ndarray, gap: int = 12) -> np.ndarray:
    """Join two panels, scaling the right one to the left one's height."""
    lh, lw = left.shape[:2]
    rh, rw = right.shape[:2]
    scale = lh / float(rh)
    resized = cv2.resize(right, (max(int(round(rw * scale)), 1), lh))
    canvas = np.full((lh, lw + gap + resized.shape[1], 3), 255, dtype=np.uint8)
    canvas[:, :lw] = left
    canvas[:, lw + gap :] = resized
    return canvas


def encode_png(image_bgr: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image_bgr)
    if not ok:
        raise RuntimeError("Failed to encode control point overlay as PNG")
    return buffer.tobytes()
