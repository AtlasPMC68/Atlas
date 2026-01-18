from uuid import UUID
from celery import current_task
from .celery_app import celery_app
import time
import logging
import pytesseract
from PIL import Image
import os
import tempfile
from typing import BinaryIO
from datetime import datetime
from PIL import Image, ImageEnhance 
from app.utils.color_extraction import extract_colors
from app.services.features import create_feature_in_db
from app.database.session import get_async_session  # whatever your factory is called
import asyncio


logger = logging.getLogger(__name__)

nb_task = 5

@celery_app.task(bind=True)
def test_task(self, name: str = "World"):
    """simple test task"""
    logger.info(f"Starting test task for {name}")
    
    for i in range(5):
        time.sleep(1)
        self.update_state(
            state="PROGRESS",
            meta={"current": i + 1, "total": nb_task , "status": f"Processing step {i + 1}"}
        )
    
    result = f"Hello {name}! Task completed successfully."
    logger.info(f"Test task completed: {result}")
    return result

@celery_app.task(bind=True)
def process_map_extraction(self, filename: str, file_content: bytes, map_id: UUID):
    """Text extraction with TesseractOCR"""
    logger.info(f"Starting map processing for {filename}")

    try:
        # Step 1: temp save
        self.update_state(
            state="PROGRESS",
            meta={"current": 1, "total": nb_task , "status": "Saving uploaded file"}
        )
        logger.info("Before sleep")
        time.sleep(2)
        logger.info("afternoon")
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name

        # Step 2: opening the picture
        self.update_state(
            state="PROGRESS", 
            meta={"current": 2, "total": nb_task , "status": "Loading and validating image"}
        )
        time.sleep(2)

        image = Image.open(tmp_file_path)
        logger.info(f"Image loaded: {image.size}, mode: {image.mode}")

        image = image.convert("L")  # Convert in grey tone

        enhancer = ImageEnhance.Contrast(image)  
        image = enhancer.enhance(2.0)

        # pixels < 140 -> black, >= 140 -> white
        image = image.point(lambda x: 0 if x < 140 else 255, '1')

        # Step 3: Extraction OCR
        self.update_state(
            state="PROGRESS",
            meta={"current": 3, "total": nb_task , "status": "Extracting text with TesseractOCR"}
        )
        time.sleep(2)
        custom_config = r'--oem 3 --psm 6'
        extracted_text = pytesseract.image_to_string(image, config=custom_config)

        # Step 4: Color Extraction
        self.update_state(
            state="PROGRESS",
            meta={"current": 4, "total": nb_task , "status": "Extracting colors from image"}
        )
        time.sleep(2)

        color_result = extract_colors(tmp_file_path)
        normalized_features = color_result["normalized_features"]
        async def persist_features():
            async with get_async_session() as db:
                for feature in normalized_features:
                    await create_feature_in_db(
                        db=db,
                        map_id=map_id,
                        is_feature_collection=True,
                        data=feature,
                    )

        asyncio.run(persist_features())
        logger.info(f"[DEBUG] Résultat color_extraction : {color_result['colors_detected']}")

        # Step 5: Cleanning
        self.update_state(
            state="PROGRESS",
            meta={"current": 5, "total": nb_task , "status": "Cleaning up and finalizing"}
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
        output_filename = f"{base_name}_{timestamp}.txt"
        output_path = os.path.join(output_dir, output_filename)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"=== OCR EXTRACTION  ===\n")
                f.write(f"Source File: {filename}\n")
                f.write(f"Date extraction: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Character extract: {len(extracted_text.strip())}\n")
                f.write(f"Tesseract Configuration: {custom_config}\n")
                f.write(f"\n=== TEXTE EXTRAIT ===\n\n")
                f.write(extracted_text.strip())

            logger.info(f"Text saved to: {output_path}")

        except Exception as e:
            logger.error(f"Failed to save text file: {str(e)}")
            output_path = f"ERROR: Could not save to {output_path}"

        result = {
            "filename": filename,
            "extracted_text": extracted_text.strip(),
            "text_length": len(extracted_text.strip()),
            "output_path": output_path,
            "status": "completeded",
            "map_id": str(map_id)
        }

        logger.info(f"Map processing completed for {filename}: {len(extracted_text)} characters extracted")

        return result

    except Exception as e:
        if 'tmp_file_path' in locals():
            try:
                os.unlink(tmp_file_path)
            except:
                pass

        logger.error(f"Error processing map {filename}: {str(e)}")
        raise e