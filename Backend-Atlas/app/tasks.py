import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
import time
from datetime import datetime
from typing import Any, List
from uuid import UUID

import cv2

from app.database.session import AsyncSessionLocal
from app.services.features import insert_feature_in_db
from app.utils.cities_validation import find_first_city
from app.utils.color_extraction import extract_colors
from app.utils.file_utils import validate_file_extension
from app.utils.georeferencing import (
    ControlPoint,
    DEFAULT_GEOREF_CONFIG,
    RunRecord,
    georeference_features,
)
from app.utils.georeferencing.debug import debug_enabled, make_run_dir
from app.utils.shapes_extraction import extract_shapes
from app.utils.text_extraction import extract_text
from app.utils.dev_test_assets import MAPS_DIR, TEST_CASES_DIR

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
# Note it makes an import markedly slower: when text extraction is off,
# georeferencing runs its own OCR (~135 s/map on CPU) because without a text
# mask about half the edge map is place names.
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


def _control_points(pixel_points: list, geo_points_lonlat: list):
    return ControlPoint.from_pairs(pixel_points, geo_points_lonlat, source="sift")


def _align_if_enabled(
    image_bgr,
    pixel_points: list,
    geo_points_lonlat: list,
    frame_bounds: dict | None,
    text_regions: list | None,
    water_click_positions: list | None,
    water_sampling_radii: list | None,
    record: "RunRecord | None" = None,
    debug_dir: str | None = None,
    config=None,
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

    if text_regions is None:
        # Georeferencing runs OCR whether or not text *extraction* was asked
        # for. Without a text mask about half the edge pixels on a labelled map
        # are place names, which is not optional noise -- it is most of the
        # evidence. Costs ~135 s/map on CPU, only when alignment is enabled.
        try:
            blocks, _clean = extract_text(
                image=image_bgr, languages=["en", "fr"], gpu_acc=False
            )
            text_regions = [block[0] for block in blocks]
            logger.info(
                f"[GEOREF] ran OCR for alignment: {len(text_regions)} text regions"
            )
        except Exception as e:
            logger.warning(f"[GEOREF] OCR for alignment failed, continuing: {e}")
            text_regions = None

    result = align_map(
        image_bgr,
        _control_points(pixel_points, geo_points_lonlat),
        frame_bounds=frame_bounds,
        text_regions=text_regions,
        water_click_positions=water_click_positions,
        water_sampling_radii=water_sampling_radii,
        config=config,
        record=record,
        debug_dir=debug_dir,
    )
    logger.info(
        f"[GEOREF] alignment method={result.method} rung={result.rung}"
        + (f" failed={result.failed_checks}" if result.failed_checks else "")
    )
    return result


def _dev_test_text_regions(test_id: str, image_bgr, config=None) -> list | None:
    """OCR regions for a dev-test map, from the derived store.

    Returns None when alignment is off (nothing consumes them) or when OCR is
    unavailable. Never raises: a missing text mask degrades the evidence, it
    does not fail the run.
    """
    if not (config or GEOREF_CONFIG).enable_curve_alignment:
        return None

    from app.utils.dev_test import find_test_image_path
    from app.utils.dev_test_derived import ensure_text_regions

    image_path = find_test_image_path(test_id)
    if not image_path:
        return None

    try:
        regions, state = ensure_text_regions(
            test_id, image_path, image_bgr, refresh=False
        )
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
    pixel_points: list,
    geo_points_lonlat: list,
    frame_bounds: dict | None = None,
    record: "RunRecord | None" = None,
    model=None,
    extra_properties: dict | None = None,
    config=None,
):
    """Fit and apply the pixel -> EPSG:4326 transform for one feature producer."""
    return georeference_features(
        pixel_feature_collections,
        _control_points(pixel_points, geo_points_lonlat),
        frame_bounds=frame_bounds,
        config=config or GEOREF_CONFIG,
        record=record,
        model=model,
        extra_properties=extra_properties,
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

@celery_app.task(bind=True)
def process_map_extraction(
    self,
    filename: str,
    file_content: bytes,
    project_id: UUID,
    map_id: UUID,
    pixel_points: list | None = None,
    geo_points_lonlat: list | None = None,
    legend_bounds: dict | None = None,
    enable_color_extraction: bool = True,
    enable_shapes_extraction: bool = False,
    enable_text_extraction: bool = False,
    imposed_click_positions: list | None = None,
    imposed_colors_names: list | None = None,
    imposed_sampling_radii: list | None = None,
    frame_bounds: dict | None = None,
    water_click_positions: list | None = None,
    water_colors_names: list | None = None,
    water_sampling_radii: list | None = None,
):

    # The water pipette is carried but not yet consumed: Step 3 builds the water
    # mask from it. Feeding it to colour extraction now would change output, and
    # Step 1 must leave output identical.
    if water_click_positions:
        logger.info(
            f"[GEOREF] {len(water_click_positions)} water pipette pick(s) received "
            f"for map {map_id}; unused until the water mask lands."
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

        # Step 2: opening the picture
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 2,
                "total": nb_task,
                "status": "Loading and validating image",
            },
        )

        image = cv2.imread(tmp_file_path)
        image.flags.writeable = False  # Makes image immutable
        if not validate_file_extension(tmp_file_path):
            ext = os.path.splitext(tmp_file_path)[1].lower()
            raise ValueError(f"Extension {ext} is not allowed.")

        # Step 3: Extraction OCR
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 3,
                "total": nb_task,
                "status": "Extracting text with EasyOCR",
            },
        )

        if enable_text_extraction:
            # GPU acceleration make the text extraction MUCH faster i
            extracted_text, clean_image = extract_text(
                image=image, languages=["en", "fr"], gpu_acc=False
            )

            text_regions = [block[0] for block in extracted_text]

            # TODO : Amener ca dans la fonction de detection de texte ===========================================================
            # Tokenize OCR text to single words and run city detection per token
            try:
                # Extract just the text strings from the list of tuples [(coords, text, prob), ...]
                text_strings = [block[1] for block in extracted_text]
                full_text = " ".join(text_strings)
                tokens = re.findall(r"\b[\w\-']+\b", full_text)
                for tok in tokens:
                    try:
                        candidate = find_first_city(tok)
                    except Exception as e:
                        logger.debug(f"find_first_city error for token '{tok}': {e}")
                        # treat as not found but persist the token
                        candidate = {
                            "found": False,
                            "query": tok,
                            "name": tok,
                            "lat": 0.0,
                            "lon": 0.0,
                        }

                    # Build feature using returned candidate; if not found, coordinates will be 0,0
                    city_feature = {
                        "type": "Feature",
                        "properties": {
                            "name": candidate.get("name") or tok,
                            "show": bool(candidate.get("found")),
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

                    city_feature_collection = {
                        "type": "FeatureCollection",
                        "features": [city_feature],
                    }
                    try:
                        asyncio.run(
                            persist_city_feature(
                                project_id, map_id, city_feature_collection
                            )
                        )
                    except Exception as e:
                        logger.error(f"Failed to persist city token '{tok}': {e}")

            except Exception as e:
                logger.error(f"City detection failed: {e}")

        else:
            text_regions = None

        # TODO : Amener ca dans la fonction de detection de texte ===========================================================

        # Curve alignment, once, before either producer runs, so shapes and
        # colors are georeferenced with the same transform. It needs the text
        # regions, hence its position right after the OCR step.
        alignment = None
        aligned_model = None
        debug_dir = None
        if debug_enabled():
            debug_dir = make_run_dir(f"map{map_id}")
        if pixel_points and geo_points_lonlat and GEOREF_CONFIG.enable_curve_alignment:
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": 3,
                    "total": nb_task,
                    "status": "Extracting reference geography and aligning the map",
                },
            )
            alignment = _align_if_enabled(
                image,
                pixel_points,
                geo_points_lonlat,
                frame_bounds,
                text_regions,
                water_click_positions,
                water_sampling_radii,
                debug_dir=debug_dir,
            )
            if alignment is not None and alignment.used_curve_evidence:
                aligned_model = alignment.model

        alignment_props = (
            {"alignment_method": alignment.method, "alignment_rung": alignment.rung}
            if alignment is not None
            else None
        )

        # Step 4: Shapes Extraction (conditionally enabled)
        zones_features: list[dict[str, Any]] | None = None
        if enable_shapes_extraction:
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": 4,
                    "total": nb_task,
                    "status": "Extracting shapes from image",
                },
            )
            time.sleep(2)
            shapes_result = extract_shapes(
                tmp_file_path,
                text_regions=text_regions,
                legend_bounds=legend_bounds,
            )
            shape_normalized_features = shapes_result["normalized_features"]
            shape_pixel_features = shapes_result.get("pixel_features", [])

            # Georeference pixel-space shape features if SIFT point pairs are provided
            if pixel_points and geo_points_lonlat:
                try:
                    shapes_georef = _georeference(
                        shape_pixel_features,
                        pixel_points,
                        geo_points_lonlat,
                        frame_bounds=frame_bounds,
                        model=aligned_model,
                        extra_properties=alignment_props,
                    )
                    asyncio.run(
                        persist_features(
                            project_id, map_id, shapes_georef.collections
                        )
                    )
                except Exception as e:
                    logger.error(
                        f"SIFT georeferencing step failed for shapes {map_id}: {e}",
                        exc_info=True,
                    )
            elif shape_normalized_features:
                asyncio.run(
                    persist_features(project_id, map_id, shape_normalized_features)
                )
        else:
            logger.info("[DEBUG] Shapes extraction disabled - skipping")
            shapes_result = {}

        # Step 5: Color Extraction (conditionally enabled)
        if enable_color_extraction:
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": 5,
                    "total": nb_task,
                    "status": "Extracting colors from image",
                },
            )

            legends_shapes = [
                s for s in shapes_result.get("shapes", []) if s.get("isLegend", False)
            ]

            imposed_click_positions_tuples = (
                [tuple(c) for c in imposed_click_positions]
                if imposed_click_positions
                else None
            )

            imposed_sampling_radii_ints = (
                [int(r) for r in imposed_sampling_radii]
                if imposed_sampling_radii
                else None
            )

            # If the frontend provided a legend box but shapes extraction was disabled,
            # we still need legend shapes to perform legend-based color extraction.
            if (
                not imposed_click_positions_tuples
                and not legends_shapes
                and legend_bounds is not None
            ):
                try:
                    legend_shapes_result = extract_shapes(
                        tmp_file_path,
                        text_regions=text_regions,
                        legend_bounds=legend_bounds,
                    )
                    legends_shapes = [
                        s
                        for s in legend_shapes_result.get("shapes", [])
                        if s.get("isLegend", False)
                    ]
                except Exception as e:
                    logger.error(
                        f"Legend-only shapes extraction failed for map {map_id}: {e}",
                        exc_info=True,
                    )

            if not imposed_click_positions_tuples and not legends_shapes:
                logger.info(
                    "[DEBUG] Color extraction skipped - no imposed colors provided"
                )
                color_result = {
                    "normalized_features": [],
                    "pixel_features": [],
                    "masks": {},
                }
            else:
                color_result = extract_colors(
                    tmp_file_path,
                    debug=False,
                    legend_shapes=legends_shapes if legends_shapes else None,
                    imposed_click_positions=imposed_click_positions_tuples,
                    imposed_colors_names=imposed_colors_names,
                    imposed_sampling_radii=imposed_sampling_radii_ints,
                )
            normalized_features = color_result.get("normalized_features", [])
            pixel_features = color_result.get("pixel_features", [])

            # TODO : Rendre ca une etape pour toutes les extractions ===================================================================
            # Georeference pixel-space features if SIFT point pairs are provided
            if pixel_points and geo_points_lonlat:
                try:
                    colors_georef = _georeference(
                        pixel_features,
                        pixel_points,
                        geo_points_lonlat,
                        frame_bounds=frame_bounds,
                        model=aligned_model,
                        extra_properties=alignment_props,
                    )
                    asyncio.run(
                        persist_features(project_id, map_id, colors_georef.collections)
                    )
                    _dump_zones_debug(debug_dir, colors_georef.collections)

                except Exception as e:
                    logger.error(
                        f"SIFT georeferencing step failed for map {map_id}: {e}",
                        exc_info=True,
                    )
            elif normalized_features:
                asyncio.run(persist_features(project_id, map_id, normalized_features))
        else:
            logger.info("[DEBUG] Color extraction disabled - skipping")
            color_result = {"colors_detected": 0}

        # Step 6: Cleaning
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 6,
                "total": nb_task,
                "status": "Cleaning up and finalizing",
            },
        )
        os.unlink(tmp_file_path)

        if enable_text_extraction:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            output_dir = os.path.join(current_dir, "extracted_texts")
            try:
                os.makedirs(output_dir, exist_ok=True)
                logger.info(
                    f"[DEBUG] Directory created or already exists: {output_dir}"
                )
            except Exception as e:
                logger.error(f"[ERROR] Failed to create directory {output_dir}: {e}")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(filename)[0]
            output_filename = f"{timestamp}_{base_name}.txt"
            output_path = os.path.join(output_dir, output_filename)

            lines = [block[1] for block in extracted_text]
            full_text = "\n".join(lines)
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("=== OCR EXTRACTION  ===\n")
                    f.write(f"Source File: {filename}\n")
                    f.write(
                        f"Date extraction: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    )
                    f.write("\n=== TEXTE EXTRAIT ===\n\n")
                    f.write(full_text)

                logger.info(f"Text saved to: {output_path}")

            except Exception as e:
                logger.error(f"Failed to save text file: {str(e)}")
                output_path = f"ERROR: Could not save to {output_path}"

        result = {
            "filename": filename,
            "output_path": output_path if enable_text_extraction else "",
            "shapes_result": shapes_result if enable_shapes_extraction else {},
            "color_result": color_result
            if enable_color_extraction
            else {"colors_detected": 0},
            "status": "completed",
            "extractions_performed": {
                "georeferencing": bool(pixel_points and geo_points_lonlat),
                "color_extraction": enable_color_extraction,
                "shapes_extraction": enable_shapes_extraction,
                "text_extraction": enable_text_extraction,
            },
            "alignment": _alignment_summary(alignment),
        }

        logger.info(f"Map processing completed for {filename}: 0 characters extracted")

        return result

    except Exception as e:
        if "tmp_file_path" in locals():
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass

        logger.error(f"Error processing map {filename}: {str(e)}")
        raise e


async def persist_features(
    project_id: UUID,
    map_id: UUID,
    normalized_features: List[dict[str, Any]],
):
    async with AsyncSessionLocal() as db:
        for feature_collection in normalized_features:
            for feature in feature_collection.get("features", []):
                feature_data = {
                    "type": "FeatureCollection",
                    "features": [feature],
                }
                try:
                    await insert_feature_in_db(
                        db=db,
                        map_id=map_id,
                        data=feature_data,
                        project_id=project_id,
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to persist individual feature for map {map_id}: {str(e)}"
                    )


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


async def persist_city_feature(project_id: UUID, map_id: UUID, feature: dict[str, Any]):
    async with AsyncSessionLocal() as db:
        try:
            await insert_feature_in_db(
                db=db,
                map_id=map_id,
                data=feature,
                project_id=project_id,
            )
        except Exception as e:
            logger.error(f"Failed to persist city feature for map {map_id}: {str(e)}")


@celery_app.task(bind=True)
def process_dev_test_extraction(
    self,
    filename: str,
    file_content: bytes,
    test_id: str,
    test_case: str,
    pixel_points: list | None = None,
    geo_points_lonlat: list | None = None,
    imposed_click_positions: list | None = None,
    imposed_colors_names: list | None = None,
    imposed_sampling_radii: list | None = None,
    frame_bounds: dict | None = None,
    water_click_positions: list | None = None,
    water_colors_names: list | None = None,
    water_sampling_radii: list | None = None,
    config_overrides: dict | None = None,
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

    georef_record = RunRecord(run_id=f"{test_id}/{test_case}")
    georef_record.set_inputs(
        waterPickCount=len(water_click_positions or []),
        caseKind=resolved_kind,
        runSwitches=switches or None,
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

        color_result = extract_colors(
            tmp_file_path,
            debug=False,
            legend_shapes=None,
            imposed_click_positions=imposed_click_positions_tuples,
            imposed_colors_names=imposed_colors_names,
            imposed_sampling_radii=imposed_sampling_radii_ints,
        )
        normalized_features = color_result.get("normalized_features", [])
        pixel_features = color_result.get("pixel_features", [])

        if pixel_points and geo_points_lonlat:
            try:
                # Text regions are a property of the *map*, not of the case, and
                # OCR costs ~135 s on CPU. Pulling them from the derived store
                # means the second case on a map -- and every re-run of the
                # first -- pays nothing, which is what makes this loop usable.
                text_regions = _dev_test_text_regions(
                    test_id, image, config=run_config
                )

                debug_dir = _dev_test_debug_dir(test_id, test_case)
                alignment = _align_if_enabled(
                    image,
                    pixel_points,
                    geo_points_lonlat,
                    frame_bounds,
                    text_regions,
                    water_click_positions,
                    water_sampling_radii,
                    record=georef_record,
                    config=run_config,
                    debug_dir=debug_dir,
                )
                aligned_model = (
                    alignment.model
                    if alignment is not None and alignment.used_curve_evidence
                    else None
                )
                georef = _georeference(
                    pixel_features,
                    pixel_points,
                    geo_points_lonlat,
                    frame_bounds=frame_bounds,
                    record=georef_record,
                    model=aligned_model,
                    config=run_config,
                )
                all_extracted_features = georef.collections
                georef_record.set_model("chosen", georef.transform_payload)
                _dump_zones_debug(debug_dir, georef.collections)
                if debug_dir:
                    logger.info(f"[DEV-TEST] alignment debug dump -> {debug_dir}")
            except Exception as e:
                logger.error(
                    f"[DEV-TEST] SIFT georeferencing failed for test {test_id}: {e}",
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
                "georeferencing": bool(pixel_points and geo_points_lonlat),
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
