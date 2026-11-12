import os
import logging

import cv2
import numpy as np
from paddleocr import TextDetection, TextRecognition

from app.utils.ocr import OCR_DET_MODEL, OCR_REC_MODEL
from app.utils.ocr import preprocessing as preprocess

logger = logging.getLogger(__name__)

# The detector shrinks images to this size on their longest side, Paddle's default
# of 960 px loses the small labels of big maps
DET_MAX_SIDE = 4000
# A box this much taller than wide is read as vertical text
VERTICAL_RATIO = 1.5
REC_BATCH_SIZE = 32

# Keep the models loaded in memory between each uses
_CACHED_DETECTOR: TextDetection | None = None
_CACHED_RECOGNIZER: TextRecognition | None = None


def initialize_models() -> tuple[TextDetection, TextRecognition]:
    """Load the PP-OCRv5 text detection and recognition models."""
    logger.debug("Initializing PaddleOCR models from %s", os.environ.get("PADDLE_PDX_CACHE_HOME"))

    detector = TextDetection(
        model_name=OCR_DET_MODEL,
        limit_type="max",
        limit_side_len=DET_MAX_SIDE,
    )
    recognizer = TextRecognition(model_name=OCR_REC_MODEL)

    logger.debug("PaddleOCR models initialized.")
    return detector, recognizer


def get_models() -> tuple[TextDetection, TextRecognition]:
    """PaddleOCR detection and recognition models singleton"""
    global _CACHED_DETECTOR, _CACHED_RECOGNIZER
    if _CACHED_DETECTOR is None:
        _CACHED_DETECTOR, _CACHED_RECOGNIZER = initialize_models()
    return _CACHED_DETECTOR, _CACHED_RECOGNIZER


def detect_text_boxes(detector: TextDetection, image: np.ndarray) -> list:
    """Find every text box of an RGB image, as quads of 4 [x, y] points (tl, tr, br, bl)."""
    prediction = next(iter(detector.predict(input=cv2.cvtColor(image, cv2.COLOR_RGB2BGR))))
    return [np.asarray(poly, dtype=float).reshape(4, 2).tolist() for poly in prediction["dt_polys"]]


def _crop_variants(crop: np.ndarray) -> list[np.ndarray]:
    """
    Every version of a text crop given to the recognizer: as-is, contrast enhanced
    and binarized, turned both ways for vertical text. Scan quality varies too much
    between maps for a single version to work everywhere.
    """
    h, w = crop.shape[:2]
    if h > w * VERTICAL_RATIO:
        orientations = [cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE), cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)]
    else:
        orientations = [crop]

    variants = []
    for img in orientations:
        variants.extend([img, preprocess.enhance_contrast(img), preprocess.binarize(img)])
    return variants


def read_text_boxes(recognizer: TextRecognition, image: np.ndarray, quads: list) -> list[tuple[str, float]]:
    """
    Read the text inside each quad of an RGB image, keeping the most confident
    reading of its variants.

    Returns: one (text, score) per quad, ("", 0.0) for boxes too small to crop
    """
    owners = []
    crops = []
    for idx, quad in enumerate(quads):
        crop = preprocess.crop_quad(image, quad)
        if crop is None:
            continue
        for variant in _crop_variants(crop):
            owners.append(idx)
            crops.append(cv2.cvtColor(variant, cv2.COLOR_RGB2BGR))

    readings = [("", 0.0) for _ in quads]
    if not crops:
        return readings

    for idx, prediction in zip(owners, recognizer.predict(input=crops, batch_size=REC_BATCH_SIZE)):
        score = float(prediction["rec_score"])
        if score > readings[idx][1]:
            readings[idx] = (str(prediction["rec_text"]).strip(), score)
    return readings


def _adaptive_preprocess(img: np.ndarray) -> tuple[np.ndarray, float]:
    """
    Upscale small maps to 1000-2000 px so their small labels are big enough for
    the detector. Large maps are left as is.

    Returns: (upscaled image, scale_factor)
    """
    h_orig, w_orig = img.shape[:2]

    target_dim = max(1000, min(2000, int(max(h_orig, w_orig) * 1.75)))
    upscaled = preprocess.upscale_for_ocr(img, min_dimension=target_dim)
    scale_factor = upscaled.shape[0] / float(h_orig) if h_orig > 0 else 1.0

    return upscaled, scale_factor


def run_pipeline(detector: TextDetection, recognizer: TextRecognition, original: np.ndarray) -> dict:
    """
    Run the OCR pipeline on one RGB image.

    1. The detector finds the text boxes on the whole upscaled image. It only uses
       convolutions, so it takes any image size without tiling.
    2. Each box is cut out of the original image and read on its own.

    Every detected box is returned, even those the recognizer could not read
    (text ""): it is still text to erase from the map.
    """
    upscaled, scale_factor = _adaptive_preprocess(original)

    quads = [
        [[x / scale_factor, y / scale_factor] for x, y in quad] for quad in detect_text_boxes(detector, upscaled)
    ]
    logger.debug(f"{len(quads)} text boxes detected")

    detections = [
        {"text": text, "score": score, "quad": quad}
        for quad, (text, score) in zip(quads, read_text_boxes(recognizer, original, quads))
    ]

    return {
        "image_size": {"width": original.shape[1], "height": original.shape[0]},
        "detections": detections,
    }
