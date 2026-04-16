import asyncio
import json
import logging
import os
import re
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
from app.utils.georeferencingSift import georeference_features_with_sift_points
from app.utils.shapes_extraction import extract_shapes
from app.utils.text_extraction import extract_text
from app.utils.dev_test_assets import MAPS_DIR, TEST_CASES_DIR

from .celery_app import celery_app

logger = logging.getLogger(__name__)

nb_task = 6

# TODO : maybe remove this debud parameter pour l'instant j'aimerais ca le garder tho
ENABLE_COASTLINE_SNAPPING = True


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
    map_id: str,
    pixel_points: list | None = None,
    geo_points_lonlat: list | None = None,
    legend_bounds: dict | None = None,
    enable_color_extraction: bool = True,
    enable_shapes_extraction: bool = False,
    enable_text_extraction: bool = False,
):
    try:
        map_uuid = UUID(map_id)
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid map_id: {map_id!r}") from e

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
                                project_id, map_uuid, city_feature_collection
                            )
                        )
                    except Exception as e:
                        logger.error(f"Failed to persist city token '{tok}': {e}")

            except Exception as e:
                logger.error(f"City detection failed: {e}")

        else:
            text_regions = None

        # TODO : Amener ca dans la fonction de detection de texte ===========================================================

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
                    georef_shape_features = georeference_features_with_sift_points(
                        shape_pixel_features, pixel_points, geo_points_lonlat
                    )
                    asyncio.run(
                        persist_features(project_id, map_uuid, georef_shape_features)
                    )
                except Exception as e:
                    logger.error(
                        f"SIFT georeferencing step failed for shapes {map_id}: {e}",
                        exc_info=True,
                    )
            elif shape_normalized_features:
                asyncio.run(
                    persist_features(project_id, map_uuid, shape_normalized_features)
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

            color_result = extract_colors(
                tmp_file_path,
                debug=False,
                legend_shapes=legends_shapes if legends_shapes else None,
            )
            normalized_features = color_result.get("normalized_features", [])
            pixel_features = color_result.get("pixel_features", [])

            # TODO : Rendre ca une etape pour toutes les extractions ===================================================================
            # Georeference pixel-space features if SIFT point pairs are provided
            if pixel_points and geo_points_lonlat:
                try:
                    georef_features = georeference_features_with_sift_points(
                        pixel_features,
                        pixel_points,
                        geo_points_lonlat,
                        snap_to_coastline=ENABLE_COASTLINE_SNAPPING,
                    )
                    asyncio.run(persist_features(project_id, map_uuid, georef_features))

                except Exception as e:
                    logger.error(
                        f"SIFT georeferencing step failed for map {map_id}: {e}",
                        exc_info=True,
                    )
            elif normalized_features:
                asyncio.run(persist_features(project_id, map_uuid, normalized_features))
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
):
    """Dev-test-only extraction task: no DB persistence, results saved to files,
    evaluation report written automatically at the end."""
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
        color_result = extract_colors(tmp_file_path, debug=False, legend_shapes=None)
        normalized_features = color_result.get("normalized_features", [])
        pixel_features = color_result.get("pixel_features", [])

        if pixel_points and geo_points_lonlat:
            try:
                georef_features = georeference_features_with_sift_points(
                    pixel_features,
                    pixel_points,
                    geo_points_lonlat,
                    snap_to_coastline=ENABLE_COASTLINE_SNAPPING,
                )
                all_extracted_features = georef_features
            except Exception as e:
                logger.error(
                    f"[DEV-TEST] SIFT georeferencing failed for test {test_id}: {e}",
                    exc_info=True,
                )
                all_extracted_features = normalized_features
        else:
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

        # Evaluate and persist reports automatically
        try:
            from app.utils.dev_test import evaluate_and_persist_case
            from app.utils.dev_test_assets import GEOREF_ASSETS_DIR

            evaluate_and_persist_case(
                assets_root=GEOREF_ASSETS_DIR,
                test_id=test_id,
                test_case_id=test_case,
                min_iou=None,
            )
            logger.info(
                f"[DEV-TEST] Evaluation report written for {test_id}/{test_case}"
            )
        except Exception as e:
            logger.warning(
                f"[DEV-TEST] Evaluation skipped (expected zones may be missing): {e}"
            )

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
