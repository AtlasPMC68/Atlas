import copy
import json
import math
import os
import re

# Pixel tolerance for merge rules
ALIGN_TOLERANCE = 10
ANGLE_TOLERANCE = 20.0
HEIGHT_DELTA_TOLERANCE = 5
H_MERGE_GAP_RATIO = 0.2
H_MERGE_GAP_MIN_PX = 5
V_MERGE_GAP_RATIO = 0.5
V_MERGE_GAP_MIN_PX = 5
H_ROW_ALIGN_RATIO = 0.4

_KNOWN_OCR_PREFIX_WORDS = {
    "province",
    "territoire",
    "district",
    "etat",
    "ocean",
    "mer",
    "lac",
    "fleuve",
    "riviere",
    "baie",
    "golfe",
    "detroit",
    "ile",
    "iles",
    "saint",
    "sainte",
    "ste",
    "st",
    "cap",
    "grand",
    "grande",
    "haut",
    "haute",
    "bas",
    "basse",
    "nouveau",
    "nouvelle",
    "mount",
    "mt",
    "fort",
    "port",
    "north",
    "south",
    "east",
    "west",
}
_LINKING_PARTICLES = {"de", "du", "des", "d", "l", "del", "of", "da", "do"}


def _has_ocr_prefix(text: str) -> bool:
    """Check if a text block contains a prefix / hyphen requiring a following word."""
    if not text:
        return False
    raw = str(text).strip()
    if not raw:
        return False
    if raw.endswith(("-", "—", "–")):
        return True
    clean = re.sub(r"[^\w\s']", " ", raw.lower()).strip()
    words = clean.split()
    if not words:
        return False
    if words[-1] in _LINKING_PARTICLES:
        return True
    if words[0] in _KNOWN_OCR_PREFIX_WORDS:
        return True
    return False


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
        float(x1),
        float(y1),
        float(x2),
        float(y1),
        float(x2),
        float(y2),
        float(x1),
        float(y2),
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


def _project_points(
    points: list[tuple[float, float]],
    axis_u: tuple[float, float],
    axis_v: tuple[float, float],
) -> tuple[float, float, float, float]:
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
    center_u = (
        (center_a[0] * axis_u[0] + center_a[1] * axis_u[1]) + (center_b[0] * axis_u[0] + center_b[1] * axis_u[1])
    ) / 2.0
    center_v = (
        (center_a[0] * axis_v[0] + center_a[1] * axis_v[1]) + (center_b[0] * axis_v[0] + center_b[1] * axis_v[1])
    ) / 2.0

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

    # Immediate rejection if angles differ too much
    if abs(angle_a - angle_b) > ANGLE_TOLERANCE:
        return None

    # Strict identical font size requirement
    min_h = min(cmp_ah, cmp_bh)
    max_h = max(cmp_ah, cmp_bh)
    if min_h <= 0 or (max_h / min_h) > 1.18 or abs(cmp_ah - cmp_bh) > max(2.5, 0.15 * min_h):
        return None

    # 1. Horizontal merge: Left block must have a prefix/hyphen, and right block must be immediately to the right
    left, right = (det_a, det_b) if ax1 <= bx1 else (det_b, det_a)
    lx1, ly1, lx2, ly2 = left.get("bbox_xyxy", [0, 0, 0, 0])
    rx1, ry1, rx2, ry2 = right.get("bbox_xyxy", [0, 0, 0, 0])
    left_text = str(left.get("text", "")).strip()

    if _has_ocr_prefix(left_text):
        x_gap = rx1 - lx2
        if -0.15 * min_h <= x_gap <= max(6.0, 0.45 * min_h):
            l_cy = (ly1 + ly2) / 2.0
            r_cy = (ry1 + ry2) / 2.0
            if abs(l_cy - r_cy) <= min_h * 0.25:
                return "horizontal"

    # 2. Vertical merge: Top block must have a prefix/hyphen, and bottom block must be immediately underneath
    top, bot = (det_a, det_b) if ay1 <= by1 else (det_b, det_a)
    tx1, ty1, tx2, ty2 = top.get("bbox_xyxy", [0, 0, 0, 0])
    bx1, by1, bx2, by2 = bot.get("bbox_xyxy", [0, 0, 0, 0])
    top_text = str(top.get("text", "")).strip()

    if _has_ocr_prefix(top_text):
        y_gap = by1 - ty2
        if -0.25 * min_h <= y_gap <= max(6.0, 0.6 * min_h):
            h_overlap = min(tx2, bx2) - max(tx1, bx1)
            min_w = min(tx2 - tx1, bx2 - bx1)
            center_diff = abs((tx1 + tx2) / 2.0 - (bx1 + bx2) / 2.0)
            left_diff = abs(tx1 - bx1)
            if h_overlap >= 0.25 * min_w or center_diff <= max(8.0, 0.3 * min_w) or left_diff <= max(8.0, 0.25 * min_w):
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
    if text_a.endswith(("-", "—", "–")):
        merged_text = f"{text_a}{text_b}"
    else:
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

    changed = True
    while changed:
        changed = False

        for i in range(len(merged)):
            if changed:
                break
            for j in range(i + 1, len(merged)):
                # Check if the two boxes should be merged. If so, find the direction.
                direction = _get_merge_direction(merged[i], merged[j])
                if direction is None:
                    continue

                merged[i] = _apply_merge(merged[i], merged[j], direction)
                merged.pop(j)
                changed = True
                break

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


def save_result(image_path: str, output_path: str, parsed: dict) -> None:
    """Save the Florence parsed result as JSON."""

    json_detections = copy.deepcopy(parsed.get("detections", []))

    parsed_for_json = {**parsed, "detections": json_detections}
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(parsed_for_json, f, ensure_ascii=False, indent=2)
