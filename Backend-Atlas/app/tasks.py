# region Imports
import asyncio
import copy
import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID, uuid4

import cv2
import numpy as np
from sqlalchemy import select, update

from app.database.session import WorkerSessionLocal
from app.models.features import Feature, ValidationStatus
from app.models.map import Map
from app.models.map_import import (
    EXTRACTION_CANCELLED,
    EXTRACTION_FAILED,
    EXTRACTION_QUEUED,
    EXTRACTION_RUNNING,
    EXTRACTION_WAITING_FOR_TEXT,
    OCR_DONE,
    OCR_FAILED,
    OCR_RUNNING,
    MapImport,
)
from app.services.imports import ImportInputs, get_import, parse_import_inputs
from app.utils.cities_validation import (
    DEFAULT_STYLE,
    MATCHING_CONFIG,
    STYLES_MAP,
    haversine_distance_km,
    match_ocr_label,
    find_nearby_candidate_place,
    is_exploitable_text,
    is_geographic_prefix_only,
    GEOGRAPHIC_PREFIX_TYPES,
    _normalize,
)
from app.utils.extraction_steps import extract_zone_colors, place_map
from app.utils.file_utils import validate_file_extension
from app.utils.georeferencing import RunRecord, build_georef_inputs
from app.utils.georeferencing.config import (
    ambient_georef_config,
    parse_config_overrides,
)
from app.utils.georeferencing.debug import debug_enabled, make_run_dir
from app.utils.imposed_colors import (
    imposed_colors_to_config_entries,
    parse_imposed_colors_entries,
)
from app.utils.legend import legend_to_entry, polygon_center_in_legend
from app.utils.shapes_extraction import extract_shapes_from_clicks
from app.utils.text_extraction import extract_text, ocr_blocks_to_payload
from app.utils.text_extraction import should_ignore
from app.utils.dev_test_assets import TEST_CASES_DIR, GEOREF_ASSETS_DIR
from app.utils.dev_test_pixel_zones import write_classified_image, write_pixel_zones
from app.utils.dev_test import (
    drop_control_points,
    evaluate_and_persist_case,
    find_test_image_path,
    inspect_case,
    load_case_config,
    parse_extraction_inputs,
    write_raw_zones,
)
from app.utils.dev_test_evaluator import build_test_case_paths
from app.utils.dev_test_cases import KIND_PROBE, resolve_case_kind
from app.utils.dev_test_derived import ensure_text_regions, text_regions_for_run

from .celery_app import celery_app
# endregion

logger = logging.getLogger(__name__)

nb_task = 6
DEV_TEST_STEPS = 5


GEOREF_CONFIG = ambient_georef_config()


def _dev_test_debug_dir(test_id: str, test_case: str) -> str | None:
    """ Where the alignement diagnostics go """
    if not debug_enabled():
        return None

    path = os.path.join(TEST_CASES_DIR, test_id, test_case, "alignment_debug")
    try:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)
        return path
    except OSError as e:
        logger.warning(f"[DEV-TEST] Could not prepare debug dir {path}: {e}")
        return None


def _write_dev_test_case_state(test_id: str, test_case: str, config=None) -> None:
    """Record which requirements this case satisfied. Never raises."""
    try:
        state, _inputs = inspect_case(
            assets_root=GEOREF_ASSETS_DIR,
            test_id=test_id,
            test_case_id=test_case,
            config=config or GEOREF_CONFIG,
        )
        state.write()
        if state.requirements.blocked:
            logger.warning(
                f"[DEV-TEST] {test_id}/{test_case} is missing user inputs the"
                f" current algorithm needs: " + ", ".join(s.key for s in state.requirements.blocked)
            )
    except Exception as e:
        logger.warning(f"[DEV-TEST] Could not record case state for {test_id}: {e}")


def _write_feature_collection(path: str, collections: list) -> None:
    """Every feature of *collections* as one FeatureCollection file."""
    flat = [f for fc in collections for f in fc.get("features", [])]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"type": "FeatureCollection", "features": flat},
            f,
            indent=2,
            ensure_ascii=False,
        )


def _dump_zones_debug(debug_dir: str | None, collections: list) -> None:
    """Write the georeferenced output beside the overlays. Never raises."""
    if not debug_dir:
        return
    try:
        _write_feature_collection(os.path.join(debug_dir, "zones.geojson"), collections)
    except Exception as e:
        logger.warning(f"Could not write debug zones: {e}")


def _alignment_summary(result) -> dict[str, Any]:
    """What the UI needs to tell the user what happened. """
    if result is None:
        return {"enabled": False, "method": "gcp_only"}
    return {
        "enabled": True,
        "method": result.method,
        "skipped": result.skipped,
        "used_curve_evidence": result.used_curve_evidence,
        "failed_checks": result.failed_checks,
        "gates": [
            {
                "name": g.name,
                "value": g.value,
                "threshold": g.threshold,
                "applicable": g.applicable,
                "passed": g.passed,
            }
            for g in result.gates
        ],
    }


@celery_app.task(bind=True)
def test_task(self, name: str = "World"):
    """simple test task"""
    logger.info(f"Starting test task for {name}")

    for i in range(5):
        time.sleep(1)
        self.update_state(
            state="PROGRESS",
            meta={
                "current": i + 1,
                "total": nb_task,
                "status": f"Processing step {i + 1}",
            },
        )

    result = f"Hello {name}! Task completed successfully."
    logger.info(f"Test task completed: {result}")
    return result


class ImportCancelled(Exception):
    """The user cancelled the extraction. Nothing has been saved."""


@dataclass(frozen=True)
class _ClaimedImport:
    project_id: UUID
    filename: str
    image: bytes
    inputs: ImportInputs
    ocr_blocks: list


def _decode_image(content: bytes):
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode the map image")
    return image

async def _claim_ocr(map_id: str, task_id: str) -> Optional[bytes]:
    async with WorkerSessionLocal() as session:
        async with session.begin():
            row = await get_import(session, UUID(map_id), for_update=True)
            if row is None or row.ocr_task_id != task_id:
                return None
            row.ocr_state = OCR_RUNNING
            return row.image


async def _finish_ocr(map_id: str, task_id: str, payload: list) -> Optional[str]:
    """Store the OCR result. Returns an extraction task id to dispatch when an
    extraction was waiting on the text: whichever of OCR and the user finishes
    last starts the extraction."""
    async with WorkerSessionLocal() as session:
        async with session.begin():
            row = await get_import(session, UUID(map_id), for_update=True)
            if row is None or row.ocr_task_id != task_id:
                return None
            row.ocr_result = payload
            row.ocr_state = OCR_DONE
            if row.extraction_state == EXTRACTION_WAITING_FOR_TEXT:
                row.extraction_task_id = str(uuid4())
                row.extraction_state = EXTRACTION_QUEUED
                return row.extraction_task_id
            return None


async def _fail_ocr(map_id: str, task_id: str, error: str) -> None:
    async with WorkerSessionLocal() as session:
        async with session.begin():
            row = await get_import(session, UUID(map_id), for_update=True)
            if row is None or row.ocr_task_id != task_id:
                return
            row.ocr_state = OCR_FAILED
            if row.extraction_state == EXTRACTION_WAITING_FOR_TEXT:
                row.extraction_state = EXTRACTION_FAILED
                row.extraction_error = f"Text analysis failed: {error}"


async def _claim_extraction(map_id: str, task_id: str) -> Optional[_ClaimedImport]:
    async with WorkerSessionLocal() as session:
        async with session.begin():
            row = await get_import(session, UUID(map_id), for_update=True)
            if row is None or row.extraction_task_id != task_id or row.extraction_state != EXTRACTION_QUEUED:
                return None
            project_id = (await session.execute(select(Map.project_id).where(Map.id == row.map_id))).scalar_one()
            row.extraction_state = EXTRACTION_RUNNING
            row.extraction_error = None
            return _ClaimedImport(
                project_id=project_id,
                filename=row.filename,
                image=row.image,
                inputs=parse_import_inputs(row.inputs),
                ocr_blocks=list(row.ocr_result or []),
            )


async def _extraction_state(map_id: str) -> Optional[str]:
    async with WorkerSessionLocal() as session:
        result = await session.execute(select(MapImport.extraction_state).where(MapImport.map_id == UUID(map_id)))
        return result.scalar_one_or_none()


async def _end_extraction(map_id: str, task_id: str, state: str, error: Optional[str] = None) -> None:
    async with WorkerSessionLocal() as session:
        async with session.begin():
            row = await get_import(session, UUID(map_id), for_update=True)
            if row is None or row.extraction_task_id != task_id:
                return
            row.extraction_state = state
            row.extraction_error = error


async def _save_extraction(
    map_id: str,
    project_id: UUID,
    collections: List[dict[str, Any]],
    georef_inputs: Optional[dict],
) -> int:
    """Save every feature, record the inputs on the map and close the import,
    in one transaction: a cancel or a crash leaves no partial map behind. """
    map_uuid = UUID(map_id)
    async with WorkerSessionLocal() as session:
        async with session.begin():
            row = await get_import(session, map_uuid, for_update=True)
            if row is None or row.extraction_state != EXTRACTION_RUNNING:
                raise ImportCancelled()

            count = 0
            for collection in collections:
                for feature in collection.get("features", []):
                    session.add(
                        Feature(
                            project_id=project_id,
                            map_id=map_uuid,
                            data={"type": "FeatureCollection", "features": [feature]},
                        )
                    )
                    count += 1

            if georef_inputs is not None:
                await session.execute(update(Map).where(Map.id == map_uuid).values(georef_inputs=georef_inputs))
            await session.delete(row)
            return count


def _raise_if_cancelled(map_id: str) -> None:
    if asyncio.run(_extraction_state(map_id)) != EXTRACTION_RUNNING:
        raise ImportCancelled()


# --- extraction steps ---------------------------------------------------------


def _make_text_feature(
    name: str,
    original_text: str,
    coords: list[float],
    quad: list,
    confidence: float,
    recognized: bool,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    validation_status = (
        ValidationStatus.ACCEPTED.value
        if recognized
        else ValidationStatus.MANUAL_REVIEW.value
    )
    props = {
        "name": name,
        "originalText": original_text,
        "show": recognized,
        "mapElementType": "point",
        "color_name": "black",
        "color_rgb": [0, 0, 0],
        "isOcrText": True,
        "recognized": recognized,
        "confidence": confidence,
        "quad": quad,
        "validationStatus": validation_status,
        "validation_status": validation_status,
    }
    if extra:
        props.update(extra)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Point", "coordinates": coords},
            }
        ],
    }


def _categorized_text_features_from_ocr(
    blocks: list,
    legend_bounds: Optional[dict],
    frame_bounds: Optional[dict],
    image_size: Optional[tuple[int, int]] = None,
) -> List[dict[str, Any]]:
    """Extract recognized places (cities or geographic entities) and unrecognized OCR text.

    Three possible cases:
    Case 1: reject immediately if the text is empty, in the legend, or a junk token
        (keywords such as scale/legend, fewer than 2 characters, etc.).
    Case 2: OCR text is usable but not recognized by geonamescache or the geographic JSON
        -> kept for manual validation (show=False, recognized=False).
    Case 3: text is recognized as a city or geographic entity from the JSON
        -> displayed on the final map (show=True, recognized=True).
    """
    collections: List[dict[str, Any]] = []
    seen_recognized = set()
    seen_unrecognized: dict[str, list[tuple[float, float]]] = {}
    source_blocks = [
        {
            "coords": coords,
            "text": str(text or "").strip(),
            "prob": prob,
            "skip": False,
            "prefix_suggestion": None,
        }
        for coords, text, prob in blocks
    ]

    def center_of(coords: Any) -> Optional[tuple[float, float]]:
        if not coords:
            return None
        try:
            return (
                sum(float(point[0]) for point in coords) / len(coords),
                sum(float(point[1]) for point in coords) / len(coords),
            )
        except (TypeError, ValueError, IndexError):
            return None

    def nearby_word_boxes(left: Any, right: Any) -> bool:
        if not left or not right:
            return False
        try:
            left_xs = [float(point[0]) for point in left]
            left_ys = [float(point[1]) for point in left]
            right_xs = [float(point[0]) for point in right]
            right_ys = [float(point[1]) for point in right]
        except (TypeError, ValueError, IndexError):
            return False

        left_height = max(left_ys) - min(left_ys)
        right_height = max(right_ys) - min(right_ys)
        word_height = max(1.0, left_height, right_height)
        horizontal_gap = max(
            0.0,
            max(
                min(right_xs) - max(left_xs),
                min(left_xs) - max(right_xs),
            ),
        )
        vertical_gap = max(
            0.0,
            max(min(right_ys) - max(left_ys), min(left_ys) - max(right_ys)),
        )
        return horizontal_gap <= word_height * 2.5 and vertical_gap <= word_height * 0.5

    def estimated_position(coords: Any) -> Optional[tuple[float, float]]:
        center = center_of(coords)
        if center is None or not frame_bounds or not image_size:
            return None
        h, w = image_size
        if w <= 0 or h <= 0:
            return None
        cx, cy = center
        south = frame_bounds.get("south", frame_bounds.get("min_lat"))
        north = frame_bounds.get("north", frame_bounds.get("max_lat"))
        west = frame_bounds.get("west", frame_bounds.get("min_lon"))
        east = frame_bounds.get("east", frame_bounds.get("max_lon"))
        if None in (south, north, west, east):
            return None
        return (
            float(north) - (cy / h) * (float(north) - float(south)),
            float(west) + (cx / w) * (float(east) - float(west)),
        )

    for prefix_index, prefix_block in enumerate(source_blocks):
        prefix_text = prefix_block["text"]
        if (
            not is_geographic_prefix_only(prefix_text)
            or should_ignore(prefix_text)
            or not is_exploitable_text(prefix_text)
            or polygon_center_in_legend(prefix_block["coords"], legend_bounds)
        ):
            continue
        prefix_key = _normalize(prefix_text)
        expected_types = next(
            (
                types
                for key, types in GEOGRAPHIC_PREFIX_TYPES.items()
                if key in prefix_key
            ),
            None,
        )
        if expected_types is None:
            continue

        for suffix_index, suffix_block in enumerate(source_blocks):
            if suffix_index == prefix_index or suffix_block["skip"]:
                continue
            suffix_text = suffix_block["text"]
            if (
                not suffix_text
                or is_geographic_prefix_only(suffix_text)
                or should_ignore(suffix_text)
                or not is_exploitable_text(suffix_text)
                or polygon_center_in_legend(suffix_block["coords"], legend_bounds)
                or not nearby_word_boxes(prefix_block["coords"], suffix_block["coords"])
            ):
                continue

            phrase = f"{prefix_text} {suffix_text}"
            phrase_position = estimated_position(suffix_block["coords"])
            try:
                place = (
                    match_ocr_label(phrase, frame_bounds, target_pos=phrase_position)
                    if phrase_position is not None
                    else match_ocr_label(phrase, frame_bounds)
                )
            except TypeError:
                place = match_ocr_label(phrase, frame_bounds)
            if not place or not place.get("found", True):
                continue
            if place.get("type") not in expected_types:
                continue

            prefix_block["skip"] = True
            suffix_block["prefix_suggestion"] = {
                "name": place.get("name", phrase),
                "coordinates": [place["lon"], place["lat"]],
                "type": place.get("type"),
            }
            break

    for block in source_blocks:
        if block["skip"]:
            continue
        coords = block["coords"]
        text = block["text"]
        prob = block["prob"]
        # Case 1: reject immediately if the text is inside the legend.
        if polygon_center_in_legend(coords, legend_bounds):
            continue

        raw_text = str(text or "").strip()
        # Ignore numeric-only text and map-scale labels; they are not place names.
        if should_ignore(raw_text) or not is_exploitable_text(raw_text):
            continue

        confidence = float(prob) if prob is not None else 1.0

        target_pos = estimated_position(coords)

        try:
            if target_pos is not None:
                entity = match_ocr_label(raw_text, frame_bounds, target_pos=target_pos)
            else:
                entity = match_ocr_label(raw_text, frame_bounds)
        except TypeError:
            entity = match_ocr_label(raw_text, frame_bounds)

        if block["prefix_suggestion"]:
            entity = None

        if entity and entity.get("out_of_bounds"):
            continue

        has_place_coordinates = (
            entity is not None
            and entity.get("lat") is not None
            and entity.get("lon") is not None
        )
        distance_requires_review = bool(
            has_place_coordinates
            and target_pos is not None
            and entity.get("matchMethod") == "fuzzy"
            and haversine_distance_km(
                target_pos[0],
                target_pos[1],
                float(entity["lat"]),
                float(entity["lon"]),
            )
            > MATCHING_CONFIG["max_fuzzy_distance_km"]
        )
        missing_position_requires_review = bool(
            entity is not None
            and entity.get("matchMethod") == "fuzzy"
            and target_pos is None
        )

        if (
            entity
            and entity.get("found", True)
            and has_place_coordinates
            and not distance_requires_review
            and not missing_position_requires_review
        ):
            # Case 3: recognized as a city or geographic entity from the JSON.
            raw_type = entity.get("type")
            entity_id = f"{raw_type or 'city'}:{entity.get('geonameid') or entity.get('name')}"
            if entity_id in seen_recognized:
                continue
            seen_recognized.add(entity_id)

            map_element_type, size_px, font_style, transform_func = STYLES_MAP.get(
                raw_type or "", DEFAULT_STYLE
            )
            display_name = transform_func(entity.get("name", raw_text))

            extra = {
                "labelText": display_name,
                "lat": entity["lat"],
                "lon": entity["lon"],
                "type": raw_type or "city",
                "rawType": raw_type or "city",
                "mapElementType": map_element_type,
                "sizePx": size_px,
                "fontStyle": font_style,
                "matchedCity": entity.get("name"),
                "population": entity.get("population"),
                "fromGeographicEntitiesJson": bool(raw_type and raw_type != "city"),
                "isGeographicEntity": bool(raw_type and raw_type != "city"),
            }
            ocr_coords = (
                [target_pos[1], target_pos[0]]
                if extra["fromGeographicEntitiesJson"] and target_pos is not None
                else [entity["lon"], entity["lat"]]
            )

        collections.append(
                _make_text_feature(
                    name=display_name,
                    original_text=raw_text,
                    coords=ocr_coords,
                    quad=coords,
                    confidence=confidence,
                    recognized=True,
                    extra=extra,
                )
            )
        else:
            # Case 2: keep OCR text even if it is not recognized -> manual validation.
            clean = raw_text.casefold()
            center = center_of(coords)
            prior_centers = seen_unrecognized.setdefault(clean, [])
            if center is None:
                if prior_centers:
                    continue
                prior_centers.append((0.0, 0.0))
            elif any(
                (center[0] - previous[0]) ** 2 + (center[1] - previous[1]) ** 2
                <= 20.0**2
                for previous in prior_centers
            ):
                continue
            else:
                prior_centers.append(center)
            suggested_place = block["prefix_suggestion"]
            if has_place_coordinates and entity and entity.get("name"):
                suggested_place = {
                    "name": entity["name"],
                    "coordinates": [entity["lon"], entity["lat"]],
                    "type": entity.get("type") or "city",
                }
            collections.append(
                _make_text_feature(
                    name=raw_text,
                    original_text=raw_text,
                    coords=[0.0, 0.0],
                    quad=coords,
                    confidence=confidence,
                    recognized=False,
                    extra={
                        "suggestedPlace": suggested_place,
                        },
                )
            )

    return collections


def _georeference_text_features(
    collections: List[dict[str, Any]],
    placement: Any,
) -> None:
    """Georeference OCR positions for review text and JSON-matched entities."""
    if placement is None:
        return

    target_features = [
        feat
        for coll in collections
        for feat in coll.get("features", [])
        if (
            (props := feat.get("properties", {})).get("isOcrText")
            and props.get("quad")
            and (
                not props.get("recognized")
                or props.get("fromGeographicEntitiesJson")
            )
        )
    ]
    if not target_features:
        return

    pixel_features = []
    for feat in target_features:
        q = feat["properties"]["quad"]
        cx = sum(float(p[0]) for p in q) / len(q)
        cy = sum(float(p[1]) for p in q) / len(q)
        pixel_features.append({"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [cx, cy]}})

    try:
        georef_res = placement.georeference(
            [{"type": "FeatureCollection", "features": pixel_features}],
            clean=False,
        )
        if georef_res.collections and georef_res.collections[0].get("features"):
            for feat, res_feat in zip(target_features, georef_res.collections[0]["features"]):
                coords = res_feat.get("geometry", {}).get("coordinates")
                if coords:
                    feat["geometry"]["coordinates"] = coords
                    if feat.get("properties", {}).get("recognized"):
                        continue
                    orig_text = (
                        feat.get("properties", {}).get("originalText") or feat.get("properties", {}).get("name") or ""
                    )
                    if not feat["properties"].get("suggestedPlace"):
                        nearby_place = find_nearby_candidate_place(
                            orig_text,
                            coords,
                            radius_km=MATCHING_CONFIG["suggestion_radius_km"],
                        )
                        if nearby_place:
                            feat["properties"]["suggestedPlace"] = {
                                "name": nearby_place.get("name_fr")
                                or nearby_place.get("name"),
                            "coordinates": [
                                    nearby_place.get("lon"),
                                    nearby_place.get("lat"),
                            ],
                                "type": nearby_place.get("type") or "city",
                    }
    except Exception as e:
        logger.debug(f"Failed to batch georeference OCR text features: {e}")


def _write_ocr_text_file(filename: str, blocks: list) -> str:
    """The OCR text as a .txt under app/extracted_texts, for inspection."""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extracted_texts")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"{timestamp}_{os.path.splitext(filename)[0]}.txt")
    try:
        os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("=== OCR EXTRACTION  ===\n")
            f.write(f"Source File: {filename}\n")
            f.write(f"Date extraction: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\n=== TEXTE EXTRAIT ===\n\n")
            f.write("\n".join(block[1] for block in blocks))
        return output_path
    except Exception as e:
        logger.error(f"Failed to save text file: {e}")
        return f"ERROR: Could not save to {output_path}"


# --- tasks --------------------------------------------------------------------


@celery_app.task(bind=True)
def run_map_ocr(self, map_id: str):
    """OCR for an import, started as soon as the map is uploaded."""
    task_id = self.request.id
    content = asyncio.run(_claim_ocr(map_id, task_id))
    if content is None:
        logger.info(f"[IMPORT] OCR for map {map_id} superseded or abandoned; skipping")
        return {"status": "skipped"}

    try:
        blocks = extract_text(map_id=UUID(map_id) if isinstance(map_id, str) else map_id, image_bytes=content)
        payload = ocr_blocks_to_payload(blocks)
    except Exception as e:
        logger.error(f"[IMPORT] OCR failed for map {map_id}: {e}", exc_info=True)
        asyncio.run(_fail_ocr(map_id, task_id, str(e)))
        raise

    extraction_task_id = asyncio.run(_finish_ocr(map_id, task_id, payload))
    if extraction_task_id:
        try:
            process_map_extraction.apply_async(kwargs={"map_id": map_id}, task_id=extraction_task_id)
        except Exception as e:
            logger.error(f"[IMPORT] Could not dispatch extraction for {map_id}: {e}")
            asyncio.run(
                _end_extraction(
                    map_id,
                    extraction_task_id,
                    EXTRACTION_FAILED,
                    "Could not start extraction",
                )
            )

    logger.info(f"[IMPORT] OCR done for map {map_id}: {len(payload)} text blocks")
    return {"status": "done", "blocks": len(payload)}


@celery_app.task(bind=True)
def process_map_extraction(self, map_id: str):
    """Extract, georeference and save a map's features from its import row."""
    task_id = self.request.id
    claimed = asyncio.run(_claim_extraction(map_id, task_id))
    if claimed is None:
        logger.info(f"[IMPORT] extraction {task_id} for map {map_id} not current; skipping")
        return {"status": "skipped"}

    inputs = claimed.inputs
    tmp_file_path: Optional[str] = None

    def progress(step: int, status: str) -> None:
        self.update_state(
            state="PROGRESS",
            meta={"current": step, "total": nb_task, "status": status},
        )

    try:
        # Step 1: load the image
        progress(1, "Loading and validating image")
        ext = os.path.splitext(claimed.filename)[1].lower()
        if not validate_file_extension(claimed.filename):
            raise ValueError(f"Extension {ext} is not allowed.")
        image = _decode_image(claimed.image)
        image.flags.writeable = False
        # Shapes and colours read from a path.
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            tmp_file.write(claimed.image)
            tmp_file_path = tmp_file.name

        # Every OCR box masks the alignment evidence, legend ones included; the
        # legend is masked there anyway.
        text_regions = [block[0] for block in claimed.ocr_blocks]
        collections: List[dict[str, Any]] = []

        # Step 2: text -> city points
        if inputs.enable_text_extraction:
            progress(2, "Detecting cities in the extracted text")
            img_size = (image.shape[0], image.shape[1]) if image is not None else None
            collections.extend(
                _categorized_text_features_from_ocr(
                    claimed.ocr_blocks,
                    inputs.legend_bounds,
                    inputs.frame_bounds,
                    image_size=img_size,
                )
            )
        _raise_if_cancelled(map_id)

        # Step 3: the transform, once, so shapes and colours share it
        progress(3, "Extracting reference geography and aligning the map")
        debug_dir = make_run_dir(f"map{map_id}") if debug_enabled() else None
        placement = place_map(
            image,
            inputs.control_points,
            frame_bounds=inputs.frame_bounds,
            legend_bounds=inputs.legend_bounds,
            water_picks=inputs.water_picks,
            text_regions=text_regions,
            config=GEOREF_CONFIG,
            debug_dir=debug_dir,
        )
        _raise_if_cancelled(map_id)

        # Georeference OCR positions for unrecognized text and JSON-matched entities.
        if inputs.enable_text_extraction:
            _georeference_text_features(collections, placement)

        # Step 4: shapes, one flood fill per click. Not snapped or clipped: a
        # shape is not a land zone and may sit at sea.
        shapes_result: dict[str, Any] = {}
        if inputs.shapes:
            progress(4, "Extracting shapes from click positions")
            shapes_result = extract_shapes_from_clicks(
                tmp_file_path,
                click_positions=inputs.shape_clicks,
                click_names=inputs.shape_names,
            )
            collections.extend(placement.georeference(shapes_result.get("pixel_features", []), clean=False).collections)
        _raise_if_cancelled(map_id)

        # Step 5: colours, from the pipette alone
        progress(5, "Extracting colors from image")
        color_result = extract_zone_colors(
            tmp_file_path,
            zone_picks=inputs.zone_picks,
            legend_bounds=inputs.legend_bounds,
            text_regions=text_regions,
            config=GEOREF_CONFIG,
        )
        color_result.pop("classified_rgb", None)
        color_collections = placement.georeference(color_result.get("pixel_features", [])).collections
        collections.extend(color_collections)
        _dump_zones_debug(debug_dir, color_collections)
        _raise_if_cancelled(map_id)

        # Step 6: save everything and close the import
        progress(6, "Saving extracted features")
        output_path = _write_ocr_text_file(claimed.filename, claimed.ocr_blocks) if inputs.enable_text_extraction else ""
        all_positions, all_names, all_radii, all_kinds = parse_imposed_colors_entries(inputs.all_colors or None)
        georef_inputs = build_georef_inputs(
            control_points=inputs.control_points or None,
            frame_bounds=inputs.frame_bounds,
            imposed_colors=imposed_colors_to_config_entries(all_positions, all_names, all_radii, all_kinds),
            legend=legend_to_entry(inputs.legend_bounds),
        )
        saved = asyncio.run(_save_extraction(map_id, claimed.project_id, collections, georef_inputs))

    except ImportCancelled:
        logger.info(f"[IMPORT] extraction cancelled for map {map_id}; nothing saved")
        asyncio.run(_end_extraction(map_id, task_id, EXTRACTION_CANCELLED))
        return {"status": "cancelled", "map_id": map_id}
    except Exception as e:
        logger.error(f"[IMPORT] extraction failed for map {map_id}: {e}", exc_info=True)
        asyncio.run(_end_extraction(map_id, task_id, EXTRACTION_FAILED, str(e)))
        raise
    finally:
        if tmp_file_path:
            try:
                os.unlink(tmp_file_path)
            except OSError:
                pass

    logger.info(f"[IMPORT] extraction done for map {map_id}: {saved} feature(s) saved")
    return {
        "status": "completed",
        "map_id": map_id,
        "filename": claimed.filename,
        "features_saved": saved,
        "output_path": output_path,
        "color_result": {"colors_detected": len(color_result.get("normalized_features", []))},
        "extractions_performed": {
            "georeferencing": True,
            "color_extraction": True,
            "shapes_extraction": bool(inputs.shapes),
            "text_extraction": inputs.enable_text_extraction,
        },
        "alignment": _alignment_summary(placement.alignment),
    }


def _iou_summary_from_report(report: dict[str, Any] | None) -> dict[str, Any]:
    """Pull the IoU numbers out of an evaluation report for the run record."""
    metrics = (report or {}).get("metrics") or {}
    per_zone = {}
    for expected in metrics.get("expected") or []:
        if not isinstance(expected, dict):
            continue
        best = expected.get("bestMatch") or {}
        per_zone[str(expected.get("name"))] = best.get("iou")

    return {
        "scoreUsed": metrics.get("scoreUsed"),
        "meanIou": (metrics.get("mean") or {}).get("meanIou"),
        "perZone": per_zone,
    }


@celery_app.task(bind=True)
def warm_dev_test_text_regions(self, test_id: str):
    """Fill a dev-test map's OCR cache while the user is still clicking."""
    if not GEOREF_CONFIG.enable_curve_alignment:
        return {"status": "skipped", "reason": "curve alignment is off"}

    image_path = find_test_image_path(test_id)
    image = cv2.imread(image_path) if image_path else None
    if image is None:
        return {"status": "skipped", "reason": "no readable image for this test"}

    regions, state = ensure_text_regions(test_id, image_path, image, refresh=False)
    logger.info(
        f"[DEV-TEST] warmed text regions for {test_id}: {len(regions or [])}" f" ({state.detail or 'already cached'})"
    )
    return {"status": "done", "regions": len(regions or [])}

@celery_app.task(bind=True)
def process_dev_test_extraction(
    self,
    test_id: str,
    test_case: str,
    config_overrides: dict | None = None,
    excluded_control_points: list | None = None,
):
    """Run a stored dev-test case from its ``config.json``, write the results to
    its folder and score it. No database. """

    def progress(step: int, status: str) -> None:
        self.update_state(
            state="PROGRESS",
            meta={"current": step, "total": DEV_TEST_STEPS, "status": status},
        )

    progress(1, "Loading the test case")
    resolved_kind = resolve_case_kind(test_id, test_case)
    switches = {
        key: value for key, value in parse_config_overrides(config_overrides).items() if getattr(GEOREF_CONFIG, key) != value
    }
    run_config = GEOREF_CONFIG.with_overrides(**switches)

    image_path = find_test_image_path(test_id)
    image = cv2.imread(image_path) if image_path else None
    if image is None:
        raise FileNotFoundError(f"No readable map image for test {test_id}")
    inputs = parse_extraction_inputs(load_case_config(GEOREF_ASSETS_DIR, test_id, test_case))
    kept_points, excluded = drop_control_points(inputs.control_points, excluded_control_points or [])
    ambient_run = not switches and not excluded

    record = RunRecord(run_id=f"{test_id}/{test_case}")
    record.set_inputs(
        waterPickCount=len(inputs.water_picks[0] or []),
        legendBounds=inputs.legend_bounds,
        caseKind=resolved_kind,
        runSwitches=switches or None,
        controlPointSources=list(run_config.gcp_sources),
        excludedControlPoints=excluded or None,
    )

    progress(2, "Extracting colors from image")
    text_regions = text_regions_for_run(test_id, image_path, image, run_config)
    color_result = extract_zone_colors(
        image_path,
        zone_picks=inputs.zone_picks,
        legend_bounds=inputs.legend_bounds,
        text_regions=text_regions,
        config=run_config,
    )
    classified_rgb = color_result.pop("classified_rgb", None)
    pixel_features = color_result.get("pixel_features", [])
    pixel_zones_snapshot = copy.deepcopy(pixel_features)
    record.set_errors(
        textFill=color_result.get("text_fill"),
        zoneGaps=color_result.get("zone_gaps"),
    )

    progress(3, "Aligning and georeferencing")
    debug_dir = _dev_test_debug_dir(test_id, test_case)
    placement = place_map(
        image,
        kept_points,
        frame_bounds=inputs.frame_bounds,
        legend_bounds=inputs.legend_bounds,
        water_picks=inputs.water_picks,
        text_regions=text_regions,
        config=run_config,
        record=record,
        debug_dir=debug_dir,
    )
    georef = placement.georeference(pixel_features, check_points=inputs.check_points)
    _dump_zones_debug(debug_dir, georef.collections)

    progress(4, "Saving test assets")
    case_dir = os.path.join(TEST_CASES_DIR, test_id, test_case)
    os.makedirs(case_dir, exist_ok=True)
    _write_feature_collection(os.path.join(case_dir, "zones.geojson"), georef.collections)
    write_raw_zones(case_dir, georef.raw_collections)
    write_pixel_zones(case_dir, pixel_zones_snapshot)
    write_classified_image(case_dir, classified_rgb)

    progress(5, "Scoring")
    paths = build_test_case_paths(GEOREF_ASSETS_DIR, test_id, test_case)
    if resolved_kind == KIND_PROBE:
        record.note("probe case: no expected zones, run not scored")
    elif not os.path.exists(paths.expected_zones_path):
        logger.warning(f"[DEV-TEST] {test_id}/{test_case} has no expected zones yet")
        record.note("regression case without expected zones: run not scored")
    else:
        report = evaluate_and_persist_case(
            assets_root=GEOREF_ASSETS_DIR,
            test_id=test_id,
            test_case_id=test_case,
            min_iou=None,
            allow_best_promotion=ambient_run,
        )
        record.set_errors(iou=_iou_summary_from_report(report))

    _write_dev_test_case_state(test_id, test_case, config=run_config)
    record.write(case_dir)
    logger.info(f"[DEV-TEST] {test_id}/{test_case} done")
    return {"status": "completed", "test_id": test_id, "test_case": test_case}
