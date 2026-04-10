import json
import logging
import os
import re
from typing import Any
from uuid import UUID

from celery import chain

from app.utils.cities_validation import find_first_city

logger = logging.getLogger(__name__)

# OCR pipeline folders configuration
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
) -> list[dict[str, Any]]:
    """
    Execute Florence+Qwen OCR pipeline on file_content.
    Returns detections in quad box format: [{"text": str, "bbox": [[x,y], ...]}, ...]
    """
    # Declaring filenames and volume folders path for OCR process.
    os.makedirs(OCR_INPUT_DIR, exist_ok=True)
    os.makedirs(OCR_INTERMEDIATE_DIR, exist_ok=True)
    os.makedirs(OCR_OUTPUT_DIR, exist_ok=True)
    input_basename = f"{map_id}_{os.path.basename(filename)}"
    input_stem = os.path.splitext(input_basename)[0]
    ocr_input_path = os.path.join(OCR_INPUT_DIR, input_basename)
    ocr_intermediate_path = os.path.join(OCR_INTERMEDIATE_DIR, f"{input_stem}-florence.json")
    ocr_output_json_path = os.path.join(OCR_OUTPUT_DIR, f"{input_stem}-qwen.json")

    # Write image file to OCR input directory
    with open(ocr_input_path, "wb") as input_file:
        input_file.write(file_content)

    # Chains together Florence and Qwen tasks, sequentially. Both run in different
    # containers and are set to concurrency=1, so this ensures that OCR do not hoard
    # resources from other users.
    task_chain = chain(
        celery_app.signature(
            "florence.run_pipeline",
            args=[ocr_input_path, ocr_intermediate_path],
        ).set(queue="florence"),
        celery_app.signature(
            "qwen.run_pipeline",
            args=[ocr_input_path, ocr_intermediate_path, ocr_output_json_path],
        ).set(queue="qwen"),
    )

    # Execute the OCR chain on dedicated OCR workers and wait for completion here.
    # This is safe in the current topology because the parent task runs on a separate queue.
    ocr_result = task_chain.apply_async()
    logger.info(f"Waiting for OCR chain to complete for map {map_id}")
    ocr_result.get(
        timeout=OCR_PIPELINE_TIMEOUT_SECONDS,
        disable_sync_subtasks=False,
    )
    logger.info(f"OCR chain completed for map {map_id}")

    # Load Qwen output JSON
    with open(ocr_output_json_path, "r", encoding="utf-8") as qwen_result_file:
        qwen_result = json.load(qwen_result_file)

    # Normalize detections for backend consumers.
    detections = qwen_result.get("detections", [])
    extracted_text = []
    for detection in detections:
        if not isinstance(detection, dict):
            continue
        bbox_xyxy = detection.get("bbox_xyxy")
        if not isinstance(bbox_xyxy, list) or len(bbox_xyxy) != 4:
            continue
        try:
            normalized_bbox = [int(v) for v in bbox_xyxy]
        except (TypeError, ValueError):
            continue
        extracted_text.append(
            {
                "text": str(detection.get("text", "")),
                "bbox": _bbox_xyxy_to_quad_points(normalized_bbox),
            }
        )

    # Clean up OCR files by explicit full paths derived from naming convention.
    try:
        os.unlink(ocr_input_path)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Failed to clean OCR input file {ocr_input_path}: {e}")

    try:
        os.unlink(ocr_intermediate_path)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(
            f"Failed to clean OCR intermediate file {ocr_intermediate_path}: {e}"
        )

    try:
        os.unlink(ocr_output_json_path)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Failed to clean OCR output file {ocr_output_json_path}: {e}")

    return extracted_text


def detect_and_persist_cities(
    extracted_text: list[dict[str, Any]], map_id: UUID
) -> dict:
    """
    Tokenize extracted OCR text and run city detection per token, then persist to DB.

    Args:
        extracted_text: List of dict detections with keys text and bbox
        map_id: Map UUID for DB persistence

    Returns:
        Dict with city detection stats: cities_detected, cities_persisted, errors
    """
    result = {"cities_detected": 0, "cities_persisted": 0, "errors": []}

    if not extracted_text:
        return result

    try:
        text_strings = [str(block.get("text", "")) for block in extracted_text]
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
) -> tuple[list[dict[str, Any]], list[list[int]]]:
    """
    Text extraction function using OCR pipeline. Uses Microsoft/Florence2-large for OCR and text
    detection, then Qwen/Qwen3.5-4B for text cleaning and correction.

    Args:
        map_id: UUID of the map being processed
        filename: Original filename of the uploaded map image
        file_content: Raw bytes of the uploaded image file
        celery_app: Celery app instance for dispatching OCR tasks
    Returns:
        (extracted_text, text_regions)
        - extracted_text: list of dict detections with keys text and bbox
        - text_regions: list of bbox polygons used by shape filtering
    Raises:
        Exception: If OCR pipeline fails or times out
    """
    logger.info(f"Starting OCR pipeline for map {map_id}: {filename}")

    extracted_text = _run_ocr_pipeline(map_id, filename, file_content, celery_app)
    text_regions = [
        block["bbox"]
        for block in extracted_text
        if isinstance(block, dict)
        and isinstance(block.get("bbox"), list)
        and len(block["bbox"]) == 4
    ]

    logger.info(
        f"OCR pipeline completed: {len(extracted_text)} detections extracted from {filename}"
    )

    return extracted_text, text_regions
