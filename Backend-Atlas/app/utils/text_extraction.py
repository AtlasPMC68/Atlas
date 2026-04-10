import json
import logging
import os
import asyncio
from typing import Any
from uuid import UUID

from celery import chain

from app.utils.cities_validation import find_first_city
from app.utils.georeferencingSift import georeference_features_with_sift_points

logger = logging.getLogger(__name__)

# OCR pipeline folders configuration
OCR_INPUT_DIR = os.getenv("OCR_INPUT_DIR", "/data/input")
OCR_INTERMEDIATE_DIR = os.getenv("OCR_INTERMEDIATE_DIR", "/data/intermediate")
OCR_OUTPUT_DIR = os.getenv("OCR_OUTPUT_DIR", "/data/result")
OCR_PIPELINE_TIMEOUT_SECONDS = int(os.getenv("OCR_PIPELINE_TIMEOUT_SECONDS", "900"))


def _extract_bbox_center_anchor(bbox_quad: object) -> tuple[float | None, float | None]:
    """Return bbox center anchor (x, y) from a quad list, or (None, None) if invalid."""
    if not isinstance(bbox_quad, list) or len(bbox_quad) != 4:
        return None, None

    try:
        xs = [float(pt[0]) for pt in bbox_quad if isinstance(pt, list) and len(pt) == 2]
        ys = [float(pt[1]) for pt in bbox_quad if isinstance(pt, list) and len(pt) == 2]
        if len(xs) != 4 or len(ys) != 4:
            return None, None
        return sum(xs) / 4.0, sum(ys) / 4.0
    except (TypeError, ValueError):
        return None, None


def _build_city_feature_collection(text: str, candidate: dict[str, Any]) -> dict[str, Any]:
    """Build one city point feature collection from gazetteer match output."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": candidate.get("name") or text,
                    "show": True,
                    "mapElementType": "point",
                    "color_name": "black",
                    "color_rgb": [0, 0, 0],
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        candidate.get("lon") or 0.0,
                        candidate.get("lat") or 0.0,
                    ],
                },
            }
        ],
    }


def _build_pixel_text_feature_collection(text: str, x: float, y: float) -> dict[str, Any]:
    """Build one pixel-space text point feature collection from bbox anchor."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": text,
                    "show": False,
                    "mapElementType": "point",
                    "color_name": "black",
                    "color_rgb": [0, 0, 0],
                    "source": "ocr_bbox_anchor",
                    "is_pixel_space": True,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [x, y],
                },
            }
        ],
    }


def geolocate_cities_and_leftover_text(
    extracted_text: list[dict[str, Any]],
    project_id: UUID,
    map_id: UUID,
    pixel_points: list | None,
    geo_points_lonlat: list | None,
    persist_city_feature_fn,
    persist_features_fn,
) -> None:
    """Persist city-matched text points and georeference unmatched OCR text anchors."""
    pixel_text_feature_collections = []

    for block in extracted_text:
        if not isinstance(block, dict):
            continue

        text = str(block.get("text", "")).strip()
        if not text:
            continue

        anchor_x, anchor_y = _extract_bbox_center_anchor(block.get("bbox"))

        try:
            candidate = find_first_city(text)
        except Exception as e:
            logger.debug(f"find_first_city error for text '{text}': {e}")
            candidate = {
                "found": False,
                "query": text,
                "name": text,
                "lat": 0.0,
                "lon": 0.0,
            }

        if bool(candidate.get("found")):
            city_feature_collection = _build_city_feature_collection(text, candidate)
            try:
                asyncio.run(
                    persist_city_feature_fn(project_id, map_id, city_feature_collection)
                )
            except Exception as e:
                logger.error(f"Failed to persist city text '{text}': {e}")
        elif anchor_x is not None and anchor_y is not None:
            pixel_text_feature_collections.append(
                _build_pixel_text_feature_collection(text, anchor_x, anchor_y)
            )

    if pixel_text_feature_collections and pixel_points and geo_points_lonlat:
        georef_text_features = georeference_features_with_sift_points(
            pixel_text_feature_collections,
            pixel_points,
            geo_points_lonlat,
            snap_to_coastline=False,
            clip_to_land_mask=False,
        )
        asyncio.run(persist_features_fn(project_id, map_id, georef_text_features))


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

    try:
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

        return extracted_text
    finally:
        # Clean up OCR files even in the case of failures/timeouts to prevent bloating
        for temp_path, label in (
            (ocr_input_path, "input"),
            (ocr_intermediate_path, "intermediate"),
            (ocr_output_json_path, "output"),
        ):
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.warning(f"Failed to clean OCR {label} file {temp_path}: {e}")


def extract_text(
    map_id: UUID,
    filename: str,
    file_content: bytes,
    celery_app,
) -> tuple[list[dict[str, Any]], list[list[list[float]]]]:
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
          Example: [{
                  "text": "Quebec",
                  "bbox": [[120.0, 80.0], [190.0, 80.0], [190.0, 110.0], [120.0, 110.0]],
              }]
        - text_regions: list of bbox polygons used by shape filtering
          Example: [
              [[120.0, 80.0], [190.0, 80.0], [190.0, 110.0], [120.0, 110.0]]
          }]
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
