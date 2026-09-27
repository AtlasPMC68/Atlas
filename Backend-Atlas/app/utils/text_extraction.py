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
            logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)

OCR_INPUT_DIR = os.getenv("OCR_INPUT_DIR", "/data/ocr_input")
OCR_INTERMEDIATE_DIR = os.getenv("OCR_INTERMEDIATE_DIR", "/data/ocr_intermediate")
OCR_OUTPUT_DIR = os.getenv("OCR_OUTPUT_DIR", "/data/ocr_result")
OCR_PIPELINE_TIMEOUT_SECONDS = int(os.getenv("OCR_PIPELINE_TIMEOUT_SECONDS", "900"))
CITY_BOUNDS_PAD_RATIO = float(os.getenv("CITY_BOUNDS_PAD_RATIO", "0.08"))
CITY_BOUNDS_PAD_MIN_DEG = float(os.getenv("CITY_BOUNDS_PAD_MIN_DEG", "0.25"))


def _extract_bbox_center_anchor(
    bbox_quad: object, center: object = None
) -> tuple[float | None, float | None]:
    """Return bbox center anchor (x, y) from explicit center or quad list, or (None, None) if invalid."""
    if isinstance(center, (list, tuple)) and len(center) == 2:
        try:
            return float(center[0]), float(center[1])
        except (TypeError, ValueError):
            pass

    if not isinstance(bbox_quad, list) or len(bbox_quad) != 4:
        return None, None

    try:
        xs = [float(pt[0]) for pt in bbox_quad if isinstance(pt, (list, tuple)) and len(pt) == 2]
        ys = [float(pt[1]) for pt in bbox_quad if isinstance(pt, (list, tuple)) and len(pt) == 2]
        if len(xs) != 4 or len(ys) != 4:
            return None, None
        return sum(xs) / 4.0, sum(ys) / 4.0
    except (TypeError, ValueError):
        return None, None


def _build_city_feature_collection(
    text: str,
    candidate: dict[str, Any],
    box_height: float = 12,
    rotation_angle: float = 0,
    anchor_x: float = 0.0,
    anchor_y: float = 0.0,
) -> dict[str, Any]:
    """Build one city point feature using pixel coordinates for later georeferencing."""
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
                    "boxHeight": box_height,
                    "rotationAngle": rotation_angle,
                    "is_pixel_space": True,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [anchor_x, anchor_y],
                },
            }
        ],
    }


def _build_pixel_text_feature_collection(
    text: str,
    x: float,
    y: float,
    box_height: float = 12,
    rotation_angle: float = 0,
    map_element_type: str = "label",
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
                    "show": False if map_element_type == "rejet" else True,
                    "mapElementType": map_element_type,
                    "color_name": "black",
                    "color_rgb": [0, 0, 0],
                    "source": "ocr_bbox_anchor",
                    "is_pixel_space": True,
                    "boxHeight": box_height,
                    "rotationAngle": rotation_angle,
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
    cities_to_georef = []
    geo_bounds = _compute_geo_bounds(geo_points_lonlat) if geo_points_lonlat else None

    for block in extracted_text:
        if not isinstance(block, dict):
            continue

        text = str(block.get("text", "")).strip()
        if not text:
            continue

        anchor_x, anchor_y = _extract_bbox_center_anchor(
            block.get("bbox"), center=block.get("center")
        )

        box_height = block.get("boxHeight", 12)
        rotation_angle = block.get("rotationAngle", 0)
        map_element_type = block.get("mapElementType", "label")

        if map_element_type == "rejet":
            candidate = {"found": False}
        else:
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

        if bool(candidate.get("found")) and anchor_x is not None and anchor_y is not None:
            city_feature_collection = _build_city_feature_collection(
                text, candidate, box_height, rotation_angle, anchor_x, anchor_y
            )
            cities_to_georef.append(city_feature_collection)
        elif anchor_x is not None and anchor_y is not None:
            pixel_text_feature_collections.append(
                _build_pixel_text_feature_collection(
                    text, anchor_x, anchor_y, box_height, rotation_angle, map_element_type
                )
            )

    async def _run_all():
        city_persist_coroutines = []
        if cities_to_georef and pixel_points and geo_points_lonlat:
            from app.utils.georeferencingSift import (
                georeference_features_with_sift_points,
            )

            georef_cities = georeference_features_with_sift_points(
                cities_to_georef,
                pixel_points,
                geo_points_lonlat,
                snap_to_coastline=False,
                clip_to_land_mask=False,
            )
            for city_feat in georef_cities:
                city_persist_coroutines.append(
                    persist_city_feature_fn(project_id, map_id, city_feat)
                )
        elif cities_to_georef:
            for city_feat in cities_to_georef:
                city_persist_coroutines.append(
                    persist_city_feature_fn(project_id, map_id, city_feat)
                )

        if city_persist_coroutines:
            results = await asyncio.gather(*city_persist_coroutines, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    logger.error(f"Failed to persist city text: {res}")

        if pixel_text_feature_collections and pixel_points and geo_points_lonlat:
            georef_text_features = georeference_features_with_sift_points(
                pixel_text_feature_collections,
                pixel_points,
                geo_points_lonlat,
                snap_to_coastline=False,
                clip_to_land_mask=False,
            )
            try:
                await persist_features_fn(project_id, map_id, georef_text_features)
            except Exception as exc:
                logger.error(f"Failed to persist georeferenced features: {exc}")

    if cities_to_georef or pixel_text_feature_collections:
        try:
            asyncio.run(_run_all())
        except RuntimeError:
            import threading

            thread = threading.Thread(target=lambda: asyncio.run(_run_all()))
            thread.start()
            thread.join()


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
        import re

        raw_text = re.sub(r"<loc_\d+>", "", raw_text).strip()
        if not raw_text:
            continue

        quad_points = None
        quad_raw = detection.get("quad")
        if isinstance(quad_raw, list):
            if len(quad_raw) == 8:
                try:
                    quad_points = [
                        [float(quad_raw[0]), float(quad_raw[1])],
                        [float(quad_raw[2]), float(quad_raw[3])],
                        [float(quad_raw[4]), float(quad_raw[5])],
                        [float(quad_raw[6]), float(quad_raw[7])],
                    ]
                except (TypeError, ValueError, IndexError):
                    quad_points = None
            elif len(quad_raw) == 4 and all(
                isinstance(pt, (list, tuple)) and len(pt) == 2 for pt in quad_raw
            ):
                try:
                    quad_points = [[float(pt[0]), float(pt[1])] for pt in quad_raw]
                except (TypeError, ValueError):
                    quad_points = None

        if quad_points is None:
            bbox_xyxy = detection.get("bbox_xyxy")
            if not isinstance(bbox_xyxy, list) or len(bbox_xyxy) != 4:
                continue
            try:
                quad_points = _bbox_xyxy_to_quad_points([float(v) for v in bbox_xyxy])
            except (TypeError, ValueError):
                continue

        center = detection.get("center")
        if isinstance(center, (list, tuple)) and len(center) == 2:
            try:
                center_pt = [float(center[0]), float(center[1])]
            except (TypeError, ValueError):
                center_pt = [
                    sum(pt[0] for pt in quad_points) / 4.0,
                    sum(pt[1] for pt in quad_points) / 4.0,
                ]
        else:
            center_pt = [
                sum(pt[0] for pt in quad_points) / 4.0,
                sum(pt[1] for pt in quad_points) / 4.0,
            ]

        try:
            import math

            dx = quad_points[1][0] - quad_points[0][0]
            dy = quad_points[1][1] - quad_points[0][1]
            rotation_angle = math.degrees(math.atan2(dy, dx))
            edge_h = math.hypot(
                quad_points[3][0] - quad_points[0][0],
                quad_points[3][1] - quad_points[0][1],
            )
            box_height = edge_h if edge_h > 0 else 12.0
        except Exception:
            rotation_angle = float(detection.get("angle", 0.0))
            box_height = 12.0

        def should_ignore(text_val: str) -> bool:
            clean = text_val.strip(" .,;:!?()[]{}'\"-–—_«»/\\")
            if not clean or all(c in " .,;:!?()[]{}'\"-–—_«»/\\" for c in text_val):
                return True

            if all(c.isdigit() or c.isspace() or c in ".,-–—_" for c in clean):
                return True

            if len(clean.split()) > 5:
                return True

            return False

        from app.utils.map_dictionary import apply_map_dictionary_correction

        # Vérifie si le bloc entier doit être ignoré
        if should_ignore(raw_text):
            continue

        corrected_text, category = apply_map_dictionary_correction(raw_text)
        if not corrected_text or category == "ignored":
            continue

        clean_word = corrected_text.strip(" .,;:!?()[]{}'\"-–—_«»/\\")
        # Si c'est un rejet : supprimer les tirets, la ponctuation et les bruits isolés de 1 caractère
        if category == "rejet":
            if not clean_word or len(clean_word) <= 1:
                continue

        extracted_text.append(
            {
                "text": corrected_text,
                "bbox": quad_points,
                "center": center_pt,
                "boxHeight": box_height,
                "rotationAngle": rotation_angle,
                "mapElementType": category,
            }
        )

    # Non-Maximum Suppression (NMS) pour éliminer les doublons et chevauchements
    extracted_text.sort(
        key=lambda x: (abs(x.get("rotationAngle", 0)), -len(x["text"]))
    )  # Garder l'angle 0 en priorité, puis les mots les plus longs
    filtered_text = []

    import math

    for current in extracted_text:
        is_duplicate = False
        c_box = current["bbox"]
        c_min_x, c_max_x = min(p[0] for p in c_box), max(p[0] for p in c_box)
        c_min_y, c_max_y = min(p[1] for p in c_box), max(p[1] for p in c_box)
        c_area = max(1, (c_max_x - c_min_x) * (c_max_y - c_min_y))
        c_center_x = current["center"][0] if "center" in current else (c_min_x + c_max_x) / 2
        c_center_y = current["center"][1] if "center" in current else (c_min_y + c_max_y) / 2
        c_text = current["text"].lower().strip()

        for kept in filtered_text:
            k_box = kept["bbox"]
            k_min_x, k_max_x = min(p[0] for p in k_box), max(p[0] for p in k_box)
            k_min_y, k_max_y = min(p[1] for p in k_box), max(p[1] for p in k_box)
            k_center_x = kept["center"][0] if "center" in kept else (k_min_x + k_max_x) / 2
            k_center_y = kept["center"][1] if "center" in kept else (k_min_y + k_max_y) / 2
            k_text = kept["text"].lower().strip()

            xA = max(c_min_x, k_min_x)
            yA = max(c_min_y, k_min_y)
            xB = min(c_max_x, k_max_x)
            yB = min(c_max_y, k_max_y)
            interArea = max(0, xB - xA) * max(0, yB - yA)
            k_area = max(1, (k_max_x - k_min_x) * (k_max_y - k_min_y))

            # Condition 1: Fort chevauchement spatial
            if interArea / min(c_area, k_area) > 0.3:
                is_duplicate = True
                break

            # Condition 2: Même texte et centres proches (distance < 2x la hauteur de la boîte)
            # Utile pour les doublons générés par les rotations de l'image
            if c_text and c_text == k_text:
                dist = math.hypot(c_center_x - k_center_x, c_center_y - k_center_y)
                max_allowed_dist = max(current["boxHeight"], kept["boxHeight"]) * 3
                if dist < max_allowed_dist:
                    is_duplicate = True
                    break

            # Condition 3: Pour les REJETS, éliminer TOUT mot dupliqué (même s'ils sont à des endroits différents)
            if current.get("mapElementType") == "rejet" and c_text and c_text == k_text:
                is_duplicate = True
                break

        if not is_duplicate:
            filtered_text.append(current)

    return filtered_text


def _run_ocr_pipeline(
    map_id: UUID,
    filename: str,
    file_content: bytes,
    celery_app,
) -> list[dict[str, Any]]:
    """
    Execute Florence-2 OCR pipeline on file_content.
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
    ocr_output_json_path = f"{OCR_OUTPUT_DIR}/{input_stem}-florence.json"

    # Send clean original image directly to Florence-2 (preserves natural antialiasing and contrast)

    with open(ocr_input_path, "wb") as input_file:
        input_file.write(file_content)

    if is_development:
        try:
            os.chmod(ocr_input_path, 0o666)
        except Exception as e:
            logger.debug(f"Failed to chmod {ocr_input_path}: {e}")

    task_chain = celery_app.signature(
        "florence.run_pipeline",
        args=[ocr_input_path, ocr_output_json_path],
    ).set(queue="florence")

    try:
        ocr_result = task_chain.apply_async()
        logger.info(f"==> [OCR] Task launched for {filename} (ID: {map_id})")
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
                            logger.info(f"    ... Still running OCR pipeline - elapsed: {elapsed}s")
                    else:
                        raise poll_err
            else:
                raise TimeoutError(f"OCR pipeline timed out after {OCR_PIPELINE_TIMEOUT_SECONDS}s")

            logger.info(f"==> [OCR] Pipeline successfully completed for {filename} in ~{elapsed}s!")

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
    legend_bounds: dict | None = None,
    title_bounds: dict | None = None,
    scale_bounds: dict | None = None,
    compass_bounds: dict | None = None,
):
    """Extract text using the Florence-2 Celery OCR pipeline."""
    if celery_app is None:
        raise ValueError("celery_app must be provided")

    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
    if len(file_content) > MAX_FILE_SIZE_BYTES:
        logger.warning(
            f"Image {filename} trop volumineuse ({len(file_content) / (1024*1024):.2f} MB). "
            f"Rejetée pour éviter un crash OOM (limite à 25 MB)."
        )
        return [], []

    # Mask the specified areas with white pixels if provided
    bounds_to_mask = {
        "legend": legend_bounds,
        "title": title_bounds,
        "scale": scale_bounds,
        "compass": compass_bounds,
    }

    has_any_mask = any(b for b in bounds_to_mask.values() if b)
    if has_any_mask:
        try:
            import cv2
            import numpy as np

            nparr = np.frombuffer(file_content, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is not None:
                masked_something = False
                for name, bounds in bounds_to_mask.items():
                    if bounds:
                        x, y = int(bounds.get("x", 0)), int(bounds.get("y", 0))
                        w, h = int(bounds.get("width", 0)), int(bounds.get("height", 0))
                        if w > 0 and h > 0:
                            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 255), -1)  # type: ignore
                            masked_something = True
                            logger.info(f"Masked {name} area ({x},{y},{w},{h}) for OCR.")

                if masked_something:
                    success, encoded_img = cv2.imencode(".png", img)  # type: ignore
                    if success:
                        file_content = encoded_img.tobytes()
            else:
                logger.error("Could not decode image to apply mask.")
        except Exception as e:
            logger.error(f"Failed to mask areas for OCR: {e}")

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
