import asyncio
import json
import logging
import os
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
from app.utils.text_extraction import extract_text, geolocate_cities_and_leftover_text

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
):
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
                "status": "Extracting text with OCR pipeline",
            },
        )

        if enable_text_extraction:
            extracted_text, text_regions = extract_text(
                map_id=map_id,
                filename=filename,
                file_content=file_content,
                celery_app=celery_app,
            )

            try:
                geolocate_cities_and_leftover_text(
                    extracted_text=extracted_text,
                    project_id=project_id,
                    map_id=map_id,
                    pixel_points=pixel_points,
                    geo_points_lonlat=geo_points_lonlat,
                    persist_city_feature_fn=persist_city_feature,
                    persist_features_fn=persist_features,
                )

            except Exception as e:
                logger.error(f"City detection failed: {e}")

        else:
            extracted_text = []
            text_regions = None

        # Step 4: Shapes Extraction (conditionally enabled)
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
                        persist_features(project_id, map_id, georef_shape_features)
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
                    georef_features = georeference_features_with_sift_points(
                        pixel_features,
                        pixel_points,
                        geo_points_lonlat,
                        snap_to_coastline=ENABLE_COASTLINE_SNAPPING,
                    )
                    asyncio.run(persist_features(project_id, map_id, georef_features))

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

            exported_lines = []
            for idx, block in enumerate(extracted_text, start=1):
                if not isinstance(block, dict):
                    continue
                text_value = str(block.get("text", ""))
                bbox_value = block.get("bbox")
                # Use JSON-escaped text so embedded newlines are preserved as "\\n".
                text_escaped = json.dumps(text_value, ensure_ascii=False)
                bbox_serialized = json.dumps(bbox_value, ensure_ascii=False)
                exported_lines.append(f"--- detection {idx} ---")
                exported_lines.append(f"bbox: {bbox_serialized}")
                exported_lines.append(f"text: {text_escaped}")

            full_text = "\n".join(exported_lines)
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
        }

        logger.info(
            "Map processing completed for %s: %s text detections extracted",
            filename,
            len(extracted_text),
        )

        return result

    except Exception as e:
        if "tmp_file_path" in locals():
            try:
                os.unlink(tmp_file_path)
            except:
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
