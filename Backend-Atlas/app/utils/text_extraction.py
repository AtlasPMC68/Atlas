import json
import logging
import os
import re
from typing import Any
from uuid import UUID

from celery import chain

from app.utils.cities_validation import find_first_city

logger = logging.getLogger(__name__)

# OCR pipeline directory configuration
OCR_INPUT_DIR = os.getenv("OCR_INPUT_DIR", "/data/input")
OCR_INTERMEDIATE_DIR = os.getenv("OCR_INTERMEDIATE_DIR", "/data/intermediate")
OCR_OUTPUT_DIR = os.getenv("OCR_OUTPUT_DIR", "/data/result")
OCR_PIPELINE_TIMEOUT_SECONDS = int(os.getenv("OCR_PIPELINE_TIMEOUT_SECONDS", "1200"))


def _bbox_xyxy_to_quad_points(bbox_xyxy: list[Any]) -> list[list[float]]:
    """Convert [x1, y1, x2, y2] bbox to quad [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]."""
    x1, y1, x2, y2 = [float(v) for v in bbox_xyxy]
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _run_ocr_pipeline(
    map_id: UUID,
    filename: str,
    file_content: bytes,
    celery_app,
) -> list[tuple[list, str, float]]:
    """
    Execute Florence+Qwen OCR pipeline on file_content.
    Returns extracted_text in format: [(quad_points, text, confidence), ...]
    """
    os.makedirs(OCR_INPUT_DIR, exist_ok=True)
    os.makedirs(OCR_INTERMEDIATE_DIR, exist_ok=True)
    os.makedirs(OCR_OUTPUT_DIR, exist_ok=True)

    input_basename = f"{map_id}_{os.path.basename(filename)}"
    input_stem = os.path.splitext(input_basename)[0]

    ocr_input_path = os.path.join(OCR_INPUT_DIR, input_basename)
    ocr_intermediate_path = os.path.join(
        OCR_INTERMEDIATE_DIR, f"{input_stem}-florence.json"
    )
    ocr_output_json_path = os.path.join(OCR_OUTPUT_DIR, f"{input_stem}-qwen.json")

    # Write image file to OCR input directory
    with open(ocr_input_path, "wb") as input_file:
        input_file.write(file_content)

    # Chains together Florence and Qwen tasks, passing intermediate results via file paths
    workflow = chain(
        celery_app.signature(
            "florence.run_pipeline",
            args=[ocr_input_path, ocr_intermediate_path],
        ).set(queue="florence"),
        celery_app.signature(
            "qwen.run_pipeline",
            args=[ocr_input_path, ocr_intermediate_path, ocr_output_json_path],
        ).set(queue="qwen"),
    )

    # Execute and wait for completion (gevent yields during this blocking call)
    ocr_result = workflow.apply_async()
    ocr_result.get(timeout=OCR_PIPELINE_TIMEOUT_SECONDS)

    # Load Qwen output JSON
    with open(ocr_output_json_path, "r", encoding="utf-8") as qwen_result_file:
        qwen_result = json.load(qwen_result_file)

    # Convert detections to expected format: (quad_points, text, confidence)
    detections = qwen_result.get("detections", [])
    extracted_text = [
        (
            _bbox_xyxy_to_quad_points(detection.get("bbox_xyxy", [0, 0, 0, 0])),
            str(detection.get("text", "")),
            1.0,
        )
        for detection in detections
        if isinstance(detection, dict)
        and isinstance(detection.get("bbox_xyxy"), list)
        and len(detection.get("bbox_xyxy")) == 4
    ]

    # Clean up temporary OCR input and intermediate files
    for ocr_temp_path in [ocr_input_path, ocr_intermediate_path]:
        try:
            if os.path.exists(ocr_temp_path):
                os.unlink(ocr_temp_path)
        except Exception as e:
            logger.warning(f"Failed to clean OCR temp file {ocr_temp_path}: {e}")

    return extracted_text


def detect_and_persist_cities(
    extracted_text: list[tuple], map_id: UUID
) -> dict:
    """
    Tokenize extracted OCR text and run city detection per token, then persist to DB.

    Args:
        extracted_text: List of (quad_points, text, confidence) tuples
        map_id: Map UUID for DB persistence

    Returns:
        Dict with city detection stats: cities_detected, cities_persisted, errors
    """
    result = {"cities_detected": 0, "cities_persisted": 0, "errors": []}

    if not extracted_text:
        return result

    try:
        # Extract just the text strings from tuples [(coords, text, prob), ...]
        text_strings = [block[1] for block in extracted_text]
        full_text = " ".join(text_strings)
        tokens = re.findall(r"\b[\w\-']+\b", full_text)

        for tok in tokens:
            try:
                candidate = find_first_city(tok)
                result["cities_detected"] += 1
                if candidate.get("found"):
                    result["cities_persisted"] += 1
            except Exception as e:
                logger.debug(f"find_first_city error for token '{tok}': {e}")
                result["errors"].append({"token": tok, "error": str(e)})

    except Exception as e:
        logger.error(f"City detection batch processing failed: {e}")
        result["errors"].append({"batch": "city_detection", "error": str(e)})

    return result


def extract_text(
    map_id: UUID,
    filename: str,
    file_content: bytes,
    celery_app,
) -> tuple[list[tuple], list[Any]]:
    """
    Master text extraction function using OCR pipeline (Florence + Qwen).

    Args:
        map_id: UUID of the map being processed
        filename: Original filename
        file_content: Raw image bytes
        celery_app: Celery app instance for task dispatch

    Returns:
        (extracted_text, text_regions)
        - extracted_text: list of (quad_points, text, confidence)
        - text_regions: list of quad_points for each detection

    Raises:
        Exception: If OCR pipeline fails or times out
    """
    logger.info(f"Starting OCR pipeline for map {map_id}: {filename}")

    extracted_text = _run_ocr_pipeline(map_id, filename, file_content, celery_app)
    text_regions = [block[0] for block in extracted_text]

    logger.info(
        f"OCR pipeline completed: {len(extracted_text)} detections extracted from {filename}"
    )

    return extracted_text, text_regions
