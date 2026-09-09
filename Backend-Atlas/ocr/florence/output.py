import math
import os
import json
import copy
import cv2
import numpy as np


# Pixel tolerance for merge rules
ALIGN_TOLERANCE = 5
ANGLE_TOLERANCE = 20.0
HEIGHT_DELTA_TOLERANCE = 5
H_MERGE_GAP_RATIO = 0.5
H_MERGE_GAP_MIN_PX = 5
V_MERGE_GAP_RATIO = 0.25
V_MERGE_GAP_MIN_PX = 5
H_ROW_ALIGN_RATIO = 0.4


def _interval_gap(a1: int, a2: int, b1: int, b2: int) -> int:
    """Return the non-overlapping gap between two 1D intervals."""
    if a2 < b1:
        return b1 - a2
    if b2 < a1:
        return a1 - b2
    return 0


def _bbox_xyxy_to_quad(bbox: list[int]) -> list[float]:
    """Convert an axis-aligned bbox_xyxy into a rectangular quad."""
    x1, y1, x2, y2 = bbox
    return [
        float(x1), float(y1),
        float(x2), float(y1),
        float(x2), float(y2),
        float(x1), float(y2),
    ]


def _quad_points(quad: list[float]) -> list[tuple[float, float]]:
    return [
        (float(quad[0]), float(quad[1])),
        (float(quad[2]), float(quad[3])),
        (float(quad[4]), float(quad[5])),
        (float(quad[6]), float(quad[7])),
    ]


def _normalize_vector(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length == 0:
        return 1.0, 0.0
    return dx / length, dy / length


def _canonicalize_vector(dx: float, dy: float) -> tuple[float, float]:
    if dx < 0 or (abs(dx) < 1e-6 and dy < 0):
        return -dx, -dy
    return dx, dy


def _quad_metrics(quad: list[float]) -> tuple[float, float, tuple[float, float]]:
    points = _quad_points(quad)

    def _edge(i: int) -> tuple[float, float, float]:
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % 4]
        dx = x2 - x1
        dy = y2 - y1
        return dx, dy, math.hypot(dx, dy)

    pair_02 = (_edge(0), _edge(2))
    pair_13 = (_edge(1), _edge(3))

    avg_02 = (pair_02[0][2] + pair_02[1][2]) / 2.0
    avg_13 = (pair_13[0][2] + pair_13[1][2]) / 2.0
    width_pair, height_pair = (pair_02, pair_13) if avg_02 >= avg_13 else (pair_13, pair_02)

    width = (width_pair[0][2] + width_pair[1][2]) / 2.0
    height = (height_pair[0][2] + height_pair[1][2]) / 2.0

    ux1, uy1 = _normalize_vector(width_pair[0][0], width_pair[0][1])
    ux2, uy2 = _normalize_vector(width_pair[1][0], width_pair[1][1])
    if ux1 * ux2 + uy1 * uy2 < 0:
        ux2, uy2 = -ux2, -uy2
    ux, uy = _normalize_vector(ux1 + ux2, uy1 + uy2)
    ux, uy = _canonicalize_vector(ux, uy)

    return width, height, (ux, uy)


def _quad_center(quad: list[float]) -> tuple[float, float]:
    points = _quad_points(quad)
    return (
        sum(x for x, _ in points) / 4.0,
        sum(y for _, y in points) / 4.0,
    )


def _project_points(points: list[tuple[float, float]], axis_u: tuple[float, float], axis_v: tuple[float, float]) -> tuple[float, float, float, float]:
    projected_u = [x * axis_u[0] + y * axis_u[1] for x, y in points]
    projected_v = [x * axis_v[0] + y * axis_v[1] for x, y in points]
    return min(projected_u), max(projected_u), min(projected_v), max(projected_v)


def _quad_from_projected_bounds(
    min_u: float,
    max_u: float,
    min_v: float,
    max_v: float,
    axis_u: tuple[float, float],
    axis_v: tuple[float, float],
) -> list[float]:
    corners = [
        (min_u, min_v),
        (max_u, min_v),
        (max_u, max_v),
        (min_u, max_v),
    ]
    quad = []
    for u_coord, v_coord in corners:
        x = axis_u[0] * u_coord + axis_v[0] * v_coord
        y = axis_u[1] * u_coord + axis_v[1] * v_coord
        quad.extend([x, y])
    return quad


def _merge_quads(det_a: dict, det_b: dict, direction: str) -> list[float]:
    quad_a = det_a["quad"]
    quad_b = det_b["quad"]

    _, _, axis_a = _quad_metrics(quad_a)
    _, _, axis_b = _quad_metrics(quad_b)
    if axis_a[0] * axis_b[0] + axis_a[1] * axis_b[1] < 0:
        axis_b = (-axis_b[0], -axis_b[1])

    axis_u = _normalize_vector(axis_a[0] + axis_b[0], axis_a[1] + axis_b[1])
    axis_u = _canonicalize_vector(*axis_u)
    axis_v = (-axis_u[1], axis_u[0])

    points_a = _quad_points(quad_a)
    points_b = _quad_points(quad_b)
    min_u_a, max_u_a, min_v_a, max_v_a = _project_points(points_a, axis_u, axis_v)
    min_u_b, max_u_b, min_v_b, max_v_b = _project_points(points_b, axis_u, axis_v)

    center_a = _quad_center(quad_a)
    center_b = _quad_center(quad_b)
    center_u = ((center_a[0] * axis_u[0] + center_a[1] * axis_u[1]) + (center_b[0] * axis_u[0] + center_b[1] * axis_u[1])) / 2.0
    center_v = ((center_a[0] * axis_v[0] + center_a[1] * axis_v[1]) + (center_b[0] * axis_v[0] + center_b[1] * axis_v[1])) / 2.0

    source_w = max(det_a.get("source_w", 0.0), det_b.get("source_w", 0.0))
    source_h = max(det_a.get("source_h", 0.0), det_b.get("source_h", 0.0))

    if direction == "horizontal":
        min_u = min(min_u_a, min_u_b)
        max_u = max(max_u_a, max_u_b)
        min_v = center_v - source_h / 2.0
        max_v = center_v + source_h / 2.0
    else:
        min_u = center_u - source_w / 2.0
        max_u = center_u + source_w / 2.0
        min_v = min(min_v_a, min_v_b)
        max_v = max(max_v_a, max_v_b)

    return _quad_from_projected_bounds(min_u, max_u, min_v, max_v, axis_u, axis_v)


def _quad_angle(quad: list) -> float:
    """Return average inclination (deg) of the two longer sides of a rectangle."""
    def _inclination_deg(dx: float, dy: float) -> float:
        # Inclination in [0, 90], invariant to edge direction.
        angle = abs(math.degrees(math.atan2(dy, dx)))
        return 180.0 - angle if angle > 90.0 else angle

    _, _, axis = _quad_metrics(quad)
    a1 = _inclination_deg(axis[0], axis[1])
    a2 = a1
    return (a1 + a2) / 2.0



def _get_merge_direction(det_a: dict, det_b: dict) -> str | None:
    """Decide whether two detections should merge horizontally, vertically, or not at all."""

    # Fetch text box dimension and orientation values for calculations
    ax1, ay1, ax2, ay2 = det_a.get("bbox_xyxy", [0, 0, 0, 0])
    bx1, by1, bx2, by2 = det_b.get("bbox_xyxy", [0, 0, 0, 0])
    aw, ah = ax2 - ax1, ay2 - ay1
    bw, bh = bx2 - bx1, by2 - by1
    # Use source_h (original pre-merge height) for size comparison if available,
    # since merged boxes have a taller bbox that no longer reflects individual text height.
    cmp_aw = det_a.get("source_w", aw)
    cmp_bw = det_b.get("source_w", bw)
    cmp_ah = det_a.get("source_h", ah)
    cmp_bh = det_b.get("source_h", bh)
    angle_a = _quad_angle(det_a.get("quad"))
    angle_b = _quad_angle(det_b.get("quad"))

    # Immediate rejection if angles or text size differ too much
    if abs(angle_a - angle_b) > ANGLE_TOLERANCE:
        return None
    if abs(cmp_ah - cmp_bh) > HEIGHT_DELTA_TOLERANCE:
        return None

    # Calculate horizontal and vertical gaps between the boxes
    x_gap = _interval_gap(ax1, ax2, bx1, bx2)
    y_gap = _interval_gap(ay1, ay2, by1, by2)
    max_h = max(cmp_ah, cmp_bh)
    min_h = min(cmp_ah, cmp_bh)

    # Horizontal merge since it is more common
    if x_gap <= max(max_h * H_MERGE_GAP_RATIO, H_MERGE_GAP_MIN_PX):
        a_cy = (ay1 + ay2) / 2
        b_cy = (by1 + by2) / 2
        if abs(a_cy - b_cy) <= min_h * H_ROW_ALIGN_RATIO:
            return "horizontal"

    # Vertical merge
    if y_gap <= max(max_h * V_MERGE_GAP_RATIO, V_MERGE_GAP_MIN_PX):
        align_tol = max(ALIGN_TOLERANCE, int(min(cmp_aw, cmp_bw) * 0.08))
        if abs(ax1 - bx1) <= align_tol:
            return "vertical"
        if abs(ax2 - bx2) <= align_tol:
            return "vertical"
        if abs((ax1 + ax2) / 2 - (bx1 + bx2) / 2) <= align_tol:
            return "vertical"

    return None


def _apply_merge(det_a: dict, det_b: dict, direction: str) -> dict:
    """Merge two detections into one combined text box using the given direction."""
    
    ax1, ay1, ax2, ay2 = det_a["bbox_xyxy"]
    bx1, by1, bx2, by2 = det_b["bbox_xyxy"]

    if direction == "vertical":
        first, second = (det_a, det_b) if ay1 <= by1 else (det_b, det_a)
        sep = "\n"
    else:
        first, second = (det_a, det_b) if ax1 <= bx1 else (det_b, det_a)
        sep = " "

    text_a = str(first.get("text", "")).strip()
    text_b = str(second.get("text", "")).strip()
    merged_text = sep.join(filter(None, [text_a, text_b]))
    merged_quad = _merge_quads(first, second, direction)
    merged_bbox = quad_to_bbox_xyxy(merged_quad)

    source_w = max(first.get("source_w", ax2 - ax1), second.get("source_w", bx2 - bx1))
    source_h = max(
        first.get("source_h", first["bbox_xyxy"][3] - first["bbox_xyxy"][1]),
        second.get("source_h", second["bbox_xyxy"][3] - second["bbox_xyxy"][1]),
    )
    return {
        "text": merged_text,
        "bbox_xyxy": merged_bbox,
        "quad": merged_quad,
        "source_w": source_w,
        "source_h": source_h,
    }


def _sanitize_detections(detections: list[dict]) -> list[dict]:
    """Validate and normalize raw Florence detections before merge heuristics."""
    result = []
    for det in detections or []:
        bbox = det.get("bbox_xyxy", [])
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        try:
            clean_bbox = [int(v) for v in bbox]
        except (TypeError, ValueError):
            continue
        try:
            text = str(det.get("text", "")).strip()
        except (TypeError, ValueError):
            continue
        clean_det = {"text": text}

        quad = det.get("quad")
        if isinstance(quad, list) and len(quad) == 8:
            try:
                clean_quad = [float(v) for v in quad]
            except (TypeError, ValueError):
                clean_quad = _bbox_xyxy_to_quad(clean_bbox)
        else:
            clean_quad = _bbox_xyxy_to_quad(clean_bbox)

        source_w, source_h, _ = _quad_metrics(clean_quad)
        clean_det["quad"] = clean_quad
        clean_det["bbox_xyxy"] = quad_to_bbox_xyxy(clean_quad)
        clean_det["source_w"] = source_w
        clean_det["source_h"] = source_h

        result.append(clean_det)
    return result


def merge_related_detections(detections: list[dict]) -> list[dict]:
    """Merge Florence text boxes that likely belong to the same label."""

    # Build a list of valid detections with filtered clean text and bbox formatting.
    merged = _sanitize_detections(detections)

    # Only stop iterating when no merges happen, to allow checking new merge possibilities after each merge.
    changed = True
    while changed:
        changed = False

        for i in range(len(merged)):
            # The array size changed if a merge happened. Therefore break to avoid index errors.
            if changed:
                break
            for j in range(i + 1, len(merged)):

                # Check if the two boxes should be merged. If so, find the direction.
                direction = _get_merge_direction(merged[i], merged[j])
                if direction is None:
                    continue

                # If a merge happens, replace i with the merged box and pop j.
                merged[i] = _apply_merge(merged[i], merged[j], direction)
                merged.pop(j)
                changed = True
                break

    # Removing temporary params, and adding bbox_xyxy because they are easier to work with.
    for det in merged:
        det["bbox_xyxy"] = quad_to_bbox_xyxy(det["quad"])
        det.pop("source_w", None)
        det.pop("source_h", None)

    return merged


def quad_to_bbox_xyxy(quad: list[float]) -> list[int]:
    """Convert a Florence quad into an axis-aligned bbox_xyxy list."""
    xs = quad[0::2]
    ys = quad[1::2]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def _save_bbox_preview_image(image_path: str, intermediate_path: str, parsed: dict) -> None:
    """Render a preview image showing parsed Florence detections and their boxes."""
    ext = os.path.splitext(os.path.basename(image_path))[1]
    img = cv2.imread(image_path)
    for det in parsed.get("detections", []):
        quad = det.get("quad", [])
        bbox = det.get("bbox_xyxy", [])
        if len(quad) == 8:
            pts = np.array(
                [[int(quad[i]), int(quad[i + 1])] for i in range(0, 8, 2)],
                dtype=np.int32,
            )
            cv2.polylines(img, [pts], isClosed=True, color=(0, 0, 255), thickness=1)
            label_x, label_y = int(quad[0]), max(int(quad[1]) - 4, 0)
        elif len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 1)
            label_x, label_y = x1, max(y1 - 4, 0)
        else:
            continue
        cv2.putText(
            img,
            det["text"],
            (label_x, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (0, 0, 255),
            1,
        )
    bbx_path = os.path.splitext(intermediate_path)[0] + f"-bbx{ext}"
    cv2.imwrite(bbx_path, img)


def save_result(image_path: str, intermediate_path: str, parsed: dict) -> None:
    """Save the Florence parsed result as JSON."""

    # Save JSON
    json_detections = copy.deepcopy(parsed.get("detections", []))

    parsed_for_json = {**parsed, "detections": json_detections}
    with open(intermediate_path, "w", encoding="utf-8") as f:
        json.dump(parsed_for_json, f, ensure_ascii=False, indent=2)
