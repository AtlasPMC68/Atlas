import os
import time
import gc
import logging
from typing import Any

import torch
import numpy as np
import preprocessing as preprocess
import output as out
from PIL import Image
from transformers import AutoProcessor, AutoModelForCausalLM
from transformers.utils import logging as hf_transformers_logging

logger = logging.getLogger(__name__)
hf_transformers_logging.disable_progress_bar()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = os.path.join(BASE_DIR, "models")

MODEL_ID = "microsoft/Florence-2-large"
INPUT_DIR = os.environ.get("INPUT_DIR", "/data/input")
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
MAX_NEW_TOKENS = 4096

# Florence-2 uses task tokens instead of instruction
OCR_TASK = "<OCR_WITH_REGION>"
CONTEXT_TASK = "<MORE_DETAILED_CAPTION>"


def get_runtime_config() -> dict:
    """Return Florence runtime settings used for OCR inference."""
    return {
        "model_id": MODEL_ID,
        "torch_dtype": torch.bfloat16,
        "device": "cpu",
        "max_new_tokens": MAX_NEW_TOKENS,
    }


def list_input_images(input_dir: str) -> list[str]:
    """List supported input image files from the configured input directory."""
    if not os.path.isdir(input_dir):
        return []
    files = []
    for name in sorted(os.listdir(input_dir)):
        if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
            files.append(os.path.join(input_dir, name))
    return files


from typing import Any, Tuple


def manually_preprocess_image(image_path: str) -> Tuple[Image.Image, float]:
    """Apply preprocessing to improve OCR quality before Florence inference."""
    img = preprocess.read_image(image_path)

    h_orig, w_orig = img.shape[:2]
    img = preprocess.upscale_for_ocr(img, min_dimension=2000)
    h_new, w_new = img.shape[:2]
    scale_factor = h_new / float(h_orig) if h_orig > 0 else 1.0

    img = preprocess.bilateral_denoise(img, sigma_color=0.04, sigma_spatial=3.0)

    # Single balanced contrast enhancement pass to avoid creating halos on small fonts
    img = preprocess.enhance_contrast_and_sharpen(img, intensity=1.8)

    return Image.fromarray(img), scale_factor


def load_model_and_processor(config: dict) -> tuple:
    """Load the Florence model and processor for OCR inference."""
    logger.info(
        "Loading Florence model %s from local cache under %s",
        config["model_id"],
        os.environ.get("HF_HOME", "/app/models"),
    )
    model = AutoModelForCausalLM.from_pretrained(
        config["model_id"],
        torch_dtype=config["torch_dtype"],
        trust_remote_code=True,
        attn_implementation="eager",
        cache_dir=os.environ.get("HF_HOME", "/app/models"),
        local_files_only=True,
    ).to(config["device"])
    processor = AutoProcessor.from_pretrained(
        config["model_id"],
        trust_remote_code=True,
        cache_dir=os.environ.get("HF_HOME", "/app/models"),
        local_files_only=True,
    )

    if getattr(model, "generation_config", None) is not None:
        model.generation_config.early_stopping = False

    logger.debug("Florence model ready.")
    return model, processor


def run_inference(model: Any, processor: Any, image: Image.Image, task_prompt: str, config: dict) -> dict:
    """Run Florence inference for one task prompt and return structured output."""
    inputs = processor(text=task_prompt, images=image, return_tensors="pt")
    pixel_values = inputs["pixel_values"].to(config["torch_dtype"])
    with torch.inference_mode():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=pixel_values,
            max_new_tokens=config["max_new_tokens"],
            do_sample=False,
            num_beams=1,
        )
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
    del inputs, generated_ids
    gc.collect()
    return processor.post_process_generation(
        generated_text,
        task=task_prompt,
        image_size=(image.width, image.height),
    )


def get_image_context(model: Any, processor: Any, image: Image.Image, config: dict) -> str:
    """Generate a short geographic context summary for the map image."""
    inputs = processor(text=CONTEXT_TASK, images=image, return_tensors="pt")
    pixel_values = inputs["pixel_values"].to(config["torch_dtype"])
    with torch.inference_mode():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=pixel_values,
            max_new_tokens=256,
            do_sample=False,
            num_beams=1,
        )
    generated_ids = generated_ids[:, inputs["input_ids"].shape[1] :]
    context_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
    logger.debug(f"Generated context: {context_text}")
    return context_text


def get_context_config() -> dict:
    """Return Florence runtime settings specialized for context generation."""
    return {
        "model_id": MODEL_ID,
        "torch_dtype": torch.bfloat16,
        "device": "cpu",
        "max_new_tokens": 256,  # Shorter output for context
    }


def run_pipeline(model: Any, processor: Any, image_path: str, config: dict) -> dict:
    """Run the Florence OCR pipeline on one image and build the parsed result payload."""

    preprocessed, scale_factor = manually_preprocess_image(image_path)

    if os.environ.get("SAVE_PREPROCESSED_IMAGES", "false").lower() == "true":
        img_dir = os.path.dirname(image_path)
        prep_dir = os.path.join(img_dir, "preprocessed")
        os.makedirs(prep_dir, exist_ok=True)
        prep_path = os.path.join(prep_dir, f"prep_{os.path.basename(image_path)}")
        preprocessed.save(prep_path)
        logger.debug(f"Saved preprocessed image to {prep_path}")

    enable_context = os.environ.get("ENABLE_IMAGE_CONTEXT", "false").lower() == "true"
    if enable_context:
        context = get_image_context(model, processor, preprocessed, get_context_config())
    else:
        context = ""
    logger.debug("Running OCR on full image (tiling disabled)")

    result = run_inference(model, processor, preprocessed, OCR_TASK, config)
    ocr_data = result.get(OCR_TASK, {})
    quad_boxes = ocr_data.get("quad_boxes", [])
    labels = ocr_data.get("labels", [])

    all_detections = []
    for quad, text in zip(quad_boxes, labels):
        bbox = out.quad_to_bbox_xyxy(quad)
        all_detections.append({"text": text, "bbox_xyxy": bbox, "quad": quad})

    all_detections = out.merge_related_detections(all_detections)

    if scale_factor != 1.0:
        for det in all_detections:
            det["quad"] = [v / scale_factor for v in det["quad"]]
            det["bbox_xyxy"] = out.quad_to_bbox_xyxy(det["quad"])

    # Return original dimensions
    orig_width = int(preprocessed.width / scale_factor)
    orig_height = int(preprocessed.height / scale_factor)

    return {
        "image_size": {"width": orig_width, "height": orig_height},
        "context": context,
        "detections": all_detections,
    }


def main() -> None:
    start = time.time()
    config = get_runtime_config()
    model, processor = load_model_and_processor(config)

    images = list_input_images(INPUT_DIR)
    if not images:
        logger.error(f"No input images found in {INPUT_DIR}.")
        return

    for image_path in images:
        logger.debug(f"Processing: {image_path}")
        parsed = run_pipeline(model, processor, image_path, config)
        intermediate_path = os.path.splitext(image_path)[0] + ".json"
        out.save_result(image_path, intermediate_path, parsed)

    logger.debug(f"Total time: {time.time() - start:.2f}s")


if __name__ == "__main__":
    main()
