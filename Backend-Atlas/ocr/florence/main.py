import os
import time
import gc
from typing import Dict, List, Tuple

import torch
import numpy as np
import preprocessing as preprocess
import output as out
from PIL import Image
from transformers import AutoProcessor, AutoModelForCausalLM

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = os.path.join(BASE_DIR, "models")

MODEL_ID = "microsoft/Florence-2-large"
INPUT_DIR = os.environ.get("INPUT_DIR", "/data/input")
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
MAX_NEW_TOKENS = 4096
TILE_SIZE = 1024
TILE_OVERLAP = 64

# Florence-2 uses task tokens instead of instruction
OCR_TASK = "<OCR_WITH_REGION>"


def get_runtime_config() -> Dict:
    """CPU mode for model."""
    return {
        "model_id": MODEL_ID,
        "torch_dtype": torch.bfloat16,
        "device": "cpu",
        "max_new_tokens": MAX_NEW_TOKENS,
    }


def list_input_images(input_dir: str) -> List[str]:
    if not os.path.isdir(input_dir):
        return []
    files = []
    for name in sorted(os.listdir(input_dir)):
        if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
            files.append(os.path.join(input_dir, name))
    return files


def manually_preprocess_image(image_path: str) -> Image.Image:
    """Stage 2: apply lightweight manual preprocessing before inference."""
    img = preprocess.read_image(image_path)
    img = preprocess.bilateral_denoise(img, sigma_color=0.03, sigma_spatial=8)
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))


def load_model_and_processor(config: Dict):
    print("Loading model...")
    model = AutoModelForCausalLM.from_pretrained(
        config["model_id"],
        torch_dtype=config["torch_dtype"],
        trust_remote_code=True,
        attn_implementation="eager",
    ).to(config["device"])
    processor = AutoProcessor.from_pretrained(config["model_id"], trust_remote_code=True)
    print("Model ready.")
    return model, processor


def run_inference(model, processor, image: Image.Image, task_prompt: str, config: Dict) -> Dict:
    """
    Run Florence-2 inference for the given task token.
    Returns the post-processed structured dict (e.g. {'<OCR_WITH_REGION>': {...}}).
    """
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


def tile_image(
    image: Image.Image, tile_size: int = TILE_SIZE, overlap: int = TILE_OVERLAP
) -> List[Tuple[Image.Image, Tuple[int, int, int, int]]]:
    """
    Split image into overlapping tiles.
    Returns list of (tile_image, (x1, y1, x2, y2)).
    """
    w, h = image.size
    tiles = []
    y = 0
    while y < h:
        x = 0
        while x < w:
            x2 = min(x + tile_size, w)
            y2 = min(y + tile_size, h)
            tiles.append((image.crop((x, y, x2, y2)), (x, y, x2, y2)))
            if x2 == w:
                break
            x += tile_size - overlap
        if y2 == h:
            break
        y += tile_size - overlap
    return tiles

def get_image_context(model, processor, image, config):
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
    return context_text

def get_context_config() -> Dict:
    """Config for Florence context generation."""
    return {
        "model_id": MODEL_ID,
        "torch_dtype": torch.bfloat16,
        "device": "cpu",
        "max_new_tokens": 256,  # Shorter output for context
    }

def run_pipeline(model, processor, image_path: str, config: Dict) -> Dict:
    """Pipeline for running Florence-2 OCR on a single image path."""
    
    preprocessed = manually_preprocess_image(image_path)

    context = get_image_context(model, processor, preprocessed, get_context_config())
    print(context)
    
    # Cut tiles from image if exceeds max pixels, otherwise run on full image.
    tiles = tile_image(preprocessed)
    all_detections = []

    for i, (tile, (x1, y1, x2, y2)) in enumerate(tiles):
        print(f"  Tile {i + 1}/{len(tiles)} ({x1},{y1})-({x2},{y2})")
        result = run_inference(model, processor, tile, OCR_TASK, config)
        ocr_data = result.get(OCR_TASK, {})
        quad_boxes = ocr_data.get("quad_boxes", [])
        labels = ocr_data.get("labels", [])

        for quad, text in zip(quad_boxes, labels):
            bbox = out.quad_to_bbox_xyxy(quad)
            # Offset tile-local coords to full-image space
            bbox = [bbox[0] + x1, bbox[1] + y1, bbox[2] + x1, bbox[3] + y1]
            offset_quad = [quad[i] + (x1 if i % 2 == 0 else y1) for i in range(len(quad))]
            all_detections.append({"text": text, "bbox_xyxy": bbox, "quad": offset_quad})

    all_detections = out.merge_related_detections(all_detections)
    all_detections = out.deduplicate_detections(detections=all_detections, containment_threshold=0.85)

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
        print(f"No supported images found in '{INPUT_DIR}'.")
        return

    for image_path in images:
        print(f"Processing: {image_path}")
        parsed = run_pipeline(model, processor, image_path, config)
        out.save_result(image_path, parsed)

    print(f"Total time: {time.time() - start:.2f}s")


if __name__ == "__main__":
    main()
