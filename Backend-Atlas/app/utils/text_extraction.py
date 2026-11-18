import logging
import re
import time
from typing import Any
from uuid import UUID

from app.utils.label_merging import merge_split_labels
from app.utils.ocr import preprocessing

logger = logging.getLogger(__name__)

# Any word length equal or less than this is ignored
MAXIMAL_IGNORED_LENGTH = 1

class OcrPipelineError(RuntimeError):
    """The OCR failed: no text was read, which is not the same as a map without text."""


# fmt: off
MAP_IGNORED_WORDS = {
    "n", "s", "e", "w", "o", "ne", "nw", "no", "se", "sw", "so",
    "nord", "sud", "est", "ouest", "n.-e.", "n.-o.", "s.-e.", "s.-o.",
}
# fmt: on

_RE_LEGEND_OR_SCALE = re.compile(
    r"\b(?:légende|legende|échelle|echelle|scale)\b|"
    r"(?<![a-z])(?:km|kms|kilom[eè]tres?|kilometers?|miles?)(?![a-z])",
)


def should_ignore(text_val: str) -> bool:
    """Ground rules that tell if a text box should be
        ignored or not."""

    # Remove trailing characters and normalize lowercase
    clean: str = text_val.lower().strip(" .,;:!?()[]{}'\"")

    # Ignore if word match any in the dictionary
    if len(clean) <= MAXIMAL_IGNORED_LENGTH:
        return True

    # Remove words containing only numbers
    if clean in MAP_IGNORED_WORDS:
        return True

    # Remove any digits
    if clean and all(c.isdigit() or c.isspace() or c in ".," for c in clean):
        return True
    if _RE_LEGEND_OR_SCALE.search(clean):
        return True

    # Text boxes cannot have more than 5 words in them
    if len(clean.split()) > 5:
        return True

    return False


def ocr_blocks_to_payload(blocks: list[dict[str, Any]]) -> list[list]:
    """Convert OCR blocks to plain JSON: [[[x, y], ...], text, prob]."""
    payload = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        coords = block.get("bbox", [])
        text = block.get("text", "")
        prob = float(block.get("prob", block.get("confidence", 1.0)))
        payload.append(
            [
                [[int(round(float(p[0]))), int(round(float(p[1])))] for p in coords],
                str(text),
                prob,
            ]
        )
    return payload


def process_candidate_text(text_val: str, quad: list[list[int]]) -> dict[str, Any] | None:
    clean_text = re.sub(r"[\(\[\{]?\b(1[0-9]{3}|20[0-9]{2})\b[\)\]\}]?", "", text_val)
    # Retain newlines, but collapse spaces within each line
    clean_text = "\n".join(" ".join(line.split()) for line in clean_text.split("\n")).strip(" .,;:!?()[]{}'\"")
    if not clean_text or should_ignore(clean_text):
        return None
    return {
        "text": clean_text,
        "bbox": quad,
        "mapElementType": "ville",
    }


def _detection_quad(detection):
    """The detection's quad as 4 integer [x, y] points, None when it has none."""
    quad = detection.get("quad")
    if not isinstance(quad, list) or len(quad) != 4:
        return None
    try:
        return [[int(round(float(pt[0]))), int(round(float(pt[1])))] for pt in quad]
    except (TypeError, ValueError, IndexError):
        return None


def _filter_detections(
    detections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the OCR detections worth placing on the map, as {"text", "bbox", "mapElementType"} dicts."""
    extracted_text: list[dict[str, Any]] = []
    for detection in detections:
        if not isinstance(detection, dict):
            continue

        raw_text = str(detection.get("text", "")).strip()
        if not raw_text:
            continue

        quad = _detection_quad(detection)
        if quad is None:
            continue

        candidate_block = process_candidate_text(raw_text, quad)
        if candidate_block is not None:
            extracted_text.append(candidate_block)

    return extracted_text


def _run_ocr_pipeline(
    map_id: UUID,
    image,
) -> list[dict[str, Any]]:
    """
    Execute the PaddleOCR pipeline on an RGB image.
    Returns detections in quad box format: [{"text": str, "bbox": [[x,y], ...]}, ...]
    """
    logger.info(f"==> [OCR] PaddleOCR processing text detection and extraction for map {map_id}...")
    started = time.monotonic()
    try:
        # Imported here so only the processes running the OCR load Paddle
        from app.utils.ocr import inference

        detector, recognizer = inference.get_models()
        detections = inference.run_ocr(detector, recognizer, image)
    except Exception as exc:
        logger.exception("OCR pipeline failed for map %s: %s", map_id, exc)
        # Raised, not returned as []: an empty list is saved as "done, no
        # text", and the user cannot tell it from a map without labels.
        raise OcrPipelineError(f"OCR failed: {exc}") from exc

    logger.info(f"==> [OCR] Pipeline successfully completed for map {map_id} in {time.monotonic() - started:.1f}s!")

    # Join the boxes of labels split over several lines, then keep only the
    # readings worth placing on the map (see should_ignore)
    detections = merge_split_labels(detections)
    return _filter_detections(detections)


def extract_text(
    map_id: UUID,
    image_bytes: bytes,
) -> list[dict[str, Any]]:
    """Extract text using the in-process PaddleOCR pipeline."""
    if not image_bytes:
        return []

    try:
        image = preprocessing.decode_image(image_bytes)
    except IOError as exc:
        logger.warning(f"Could not decode the image of map {map_id}: {exc}")
        return []

    if preprocessing.exceeds_max_side(image):
        height, width = image.shape[:2]
        logger.warning(
            f"Image for map {map_id} is too large ({width}x{height} px). "
            f"Rejected to prevent an OOM crash ({preprocessing.MAX_IMAGE_SIDE} px limit on the longest side)."
        )
        return []

    logger.info(f"Starting OCR pipeline for map {map_id}")

    extracted_text = _run_ocr_pipeline(
        map_id=map_id,
        image=image,
    )
    logger.debug(f"[OCR] PaddleOCR : {len(extracted_text)} text boxes detected for map {map_id}")
    return extracted_text
