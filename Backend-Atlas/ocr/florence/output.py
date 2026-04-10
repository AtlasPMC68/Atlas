import math
import os
import json

import cv2
import numpy as np


def _interval_gap(a1, a2, b1, b2):
    if a2 < b1:
        return b1 - a2
    if b2 < a1:
        return a1 - b2
    return 0


# Pixel tolerance for left/right/center edge alignment in vertical merges.
ALIGN_TOLERANCE = 5
ANGLE_TOLERANCE = 5.0
HEIGHT_DELTA_TOLERANCE = 5
H_MERGE_GAP_RATIO = 0.5
H_MERGE_GAP_MIN_PX = 5
V_MERGE_GAP_RATIO = 0.25
V_MERGE_GAP_MIN_PX = 5
H_ROW_ALIGN_RATIO = 0.4


def _box_angle(w: int, h: int) -> float:
    """Angle in degrees of the box's long axis, always in [0°, 45°].
    0° = perfectly wide/flat, 45° = perfectly square."""
    long_side = max(w, h)
    short_side = min(w, h)
    return math.degrees(math.atan2(short_side, long_side))


def _quad_angle(quad: list) -> float:
    """True rotation angle of the bottom edge of a quad [x1,y1,x2,y2,x3,y3,x4,y4], in degrees.
    Returns the absolute angle in [0°, 90°] of the baseline."""
    # Bottom edge is corner 0→1 (Florence quad order: top-left, top-right, bottom-right, bottom-left)
    dx = quad[2] - quad[0]
    dy = quad[3] - quad[1]
    return abs(math.degrees(math.atan2(dy, dx)))


def _get_merge_direction(det_a: dict, det_b: dict) -> str | None:
    """
    Determine how two detections should be merged based on their spatial relationship.

    Args:
        det_a (dict[str,list[int]]): dict with "bbox_xyxy" key containing [x1, y1, x2, y2] of the first box
        det_b (dict[str,list[int]]): dict with "bbox_xyxy" key containing [x1, y1, x2, y2] of the second box

    Returns:
        orientation (str | None): 'horizontal' if the boxes are side by side on the same row,
        'vertical' if one is stacked above the other with matching alignment,
        or None if they should not be merged.
    """

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
    # Need a gap smaller than 1/2 of text height, and y-aligned
    if x_gap <= max(max_h * H_MERGE_GAP_RATIO, H_MERGE_GAP_MIN_PX):
        a_cy = (ay1 + ay2) / 2
        b_cy = (by1 + by2) / 2
        if abs(a_cy - b_cy) <= min_h * H_ROW_ALIGN_RATIO:
            return "horizontal"

    # Vertical merge
    # Gap at most a 1/4 of text height, and text alignment check.
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
    """
    Merge two detected text boxes into one, combining their text and redimensioning the bounding box to encompass both.
    Args:
        det_a (dict): dict with "text" and "bbox_xyxy" keys for the first detection
        det_b (dict): dict with "text" and "bbox_xyxy" keys for the second detection
        direction (str): 'horizontal' or 'vertical' indicating how the boxes should be merged

    Returns:
        merged (dict): dict with combined "text" and new "bbox_xyxy" that covers both input boxes
    """
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
    """Validate and normalize raw Florence detections before merging."""
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
    """
    Merge text boxes likely belonging to one label.

    Args:
        detections: list of {"text": str, "bbox_xyxy": [x1, y1, x2, y2]} dicts
    """

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
    """Convert Florence quad_box [x1,y1,x2,y2,x3,y3,x4,y4] to axis-aligned bbox_xyxy."""
    xs = quad[0::2]
    ys = quad[1::2]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def _save_bbox_preview_image(image_path: str, intermediate_path: str, parsed: dict) -> None:
    """Optional helper to render detections on the source image and save a -bbx preview."""
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

    # Save JSON — strip internal fields not part of the output format
    import copy
    json_detections = copy.deepcopy(parsed.get("detections", []))
    for det in json_detections:
        det.pop("quad", None)
    parsed_for_json = {**parsed, "detections": json_detections}
    with open(intermediate_path, "w", encoding="utf-8") as f:
        json.dump(parsed_for_json, f, ensure_ascii=False, indent=2)
