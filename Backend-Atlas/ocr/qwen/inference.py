import gc
import json
import logging
import os
import re
from typing import Any, cast

import torch
from merge import _sanitize_detection_for_prompt
from PIL import Image, ImageEnhance, ImageOps
from transformers import AutoProcessor, PreTrainedModel, Qwen3_5ForConditionalGeneration
from transformers.utils import logging as hf_transformers_logging

logger = logging.getLogger(__name__)
hf_transformers_logging.disable_progress_bar()

MODEL_ID = "Qwen/Qwen3.5-2B"
MODELS_ROOT_DIR = os.getenv("MODELS_ROOT_DIR", "/app/models")
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
MAX_NEW_TOKENS = 512
MAX_IMAGE_PIXELS = 2560 * 2560
CROP_PADDING = 15
MAX_NEW_TOKENS_SINGLE = 32


def get_runtime_config() -> dict[str, Any]:
    """Return model/runtime settings used by the Qwen OCR pipeline."""
    return {
        "model_id": MODEL_ID,
        "torch_dtype": torch.bfloat16,
        "device": "cpu",
        "max_new_tokens": MAX_NEW_TOKENS,
        "max_image_pixels": MAX_IMAGE_PIXELS,
    }


def _crop_detection(
    image: Image.Image,
    bbox_xyxy: list[int],
    min_dim: int = 48,
) -> Image.Image:
    """Crop image around a detection bbox with adaptive padding and resolution boost."""
    iw, ih = image.size
    x1, y1, x2, y2 = [int(v) for v in bbox_xyxy]
    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)

    # Adaptive padding: proportional to label dimensions to avoid capturing nearby clutter
    pad_x = max(6, min(25, int(bw * 0.15)))
    pad_y = max(4, min(18, int(bh * 0.25)))

    cx1 = max(0, x1 - pad_x)
    cy1 = max(0, y1 - pad_y)
    cx2 = min(iw, x2 + pad_x)
    cy2 = min(ih, y2 + pad_y)
    if cx2 <= cx1 or cy2 <= cy1:
        return image

    crop = image.crop((cx1, cy1, cx2, cy2))

    # Upscale tiny crops so vision encoder can clearly read small historical font
    cw, ch = crop.size
    if cw < min_dim or ch < min_dim:
        scale = max(min_dim / float(cw), min_dim / float(ch))
        new_w = max(min_dim, int(cw * scale))
        new_h = max(min_dim, int(ch * scale))
        crop = crop.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Gentle local contrast boost to separate dark ink from colored/dark backgrounds (blue/red)
    try:
        crop = ImageEnhance.Contrast(crop).enhance(1.25)
    except Exception:
        pass

    return crop


def _build_single_det_prompt(text: str, context: str = "") -> str:
    """Prompt for correcting a single OCR detection from a cropped image."""
    short_context = " ".join(str(context).split())[:180]
    context_line = f"Context hint of the whole image: {short_context}\n" if short_context else ""
    return (
        "You are correcting character-level OCR errors in a historical map label.\n"
        "The image may show nearby text: focus only on the region matching the OCR input.\n"
        f'The OCR system produced: "{text}"\n'
        # f'The full image context: "{context_line}"'
        "Rules:\n"
        "- Do word corrections only when visually supported by the image.\n"
        "- Fix character-level errors: wrong letters, missing accents, noise artifacts (e.g. </s>, trailing dots).\n"
        # "- Use the image context as a hint, to contextualize and theme the corrections\n"
        "- Respond with ONLY the corrected text. No explanation."
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

    if getattr(model, "generation_config", None) is not None:
        model.generation_config.early_stopping = False

    logger.debug("Qwen 3.5 model ready.")
    return model, processor


def _sanitize_generated_text(text: str) -> str:
    """Remove generation artifacts like EOS markers and trailing punctuation noise."""
    if text is None:
        return ""

    sanitized = str(text)
    for marker in ("</s>", "<|im_end|>", "<|endoftext|>"):
        sanitized = sanitized.replace(marker, " ")

    sanitized = sanitized.replace("\r\n", "\n").replace("\r", "\n")
    sanitized = sanitized.replace("\u200b", "")
    sanitized = re.sub(r"\s+", " ", sanitized)
    sanitized = sanitized.strip(" \t\n.-_:;,.!?()[]{}<>|/\\")
    sanitized = re.sub(r"(?:^|\s)[.,;:!?]+(?=\s|$)", "", sanitized)
    sanitized = re.sub(r"[\u0000-\u001F\u007F]+", "", sanitized)
    return sanitized.strip()


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
    text_input = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    inputs = processor(text=[text_input], images=[crop], padding=True, return_tensors="pt")

    # Dynamic token limit based on input length to avoid wasting CPU cycles
    words_count = max(1, len(text.split()))
    token_limit = max(8, min(24, words_count * 5))

    tokenizer = getattr(processor, "tokenizer", None)
    eos_id = getattr(tokenizer, "eos_token_id", None)
    pad_id = getattr(model.generation_config, "pad_token_id", None) or eos_id
    with torch.inference_mode():
        output_ids = cast(Any, model).generate(
            **inputs,
            max_new_tokens=token_limit,
            do_sample=False,
            pad_token_id=pad_id,
            eos_token_id=eos_id,
        )
    trimmed = [out[len(inp) :] for inp, out in zip(inputs.input_ids, output_ids)]
    result = processor.batch_decode(
        trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True,
    )[0]
    del inputs, output_ids, trimmed
    return _sanitize_generated_text(result)


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
    total_detections = len(detections)
    for idx, det in enumerate(detections):
        compact = _sanitize_detection_for_prompt(det)
        if compact is None:
            continue
        text = compact["text"]
        bbox = compact["bbox_xyxy"]

        # Skip running costly LLM inference on single punctuation or blank detections
        stripped = text.strip()
        if len(stripped) <= 1 and not stripped.isalnum():
            results.append({"text": text, "bbox_xyxy": bbox})
            continue

        crop = _crop_detection(image, bbox)
        corrected = _run_single_det_inference(model, processor, crop, text, config, context)
        logger.debug(f"Qwen correction ({idx + 1}/{total_detections}) input='{text}' output='{corrected}'")
        # Fallback to original text if Qwen returned empty
        results.append({"text": corrected or text, "bbox_xyxy": bbox})

        if idx % 8 == 0:
            gc.collect()

    gc.collect()
    return results


def save_result(image_path: str, output_path: str, result: dict[str, Any]) -> None:
    """Save cleaned Qwen results as JSON; optional preview rendering is disabled."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved: {output_path}")
