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
from app.models.features import Feature
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
from app.utils.city_gazetteer import find_cities_in_text, frame_city_index
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
from app.utils.shapes_extraction import extract_shapes
from app.utils.text_extraction import extract_text, ocr_blocks_to_payload
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
                f" current algorithm needs: "
                + ", ".join(s.key for s in state.requirements.blocked)
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
        "rung": result.rung,
        "used_curve_evidence": result.used_curve_evidence,
        "failed_checks": result.failed_checks,
        "probe_agreement_px": result.probe_agreement_px,
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

OCR_LANGUAGES = ["en", "fr"]


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
                row.extraction_error = f"L'analyse du texte a échoué : {error}"


async def _claim_extraction(map_id: str, task_id: str) -> Optional[_ClaimedImport]:
    async with WorkerSessionLocal() as session:
        async with session.begin():
            row = await get_import(session, UUID(map_id), for_update=True)
            if (
                row is None
                or row.extraction_task_id != task_id
                or row.extraction_state != EXTRACTION_QUEUED
            ):
                return None
            project_id = (
                await session.execute(select(Map.project_id).where(Map.id == row.map_id))
            ).scalar_one()
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
        result = await session.execute(
            select(MapImport.extraction_state).where(MapImport.map_id == UUID(map_id))
        )
        return result.scalar_one_or_none()


async def _end_extraction(
    map_id: str, task_id: str, state: str, error: Optional[str] = None
) -> None:
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
                await session.execute(
                    update(Map).where(Map.id == map_uuid).values(georef_inputs=georef_inputs)
                )
            await session.delete(row)
            return count


def _raise_if_cancelled(map_id: str) -> None:
    if asyncio.run(_extraction_state(map_id)) != EXTRACTION_RUNNING:
        raise ImportCancelled()


# --- extraction steps ---------------------------------------------------------


def _city_features_from_text(
    blocks: list, legend_bounds: Optional[dict], frame_bounds: Optional[dict]
) -> List[dict[str, Any]]:
    """One point feature per place name read off the map."""
    index = frame_city_index(frame_bounds)

    collections: List[dict[str, Any]] = []
    for coords, text, _prob in blocks:
        if polygon_center_in_legend(coords, legend_bounds):
            continue
        for phrase, city in find_cities_in_text(text, index):
            collections.append(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "name": city.name if city else phrase,
                                "show": city is not None,
                                "mapElementType": "point",
                                "color_name": "black",
                                "color_rgb": [0, 0, 0],
                            },
                            "geometry": {
                                "type": "Point",
                                "coordinates": [
                                    city.lon if city else 0.0,
                                    city.lat if city else 0.0,
                                ],
                            },
                        }
                    ],
                }
            )
    return collections


def _write_ocr_text_file(filename: str, blocks: list) -> str:
    """The OCR text as a .txt under app/extracted_texts, for inspection."""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extracted_texts")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(
        output_dir, f"{timestamp}_{os.path.splitext(filename)[0]}.txt"
    )
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
        image = _decode_image(content)
        blocks, _clean = extract_text(image=image, languages=OCR_LANGUAGES, gpu_acc=False)
        payload = ocr_blocks_to_payload(blocks)
    except Exception as e:
        logger.error(f"[IMPORT] OCR failed for map {map_id}: {e}", exc_info=True)
        asyncio.run(_fail_ocr(map_id, task_id, str(e)))
        raise

    extraction_task_id = asyncio.run(_finish_ocr(map_id, task_id, payload))
    if extraction_task_id:
        try:
            process_map_extraction.apply_async(
                kwargs={"map_id": map_id}, task_id=extraction_task_id
            )
        except Exception as e:
            logger.error(f"[IMPORT] Could not dispatch extraction for {map_id}: {e}")
            asyncio.run(
                _end_extraction(
                    map_id,
                    extraction_task_id,
                    EXTRACTION_FAILED,
                    "Impossible de lancer l'extraction",
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
            collections.extend(
                _city_features_from_text(
                    claimed.ocr_blocks, inputs.legend_bounds, inputs.frame_bounds
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

        # Step 4: shapes
        shapes_result: dict[str, Any] = {}
        if inputs.enable_shapes_extraction:
            progress(4, "Extracting shapes from image")
            shapes_result = extract_shapes(
                tmp_file_path,
                text_regions=text_regions,
                legend_bounds=inputs.legend_bounds,
            )
            collections.extend(
                placement.georeference(shapes_result.get("pixel_features", [])).collections
            )
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
        color_collections = placement.georeference(
            color_result.get("pixel_features", [])
        ).collections
        collections.extend(color_collections)
        _dump_zones_debug(debug_dir, color_collections)
        _raise_if_cancelled(map_id)

        # Step 6: save everything and close the import
        progress(6, "Saving extracted features")
        output_path = (
            _write_ocr_text_file(claimed.filename, claimed.ocr_blocks)
            if inputs.enable_text_extraction
            else ""
        )
        all_positions, all_names, all_radii, all_kinds = parse_imposed_colors_entries(
            inputs.all_colors or None
        )
        georef_inputs = build_georef_inputs(
            control_points=inputs.control_points or None,
            frame_bounds=inputs.frame_bounds,
            imposed_colors=imposed_colors_to_config_entries(
                all_positions, all_names, all_radii, all_kinds
            ),
            legend=legend_to_entry(inputs.legend_bounds),
        )
        saved = asyncio.run(
            _save_extraction(map_id, claimed.project_id, collections, georef_inputs)
        )

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
        "color_result": {
            "colors_detected": len(color_result.get("normalized_features", []))
        },
        "extractions_performed": {
            "georeferencing": True,
            "color_extraction": True,
            "shapes_extraction": inputs.enable_shapes_extraction,
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
        f"[DEV-TEST] warmed text regions for {test_id}: {len(regions or [])}"
        f" ({state.detail or 'already cached'})"
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
    its folder and score it. No database.

    The pipeline is the production one (``extraction_steps``); what differs is
    where the inputs come from (the case config and the test's stored image)
    and where the results go (files, a report, the run record).

    ``config_overrides`` are per-run switches; ``excluded_control_points`` are
    indices into the stored control points left out of this run. A run using
    either is never promoted to the case's best.
    """

    def progress(step: int, status: str) -> None:
        self.update_state(
            state="PROGRESS",
            meta={"current": step, "total": DEV_TEST_STEPS, "status": status},
        )

    progress(1, "Loading the test case")
    resolved_kind = resolve_case_kind(test_id, test_case)
    switches = {
        key: value
        for key, value in parse_config_overrides(config_overrides).items()
        if getattr(GEOREF_CONFIG, key) != value
    }
    run_config = GEOREF_CONFIG.with_overrides(**switches)

    image_path = find_test_image_path(test_id)
    image = cv2.imread(image_path) if image_path else None
    if image is None:
        raise FileNotFoundError(f"No readable map image for test {test_id}")
    inputs = parse_extraction_inputs(
        load_case_config(GEOREF_ASSETS_DIR, test_id, test_case)
    )
    kept_points, excluded = drop_control_points(
        inputs.control_points, excluded_control_points or []
    )
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
