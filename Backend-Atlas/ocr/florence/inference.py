import os
import time
import gc
import logging

import torch
import numpy as np
import preprocessing as preprocess
import output as out
from PIL import Image
from transformers import AutoProcessor, AutoModelForCausalLM

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = os.path.join(BASE_DIR, "models")

MODEL_ID = "microsoft/Florence-2-large"
INPUT_DIR = os.environ.get("INPUT_DIR", "/data/input")
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
MAX_NEW_TOKENS = 4096

# Florence-2 uses task tokens instead of instruction
OCR_TASK = "<OCR_WITH_REGION>"


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


def manually_preprocess_image(image_path: str) -> Image.Image:
    """Apply lightweight preprocessing to improve OCR quality before inference."""
    img = preprocess.read_image(image_path)
    img = preprocess.bilateral_denoise(img, sigma_color=0.03, sigma_spatial=8)
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))


def load_model_and_processor(config: dict) -> tuple:
    """Load the Florence model and processor for OCR inference."""
    logger.info("Loading model...")
    model = AutoModelForCausalLM.from_pretrained(
        config["model_id"],
        torch_dtype=config["torch_dtype"],
        trust_remote_code=True,
        attn_implementation="eager",
    ).to(config["device"])
    processor = AutoProcessor.from_pretrained(config["model_id"], trust_remote_code=True)
    logger.info("Model ready.")
    return model, processor


def run_inference(
        model: object, 
        processor: object, 
        image: Image.Image, 
        task_prompt: str, 
        config: dict
    ) -> dict:
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
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    del inputs, generated_ids
    gc.collect()
    return processor.post_process_generation(
        generated_text,
        task=task_prompt,
        image_size=(image.width, image.height),
    )


def get_image_context(
        model: object, processor: object, image: Image.Image, config: dict) -> str:
    """Generate a short geographic context summary for the map image."""
    context_prompt = "\
        Describe the context of this map image. \
        Then, list the biggest and major geographical features visible in this historical map: \
        countries, regions, provinces, cities, rivers, lakes, oceans, and seas. \
        Keep it concise.\
        "
    inputs = processor(text=context_prompt, images=image, return_tensors="pt")
    pixel_values = inputs["pixel_values"].to(config["torch_dtype"])
    with torch.inference_mode():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=pixel_values,
            max_new_tokens=256,
            do_sample=False,
            num_beams=1,
        )
    context_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
    logger.info(f"Generated context: {context_text}")
    return context_text


def get_context_config() -> dict:
    """Return Florence runtime settings specialized for context generation."""
    return {
        "model_id": MODEL_ID,
        "torch_dtype": torch.bfloat16,
        "device": "cpu",
        "max_new_tokens": 256,  # Shorter output for context
    }


def run_pipeline(
        model: object, 
        processor: object, 
        image_path: str, 
        config: dict
    ) -> dict:
    """Run the Florence OCR pipeline on one image and build the parsed result payload."""

    preprocessed = manually_preprocess_image(image_path)

    context = get_image_context(model, processor, preprocessed, get_context_config())
    logger.info("Running OCR on full image (tiling disabled)")

    result = run_inference(model, processor, preprocessed, OCR_TASK, config)
    ocr_data = result.get(OCR_TASK, {})
    quad_boxes = ocr_data.get("quad_boxes", [])
    labels = ocr_data.get("labels", [])

    all_detections = []
    for quad, text in zip(quad_boxes, labels):
        bbox = out.quad_to_bbox_xyxy(quad)
        all_detections.append({"text": text, "bbox_xyxy": bbox, "quad": quad})

    all_detections = out.merge_related_detections(all_detections)

    return {
        "image_size": {"width": preprocessed.width, "height": preprocessed.height},
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
        logger.info(f"Processing: {image_path}")
        parsed = run_pipeline(model, processor, image_path, config)
        out.save_result(image_path, parsed)

    logger.info(f"Total time: {time.time() - start:.2f}s")


if __name__ == "__main__":
    main()
