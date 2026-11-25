import json
import logging
import os
import re
from typing import Any
from uuid import UUID, uuid4

from celery import current_task

from app.celery_app import celery_app
from app.utils.place_nomenclature import _find_geographic_prefix, _normalize

logger = logging.getLogger(__name__)

OCR_INPUT_DIR = os.getenv("OCR_INPUT_DIR", "/data/ocr_input")
OCR_OUTPUT_DIR = os.getenv("OCR_OUTPUT_DIR", "/data/ocr_result")
OCR_PIPELINE_TIMEOUT_SECONDS = int(os.getenv("OCR_PIPELINE_TIMEOUT_SECONDS", "900"))


class OcrPipelineError(RuntimeError):
    """Florence failed or timed out: no text was read, which is not the same as a map without text."""


def florence_task_id(ocr_task_id: str) -> str:
    """Id of the Florence task started by an OCR task, so cancelling the import
    can revoke it too. Revoking only the OCR task stops the wait, not Florence,
    which then keeps the CPU busy until its time limit and delays the next import."""
    return f"{ocr_task_id}-florence"

# fmt: off
MAP_IGNORED_WORDS = {
    "n", "s", "e", "w", "o", "ne", "nw", "no", "se", "sw", "so",
    "nord", "sud", "est", "ouest", "n.-e.", "n.-o.", "s.-e.", "s.-o.",
}
# fmt: on

_RE_LEGEND_OR_SCALE = re.compile(
    r"\b(?:légende|legende|échelle|echelle|scale)\b|"
    r"(?<![a-z])(?:km|kms|kilom[eè]tres?|kilometers?|miles?)(?![a-z])",
)


def should_ignore(text_val: str) -> bool:
    clean = text_val.lower().strip(" .,;:!?()[]{}'\"")

    if clean in MAP_IGNORED_WORDS:
        return True

    if clean and all(c.isdigit() or c.isspace() or c in ".," for c in clean):
        return True
    if _RE_LEGEND_OR_SCALE.search(clean):
        return True

    if len(clean.split()) > 5:
        return True

    return False


def ocr_blocks_to_payload(blocks: list[dict[str, Any]]) -> list[list]:
    """Convert OCR blocks to plain JSON: [[[x, y], ...], text, prob]."""
    payload = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        coords = block.get("bbox", [])
        text = block.get("text", "")
        prob = float(block.get("prob", block.get("confidence", 1.0)))
        payload.append(
            [
                [[int(round(float(p[0]))), int(round(float(p[1])))] for p in coords],
                str(text),
                prob,
            ]
        )
    return merge_multiline_ocr_blocks(payload)


_KNOWN_MULTILINE_PREFIX_WORDS = {
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


def _has_multiline_prefix(top_text: str, bottom_text: str = "") -> bool:
    """Return True if the top block (or the combined text) starts with a recognized geographic prefix or linking particle."""
    if not top_text:
        return False
    raw_top = str(top_text).strip()
    if not raw_top:
        return False
    # Hyphen continuation at the end (e.g. 'NOUVEAU-', 'CAP-')
    if raw_top.endswith(("-", "—", "–")):
        return True

    norm_top = _normalize(raw_top)
    if not norm_top:
        return False
    if _find_geographic_prefix(norm_top) is not None:
        return True
    if bottom_text:
        norm_combined = _normalize(f"{raw_top} {bottom_text}")
        if _find_geographic_prefix(norm_combined) is not None:
            return True

    words = norm_top.split()
    if not words:
        return False
    if words[0] in _KNOWN_MULTILINE_PREFIX_WORDS:
        return True
    if words[-1] in _LINKING_PARTICLES:
        return True

    return False


def merge_multiline_ocr_blocks(blocks: list[list]) -> list[list]:
    """Merge OCR text blocks that belong to the same multi-line label (e.g. 'Mer de' + 'Baffin').

    Heuristic:
    - MUST have a recognized geographic prefix or hyphen continuation.
    - Font sizes must be identical (height ratio within [0.85, 1.30] and delta <= max(2.5, 0.15 * min_h)).
    - Very close to the right or underneath.
    - Top-to-bottom / left-to-right reading order when combining text.
    """
    if not blocks or len(blocks) < 2:
        return blocks

    # Parse each block into a structured representation: (coords, text, prob, bbox)
    items = []
    for b in blocks:
        if not isinstance(b, (list, tuple)) or len(b) < 2:
            continue
        coords = b[0]
        text = str(b[1]).strip()
        prob = float(b[2]) if len(b) > 2 and b[2] is not None else 1.0
        if not coords or not text:
            continue
        xs = [float(pt[0]) for pt in coords]
        ys = [float(pt[1]) for pt in coords]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        h = max(1.0, max_y - min_y)
        w = max(1.0, max_x - min_x)
        items.append({
            "coords": coords,
            "text": text,
            "prob": prob,
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "w": w,
            "h": h,
            "cx": (min_x + max_x) / 2.0,
            "cy": (min_y + max_y) / 2.0,
            "has_prefix": _has_multiline_prefix(text),
        })

    if len(items) < 2:
        return blocks

    merged = True
    while merged:
        merged = False
        n = len(items)
        best_pair = None
        best_dist = float("inf")

        for i in range(n):
            for j in range(i + 1, n):
                a = items[i]
                b = items[j]

                # Strict identical font size check: height ratio must be <= 1.30 (no horizontal merge if ratio > 1.3 - 1.5)
                min_h = min(a["h"], b["h"])
                max_h = max(a["h"], b["h"])
                if min_h <= 0 or (max_h / min_h) > 1.30 or abs(a["h"] - b["h"]) > max(2.5, 0.15 * min_h):
                    continue

                max_v_gap = max(6.0, 0.6 * min_h)
                max_x_gap = max(6.0, 0.45 * min_h)
                too_far_vertically = (
                    b["min_y"] - a["max_y"] > max_v_gap
                    or a["min_y"] - b["max_y"] > max_v_gap
                )
                too_far_horizontally = (
                    b["min_x"] - a["max_x"] > max_x_gap
                    or a["min_x"] - b["max_x"] > max_x_gap
                )
                if too_far_vertically and too_far_horizontally:
                    continue

                # 1. Vertical candidate (en dessous)
                if a["min_y"] <= b["min_y"]:
                    top, bot = a, b
                    t_idx, b_idx = i, j
                else:
                    top, bot = b, a
                    t_idx, b_idx = j, i

                v_gap = bot["min_y"] - top["max_y"]
                has_prefix = top["has_prefix"] or _has_multiline_prefix(top["text"], bot["text"])
                if has_prefix and (-0.25 * min_h <= v_gap <= max_v_gap):
                    h_overlap = min(top["max_x"], bot["max_x"]) - max(top["min_x"], bot["min_x"])
                    min_w = min(top["w"], bot["w"])
                    center_diff = abs(top["cx"] - bot["cx"])
                    left_diff = abs(top["min_x"] - bot["min_x"])
                    if (h_overlap >= 0.25 * min_w) or (center_diff <= max(8.0, 0.3 * min_w)) or (left_diff <= max(8.0, 0.25 * min_w)):
                        dist = max(0.0, v_gap) + center_diff * 0.5
                        if dist < best_dist:
                            best_dist = dist
                            best_pair = (t_idx, b_idx, top, bot)

                # 2. Horizontal candidate (a droit)
                if a["min_x"] <= b["min_x"]:
                    left, right = a, b
                    l_idx, r_idx = i, j
                else:
                    left, right = b, a
                    l_idx, r_idx = j, i

                x_gap = right["min_x"] - left["max_x"]
                has_h_prefix = left["has_prefix"] or _has_multiline_prefix(left["text"], right["text"])
                if has_h_prefix and (-0.15 * min_h <= x_gap <= max_x_gap):
                    y_diff = abs(left["cy"] - right["cy"])
                    if y_diff <= 0.25 * min_h:
                        dist = max(0.0, x_gap) + y_diff * 0.5
                        if dist < best_dist:
                            best_dist = dist
                            best_pair = (l_idx, r_idx, left, right)

        if best_pair:
            first_idx, second_idx, first, second = best_pair
            first_text = first["text"].strip()
            second_text = second["text"].strip()
            if first_text.endswith(("-", "—", "–")):
                combined_text = f"{first_text}{second_text}"
            else:
                combined_text = f"{first_text} {second_text}"

            new_min_x = min(first["min_x"], second["min_x"])
            new_max_x = max(first["max_x"], second["max_x"])
            new_min_y = min(first["min_y"], second["min_y"])
            new_max_y = max(first["max_y"], second["max_y"])
            new_quad = [
                [int(round(new_min_x)), int(round(new_min_y))],
                [int(round(new_max_x)), int(round(new_min_y))],
                [int(round(new_max_x)), int(round(new_max_y))],
                [int(round(new_min_x)), int(round(new_max_y))],
            ]
            combined_prob = (first["prob"] + second["prob"]) / 2.0
            new_item = {
                "coords": new_quad,
                "text": combined_text,
                "prob": combined_prob,
                "min_x": new_min_x,
                "max_x": new_max_x,
                "min_y": new_min_y,
                "max_y": new_max_y,
                "w": new_max_x - new_min_x,
                "h": new_max_y - new_min_y,
                "cx": (new_min_x + new_max_x) / 2.0,
                "cy": (new_min_y + new_max_y) / 2.0,
                "has_prefix": _has_multiline_prefix(combined_text),
            }
            # Remove indices from highest to lowest to preserve positions
            del items[max(first_idx, second_idx)]
            del items[min(first_idx, second_idx)]
            items.append(new_item)
            merged = True

    return [
        [
            [[int(round(pt[0])), int(round(pt[1]))] for pt in it["coords"]],
            it["text"],
            it["prob"],
        ]
        for it in items
    ]


def process_candidate_text(text_val: str, quad: list[list[int]]) -> dict[str, Any] | None:
    clean_text = re.sub(r"[\(\[\{]?\b(1[0-9]{3}|20[0-9]{2})\b[\)\]\}]?", "", text_val)
    # Retain newlines, but collapse spaces within each line
    clean_text = "\n".join(" ".join(line.split()) for line in clean_text.split("\n")).strip(" .,;:!?()[]{}'\"")
    if not clean_text or should_ignore(clean_text):
        return None
    return {
        "text": clean_text,
        "bbox": quad,
        "mapElementType": "ville",
    }


def _bbox_xyxy_to_quad_points(bbox_xyxy: list[Any]) -> list[list[float]]:
    """Convert [x1, y1, x2, y2] bbox to quad [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]."""
    x1, y1, x2, y2 = [float(v) for v in bbox_xyxy]
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _build_extracted_text_from_detections(
    detections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert raw OCR detections to the expected text/bbox structure used by the tests."""
    extracted_text: list[dict[str, Any]] = []
    for detection in detections:
        if not isinstance(detection, dict):
            continue

        raw_text = str(detection.get("text", "")).strip()
        if not raw_text:
            continue

        quad = detection.get("quad")
        if not isinstance(quad, list) or len(quad) != 4:
            bbox_xyxy = detection.get("bbox_xyxy")
            if not isinstance(bbox_xyxy, list) or len(bbox_xyxy) != 4:
                continue
            try:
                normalized_bbox = [int(v) for v in bbox_xyxy]
                quad = _bbox_xyxy_to_quad_points(normalized_bbox)
            except (TypeError, ValueError):
                continue
        else:
            try:
                quad = [[int(pt[0]), int(pt[1])] for pt in quad]
            except (TypeError, ValueError, IndexError):
                continue

        candidate_block = process_candidate_text(raw_text, quad)
        if candidate_block is not None:
            extracted_text.append(candidate_block)

    return extracted_text


def _run_ocr_pipeline(
    map_id: UUID,
    image_bytes: bytes,
) -> list[dict[str, Any]]:
    """
    Execute Florence-2 OCR pipeline on image_bytes.
    Returns detections in quad box format: [{"text": str, "bbox": [[x,y], ...]}, ...]
    """
    is_development = os.environ.get("ENV", "development").lower() not in (
        "production",
        "prod",
    )
    for d in (OCR_INPUT_DIR, OCR_OUTPUT_DIR):
        os.makedirs(d, exist_ok=True)
        if is_development:
            try:
                os.chmod(d, 0o777)
            except Exception as e:
                logger.debug(f"Failed to chmod {d}: {e}")

    input_basename = f"{map_id}.png"
    input_stem = str(map_id)
    ocr_input_path = f"{OCR_INPUT_DIR}/{input_basename}"
    ocr_output_json_path = f"{OCR_OUTPUT_DIR}/{input_stem}-florence.json"

    with open(ocr_input_path, "wb") as input_file:
        input_file.write(image_bytes)

    if is_development:
        try:
            os.chmod(ocr_input_path, 0o666)
        except Exception as e:
            logger.debug(f"Failed to chmod {ocr_input_path}: {e}")

    task_chain = celery_app.signature(
        "florence.run_pipeline",
        args=[ocr_input_path, ocr_output_json_path],
        immutable=True,
    ).set(queue="florence")

    parent_id = getattr(current_task, "request", None) and current_task.request.id
    florence_id = florence_task_id(parent_id) if parent_id else str(uuid4())

    try:
        ocr_result = task_chain.apply_async(task_id=florence_id)
        logger.info(f"==> [OCR] Task launched for map {map_id} (florence task {florence_id})")
        logger.info("==> [OCR] Florence-2 processing text detection and extraction...")

        try:
            assert ocr_result is not None
            elapsed = 0
            poll_interval = 5
            while elapsed < OCR_PIPELINE_TIMEOUT_SECONDS:
                if ocr_result.ready():
                    break
                try:
                    ocr_result.get(timeout=poll_interval, disable_sync_subtasks=False)
                    break
                except Exception as poll_err:
                    if poll_err.__class__.__name__ in ("TimeoutError", "CeleryTimeoutError"):
                        elapsed += poll_interval
                        if elapsed % 60 == 0:
                            logger.info(f"    ... Still running OCR pipeline - elapsed: {elapsed/60:.1f} min")
                    else:
                        raise poll_err
            else:
                raise TimeoutError(f"OCR pipeline timed out after {OCR_PIPELINE_TIMEOUT_SECONDS}s")

            logger.info(f"==> [OCR] Pipeline successfully completed for map {map_id} in ~{elapsed/60:.1f}min!")

            with open(ocr_output_json_path, "r", encoding="utf-8") as florence_result_file:
                florence_result = json.load(florence_result_file)

            if florence_result.get("partial"):
                logger.warning(
                    f"==> [OCR] Florence hit its time limit for map {map_id}: "
                    "keeping the text read before it, some labels may be missing"
                )
            detections = florence_result.get("detections", [])
            return _build_extracted_text_from_detections(detections)

        except Exception as exc:
            # Stop Florence too: otherwise it keeps working on a result nobody
            # waits for. Harmless when it already finished.
            try:
                celery_app.control.revoke(florence_id, terminate=True)
            except Exception as revoke_exc:
                logger.warning(f"Could not revoke florence task {florence_id}: {revoke_exc}")
            logger.exception("OCR pipeline failed or timed out for map %s: %s", map_id, exc)
            # Raised, not returned as []: an empty list is saved as "done, no
            # text", and the user cannot tell it from a map without labels.
            raise OcrPipelineError(f"OCR failed or timed out: {exc}") from exc
    finally:
        for temp_path in (ocr_input_path, ocr_output_json_path):
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            except Exception as exc:
                logger.warning(f"Failed to clean OCR temp file {temp_path}: {exc}")


def extract_text(
    map_id: UUID,
    image_bytes: bytes,
) -> list[dict[str, Any]]:
    """Extract text using the Florence-2 Celery OCR pipeline."""
    if not image_bytes:
        return []

    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
    if len(image_bytes) > MAX_FILE_SIZE_BYTES:
        logger.warning(
            f"Image for map {map_id} is too large ({len(image_bytes) / (1024 * 1024):.2f} MB). "
            f"Rejected to prevent an OOM crash (25 MB limit)."
        )
        return []

    logger.info(f"Starting OCR pipeline for map {map_id}")

    extracted_text = _run_ocr_pipeline(
        map_id=map_id,
        image_bytes=image_bytes,
    )
    logger.info(f"==> [OCR] Florence-2 : {len(extracted_text)} zones de texte détectées pour {map_id}")
    return extracted_text
