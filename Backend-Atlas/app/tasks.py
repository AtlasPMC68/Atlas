import cv2
from celery import current_task
from .celery_app import celery_app
import time
import asyncio
import logging
import os
import tempfile
from typing import Any, List
import time
import re
from datetime import datetime
from typing import Any, List
from uuid import UUID
from PIL import Image, ImageEnhance

from app.database.session import AsyncSessionLocal
from app.services.features import insert_feature_in_db
from app.utils.color_extraction import extract_colors
from app.utils.text_extraction import extract_text
from app.utils.shapes_extraction import extract_shapes
from app.utils.cities_validation import detect_cities_from_text, find_first_city

from .celery_app import celery_app

logger = logging.getLogger(__name__)

nb_task = 6


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
def process_map_extraction(self, filename: str, file_content: bytes, map_id: str):
    """"""
    logger.info(f"Starting map processing for {filename}")

    # Ensure we are working with a UUID instance inside the task
    map_uuid = UUID(map_id)

    try:
        # Step 1: temp save
        self.update_state(
            state="PROGRESS",
            meta={"current": 1, "total": nb_task, "status": "Saving uploaded file"},
        )
        logger.info("Before sleep")
        time.sleep(2)
        logger.info("afternoon")
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
        time.sleep(2)

        image = cv2.imread(tmp_file_path)
        image.flags.writeable = False # Makes image immutable
        validate_file_extension(tmp_file_path)

        # Step 3: Extraction OCR
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 3,
                "total": nb_task,
                "status": "Extracting text with EasyOCR",
            },
        )
        time.sleep(2)

        # GPU acceleration make the text extraction MUCH faster i
        extracted_text, clean_image = extract_text(image=image, languages=['en', 'fr'], gpu_acc=False)

        # TODO : Amener ca dans la fonction de detection de texte ===========================================================
        # Tokenize OCR text to single words and run city detection per token
        try:
            tokens = re.findall(r"\b[\w\-']+\b", extracted_text or "")
            for tok in tokens:
                try:
                    candidate = find_first_city(tok)
                except Exception as e:
                    logger.debug(f"find_first_city error for token '{tok}': {e}")
                    # treat as not found but persist the token
                    candidate = {"found": False, "query": tok, "name": tok, "lat": 0.0, "lon": 0.0}

                # Build feature using returned candidate; if not found, coordinates will be 0,0
                logger.info(f"City detection result for token '{tok}': {candidate}")
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
                    "geometry": {"type": "Point", "coordinates": [candidate.get("lon") or 0.0, candidate.get("lat") or 0.0]},
                }

                city_feature_collection = {
                    "type": "FeatureCollection",
                    "features": [city_feature],
                }

                try:
                    asyncio.run(persist_city_feature(map_uuid, city_feature_collection))
                    logger.info(f"Persisted city token feature: {candidate.get('name')}")
                except Exception as e:
                    logger.error(f"Failed to persist city token '{tok}': {e}")

        except Exception as e:
            logger.error(f"City detection failed: {e}")

        # TODO : Amener ca dans la fonction de detection de texte ===========================================================

        # Step 4: Color Extraction
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 4,
                "total": nb_task,
                "status": "Extracting colors from image",
            },
        )
        time.sleep(2)

        color_result = extract_colors(tmp_file_path)
        normalized_features = color_result["normalized_features"]

        asyncio.run(persist_features(map_uuid, normalized_features))
        logger.info(
            f"[DEBUG] Résultat color_extraction : {color_result['colors_detected']}"
        )

        # Step 5: Shapes Extraction
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 5,
                "total": nb_task,
                "status": "Extracting shapes from image",
            },
        )
        time.sleep(2)
        shapes_result = extract_shapes(tmp_file_path)
        logger.info(f"[DEBUG] Résultat shapes_extraction : {shapes_result}")

        # Step 6: Cleanning
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 5,
                "total": nb_task,
                "status": "Cleaning up and finalizing",
            },
        )
        time.sleep(2)
        os.unlink(tmp_file_path)

        current_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(current_dir, "extracted_texts")
        try:
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"[DEBUG] Directory created or already exists: {output_dir}")
        except Exception as e:
            logger.error(f"[ERROR] Failed to create directory {output_dir}: {e}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(filename)[0]
        output_filename = f"{timestamp}_{base_name}.txt"
        output_path = os.path.join(output_dir, output_filename)

        lines = [block[1] for block in extracted_text]
        full_text = "\n".join(lines)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"=== OCR EXTRACTION  ===\n")
                f.write(f"Source File: {filename}\n")
                f.write(f"Date extraction: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"\n=== TEXTE EXTRAIT ===\n\n")
                f.write(full_text)

            logger.info(f"Text saved to: {output_path}")

        except Exception as e:
            logger.error(f"Failed to save text file: {str(e)}")
            output_path = f"ERROR: Could not save to {output_path}"

        result = {
            "filename": filename,
            "extracted_text": lines,
            "output_path": output_path,
            "shapes_result": shapes_result,
            "color_result": color_result,
            "status": "completed",
        }

        logger.info(
            f"Map processing completed for {filename}: {len(extracted_text)} characters extracted"
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

def validate_file_extension(file_path: str) -> None:
    supported_file_ext = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp', '.ppm', '.pgm', '.pbm')
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in supported_file_ext:
        raise ValueError(f"Extension {ext} non autorisée pour le système du consortium.")

# TODO : Remove type Any
async def persist_features(map_uuid: UUID, normalized_features: List[dict[str, Any]]):
    async with AsyncSessionLocal() as db:
        for feature in normalized_features:
            try:
                await insert_feature_in_db(
                    db=db,
                    map_id=map_uuid,
                    is_feature_collection=True,
                    data=feature,
                )
            except Exception as e:
                logger.error(f"Failed to persist feature for map {map_uuid}: {str(e)}")


async def persist_city_feature(map_uuid: UUID, feature: dict[str, Any]):
    async with AsyncSessionLocal() as db:
        try:
            await insert_feature_in_db(
                db=db,
                map_id=map_uuid,
                is_feature_collection=False,
                data=feature,
            )
        except Exception as e:
            logger.error(f"Failed to persist city feature for map {map_uuid}: {str(e)}")
