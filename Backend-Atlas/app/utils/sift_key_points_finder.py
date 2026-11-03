import os
from typing import List, Optional, Tuple

import cv2
import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from app.utils.georeferencing.reference import (
    COASTLINE_FILE,
    LAKES_FILE,
    ReferenceGrid,
    load_reference_linework,
)

NUMBER_OF_KEYPOINTS = 15

# Ratios of the image diagonal, not pixels: this module rasterizes the framing
# box at whatever size the caller asks for (the endpoint takes width/height),
# and a constant in pixels silently means something different at each size.
BORDER_MARGIN_RATIO = 0.02  # ~25 px on the 1024x768 default
# Only a duplicate floor, *not* how the points get spread out -- that is the
# sampling below. SIFT reports several keypoints at one location (different
# scales and orientations), and two control points in the same spot constrain
# nothing.
MIN_SEPARATION_RATIO = 0.01  # ~13 px on the 1024x768 default
# What "well spaced" means when choosing between a coastline and a lake
# keypoint: a lake point is only taken when no coastline point is at least this
# far from every point already chosen. Measured on the test cases' framing
# boxes: at 5% of the diagonal, 6 of 14 boxes gain 1-5 lake points and the
# points' hull roughly doubles there (~0.25 -> ~0.45 of the frame); the others
# stay all coastline.
WELL_SPACED_RATIO = 0.05  # ~64 px on the 1024x768 default

COASTLINE = "coastline"
LAKE = "lake"

# Sampling cost is candidates x points, so a cap keeps the worst case bounded
# on a dense raster. Candidates are taken strongest-first, so what is dropped
# is the weak tail.
MAX_CANDIDATES = 5000

# The coastline is drawn this wide. SIFT may only place keypoints under the
# Canny outline of that line, widened by this kernel to cover the whole line:
# unwidened, the mask is the 1 px outline of a 3 px line, and SIFT, which puts a
# keypoint at the centre of what it finds, lost ~98% of its detections (on 52
# synthetic frames: median 10 per frame instead of ~460, 20 frames under 6).
LINE_WIDTH_PX = 3
MASK_DILATION_PX = 5

# OpenCV draws with sub-pixel coordinates in 1/16 px.
_SUBPIXEL_BITS = 4
_SUBPIXEL = 1 << _SUBPIXEL_BITS

DEBUG = False


def select_spread_keypoints(
    coastline_keypoints,
    lake_keypoints,
    count: int,
    well_spaced_px: float,
    min_separation_px: float,
):
    """Pick up to `count` keypoints spread as widely as possible, coastline first."""
    candidates = [
        (kp, feature)
        for feature, keypoints in ((COASTLINE, coastline_keypoints), (LAKE, lake_keypoints))
        for kp in sorted(keypoints, key=lambda kp: kp.response, reverse=True)[:MAX_CANDIDATES]
    ]
    if count <= 0 or not candidates:
        return []

    points = np.array([kp.pt for kp, _ in candidates], dtype=float)
    is_coast = np.array([feature == COASTLINE for _, feature in candidates])

    # Candidates are strongest-first within each feature, coastline first.
    chosen = [0]
    # Distance from every candidate to the nearest chosen point, kept as a
    # running minimum so each round costs one pass rather than one per pair.
    distance = np.hypot(points[:, 0] - points[0, 0], points[:, 1] - points[0, 1])

    for spacing in (well_spaced_px, min_separation_px):
        while len(chosen) < count:
            eligible = distance >= spacing
            pool = eligible & is_coast
            if not pool.any():
                pool = eligible & ~is_coast
            if not pool.any():
                break
            index = np.flatnonzero(pool)
            pick = int(index[np.argmax(distance[index])])
            chosen.append(pick)
            np.minimum(
                distance,
                np.hypot(points[:, 0] - points[pick, 0], points[:, 1] - points[pick, 1]),
                out=distance,
            )

    return [candidates[i] for i in chosen]


def detect_sift_candidates(gray_image: np.ndarray, apply_edge_detection: bool = True):
    """Every SIFT keypoint on the render's lines, away from its borders."""
    height, width = gray_image.shape
    border_margin = BORDER_MARGIN_RATIO * float(np.hypot(width, height))

    if apply_edge_detection:
        # Apply blur to reduce noise before edge detection
        blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)
        # The Canny outline of the drawn line, widened to cover the whole line
        # (see MASK_DILATION_PX).
        edges = cv2.dilate(
            cv2.Canny(blurred, 75, 175), np.ones((MASK_DILATION_PX, MASK_DILATION_PX), np.uint8)
        )
    else:
        edges = None

    sift = cv2.SIFT_create()
    keypoints, _ = sift.detectAndCompute(gray_image, mask=edges)

    return [
        kp
        for kp in keypoints
        if border_margin < kp.pt[0] < width - border_margin
        and border_margin < kp.pt[1] < height - border_margin
    ]


def render_linework(geom: Optional[BaseGeometry], grid: ReferenceGrid) -> Tuple[np.ndarray, BaseGeometry]:
    """The layer drawn over the framing box, and the same lines in render pixels.

    Lines are clipped to the box, never joined across a gap: dropping the
    vertices outside the box would draw a straight line from where a coast
    leaves the frame to where it comes back, and farthest-point sampling picks
    exactly such isolated, invented lines.
    """
    render = np.zeros((grid.height, grid.width), dtype=np.uint8)
    lines: List[LineString] = []
    if geom is not None and not geom.is_empty:
        for clip_box, lon_shift in grid.clip_boxes():
            clipped = shapely.clip_by_rect(geom, *clip_box.bounds)
            for part in shapely.get_parts(shapely.get_parts(clipped)):
                if part.geom_type != "LineString" or len(part.coords) < 2:
                    continue
                coords = np.asarray(part.coords, dtype=float)
                px, py = grid.to_pixel(coords[:, 0] + lon_shift, coords[:, 1])
                points = np.column_stack((px, py))
                cv2.polylines(
                    render,
                    [np.round(points * _SUBPIXEL).astype(np.int32)],
                    False,
                    255,
                    LINE_WIDTH_PX,
                    cv2.LINE_AA,
                    shift=_SUBPIXEL_BITS,
                )
                lines.append(LineString(points))
    return render, shapely.MultiLineString(lines)


def snap_to_lines(point: Tuple[float, float], lines: BaseGeometry) -> Tuple[float, float]:
    """The nearest point on *lines*. A keypoint sits somewhere on the drawn
    line, up to half its width off the curve, and its lon/lat becomes the
    control point's true position: 1.5 px is ~6 km on a 40 degree frame."""
    if lines.is_empty:
        return point
    snapped = nearest_points(lines, Point(point))[0]
    return float(snapped.x), float(snapped.y)


def find_coastline_keypoints(bounds: dict, width: int = 1024, height: int = 768):
    """Suggest SIFT keypoints for the user to match, inside geographic bounds."""

    grid = ReferenceGrid.from_bounds(bounds, width, height)
    diagonal = float(np.hypot(width, height))

    renders = {}
    lines = {}
    candidates = {}
    for feature, filename in ((COASTLINE, COASTLINE_FILE), (LAKE, LAKES_FILE)):
        renders[feature], lines[feature] = render_linework(load_reference_linework(filename), grid)
        candidates[feature] = detect_sift_candidates(renders[feature], apply_edge_detection=True)

    selected = select_spread_keypoints(
        candidates[COASTLINE],
        candidates[LAKE],
        NUMBER_OF_KEYPOINTS,
        WELL_SPACED_RATIO * diagonal,
        MIN_SEPARATION_RATIO * diagonal,
    )
    used_lakes = any(feature == LAKE for _, feature in selected)

    keypoints = []
    for i, (kp, feature) in enumerate(selected):
        px, py = snap_to_lines(kp.pt, lines[feature])
        lon, lat = grid.to_lonlat(px, py)

        keypoints.append({
            "id": i + 1,
            "pixel": {"x": px, "y": py},
            "geo": {"lat": float(lat), "lng": float(lon)},
            "response": float(kp.response),
            "feature": feature,
        })

    if DEBUG:
        output_dir = os.path.join(os.path.dirname(__file__), "extracted_texts")
        os.makedirs(output_dir, exist_ok=True)
        img_vis = cv2.cvtColor(np.maximum(renders[COASTLINE], renders[LAKE]), cv2.COLOR_GRAY2BGR)
        for i, point in enumerate(keypoints):
            x, y = int(point["pixel"]["x"]), int(point["pixel"]["y"])
            colour = (0, 255, 0) if point["feature"] == COASTLINE else (255, 160, 0)
            cv2.circle(img_vis, (x, y), 15, colour, 2)
            cv2.circle(img_vis, (x, y), 3, (0, 0, 255), -1)
            cv2.putText(img_vis, str(i + 1), (x + 20, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        cv2.imwrite(os.path.join(output_dir, "sift_keypoints.png"), img_vis)

    return {"keypoints": keypoints, "total": len(keypoints), "used_lakes": used_lakes}
