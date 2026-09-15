import asyncio
import json
import logging
import os
import sys
from typing import Any
from uuid import UUID

from celery import chain

from app.utils.cities_validation import find_first_city
from app.utils.georeferencingSift import georeference_features_with_sift_points

try:
    import coloredlogs

    HAS_COLOREDLOGS = True
except ImportError:
    HAS_COLOREDLOGS = False

logger = logging.getLogger(__name__)
log_level = os.getenv("OCR_LOG_LEVEL", "INFO").upper()

if HAS_COLOREDLOGS:
    coloredlogs.install(
        level=log_level,
        logger=logger,
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
else:
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
            )
        )
        logger.addHandler(handler)

# OCR pipeline folders configuration
OCR_INPUT_DIR = os.getenv("OCR_INPUT_DIR", "/data/ocr_input")
OCR_INTERMEDIATE_DIR = os.getenv("OCR_INTERMEDIATE_DIR", "/data/ocr_intermediate")
OCR_OUTPUT_DIR = os.getenv("OCR_OUTPUT_DIR", "/data/ocr_result")
OCR_PIPELINE_TIMEOUT_SECONDS = int(os.getenv("OCR_PIPELINE_TIMEOUT_SECONDS", "900"))
CITY_BOUNDS_PAD_RATIO = float(os.getenv("CITY_BOUNDS_PAD_RATIO", "0.08"))
CITY_BOUNDS_PAD_MIN_DEG = float(os.getenv("CITY_BOUNDS_PAD_MIN_DEG", "0.25"))


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


def _build_city_feature_collection(
    text: str, candidate: dict[str, Any]
) -> dict[str, Any]:
    """Build one city point feature for each geolocated city candidate."""
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


def _build_pixel_text_feature_collection(
    text: str, x: float, y: float
) -> dict[str, Any]:
    """Build text zones for OCR detections that could not be geolocated as cities."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": text,
                    "labelText": text,
                    "show": True,
                    "mapElementType": "label",
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


def _compute_geo_bounds(geo_points_lonlat: list) -> dict[str, float] | None:
    """Return {min_lon, max_lon, min_lat, max_lat} from a list of (lon, lat) points, or None."""
    if not geo_points_lonlat or len(geo_points_lonlat) < 2:
        return None
    try:
        lons = [float(p[0]) for p in geo_points_lonlat]
        lats = [float(p[1]) for p in geo_points_lonlat]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)

        lon_span = max_lon - min_lon
        lat_span = max_lat - min_lat
        lon_pad = max(lon_span * CITY_BOUNDS_PAD_RATIO, CITY_BOUNDS_PAD_MIN_DEG)
        lat_pad = max(lat_span * CITY_BOUNDS_PAD_RATIO, CITY_BOUNDS_PAD_MIN_DEG)

        return {
            "min_lon": min_lon - lon_pad,
            "max_lon": max_lon + lon_pad,
            "min_lat": min_lat - lat_pad,
            "max_lat": max_lat + lat_pad,
        }
    except (TypeError, ValueError, IndexError):
        return None


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
    geo_bounds = _compute_geo_bounds(geo_points_lonlat) if geo_points_lonlat else None

    for block in extracted_text:
        if not isinstance(block, dict):
            continue

        text = str(block.get("text", "")).strip()
        if not text:
            continue

        anchor_x, anchor_y = _extract_bbox_center_anchor(block.get("bbox"))

        try:
            candidate = find_first_city(text, geo_bounds=geo_bounds)
        except Exception as exc:
            logger.debug(f"find_first_city error for text '{text}': {exc}")
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
            except Exception as exc:
                logger.error(f"Failed to persist city text '{text}': {exc}")
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


def _build_extracted_text_from_detections(
    detections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert raw OCR detections to the expected text/bbox structure used by the tests."""
    extracted_text: list[dict[str, Any]] = []
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

        raw_text = str(detection.get("text", "")).strip()
        if not raw_text:
            continue

        quad = _bbox_xyxy_to_quad_points(normalized_bbox)
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        if len(lines) > 1:
            for line in lines:
                extracted_text.append({"text": line, "bbox": quad})
        extracted_text.append({"text": raw_text, "bbox": quad})

    return extracted_text


def preprocess_image_for_ocr(file_content: bytes) -> bytes:
    """Preprocess the image bytes for better OCR results using CLAHE and sharpening."""
    try:
        import cv2
        import numpy as np

        np_arr = np.frombuffer(file_content, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:
            return file_content

        # Enhance contrast without losing color information using LAB color space
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        # Apply Contrast Limited Adaptive Histogram Equalization (CLAHE) to the L-channel
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)

        # Merge back and convert to BGR
        limg = cv2.merge((cl, a, b))
        enhanced_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

        # Upscale the image by 2x to help OCR models read small and blurry historical fonts
        enhanced_img = cv2.resize(
            enhanced_img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC
        )

        # Encode back to bytes
        _, encoded_img = cv2.imencode(".jpg", enhanced_img)
        return encoded_img.tobytes()

    except (ImportError, AttributeError):
        return file_content


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
    is_development = os.environ.get("ENV", "development").lower() not in (
        "production",
        "prod",
    )
    for d in (OCR_INPUT_DIR, OCR_INTERMEDIATE_DIR, OCR_OUTPUT_DIR):
        os.makedirs(d, exist_ok=True)
        if is_development:
            try:
                os.chmod(d, 0o777)
            except Exception as e:
                logger.debug(f"Failed to chmod {d}: {e}")

    input_basename = f"{map_id}_{os.path.basename(filename)}"
    input_stem = os.path.splitext(input_basename)[0]
    ocr_input_path = f"{OCR_INPUT_DIR}/{input_basename}"
    ocr_intermediate_path = f"{OCR_INTERMEDIATE_DIR}/{input_stem}-florence.json"
    ocr_output_json_path = f"{OCR_OUTPUT_DIR}/{input_stem}-qwen.json"

    with open(ocr_input_path, "wb") as input_file:
        input_file.write(file_content)

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
        ocr_result = task_chain.apply_async()
        logger.info(f"==> [OCR] Task chain launched for {filename} (ID: {map_id})")
        logger.info(
            "==> [OCR] Step 1/2: Florence-2 processing text detection and captioning..."
        )
        try:
            assert ocr_result is not None
            # Poll with timeout to give live user feedback instead of a silent hang
            elapsed = 0
            poll_interval = 5
            stage = "florence"
            while elapsed < OCR_PIPELINE_TIMEOUT_SECONDS:
                if stage == "florence" and os.path.exists(ocr_intermediate_path):
                    stage = "qwen"
                    logger.info(
                        f"==> [OCR] Step 1/2 complete ({elapsed}s)! Step 2/2: Qwen model correcting text..."
                    )

                if ocr_result.ready():
                    break

                try:
                    ocr_result.get(timeout=poll_interval, disable_sync_subtasks=False)
                    break
                except Exception as poll_err:
                    # TimeoutError means task is still running in background Celery worker
                    if poll_err.__class__.__name__ in (
                        "TimeoutError",
                        "CeleryTimeoutError",
                    ):
                        elapsed += poll_interval
                        if elapsed % 60 == 0:
                            current_step = (
                                "Florence-2 (detecting text)"
                                if stage == "florence"
                                else "Qwen (correcting text)"
                            )
                            logger.info(
                                f"    ... Still running {current_step} - elapsed: {elapsed}s"
                            )
                    else:
                        raise poll_err
            else:
                raise TimeoutError(
                    f"OCR pipeline timed out after {OCR_PIPELINE_TIMEOUT_SECONDS}s"
                )

            logger.info(
                f"==> [OCR] Pipeline successfully completed for {filename} in ~{elapsed}s!"
            )

            with open(ocr_output_json_path, "r", encoding="utf-8") as qwen_result_file:
                qwen_result = json.load(qwen_result_file)
            detections = qwen_result.get("detections", [])
            return _build_extracted_text_from_detections(detections)
        except Exception as exc:
            logger.warning(
                "OCR full chain timed out or failed for map %s; falling back to Florence output: %s",
                map_id,
                exc,
            )

            if os.path.exists(ocr_intermediate_path):
                try:
                    with open(
                        ocr_intermediate_path, "r", encoding="utf-8"
                    ) as florence_result_file:
                        florence_result = json.load(florence_result_file)
                    detections = florence_result.get("detections", [])
                    return _build_extracted_text_from_detections(detections)
                except json.JSONDecodeError:
                    logger.warning(
                        "Florence intermediate file exists but is incomplete (race condition during fallback)."
                    )
            raise
    finally:
        for temp_path in (ocr_input_path, ocr_intermediate_path, ocr_output_json_path):
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            except Exception as exc:
                logger.warning(f"Failed to clean OCR temp file {temp_path}: {exc}")


def _extract_text_via_pipeline(
    map_id: UUID,
    filename: str,
    file_content: bytes,
    celery_app,
) -> tuple[list[dict[str, Any]], list[list[list[float]]]]:
    extracted_text = _run_ocr_pipeline(map_id, filename, file_content, celery_app)
    text_regions = [
        block["bbox"]
        for block in extracted_text
        if isinstance(block, dict)
        and isinstance(block.get("bbox"), list)
        and len(block["bbox"]) == 4
    ]
    return extracted_text, text_regions


def extract_text(
    map_id: UUID,
    filename: str,
    file_content: bytes,
    celery_app=None,
):
    """Extract text using the Florence+Qwen Celery OCR pipeline."""
    if celery_app is None:
        raise ValueError("celery_app must be provided")

    # Limite préventive pour éviter le crash OOM (Out of Memory) sur les workers OCR
    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
    if len(file_content) > MAX_FILE_SIZE_BYTES:
        logger.warning(
            f"Image {filename} trop volumineuse ({len(file_content) / (1024*1024):.2f} MB). "
            f"Rejetée pour éviter un crash OOM (limite à 25 MB)."
        )
        return [], []

    logger.info(f"Starting OCR pipeline for map {map_id}: {filename}")
    extracted_text, text_regions = _extract_text_via_pipeline(
        map_id=map_id,
        filename=filename,
        file_content=file_content,
        celery_app=celery_app,
    )
    logger.info(
        f"OCR pipeline completed: {len(extracted_text)} detections extracted from {filename}"
    )
    return extracted_text, text_regions
