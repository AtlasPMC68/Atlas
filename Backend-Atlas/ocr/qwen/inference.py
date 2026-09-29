import os
import json
import torch
import logging
from typing import Any
from PIL import Image
from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration
from transformers.utils import logging as hf_transformers_logging
from merge import _sanitize_detection_for_prompt

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
        "torch_dtype": torch.float32,
        "device": "cpu",
        "max_new_tokens": MAX_NEW_TOKENS,
        "max_image_pixels": MAX_IMAGE_PIXELS,
    }


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
        #f'The full image context: "{context_line}"'
        "Rules:\n"
        "- Do word corrections only when visually supported by the image.\n"
        "- Fix character-level errors: wrong letters, missing accents, noise artifacts (e.g. </s>, trailing dots).\n"
        #"- Use the image context as a hint, to contextualize and theme the corrections\n"
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
    return result


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


def save_result(image_path: str, output_path: str, result: dict[str, Any]) -> None:
    """Save cleaned Qwen results as JSON; optional preview rendering is disabled."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved: {output_path}")
