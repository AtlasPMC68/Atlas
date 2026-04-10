import os
import json
import cv2
import torch
import logging
import unicodedata
from typing import Any
from PIL import Image
from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration
from transformers.utils import logging as hf_transformers_logging

logger = logging.getLogger(__name__)
hf_transformers_logging.disable_progress_bar()

MODEL_ID = "Qwen/Qwen3.5-4B"
MODELS_ROOT_DIR = os.getenv("MODELS_ROOT_DIR", "/app/models")
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
MAX_NEW_TOKENS = 512
MAX_IMAGE_PIXELS = 2560 * 2560
MAX_PROMPT_DETECTIONS = 160
ASSISTANT_JSON_PREFILL = '{"detections":['
CROP_PADDING = 15
MAX_NEW_TOKENS_SINGLE = 32
MERGE_MAX_VERTICAL_DISTANCE_PX = 15
MERGE_MAX_HORIZONTAL_DISTANCE_PX = 15


def get_runtime_config() -> dict[str, Any]:
    """Return model/runtime settings used by the Qwen OCR pipeline."""
    return {
        "model_id": MODEL_ID,
        "torch_dtype": torch.float32,
        "device": "cpu",
        "max_new_tokens": MAX_NEW_TOKENS,
        "max_image_pixels": MAX_IMAGE_PIXELS,
    }


def _sanitize_detection_for_prompt(det: Any) -> dict[str, Any] | None:
    """Normalize one detection to a minimal {text, bbox_xyxy} structure."""
    if not isinstance(det, dict):
        return None
    text = str(det.get("text", "")).strip()
    bbox = det.get("bbox_xyxy", [])
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
    except (TypeError, ValueError):
        return None
    return {"text": text, "bbox_xyxy": [x1, y1, x2, y2]}


def _crop_detection(
    image: Image.Image,
    bbox_xyxy: list[int],
    padding: int = CROP_PADDING,
) -> Image.Image:
    """Crop image around a detection bbox with padding, clamped to image bounds."""
    iw, ih = image.size
    x1, y1, x2, y2 = [int(v) for v in bbox_xyxy]
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(iw, x2 + padding)
    y2 = min(ih, y2 + padding)
    if x2 <= x1 or y2 <= y1:
        return image
    return image.crop((x1, y1, x2, y2))


def _build_single_det_prompt(
        text: str, 
        context: str = ""
    ) -> str:
    """Prompt for correcting a single OCR detection from a cropped image."""
    short_context = " ".join(str(context).split())[:180]
    context_line = f"Context hint of the whole image: {short_context}\n" if short_context else ""
    return (
        "You are correcting character-level OCR errors in a historical map label.\n"
        "The image may show nearby text: focus only on the region matching the OCR input.\n"
        f'The OCR system produced: "{text}"\n'
        f"{context_line}"
        "Rules:\n"
        "- Fix character-level errors: wrong letters, missing accents, noise artifacts (e.g. </s>).\n"
        "- Use the image context as a hint, to contextualize and theme the corrections\n"
        "- You can modify but try to follow the context and visible text closely.\n"
        "Respond with ONLY the corrected text. No explanation."
    )


def _build_cleaning_prompt(
    detections: list[dict[str, Any]] | None,
    context: str = "",
) -> str:
    """Build a JSON-constrained cleaning prompt for batched OCR detections."""
    cleaned = []
    for det in detections or []:
        compact = _sanitize_detection_for_prompt(det)
        if compact is not None:
            cleaned.append(compact)

    # Put an artificially high limit on the number of detection.
    # It is unlikely that a map would have more than 75 text regions.
    cleaned = cleaned[:75]
    packed_detections = json.dumps(
        [d["text"] for d in cleaned], ensure_ascii=False, separators=(",", ":")
    )
    short_context = " ".join(str(context).split())[:180]
    context_line = f"Context hint (may be imperfect): {short_context}\n" if short_context else ""

    return (
        "Task: repair OCR detections for this historical map image.\n"
        "Use the image to correct obvious OCR errors in the provided detections.\n"
        "Rules:\n"
        "- Return JSON only (no markdown, no explanation).\n"
        "- Output must start with {\"detections\": and follow this schema:\n"
        '{"detections":[{"text":"string","bbox_xyxy":[int,int,int,int]}]}\n'
        "- Keep one object per text region.\n"
        "- Keep bbox unchanged unless clearly wrong.\n"
        "- Preserve visible language/script and spelling exactly as shown (including accents/case).\n"
        "- Use context only as a weak hint; if context conflicts with visible text, trust the image.\n"
        "- Fix OCR confusions only when visually clear.\n"
        "- Do not invent new places or words not visible in the image.\n"
        "- Remove stray markup/noise tokens (ex: </s>).\n"
        "- Remove obvious garbage/unreadable detections.\n"
        f"{context_line}"
        f"Input detections: {packed_detections}\n"
    )



def _build_ocr_messages(image: Image.Image, prompt: str, processor: Any) -> Any:
    """Build chat-formatted multimodal inputs for model.generate()."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt},
            ],
        }
        ,
        {
            "role": "assistant",
            "content": ASSISTANT_JSON_PREFILL,
        }
    ]
    text_prompt = processor.apply_chat_template(
        messages,
        tokenize=False,
        continue_final_message=True,
    )
    return processor(
        text=[text_prompt],
        images=[image],
        padding=True,
        return_tensors="pt",
    )


def load_model_and_processor(
    config: dict[str, Any],
) -> tuple[Qwen3_5ForConditionalGeneration, AutoProcessor]:
    """Load and configure the Qwen model and processor from the local HF cache only."""
    logger.info(f"Loading Qwen model {config['model_id']} from local cache under {MODELS_ROOT_DIR}")

    model = Qwen3_5ForConditionalGeneration.from_pretrained(
        config["model_id"],
        torch_dtype=config["torch_dtype"],
        cache_dir=MODELS_ROOT_DIR,
        local_files_only=True,
    ).to(config["device"])

    processor = AutoProcessor.from_pretrained(
        config["model_id"],
        cache_dir=MODELS_ROOT_DIR,
        local_files_only=True,
    )

    # Prevent repeated generate() warnings about pad_token_id fallback.
    eos_token_id = getattr(getattr(processor, "tokenizer", None), "eos_token_id", None)
    if eos_token_id is not None:
        model.config.pad_token_id = eos_token_id
        if getattr(model, "generation_config", None) is not None:
            model.generation_config.pad_token_id = eos_token_id

    logger.debug("Qwen 3.5 model ready.")
    return model, processor


def _run_inference(
    model: Qwen3_5ForConditionalGeneration,
    processor: Any,
    image: Image.Image,
    prompt: str,
    config: dict[str, Any],
    skip_special_tokens: bool = True,
) -> str:
    """Run one model pass for a full-image JSON-cleaning prompt."""

    inputs = _build_ocr_messages(image, prompt, processor)
    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=config["max_new_tokens"],
            do_sample=True,
            num_beams=1,
            pad_token_id=getattr(model.generation_config, "pad_token_id", None),
        )
    trimmed_ids = [out[len(inp):] for inp, out in zip(inputs.input_ids, output_ids)]
    decoded = processor.batch_decode(
        trimmed_ids,
        skip_special_tokens=skip_special_tokens,
        clean_up_tokenization_spaces=False,
    )[0]

    stripped = decoded.lstrip()
    if stripped.startswith('{"detections"'):
        return decoded
    return ASSISTANT_JSON_PREFILL + decoded

    
def _run_single_det_inference(
    model: Qwen3_5ForConditionalGeneration,
    processor: Any,
    crop: Image.Image,
    text: str,
    config: dict[str, Any],
    context: str = "",
) -> str:
    """Run Qwen on one cropped detection image. Returns corrected text string."""
    prompt = _build_single_det_prompt(text, context)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": crop},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    text_input = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    inputs = processor(
        text=[text_input],
        images=[crop],
        padding=True,
        return_tensors="pt",
    )
    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS_SINGLE,
            do_sample=False,
            pad_token_id=getattr(model.generation_config, "pad_token_id", None),
        )
    trimmed = [out[len(inp):] for inp, out in zip(inputs.input_ids, output_ids)]
    result = processor.batch_decode(
        trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True,
    )[0].strip()
    return result or text


def run_per_detection(
    model: Qwen3_5ForConditionalGeneration,
    processor: Any,
    image: Image.Image,
    detections: list[dict[str, Any]],
    config: dict[str, Any],
    context: str = "",
) -> list[dict[str, Any]]:
    """
    Run Qwen once per detection on a cropped image region.
    Returns list of dicts with 'text' (corrected) and 'bbox_xyxy' (unchanged).
    """
    results = []
    for det in detections:
        compact = _sanitize_detection_for_prompt(det)
        if compact is None:
            continue
        text = compact["text"]
        bbox = compact["bbox_xyxy"]
        crop = _crop_detection(image, bbox)
        corrected = _run_single_det_inference(model, processor, crop, text, config, context)
        logger.debug(f"Qwen correction input={text} output={corrected}")
        results.append({"text": corrected, "bbox_xyxy": bbox})
    return results


def _normalize_text_key(text: str) -> str:
    """Normalize text for accent/case-insensitive equality checks."""
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(no_accents.casefold().split())


def _within_merge_distance_constraints(
    first_bbox_xyxy: list[int],
    second_bbox_xyxy: list[int],
) -> bool:
    """Return True when candidate bbox is close enough to be merged with first bbox."""
    ax1, ay1, ax2, ay2 = first_bbox_xyxy
    bx1, by1, bx2, by2 = second_bbox_xyxy

    a_width = max(1, ax2 - ax1)
    a_height = max(1, ay2 - ay1)
    b_width = max(1, bx2 - bx1)
    b_height = max(1, by2 - by1)

    a_cx = (ax1 + ax2) / 2.0
    a_cy = (ay1 + ay2) / 2.0
    b_cx = (bx1 + bx2) / 2.0
    b_cy = (by1 + by2) / 2.0

    horizontal_distance = abs(a_cx - b_cx)
    vertical_distance = abs(a_cy - b_cy)

    return (
        vertical_distance <= MERGE_MAX_VERTICAL_DISTANCE_PX and
        horizontal_distance <= MERGE_MAX_HORIZONTAL_DISTANCE_PX
    )


def merge_same_text_bboxes_keep_first(
    detections: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Merge detections with the same normalized text. Has distance constraints.
    This is a post-processing step in case Qwen finds it fitting to merge two
    text detections that were kept split during pre-processing.
    
    - Compares with accent and case insensitivity.
    - Keeps the first of the compared detection text/value.
    - Expands first detection bbox to include matching duplicates.
    """
    merged = []
    text_index = {}

    for det in detections or []:
        clean = _sanitize_detection_for_prompt(det)
        if clean is None:
            continue

        key = _normalize_text_key(clean.get("text", ""))
        if not key:
            merged.append(clean)
            continue

        if key not in text_index:
            text_index[key] = len(merged)
            merged.append(clean)
            continue

        first_idx = text_index[key]
        first = merged[first_idx]

        ax1, ay1, ax2, ay2 = first["bbox_xyxy"]
        bx1, by1, bx2, by2 = clean["bbox_xyxy"]

        if not _within_merge_distance_constraints(first["bbox_xyxy"], clean["bbox_xyxy"]):
            merged.append(clean)
            continue

        first["bbox_xyxy"] = [
            min(ax1, bx1),
            min(ay1, by1),
            max(ax2, bx2),
            max(ay2, by2),
        ]

    return merged


def _extract_first_json_value(text: str) -> Any | None:
    """Extract the first decodable JSON object or array from free-form text."""
    decoder = json.JSONDecoder()
    starts = [i for i, ch in enumerate(text) if ch in "[{"]
    for start in starts:
        try:
            obj, _ = decoder.raw_decode(text[start:])
            return obj
        except json.JSONDecodeError:
            continue
    return None


def _normalize_detections(obj: Any) -> list[dict[str, Any]]:
    """Normalize parsed JSON from florence into a validated detections list."""
    if isinstance(obj, dict):
        detections = obj.get("detections", [])
    elif isinstance(obj, list):
        detections = obj
    else:
        return []

    cleaned = []
    for det in detections:
        compact = _sanitize_detection_for_prompt(det)
        if compact is not None:
            cleaned.append(compact)
    return cleaned


def _parse_json_or_empty(raw_text: str) -> list[dict[str, Any]]:
    """Parse JSON detections from model text, returning an empty list on failure."""
    raw = raw_text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()

    obj = _extract_first_json_value(raw)
    if obj is None:
        return []
    return _normalize_detections(obj)


def _save_bbox_preview_image(
    image_path: str,
    output_path: str,
    result: dict[str, Any],
) -> None:
    """Optional helper to render detections on the source image and save a -bbx preview."""
    img = cv2.imread(image_path)
    ext = os.path.splitext(image_path)[1]
    for det in result.get("detections", []):
        bbox = det.get("bbox_xyxy", [])
        if len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 1)
            label_x, label_y = x1, max(y1 - 4, 0)
        else:
            continue
        cv2.putText(
            img,
            det["text"],
            (label_x, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (0, 0, 255),
            1,
        )
    bbx_path = os.path.splitext(output_path)[0] + f"-bbx{ext}"
    cv2.imwrite(bbx_path, img)


def save_result(image_path: str, output_path: str, result: dict[str, Any]) -> None:
    """Save cleaned Qwen results as JSON; optional preview rendering is disabled."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved: {output_path}")

    # _save_bbox_preview_image(image_path, output_path, result)


