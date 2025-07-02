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

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def test_task(self, name: str = "World"):
    """Tâche de test simple"""
    logger.info(f"Starting test task for {name}")
    
    # Simuler du travail
    for i in range(5):
        time.sleep(1)
        # Mettre à jour le statut
        self.update_state(
            state="PROGRESS",
            meta={"current": i + 1, "total": 5, "status": f"Processing step {i + 1}"}
        )
    
    result = f"Hello {name}! Task completed successfully."
    logger.info(f"Test task completed: {result}")
    return result

@celery_app.task(bind=True)
def process_map_extraction(self, filename: str, file_content: bytes):
    """Tâche pour extraire le texte d'une carte avec TesseractOCR"""
    logger.info(f"Starting map processing for {filename}")

    try:
        # Étape 1: Sauvegarde temporaire
        self.update_state(
            state="PROGRESS",
            meta={"current": 1, "total": 4, "status": "Saving uploaded file"}
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name

        # Étape 2: Ouverture et validation de l'image
        self.update_state(
            state="PROGRESS", 
            meta={"current": 2, "total": 4, "status": "Loading and validating image"}
        )

        image = Image.open(tmp_file_path)
        logger.info(f"Image loaded: {image.size}, mode: {image.mode}")

        image = image.convert("L")  # Conversion en niveaux de gris

        enhancer = ImageEnhance.Contrast(image)  # Création d’un enhanceur de contraste
        image = enhancer.enhance(2.0)  # Augmentation du contraste (2.0 = facteur d’amélioration)

        # Binarisation : pixels < 140 -> noir, >= 140 -> blanc
        image = image.point(lambda x: 0 if x < 140 else 255, '1')

        # Étape 3: Extraction OCR
        self.update_state(
            state="PROGRESS",
            meta={"current": 3, "total": 4, "status": "Extracting text with TesseractOCR"}
        )

        custom_config = r'--oem 3 --psm 6'
        extracted_text = pytesseract.image_to_string(image, config=custom_config)

        # Étape 4: Nettoyage
        self.update_state(
            state="PROGRESS",
            meta={"current": 4, "total": 4, "status": "Cleaning up and finalizing"}
        )

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
                f.write(f"=== EXTRACTION OCR ===\n")
                f.write(f"Fichier source: {filename}\n")
                f.write(f"Date extraction: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Caractères extraits: {len(extracted_text.strip())}\n")
                f.write(f"Configuration Tesseract: {custom_config}\n")
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
            "status": "completeded"
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