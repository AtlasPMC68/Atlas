import json
import logging
import os
import re
from typing import Any
from uuid import UUID

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

OCR_INPUT_DIR = os.getenv("OCR_INPUT_DIR", "/data/ocr_input")
OCR_OUTPUT_DIR = os.getenv("OCR_OUTPUT_DIR", "/data/ocr_result")
OCR_PIPELINE_TIMEOUT_SECONDS = int(os.getenv("OCR_PIPELINE_TIMEOUT_SECONDS", "900"))

# fmt: off
MAP_IGNORED_WORDS = {
    "n", "s", "e", "w", "o", "ne", "nw", "no", "se", "sw", "so",
    "nord", "sud", "est", "ouest", "n.-e.", "n.-o.", "s.-e.", "s.-o.",
}
# fmt: on


def should_ignore(text_val: str) -> bool:
    clean = text_val.lower().strip(" .,;:!?()[]{}'\"")

    if clean in MAP_IGNORED_WORDS:
        return True

    if all(c.isdigit() or c.isspace() or c in ".," for c in clean):
        return True
    for keyword in ["légende", "legende", "échelle", "echelle", "scale", "kilomètre", "kilometre", "miles"]:
        if keyword in clean:
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
    return payload


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

    try:
        ocr_result = task_chain.apply_async()
        logger.info(f"==> [OCR] Task launched for map {map_id}")
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

            detections = florence_result.get("detections", [])
            return _build_extracted_text_from_detections(detections)

        except Exception as exc:
            logger.exception("OCR pipeline failed or timed out for map %s: %s", map_id, exc)
            return []
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
