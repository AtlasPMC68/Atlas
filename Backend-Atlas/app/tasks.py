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
    map_id: str,
    pixel_points: list | None = None,
    geo_points_lonlat: list | None = None,
    legend_bounds: dict | None = None,
    enable_color_extraction: bool = True,
    enable_shapes_extraction: bool = False,
    enable_text_extraction: bool = False,
    is_test: bool = False,
    test_case: str | None = None,
):
    # Only parse DB UUID when we will persist.
    map_uuid: UUID | None = None

    if not is_test:
        try:
            map_uuid = UUID(map_id)
        except (ValueError, AttributeError) as e:
            raise ValueError(
                f"Invalid map_id for non-test extraction: {map_id!r}"
            ) from e

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
                            "start_date": "0-01-01",
                            "end_date": "5000-01-01",
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

                    # In test mode, skip persisting city features to the database.
                    if not is_test:
                        try:
                            asyncio.run(
                                persist_city_feature(map_uuid, city_feature_collection)
                            )
                        except Exception as e:
                            logger.error(f"Failed to persist city token '{tok}': {e}")

            except Exception as e:
                logger.error(f"City detection failed: {e}")

        else:
            text_regions = None

        # TODO : Amener ca dans la fonction de detection de texte ===========================================================

        # Step 4: Color Extraction (conditionally enabled)
        zones_features: list[dict[str, Any]] | None = None
        if enable_color_extraction:
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": 4,
                    "total": nb_task,
                    "status": "Extracting colors from image",
                },
            )

            color_result = extract_colors(tmp_file_path)
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
                    zones_features = georef_features
                    if not is_test:
                        asyncio.run(persist_features(map_uuid, georef_features))

                except Exception as e:
                    logger.error(
                        f"SIFT georeferencing step failed for map {map_id}: {e}",
                        exc_info=True,
                    )
            elif normalized_features:
                zones_features = normalized_features
                if not is_test:
                    asyncio.run(persist_features(map_uuid, normalized_features))
        else:
            logger.info("[DEBUG] Color extraction disabled - skipping")
            color_result = {"colors_detected": 0}

        # Step 5: Shapes Extraction (conditionally enabled)
        if enable_shapes_extraction:
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": 5,
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
                    if not is_test:
                        asyncio.run(persist_features(map_uuid, georef_shape_features))
                except Exception as e:
                    logger.error(
                        f"SIFT georeferencing step failed for shapes {map_id}: {e}",
                        exc_info=True,
                    )
            elif shape_normalized_features:
                if not is_test:
                    asyncio.run(persist_features(map_uuid, shape_normalized_features))
        else:
            logger.info("[DEBUG] Shapes extraction disabled - skipping")
            shapes_result = {}

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

        # In test mode, persist the image and zones GeoJSON to files under tests/assets
        image_output_path = ""
        zones_output_path = ""
        image_url = ""
        zones_url = ""
        if is_test and (test_case or "").strip():
            try:
                safe_case = (test_case or "").strip()

                os.makedirs(MAPS_DIR, exist_ok=True)

                case_dir = os.path.join(TEST_CASES_DIR, map_id)
                os.makedirs(case_dir, exist_ok=True)

                # Prefer an existing tracked map image if present, to avoid rewriting
                # bytes on every test run (cv2.imwrite can change encoding/metadata).
                existing_map_path: str | None = None
                try:
                    for existing in os.listdir(MAPS_DIR):
                        stem, _e = os.path.splitext(existing)
                        if stem == map_id:
                            existing_map_path = os.path.join(MAPS_DIR, existing)
                            break
                except OSError:
                    existing_map_path = None

                if existing_map_path and os.path.exists(existing_map_path):
                    image_output_path = existing_map_path
                    ext = os.path.splitext(existing_map_path)[1] or ".png"
                else:
                    # Save the original image under a stable name based on map_id
                    ext = os.path.splitext(filename)[1] or ".png"
                    image_output_path = os.path.join(MAPS_DIR, f"{map_id}{ext}")

                    # image was loaded earlier with cv2.imread
                    cv2.imwrite(image_output_path, image)

                # Save zones as a single FeatureCollection if available
                all_features: list[dict[str, Any]] = []
                if zones_features:
                    for fc in zones_features:
                        all_features.extend(fc.get("features", []))

                zones_geojson = {
                    "type": "FeatureCollection",
                    "features": all_features,
                }
                # tests/assets/georef/test_cases/<map_id>/<case_id>/zones.geojson
                nested_case_dir = os.path.join(case_dir, safe_case)
                os.makedirs(nested_case_dir, exist_ok=True)
                zones_output_path = os.path.join(nested_case_dir, "zones.geojson")
                with open(zones_output_path, "w", encoding="utf-8") as f:
                    json.dump(zones_geojson, f, indent=2, ensure_ascii=False)

                # Build HTTP URLs corresponding to the StaticFiles mount (/dev-test)
                image_url = f"/dev-test/maps/{map_id}{ext}"
                zones_url = f"/dev-test/test_cases/{map_id}/{safe_case}/zones.geojson"

                logger.info(
                    f"[TEST] Saved test image to {image_output_path} and zones to {zones_output_path}"
                )
            except Exception as e:
                logger.error(f"[TEST] Failed to save test assets for {filename}: {e}")

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
            # "extracted_text": lines,
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
            "is_test": is_test,
            "test_assets": {
                "image_path": image_output_path,
                "zones_path": zones_output_path,
                "image_url": image_url,
                "zones_url": zones_url,
            }
            if is_test
            else {},
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


# TODO : Remove type Any
async def persist_features(map_id: UUID, normalized_features: List[dict[str, Any]]):
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
                        is_feature_collection=False,
                        data=feature_data,
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to persist individual feature for map {map_id}: {str(e)}"
                    )


async def persist_city_feature(map_id: UUID, feature: dict[str, Any]):
    async with AsyncSessionLocal() as db:
        try:
            await insert_feature_in_db(
                db=db,
                map_id=map_id,
                is_feature_collection=False,
                data=feature,
            )
        except Exception as e:
            logger.error(f"Failed to persist city feature for map {map_id}: {str(e)}")
