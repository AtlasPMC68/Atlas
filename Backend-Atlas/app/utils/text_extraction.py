import asyncio
import copy
import json
import logging
import os
from pathlib import Path
from typing import Any
from uuid import UUID

import cv2
import easyocr
import numpy as np
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


def _build_pixel_text_feature_collection(text: str, x: float, y: float) -> dict[str, Any]:
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
        except Exception as exc:
            logger.debug("find_first_city error for text '%s': %s", text, exc)
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
                logger.error("Failed to persist city text '%s': %s", text, exc)
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
    os.makedirs(OCR_INPUT_DIR, exist_ok=True)
    os.makedirs(OCR_INTERMEDIATE_DIR, exist_ok=True)
    os.makedirs(OCR_OUTPUT_DIR, exist_ok=True)

    input_basename = f"{map_id}_{os.path.basename(filename)}"
    input_stem = os.path.splitext(input_basename)[0]
    ocr_input_path = os.path.join(OCR_INPUT_DIR, input_basename)
    ocr_intermediate_path = os.path.join(OCR_INTERMEDIATE_DIR, f"{input_stem}-florence.json")
    ocr_output_json_path = os.path.join(OCR_OUTPUT_DIR, f"{input_stem}-qwen.json")

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
        logger.info("Waiting for OCR chain to complete for map %s", map_id)
        ocr_result.get(
            timeout=OCR_PIPELINE_TIMEOUT_SECONDS,
            disable_sync_subtasks=False,
        )
        logger.info("OCR chain completed for map %s", map_id)

        with open(ocr_output_json_path, "r", encoding="utf-8") as qwen_result_file:
            qwen_result = json.load(qwen_result_file)

        detections = qwen_result.get("detections", [])
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

            extracted_text.append(
                {
                    "text": str(detection.get("text", "")),
                    "bbox": _bbox_xyxy_to_quad_points(normalized_bbox),
                }
            )

        return extracted_text
    finally:
        for temp_path in (ocr_input_path, ocr_intermediate_path, ocr_output_json_path):
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            except Exception as exc:
                logger.warning("Failed to clean OCR temp file %s: %s", temp_path, exc)


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


def _extract_text_via_easyocr(
    image: np.ndarray,
    languages: list[str],
    gpu_acc: bool = False,
) -> tuple[list, np.ndarray]:
    logger.debug("Initiating legacy EasyOCR text extraction")
    extractor = TextExtraction(img=image, lang=languages, gpu_acc=gpu_acc)
    extractor.check_language_code_validity()

    text_info = extractor.read_text_from_image()
    clean_image = copy.deepcopy(image)

    logger.debug("Completed legacy EasyOCR text extraction")
    return text_info, clean_image


def extract_text(
    image: np.ndarray | None = None,
    languages: list[str] | None = None,
    gpu_acc: bool = False,
    image_path: str | os.PathLike[str] | None = None,
    map_id: UUID | None = None,
    filename: str | None = None,
    file_content: bytes | None = None,
    celery_app=None,
):
    """
    Unified text extraction entrypoint.

    Supported modes:
    1) Legacy EasyOCR mode (used by tests):
       - Provide image_path + languages, or image + languages.
       - Returns (found_texts, clean_image).

    2) Celery OCR pipeline mode (used by map task flow):
       - Provide map_id + filename + file_content + celery_app.
       - Returns (extracted_text, text_regions).
    """
    if map_id is not None and filename is not None and file_content is not None and celery_app is not None:
        logger.info("Starting OCR pipeline for map %s: %s", map_id, filename)
        extracted_text, text_regions = _extract_text_via_pipeline(
            map_id=map_id,
            filename=filename,
            file_content=file_content,
            celery_app=celery_app,
        )
        logger.info(
            "OCR pipeline completed: %s detections extracted from %s",
            len(extracted_text),
            filename,
        )
        return extracted_text, text_regions

    if languages is None:
        raise ValueError("languages must be provided for legacy EasyOCR mode")

    if image is None:
        if image_path is None:
            raise ValueError("Provide either image or image_path for legacy EasyOCR mode")
        image = cv2.imread(str(Path(image_path)))
        if image is None:
            raise ValueError(f"Could not read image at path: {image_path}")

    return _extract_text_via_easyocr(image=image, languages=languages, gpu_acc=gpu_acc)


class TextExtraction:
    LANGUAGE_CODES_HASHMAP = {
        "Abaza": "abq", "Adyghe": "ady", "Afrikaans": "af", "Angika": "ang", "Arabic": "ar", "Assamese": "as",
        "Avar": "ava", "Azerbaijani": "az", "Belarusian": "be", "Bulgarian": "bg", "Bihari": "bh",
        "Bhojpuri": "bho",
        "Bengali": "bn", "Bosnian": "bs", "Simplified Chinese": "ch_sim", "Traditional Chinese": "ch_tra",
        "Chechen": "che",
        "Czech": "cs", "Welsh": "cy", "Danish": "da", "Dargwa": "dar", "German": "de", "English": "en",
        "Spanish": "es",
        "Estonian": "et", "Persian (Farsi)": "fa", "French": "fr", "Irish": "ga", "Goan Konkani": "gom",
        "Hindi": "hi",
        "Croatian": "hr", "Hungarian": "hu", "Indonesian": "id", "Ingush": "inh", "Icelandic": "is",
        "Italian": "it",
        "Japanese": "ja", "Kabardian": "kbd", "Kannada": "kn", "Korean": "ko", "Kurdish": "ku", "Latin": "la",
        "Lak": "lbe", "Lezghian": "lez", "Lithuanian": "lt", "Latvian": "lv", "Magahi": "mah", "Maithili": "mai",
        "Maori": "mi", "Mongolian": "mn", "Marathi": "mr", "Malay": "ms", "Maltese": "mt", "Nepali": "ne",
        "Newari": "new",
        "Dutch": "nl", "Norwegian": "no", "Occitan": "oc", "Pali": "pi", "Polish": "pl", "Portuguese": "pt",
        "Romanian": "ro", "Russian": "ru", "Serbian (cyrillic)": "rs_cyrillic", "Serbian (latin)": "rs_latin",
        "Nagpuri": "sck", "Slovak": "sk", "Slovenian": "sl", "Albanian": "sq", "Swedish": "sv", "Swahili": "sw",
        "Tamil": "ta", "Tabassaran": "tab", "Telugu": "te", "Thai": "th", "Tajik": "tjk", "Tagalog": "tl",
        "Turkish": "tr",
        "Uyghur": "ug", "Ukranian": "uk", "Urdu": "ur", "Uzbek": "uz", "Vietnamese": "vi"
    }
    LANGUAGE_CODES = [
        "abq", "ady", "af", "ang", "ar", "as", "ava", "az", "be", "bg", "bh", "bho",
        "bn", "bs", "ch_sim", "ch_tra", "che", "cs", "cy", "da", "dar", "de", "en", "es",
        "et", "fa", "fr", "ga", "gom", "hi", "hr", "hu", "id", "inh", "is", "it", "ja",
        "kbd", "kn", "ko", "ku", "la", "lbe", "lez", "lt", "lv", "mah", "mai", "mi", "mn",
        "mr", "ms", "mt", "ne", "new", "nl", "no", "oc", "pi", "pl", "pt", "ro", "ru",
        "rs_cyrillic", "rs_latin", "sck", "sk", "sl", "sq", "sv", "sw", "ta", "tab",
        "te", "th", "tjk", "tl", "tr", "ug", "uk", "ur", "uz", "vi"
    ]
    image: np.ndarray

    def __init__(self, img: np.ndarray, lang: list[str] | None = None, gpu_acc: bool = False):
        self.image: np.ndarray = img
        self.lang: list[str] = list(lang if lang is not None else ["en", "fr"])
        self.gpu_acc: bool = gpu_acc

    def read_text_from_image(self, scale_xy: tuple[float, float] = (2.0, 2.0)):
        reader = easyocr.Reader(
            lang_list=list(self.lang),
            gpu=self.gpu_acc,
        )

        shading = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)

        # Resizing implies rescaling resulting coordinates to preserve original pixel references.
        upscaling = cv2.resize(
            shading,
            None,
            fx=scale_xy[0],
            fy=scale_xy[1],
            interpolation=cv2.INTER_LANCZOS4,
        )

        extracted_text = reader.readtext(
            upscaling,
            text_threshold=0.7,
            low_text=0.4,
            link_threshold=0.4,
            width_ths=0.7,
            height_ths=0.7,
        )

        scaled_extracted_text = []
        for coords, text, prob in extracted_text:
            rescaled_coords = []
            for x, y in coords:
                rescaled_x = int(x / scale_xy[0])
                rescaled_y = int(y / scale_xy[1])
                rescaled_coords.append([rescaled_x, rescaled_y])

            scaled_extracted_text.append((rescaled_coords, text, prob))

        logger.debug("Extracted text: %s", extracted_text)
        return scaled_extracted_text

    def remove_text_from_image(self, text_info: list):
        _ = text_info
        image_no_text: np.ndarray = copy.deepcopy(self.image)
        return image_no_text

    def draw_bounding_box(self, scaled_extracted_text) -> np.ndarray:
        image_with_boxes: np.ndarray = copy.deepcopy(self.image)

        for bbox, text, conf in scaled_extracted_text:
            boxes = np.array(bbox, dtype=np.int32)
            cv2.polylines(image_with_boxes, [boxes], isClosed=True, color=(0, 0, 255), thickness=2)

            text_x = bbox[0][0]
            text_y = bbox[0][1] - 10 if bbox[0][1] - 10 > 10 else bbox[0][1] + 20
            label = f"{text} ({conf:.2f})"
            cv2.putText(
                image_with_boxes,
                label,
                (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),
                1,
            )

        return image_with_boxes

    def check_language_code_validity(self) -> None:
        """Raises ValueError if at least one language code is not supported."""
        for code in self.lang:
            if code not in self.LANGUAGE_CODES:
                raise ValueError(f"Invalid language code: {code}")
