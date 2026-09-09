import unicodedata
from typing import Any


MERGE_MAX_VERTICAL_DISTANCE_PX = 15
MERGE_MAX_HORIZONTAL_DISTANCE_PX = 15


def _sanitize_detection_for_prompt(det: Any) -> dict[str, Any] | None:
    """Normalize one detection to a minimal {text, bbox_xyxy} structure."""
    if not isinstance(det, dict):
        return None
    text = str(det.get("text", "")).strip()
    bbox = det.get("bbox_xyxy", [])
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
    except (TypeError, ValueError):
        return None
    return {"text": text, "bbox_xyxy": [x1, y1, x2, y2]}


def _normalize_text_key(text: str) -> str:
    """Normalize text for accent/case-insensitive equality checks."""
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(no_accents.casefold().split())


def _within_merge_distance_constraints(
    first_bbox_xyxy: list[int],
    second_bbox_xyxy: list[int],
) -> bool:
    """Return True when candidate bbox is close enough to be merged with first bbox."""
    ax1, ay1, ax2, ay2 = first_bbox_xyxy
    bx1, by1, bx2, by2 = second_bbox_xyxy

    a_cx = (ax1 + ax2) / 2.0
    a_cy = (ay1 + ay2) / 2.0
    b_cx = (bx1 + bx2) / 2.0
    b_cy = (by1 + by2) / 2.0

    horizontal_distance = abs(a_cx - b_cx)
    vertical_distance = abs(a_cy - b_cy)

    return (
        vertical_distance <= MERGE_MAX_VERTICAL_DISTANCE_PX and
        horizontal_distance <= MERGE_MAX_HORIZONTAL_DISTANCE_PX
    )


def merge_same_text_bboxes_keep_first(
    detections: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Merge detections with the same normalized text. Has distance constraints.
    This is a post-processing step in case Qwen finds it fitting to merge two
    text detections that were kept split during pre-processing.

    - Compares with accent and case insensitivity.
    - Keeps the first of the compared detection text/value.
    - Expands first detection bbox to include matching duplicates.
    """
    merged = []
    text_index = {}

    for det in detections or []:
        clean = _sanitize_detection_for_prompt(det)
        if clean is None:
            continue

        key = _normalize_text_key(clean.get("text", ""))
        if not key:
            merged.append(clean)
            continue

        if key not in text_index:
            text_index[key] = len(merged)
            merged.append(clean)
            continue

        first_idx = text_index[key]
        first = merged[first_idx]

        ax1, ay1, ax2, ay2 = first["bbox_xyxy"]
        bx1, by1, bx2, by2 = clean["bbox_xyxy"]

        if not _within_merge_distance_constraints(first["bbox_xyxy"], clean["bbox_xyxy"]):
            merged.append(clean)
            continue

        first["bbox_xyxy"] = [
            min(ax1, bx1),
            min(ay1, by1),
            max(ax2, bx2),
            max(ay2, by2),
        ]

    return merged
