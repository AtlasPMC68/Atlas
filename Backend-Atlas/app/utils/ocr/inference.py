import os
import logging

import cv2
import numpy as np
from paddleocr import TextDetection, TextRecognition

from app.utils.ocr import OCR_DET_MODEL, OCR_REC_MODEL
from app.utils.ocr import preprocessing as pp

logger = logging.getLogger(__name__)

# A box this much taller than wide is read as vertical text
VERTICAL_RATIO = 1.5
REC_BATCH_SIZE = 32
OCR_CPU_THREADS = max(1, min(int(os.environ.get("OCR_CPU_THREADS", "4")), os.cpu_count() or 1))

# Keep the models loaded in memory between each uses
_CACHED_DETECTOR: TextDetection | None = None
_CACHED_RECOGNIZER: TextRecognition | None = None


def initialize_models() -> tuple[TextDetection, TextRecognition]:
    """Load the PP-OCRv5 text detection and recognition models."""
    logger.debug("Initializing PaddleOCR models from %s", os.environ.get("PADDLE_PDX_CACHE_HOME"))

    # Paddle's default of 960 px loses the small labels of big maps
    detector = TextDetection(
        model_name=OCR_DET_MODEL,
        limit_type="max",
        limit_side_len=pp.MAX_IMAGE_SIDE,
        cpu_threads=OCR_CPU_THREADS,
    )
    recognizer = TextRecognition(model_name=OCR_REC_MODEL, cpu_threads=OCR_CPU_THREADS)

    logger.debug("PaddleOCR models initialized.")
    return detector, recognizer


def get_models() -> tuple[TextDetection, TextRecognition]:
    """PaddleOCR detection and recognition models singletons"""
    global _CACHED_DETECTOR, _CACHED_RECOGNIZER
    if _CACHED_DETECTOR is None:
        _CACHED_DETECTOR, _CACHED_RECOGNIZER = initialize_models()
    return _CACHED_DETECTOR, _CACHED_RECOGNIZER


def _detect_text_boxes(detector: TextDetection, image: np.ndarray) -> list:
    """Find every text box of an RGB image, as quads of 4 [x, y] points (tl, tr, br, bl)."""
    prediction = next(iter(detector.predict(input=cv2.cvtColor(image, cv2.COLOR_RGB2BGR))))
    return [np.asarray(poly, dtype=float).reshape(4, 2).tolist() for poly in prediction["dt_polys"]]


def _crop_variants(crop: np.ndarray) -> list[np.ndarray]:
    """
    Every version of a text crop given to the recognizer. Scan quality varies too
    much between maps for a single version to work everywhere.
    """
    h, w = crop.shape[:2]
    if h > w * VERTICAL_RATIO:
        variants = []

        # Vertical text is processed twice since we need to find the right orientation.
        # Therefore, less variants are offered because we duplicate each one with a [-90,90] rotation
        for img in (cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE), cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)):
            c = pp.Crop(img)
            variants.extend([
                img,
                c.enhance_contrast(pp.NORMAL_CONTRAST).img,
                c.denoise(pp.LIGHT_DENOISE).enhance_contrast(pp.NORMAL_CONTRAST).binarize().img,
            ])
        return variants

    # For the majority of the text boxes, we return a multitude of variants
    c = pp.Crop(crop)
    return [
        crop,
        c.enhance_contrast(pp.LIGHT_CONTRAST).img,
        c.enhance_contrast(pp.NORMAL_CONTRAST).img,
        c.denoise(pp.STRONG_DENOISE).enhance_contrast(pp.STRONG_CONTRAST).img,
        c.denoise(pp.LIGHT_DENOISE).enhance_contrast(pp.NORMAL_CONTRAST).binarize().img,
    ]


def _read_text_boxes(recognizer: TextRecognition, image: np.ndarray, quads: list) -> list[tuple[str, float]]:
    """
    Read the text inside each quad of an RGB image, keeping the most confident
    reading of its variants.

    Returns: one (text, score) per quad, ("", 0.0) for boxes too small to crop
    """
    owners = []
    crops = []

    # Create variants of the same cropped text box, then flatten into
    # a crops array which remember a variant's original crop
    for idx, quad in enumerate(quads):
        crop = pp.crop_quad(image, quad)
        if crop is None:
            continue
        for variant in _crop_variants(crop):
            owners.append(idx)
            # Paddle model requires BGR
            crops.append(cv2.cvtColor(variant, cv2.COLOR_RGB2BGR))

    # One empty reading per quad, since we need a starting base of comparison
    readings = [("", 0.0) for _ in quads]

    # Nothing to read, skip the recognizer
    if not crops:
        return readings

    # Batch read the array. Keep only the biggest confidence score for each crop
    for idx, prediction in zip(owners, recognizer.predict(input=crops, batch_size=REC_BATCH_SIZE)):
        score = float(prediction["rec_score"])
        if score > readings[idx][1]:
            readings[idx] = (str(prediction["rec_text"]).strip(), score)
    return readings


def run_ocr(detector: TextDetection, recognizer: TextRecognition, original: np.ndarray) -> list:
    """
    Run the OCR pipeline on one RGB image.
    Boxes the recognizer could not read (text "") are dropped.
    """
    # Detect and read on the upscaled image: its crops read the letters at the box
    # edges better (scripts/ocr_compare_read_source.py)
    upscaled, scale_factor = pp.adaptive_upscaling(original)
    upscaled_quads = _detect_text_boxes(detector, upscaled)
    logger.debug(f"{len(upscaled_quads)} text boxes detected")
    readings = _read_text_boxes(recognizer, upscaled, upscaled_quads)

    # Text boxes are returned in the coordinates of the original image
    quads = pp.downscale_quads(upscaled_quads, scale_factor)
    return [{"text": text, "score": score, "quad": quad} for quad, (text, score) in zip(quads, readings) if text]
