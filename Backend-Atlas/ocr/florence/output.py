import math
import os
import json

import cv2
import numpy as np


def _interval_gap(a1: int, a2: int, b1: int, b2: int) -> int:
    """Return the non-overlapping gap between two 1D intervals."""
    if a2 < b1:
        return b1 - a2
    if b2 < a1:
        return a1 - b2
    return 0


# Pixel tolerance for merge rules
ALIGN_TOLERANCE = 5
ANGLE_TOLERANCE = 25.0
HEIGHT_DELTA_TOLERANCE = 5
H_MERGE_GAP_RATIO = 0.5
H_MERGE_GAP_MIN_PX = 5
V_MERGE_GAP_RATIO = 0.25
V_MERGE_GAP_MIN_PX = 5
H_ROW_ALIGN_RATIO = 0.4


def _box_angle(w: int, h: int) -> float:
    """Return the aspect-derived angle of an axis-aligned box in degrees."""
    long_side = max(w, h)
    short_side = min(w, h)
    return math.degrees(math.atan2(short_side, long_side))


def _quad_angle(quad: list) -> float:
    """Return the baseline rotation angle of a Florence quad in degrees."""
    dx = quad[2] - quad[0]
    dy = quad[3] - quad[1]
    return abs(math.degrees(math.atan2(dy, dx)))


def _get_merge_direction(det_a: dict, det_b: dict) -> str | None:
    """Decide whether two detections should merge horizontally, vertically, or not at all."""

    # Fetch text box dimension and orientation values for calculations
    ax1, ay1, ax2, ay2 = det_a.get("bbox_xyxy", [0, 0, 0, 0])
    bx1, by1, bx2, by2 = det_b.get("bbox_xyxy", [0, 0, 0, 0])
    aw, ah = ax2 - ax1, ay2 - ay1
    bw, bh = bx2 - bx1, by2 - by1
    # Use source_h (original pre-merge height) for size comparison if available,
    # since merged boxes have a taller bbox that no longer reflects individual text height.
    cmp_ah = det_a.get("source_h", ah)
    cmp_bh = det_b.get("source_h", bh)
    quad_a = det_a.get("quad")
    quad_b = det_b.get("quad")
    if quad_a and quad_b:
        angle_a = _quad_angle(quad_a)
        angle_b = _quad_angle(quad_b)
    else:
        angle_a = _box_angle(aw, cmp_ah)
        angle_b = _box_angle(bw, cmp_bh)

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
        align_tol = max(ALIGN_TOLERANCE, int(min(aw, bw) * 0.08))
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

    source_h = min(
        first.get("source_h", first["bbox_xyxy"][3] - first["bbox_xyxy"][1]),
        second.get("source_h", second["bbox_xyxy"][3] - second["bbox_xyxy"][1]),
    )
    return {
        "text": merged_text,
        "bbox_xyxy": [min(ax1, bx1), min(ay1, by1), max(ax2, bx2), max(ay2, by2)],
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
        h = clean_bbox[3] - clean_bbox[1]
        result.append({"text": text, "bbox_xyxy": clean_bbox, "source_h": h})
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

    for det in merged:
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
    """Save the Florence parsed result as JSON, stripping internal-only quad fields."""

    # Save JSON — strip internal fields not part of the output format
    import copy
    json_detections = copy.deepcopy(parsed.get("detections", []))
    for det in json_detections:
        det.pop("quad", None)
    parsed_for_json = {**parsed, "detections": json_detections}
    with open(intermediate_path, "w", encoding="utf-8") as f:
        json.dump(parsed_for_json, f, ensure_ascii=False, indent=2)
