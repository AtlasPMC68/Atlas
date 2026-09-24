import asyncio
import json
import logging
import os
import re
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
from app.utils.color_extraction import extract_colors
from app.utils.file_utils import validate_file_extension
from app.utils.georeferencing import (
    ControlPoint,
    DEFAULT_GEOREF_CONFIG,
    RunRecord,
    build_georef_inputs,
    georeference_features,
    parse_control_points,
    select_control_points,
)
from app.utils.georeferencing.debug import debug_enabled, make_run_dir
from app.utils.imposed_colors import (
    imposed_colors_to_config_entries,
    parse_imposed_colors_entries,
)
from app.utils.legend import legend_to_entry, polygon_center_in_legend
from app.utils.shapes_extraction import extract_shapes
from app.utils.text_extraction import extract_text, ocr_blocks_to_payload
from app.utils.dev_test_assets import MAPS_DIR, TEST_CASES_DIR
from app.utils.dev_test_pixel_zones import write_classified_image, write_pixel_zones

from .celery_app import celery_app

logger = logging.getLogger(__name__)

nb_task = 6

# TODO : maybe remove this debud parameter pour l'instant j'aimerais ca le garder tho
# Roadmap section 4.3 says to turn this off once chamfer alignment begins, and
# measurement now backs that up rather than just asserting it. Translating the
# *same* transform by a few pixels and re-scoring gives, on the one test case:
#
#   snapping ON   IoU jumps around non-monotonically, spread 0.0125 over 8 px,
#                 with a 0.012 spike down at 5 px
#   snapping OFF  IoU falls smoothly and monotonically, spread 0.0063
#
# Blind vertex snapping corrects whatever the transform got wrong, so it both
# flatters the baseline (0.941 vs 0.926 here) and hides any improvement an
# aligned transform makes -- and it injects a step function into the very metric
# used to judge alignment. Left ON by default so nothing changes silently; turn
# it off when judging alignment quality.
ENABLE_COASTLINE_SNAPPING = os.getenv(
    "GEOREF_ENABLE_COASTLINE_SNAPPING", "true"
).strip().lower() not in ("0", "false", "no", "off")

# Step 4 curve alignment. Toggle without touching code:
#   GEOREF_ENABLE_CURVE_ALIGNMENT=false docker compose up
# It needs the OCR text mask (without one about half the edge map is place
# names); imports get it from the OCR task that runs at upload.
ENABLE_CURVE_ALIGNMENT = os.getenv(
    "GEOREF_ENABLE_CURVE_ALIGNMENT", "true"
).strip().lower() not in ("0", "false", "no", "off")

# One config for every georeferencing call in this module, so the snapping flag
# actually governs both producers. It previously only reached the colors path
# (current section 9, limitation 7).
GEOREF_CONFIG = DEFAULT_GEOREF_CONFIG.with_overrides(
    snap_to_coastline=ENABLE_COASTLINE_SNAPPING,
    enable_curve_alignment=ENABLE_CURVE_ALIGNMENT,
)


def _control_points(payload: list | None, config=None) -> list[ControlPoint]:
    """The task's control points, restricted to the sources the run uses.

    Filtered once, here, so the alignment, its gates, the baseline fit and the
    piecewise correction all work from the same set. The payload was validated
    by the route that dispatched the task, so a malformed one is a bug and
    raises.
    """
    points = parse_control_points(payload or [])
    return select_control_points(points, (config or GEOREF_CONFIG).gcp_sources)


def _align_if_enabled(
    image_bgr,
    control_points: list[ControlPoint],
    frame_bounds: dict | None,
    text_regions: list | None,
    water_click_positions: list | None,
    water_sampling_radii: list | None,
    record: "RunRecord | None" = None,
    debug_dir: str | None = None,
    config=None,
    legend_bounds: dict | None = None,
):
    """Step 4 curve alignment, when it is switched on.

    Returns the `AlignmentResult`, or None when alignment is switched off.
    Never raises: `align_map` gates its own result and hands back the GCP-only
    baseline on any failure, so the caller can always use it.

    `config` defaults to the process-wide `GEOREF_CONFIG`; a dev-test re-run
    passes its own so switches like snapping can be flipped per run rather than
    per deployment.
    """
    config = config or GEOREF_CONFIG
    if not config.enable_curve_alignment or image_bgr is None:
        return None

    from app.utils.georeferencing.runner import align_map

    result = align_map(
        image_bgr,
        control_points,
        frame_bounds=frame_bounds,
        text_regions=text_regions,
        water_click_positions=water_click_positions,
        water_sampling_radii=water_sampling_radii,
        config=config,
        record=record,
        debug_dir=debug_dir,
        legend_bounds=legend_bounds,
    )
    logger.info(
        f"[GEOREF] alignment method={result.method} rung={result.rung}"
        + (f" failed={result.failed_checks}" if result.failed_checks else "")
    )
    return result


def _dev_test_text_regions(test_id: str, image_bgr, config=None) -> list | None:
    """OCR regions for a dev-test map, from the derived store.

    Two consumers now: the alignment's text mask, and the text-aware zone fill.
    When alignment is on, OCR runs (~135 s, once per map) and both get it.
    When it is off, the cache is *read but never filled*: the regression suite
    runs with alignment off, and paying OCR per case there would take it from
    about 90 seconds to over four minutes. A map whose cache is warm from an
    earlier run still gets the text fill.

    Never raises: a missing text mask degrades the zones and the evidence, it
    does not fail the run.
    """
    resolved = config or GEOREF_CONFIG
    wants_ocr = resolved.enable_curve_alignment
    if not wants_ocr and not resolved.text_aware_zone_fill:
        return None

    from app.utils.dev_test import find_test_image_path
    from app.utils.dev_test_derived import ensure_text_regions

    image_path = find_test_image_path(test_id)
    if not image_path:
        return None

    try:
        regions, state = ensure_text_regions(
            test_id, image_path, image_bgr, refresh=False, allow_compute=wants_ocr
        )
        if regions is None:
            logger.info(
                f"[DEV-TEST] no cached text regions for {test_id};"
                " skipping the text-aware zone fill (alignment is off)"
            )
            return None
        logger.info(
            f"[DEV-TEST] text regions for {test_id}: {len(regions or [])}"
            f" ({state.detail or 'reused from cache'})"
        )
        return regions
    except Exception as e:
        logger.warning(f"[DEV-TEST] Could not obtain text regions for {test_id}: {e}")
        return None


def _dev_test_debug_dir(test_id: str, test_case: str) -> str | None:
    """Where this case's alignment diagnostics go, or None when off.

    Into the case folder rather than the timestamped `debug_runs/` the
    production import path uses: a harness case is re-run against the same map
    over and over, so one folder per case that is overwritten beats an
    ever-growing pile you have to date-match back to a run. It sits next to
    `reference_debug/` and `evidence_debug/`, which already work this way.

    Gated by `GEOREF_DEBUG`, which is already set on `celery-worker` and not on
    `test-backend`, so a UI re-run gets diagnostics and the regression suite
    stays fast without either needing its own switch.
    """
    if not debug_enabled():
        return None

    path = os.path.join(TEST_CASES_DIR, test_id, test_case, "alignment_debug")
    try:
        # Cleared, not merged: a run that writes fewer files than the last one
        # would otherwise leave stale overlays that read as current.
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)
        return path
    except OSError as e:
        logger.warning(f"[DEV-TEST] Could not prepare debug dir {path}: {e}")
        return None


def _write_dev_test_case_state(test_id: str, test_case: str, config=None) -> None:
    """Record which requirements this case satisfied. Never raises."""
    try:
        from app.utils.dev_test import inspect_case
        from app.utils.dev_test_assets import GEOREF_ASSETS_DIR

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


def _dump_zones_debug(debug_dir: str | None, collections: list) -> None:
    """Write the georeferenced output beside the overlays. Never raises."""
    if not debug_dir:
        return
    try:
        flat = [f for fc in collections for f in fc.get("features", [])]
        with open(os.path.join(debug_dir, "zones.geojson"), "w", encoding="utf-8") as f:
            json.dump(
                {"type": "FeatureCollection", "features": flat},
                f,
                indent=2,
                ensure_ascii=False,
            )
    except Exception as e:
        logger.warning(f"Could not write debug zones: {e}")


def _alignment_summary(result) -> dict[str, Any]:
    """What the UI needs to tell the user what happened (plan section 8.4)."""
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


def _georeference(
    pixel_feature_collections: list,
    control_points: list[ControlPoint],
    frame_bounds: dict | None = None,
    record: "RunRecord | None" = None,
    model=None,
    extra_properties: dict | None = None,
    config=None,
    image=None,
):
    """Fit and apply the pixel -> EPSG:4326 transform for one feature producer.

    `image` is only read for its size: the coastline snap tolerance is a share
    of the scan's diagonal.
    """
    return georeference_features(
        pixel_feature_collections,
        control_points,
        frame_bounds=frame_bounds,
        config=config or GEOREF_CONFIG,
        record=record,
        model=model,
        extra_properties=extra_properties,
        image_size=(image.shape[1], image.shape[0]) if image is not None else None,
    )


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


# --- import row transitions ---------------------------------------------------
#
# Every transition locks the row, so the OCR task, the extraction task and the
# routes never interleave. Rows are matched on the task id as well as the map:
# a task that was superseded (OCR re-dispatched, extraction relaunched after a
# cancel) finds a different id and leaves the row alone.


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
    in one transaction: a cancel or a crash leaves no partial map behind.

    The cancel check happens under the same lock as the writes, so a cancel
    either lands before it (nothing saved) or finds the import already gone.
    """
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
    """One point feature per place name read off the map.

    Each OCR label is matched against the gazetteer cities inside the framing
    box only -- a city outside the world area the user framed is not on their
    map, whatever its name -- exactly, longest phrase first, so "Trois
    Rivieres" is one city. Words that match nothing are kept hidden at (0, 0)
    so the user can still place them by hand. Legend text is skipped: its
    labels name the key's entries, not places.
    """
    index = frame_city_index(frame_bounds) if frame_bounds else None

    collections: List[dict[str, Any]] = []
    for coords, text, _prob in blocks:
        if polygon_center_in_legend(coords, legend_bounds):
            continue
        phrases = (
            find_cities_in_text(text, index)
            if index is not None
            else [(word, None) for word in re.findall(r"[\w\-']+", text)]
        )
        for phrase, city in phrases:
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


def _georeferenced_or_normalized(
    pixel_features: list,
    normalized_features: list,
    points: list[ControlPoint],
    frame_bounds: dict | None,
    aligned_model,
    alignment_props: dict | None,
    image=None,
) -> list:
    if not points:
        return normalized_features
    return _georeference(
        pixel_features,
        points,
        frame_bounds=frame_bounds,
        model=aligned_model,
        extra_properties=alignment_props,
        image=image
    ).collections


# --- tasks --------------------------------------------------------------------


@celery_app.task(bind=True)
def run_map_ocr(self, map_id: str):
    """OCR for an import, started as soon as the map is uploaded.

    The slowest step of an import (~135 s/map on CPU), so it runs while the user
    is still framing, matching points and picking colours. It reads the whole
    map: detection costs the same whatever is masked, and the legend is applied
    to the result at extraction time instead, so the user can draw it in any
    order. Writes nothing but ``ocr_result``.
    """
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
    """Extract, georeference and save a map's features from its import row.

    Takes only the map id: the image, the user's inputs and the OCR result are
    all on ``map_imports``, which also keeps Celery messages small and the task
    signature stable as inputs are added.

    Cancellation is cooperative: the route marks the row ``cancelling`` and the
    task stops at its next check. Features are saved in one transaction at the
    very end, so a cancelled or failed run leaves the map exactly as it was.
    """
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

        # Step 3: curve alignment, once, so shapes and colours share a transform
        points = select_control_points(inputs.control_points, GEOREF_CONFIG.gcp_sources)
        water_positions, _water_names, water_radii = inputs.water_picks
        alignment = None
        aligned_model = None
        debug_dir = make_run_dir(f"map{map_id}") if debug_enabled() else None
        if points and GEOREF_CONFIG.enable_curve_alignment:
            progress(3, "Extracting reference geography and aligning the map")
            alignment = _align_if_enabled(
                image,
                points,
                inputs.frame_bounds,
                text_regions,
                water_positions,
                water_radii,
                debug_dir=debug_dir,
                legend_bounds=inputs.legend_bounds,
            )
            if alignment is not None and alignment.used_curve_evidence:
                aligned_model = alignment.model
        alignment_props = (
            {"alignment_method": alignment.method, "alignment_rung": alignment.rung}
            if alignment is not None
            else None
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
                _georeferenced_or_normalized(
                    shapes_result.get("pixel_features", []),
                    shapes_result.get("normalized_features", []),
                    points,
                    inputs.frame_bounds,
                    aligned_model,
                    alignment_props,
                    image=image,
                )
            )
        _raise_if_cancelled(map_id)

        # Step 5: colours, from the pipette alone
        progress(5, "Extracting colors from image")
        zone_positions, zone_names, zone_radii = inputs.zone_picks
        color_result = extract_colors(
            tmp_file_path,
            debug=False,
            legend_bounds=inputs.legend_bounds,
            imposed_click_positions=[tuple(c) for c in zone_positions or []] or None,
            imposed_colors_names=zone_names,
            imposed_sampling_radii=[int(r) for r in zone_radii] if zone_radii else None,
            text_regions=(text_regions if GEOREF_CONFIG.text_aware_zone_fill else None),
            text_fill_min_context=GEOREF_CONFIG.text_fill_min_context,
            text_fill_max_distance_px=GEOREF_CONFIG.text_fill_max_distance_px,
            text_fill_method=GEOREF_CONFIG.text_fill_method,
            text_inpaint_dilation_px=GEOREF_CONFIG.text_inpaint_dilation_px,
            text_inpaint_radius_px=GEOREF_CONFIG.text_inpaint_radius_px,
            text_inpaint_max_ink_ratio=GEOREF_CONFIG.text_inpaint_max_ink_ratio,
            text_inpaint_algo=GEOREF_CONFIG.text_inpaint_algo,
            text_inpaint_ink_deltaE=GEOREF_CONFIG.text_inpaint_ink_deltaE,
            zone_gap_fill=GEOREF_CONFIG.zone_gap_fill,
            zone_gap_max_ratio_of_diagonal=GEOREF_CONFIG.zone_gap_max_ratio_of_diagonal,
        )

        color_result.pop("classified_rgb", None)
        
        color_collections = _georeferenced_or_normalized(
            color_result.get("pixel_features", []),
            color_result.get("normalized_features", []),
            points,
            inputs.frame_bounds,
            aligned_model,
            alignment_props,
            image=image,
        )
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
            "georeferencing": bool(points),
            "color_extraction": True,
            "shapes_extraction": inputs.enable_shapes_extraction,
            "text_extraction": inputs.enable_text_extraction,
        },
        "alignment": _alignment_summary(alignment),
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
    """Fill a dev-test map's OCR cache while the user is still clicking.

    Started when the import view opens in dev-test mode, so the first case on a
    new map does not wait ~135 s for OCR. A case run arriving meanwhile waits on
    the same per-map lock and reuses the result instead of running it again.
    """
    if not GEOREF_CONFIG.enable_curve_alignment:
        return {"status": "skipped", "reason": "curve alignment is off"}

    from app.utils.dev_test import find_test_image_path
    from app.utils.dev_test_derived import ensure_text_regions

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
    filename: str,
    file_content: bytes,
    test_id: str,
    test_case: str,
    control_points: list | None = None,
    imposed_click_positions: list | None = None,
    imposed_colors_names: list | None = None,
    imposed_sampling_radii: list | None = None,
    frame_bounds: dict | None = None,
    water_click_positions: list | None = None,
    water_colors_names: list | None = None,
    water_sampling_radii: list | None = None,
    config_overrides: dict | None = None,
    legend_bounds: dict | None = None,
):
    """Dev-test-only extraction task: no DB persistence, results saved to files,
    evaluation report written automatically at the end.

    ``config_overrides`` sets any ``GeorefConfig`` field for this run only --
    the per-run switches (``snap_to_coastline`` and friends) and the dev tool's
    tuning panel both arrive here. It is one extensible dict rather than a flag
    per setting on purpose: every kwarg added to a Celery task breaks in-flight
    messages and any caller that has not restarted alongside the worker, so a
    new setting should not change this signature at all. Unknown keys are
    dropped; see ``parse_config_overrides``.

    Whether the run is *scored* comes from the case's kind, which is resolved
    here from disk rather than passed in. A ``probe`` case has no hand-drawn
    expected zones and exists only to replay a map's stored clicks quickly, so
    it writes zones and a run record but no report -- there is nothing to
    compare against, and a fabricated one would be worse than none.

    Resolved rather than passed because the worker mounts the test assets and
    already re-reads this config below, so a kwarg would be a second source of
    truth for the same fact -- and every kwarg added here breaks in-flight
    tasks and any caller that has not restarted alongside the worker.
    """
    from app.utils.dev_test_cases import KIND_PROBE, resolve_case_kind
    from app.utils.georeferencing.config import parse_config_overrides

    resolved_kind = resolve_case_kind(test_id, test_case)
    # An "override" equal to the ambient value is not one. Dropping those keeps
    # the record honest about what differed, and keeps a run the tuning panel
    # sent back at defaults eligible for `zones_best`.
    switches = {
        key: value
        for key, value in parse_config_overrides(config_overrides).items()
        if getattr(GEOREF_CONFIG, key) != value
    }
    run_config = GEOREF_CONFIG.with_overrides(**switches)

    # A run under non-ambient switches is not comparable to one under the
    # defaults -- snapping alone moves this map's IoU 0.941 vs 0.926 (plan 8c).
    # Letting such a run win `zones_best` would mean "best" silently mixing two
    # different metrics, so it is written but never promoted.
    ambient_run = not switches

    # The run's sources only: unticking "cities" in the dev tool means the
    # cities play no part anywhere, not merely in the final fit.
    points = _control_points(control_points, run_config)

    georef_record = RunRecord(run_id=f"{test_id}/{test_case}")
    georef_record.set_inputs(
        waterPickCount=len(water_click_positions or []),
        legendBounds=legend_bounds,
        caseKind=resolved_kind,
        runSwitches=switches or None,
        controlPointSources=list(run_config.gcp_sources),
    )
    try:
        # Step 1: temp save
        self.update_state(
            state="PROGRESS",
            meta={"current": 1, "total": nb_task, "status": "Saving uploaded file"},
        )
        time.sleep(2)

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(filename)[1]
        ) as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name

        # Step 2: load and validate image
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 2,
                "total": nb_task,
                "status": "Loading and validating image",
            },
        )

        image = cv2.imread(tmp_file_path)
        if image is None:
            raise ValueError(f"Could not read image file: {filename}")
        if not validate_file_extension(tmp_file_path):
            ext = os.path.splitext(tmp_file_path)[1].lower()
            raise ValueError(f"Extension {ext} is not allowed.")

        # Steps 3-4: skip text and shapes extraction for dev-test
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 3,
                "total": nb_task,
                "status": "Skipping text extraction (dev-test mode)",
            },
        )
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 4,
                "total": nb_task,
                "status": "Skipping shapes extraction (dev-test mode)",
            },
        )

        # Step 5: color extraction + georeferencing (always enabled for dev-test)
        all_extracted_features: list[dict[str, Any]] = []
        color_result: dict[str, Any] = {"colors_detected": 0}

        self.update_state(
            state="PROGRESS",
            meta={
                "current": 5,
                "total": nb_task,
                "status": "Extracting colors from image",
            },
        )
        # Colors are always imposed (pipette): without click positions the
        # extraction returns nothing and there is no zone left to georeference.
        imposed_click_positions_tuples = (
            [tuple(c) for c in imposed_click_positions]
            if imposed_click_positions
            else None
        )
        imposed_sampling_radii_ints = (
            [int(r) for r in imposed_sampling_radii] if imposed_sampling_radii else None
        )

        if not imposed_click_positions_tuples:
            logger.warning(
                f"[DEV-TEST] No imposed colors for test {test_id}/{test_case}; "
                "color extraction will return no zones"
            )

        # Text regions are a property of the *map*, not of the case, and OCR
        # costs ~135 s on CPU. Pulling them from the derived store means the
        # second case on a map -- and every re-run of the first -- pays
        # nothing, which is what makes this loop usable. Fetched before colour
        # extraction because the zone fill needs them too, not only alignment.
        text_regions = _dev_test_text_regions(test_id, image, config=run_config)

        color_result = extract_colors(
            tmp_file_path,
            debug=False,
            legend_bounds=legend_bounds,
            imposed_click_positions=imposed_click_positions_tuples,
            imposed_colors_names=imposed_colors_names,
            imposed_sampling_radii=imposed_sampling_radii_ints,
            text_regions=text_regions if run_config.text_aware_zone_fill else None,
            text_fill_min_context=run_config.text_fill_min_context,
            text_fill_max_distance_px=run_config.text_fill_max_distance_px,
            text_fill_method=run_config.text_fill_method,
            text_inpaint_dilation_px=run_config.text_inpaint_dilation_px,
            text_inpaint_radius_px=run_config.text_inpaint_radius_px,
            text_inpaint_max_ink_ratio=run_config.text_inpaint_max_ink_ratio,
            text_inpaint_algo=run_config.text_inpaint_algo,
            text_inpaint_ink_deltaE=run_config.text_inpaint_ink_deltaE,
            zone_gap_fill=run_config.zone_gap_fill,
            zone_gap_max_ratio_of_diagonal=run_config.zone_gap_max_ratio_of_diagonal,
        )
        # Out of the dict before anything else: it is returned to Celery, which
        # cannot serialise an array. Written beside the zones further down.
        classified_rgb = color_result.pop("classified_rgb", None)
        normalized_features = color_result.get("normalized_features", [])
        pixel_features = color_result.get("pixel_features", [])
        georef_record.set_errors(
            textFill=color_result.get("text_fill"),
            zoneGaps=color_result.get("zone_gaps"),
        )
        # Copied now: georeferencing rewrites these features' properties in
        # place, and the test tool shows the extraction on its own, before
        # any transform touched it.
        pixel_zones_snapshot = json.loads(json.dumps(pixel_features))

        if points:
            try:
                debug_dir = _dev_test_debug_dir(test_id, test_case)
                alignment = _align_if_enabled(
                    image,
                    points,
                    frame_bounds,
                    text_regions,
                    water_click_positions,
                    water_sampling_radii,
                    record=georef_record,
                    config=run_config,
                    debug_dir=debug_dir,
                    legend_bounds=legend_bounds,
                )
                aligned_model = (
                    alignment.model
                    if alignment is not None and alignment.used_curve_evidence
                    else None
                )
                georef = _georeference(
                    pixel_features,
                    points,
                    frame_bounds=frame_bounds,
                    record=georef_record,
                    model=aligned_model,
                    config=run_config,
                    image=image,
                )
                all_extracted_features = georef.collections
                georef_record.set_model("chosen", georef.transform_payload)
                _dump_zones_debug(debug_dir, georef.collections)
                if debug_dir:
                    logger.info(f"[DEV-TEST] alignment debug dump -> {debug_dir}")
            except Exception as e:
                logger.error(
                    f"[DEV-TEST] Georeferencing failed for test {test_id}: {e}",
                    exc_info=True,
                )
                georef_record.note(f"georeferencing failed: {e}")
                all_extracted_features = normalized_features
        else:
            georef_record.note("no control points; features stay in normalised space")
            all_extracted_features = normalized_features

        # Step 6: save assets to files
        self.update_state(
            state="PROGRESS",
            meta={"current": 6, "total": nb_task, "status": "Saving test assets"},
        )

        os.unlink(tmp_file_path)

        image_output_path = ""
        zones_output_path = ""
        image_url = ""
        zones_url = ""

        try:
            os.makedirs(MAPS_DIR, exist_ok=True)
            case_dir = os.path.join(TEST_CASES_DIR, test_id)
            os.makedirs(case_dir, exist_ok=True)

            # Reuse existing map image if already present to avoid rewriting bytes
            existing_map_path: str | None = None
            try:
                for existing in os.listdir(MAPS_DIR):
                    stem, _e = os.path.splitext(existing)
                    if stem == test_id:
                        existing_map_path = os.path.join(MAPS_DIR, existing)
                        break
            except OSError:
                existing_map_path = None

            if existing_map_path and os.path.exists(existing_map_path):
                image_output_path = existing_map_path
                ext = os.path.splitext(existing_map_path)[1] or ".png"
            else:
                ext = os.path.splitext(filename)[1] or ".png"
                image_output_path = os.path.join(MAPS_DIR, f"{test_id}{ext}")
                cv2.imwrite(image_output_path, image)

            # Flatten all feature collections into one FeatureCollection
            all_flat_features: list[dict[str, Any]] = []
            for fc in all_extracted_features:
                all_flat_features.extend(fc.get("features", []))

            zones_geojson = {"type": "FeatureCollection", "features": all_flat_features}
            nested_case_dir = os.path.join(case_dir, test_case)
            os.makedirs(nested_case_dir, exist_ok=True)
            zones_output_path = os.path.join(nested_case_dir, "zones.geojson")
            with open(zones_output_path, "w", encoding="utf-8") as f:
                json.dump(zones_geojson, f, indent=2, ensure_ascii=False)
            write_pixel_zones(nested_case_dir, pixel_zones_snapshot)
            write_classified_image(nested_case_dir, classified_rgb)

            image_url = f"/dev-test/maps/{test_id}{ext}"
            zones_url = f"/dev-test/test_cases/{test_id}/{test_case}/zones.geojson"

            logger.info(
                f"[DEV-TEST] Saved image to {image_output_path} and zones to {zones_output_path}"
            )
        except Exception as e:
            logger.error(f"[DEV-TEST] Failed to save test assets for {filename}: {e}")

        # Evaluate and persist reports automatically -- but only for a scored
        # case. A probe has no expected zones by design, so there is nothing to
        # evaluate and no report is written; the zones and the run record are
        # the whole deliverable.
        if resolved_kind == KIND_PROBE:
            logger.info(
                f"[DEV-TEST] {test_id}/{test_case} is a probe case: zones written,"
                " no score computed"
            )
            georef_record.note("probe case: no expected zones, run not scored")
        else:
            try:
                from app.utils.dev_test import evaluate_and_persist_case
                from app.utils.dev_test_assets import GEOREF_ASSETS_DIR

                report = evaluate_and_persist_case(
                    assets_root=GEOREF_ASSETS_DIR,
                    test_id=test_id,
                    test_case_id=test_case,
                    min_iou=None,
                    allow_best_promotion=ambient_run,
                )
                georef_record.set_errors(iou=_iou_summary_from_report(report))
                logger.info(
                    f"[DEV-TEST] Evaluation report written for {test_id}/{test_case}"
                )
            except Exception as e:
                logger.warning(
                    f"[DEV-TEST] Evaluation skipped (expected zones may be missing): {e}"
                )

        # The resolved requirement state goes on disk next to the run record, so
        # "why is this case's number odd" can be answered without re-deriving it.
        _write_dev_test_case_state(test_id, test_case, config=run_config)

        # The run record goes next to report.json whether or not evaluation ran:
        # an IoU number alone cannot tell you which stage moved it.
        record_dir = os.path.join(TEST_CASES_DIR, test_id, test_case)
        georef_record.write(record_dir)

        result = {
            "filename": filename,
            "status": "completed",
            "color_result": color_result,
            "extractions_performed": {
                "georeferencing": bool(points),
                "color_extraction": True,
            },
            "test_assets": {
                "image_path": image_output_path,
                "zones_path": zones_output_path,
                "image_url": image_url,
                "zones_url": zones_url,
            },
        }

        logger.info(
            f"[DEV-TEST] Extraction completed for {filename} (test_id={test_id}, case={test_case})"
        )
        return result

    except Exception as e:
        if "tmp_file_path" in locals():
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass
        logger.error(f"[DEV-TEST] Error processing test map {filename}: {str(e)}")
        raise e
