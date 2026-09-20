import os
import time
import gc
import logging
from typing import Any, Tuple

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

MODEL_ID = "microsoft/Florence-2-base"
INPUT_DIR = os.environ.get("INPUT_DIR", "/data/input")
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
MAX_NEW_TOKENS = 4096

# Florence-2 uses task tokens instead of instruction
OCR_TASK = "<OCR_WITH_REGION>"
CONTEXT_TASK = "<MORE_DETAILED_CAPTION>"


def get_runtime_config() -> dict:
    """Return Florence runtime settings used for OCR inference."""
    device = "cpu"
    return {
        "model_id": MODEL_ID,
        "torch_dtype": torch.float32 if device == "cpu" else torch.bfloat16,
        "device": device,
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
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    generated_text = generated_text.replace("</s>", "").replace("<s>", "")
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
    device = "cpu"
    return {
        "model_id": MODEL_ID,
        "torch_dtype": torch.float32 if device == "cpu" else torch.bfloat16,
        "device": device,
        "max_new_tokens": 256,
    }


def _adaptive_preprocess(image_path: str) -> Tuple[Image.Image, float, int]:
    """
    Apply preprocessing to improve OCR quality before Florence inference.

    Always applies: upscale + bilateral_denoise + contrast enhancement.
    The bilateral_denoise removes background color noise on ALL images without
    blurring text edges (data showed skipping it causes regressions on Quebec maps).

    Returns: (preprocessed PIL Image, scale_factor, longest_side of original)
    """
    img = preprocess.read_image(image_path)
    h_orig, w_orig = img.shape[:2]
    longest_side = max(h_orig, w_orig)

    # Dynamic upscale target: 1.75x but capped [1000, 2000]
    target_dim = max(1000, min(2000, int(longest_side * 1.75)))
    img = preprocess.upscale_for_ocr(img, min_dimension=target_dim)

    h_new, w_new = img.shape[:2]
    scale_factor = h_new / float(h_orig) if h_orig > 0 else 1.0

    # Always apply full pipeline: denoise removes background noise, contrast sharpens text
    img = preprocess.bilateral_denoise(img, sigma_color=0.04, sigma_spatial=3.0)
    img = preprocess.enhance_contrast_and_sharpen(img, intensity=1.8)

    return Image.fromarray(img), scale_factor, longest_side


def _generate_tiles(w: int, h: int, grid: int, overlap_pct: float = 0.10) -> list[tuple[int, int, int, int]]:
    """Generate tile coordinates for a given grid size (2 for 2x2, 3 for 3x3) with overlap."""
    tiles = []
    overlap_x = int(w * overlap_pct)
    overlap_y = int(h * overlap_pct)

    for row in range(grid):
        for col in range(grid):
            x1 = max(0, col * w // grid - (overlap_x if col > 0 else 0))
            y1 = max(0, row * h // grid - (overlap_y if row > 0 else 0))
            x2 = min(w, (col + 1) * w // grid + (overlap_x if col < grid - 1 else 0))
            y2 = min(h, (row + 1) * h // grid + (overlap_y if row < grid - 1 else 0))
            if x2 > x1 and y2 > y1:
                tiles.append((x1, y1, x2, y2))

    return tiles


def _remove_duplicate_detections(all_detections: list[dict]) -> list[dict]:
    """Remove duplicate detections where one box overlaps >60% of another (IoA dedup)."""
    import shapely.geometry

    def get_poly(d):
        quad = d.get("quad")
        if quad and len(quad) >= 8:
            return shapely.geometry.Polygon([(quad[0], quad[1]), (quad[2], quad[3]), (quad[4], quad[5]), (quad[6], quad[7])])
        b = d.get("bbox_xyxy", [0, 0, 0, 0])
        return shapely.geometry.Polygon([(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])])

    polys = []
    for d in all_detections:
        try:
            p = get_poly(d)
            if not p.is_valid:
                p = p.buffer(0)
            if p.area > 0:
                polys.append({"det": d, "poly": p, "area": p.area})
        except Exception:
            pass

    polys.sort(key=lambda x: x["area"], reverse=True)
    unique_dets = []
    unique_polys = []

    for item in polys:
        det = item["det"]
        pA = item["poly"]
        areaA = item["area"]
        is_dup = False

        for upoly, uarea in unique_polys:
            if pA.intersects(upoly):
                inter_area = pA.intersection(upoly).area
                ioa_small = inter_area / areaA
                ioa_large = inter_area / uarea
                # Only merge if the smaller box is mostly inside, AND the larger box isn't a massive hallucination (>5x size)
                if ioa_small > 0.6 and ioa_large > 0.2:
                    is_dup = True
                    break
        if not is_dup:
            unique_dets.append(det)
            unique_polys.append((pA, areaA))

    return unique_dets


def run_pipeline(model: Any, processor: Any, image_path: str, config: dict) -> dict:
    """
    Run the Florence OCR pipeline on one image with adaptive preprocessing and tiling.

    The pipeline automatically adapts to each image:
    1. Small images (<=800px): Single pass, no tiling (fast)
    2. Medium images (800-1200px): 2x2 tiling (balanced)
    3. Large/dense images (>1200px): 2x2 tiling, then check density.
       If first pass detects many labels, switch to 3x3 tiling for better coverage.
    """
    preprocessed, scale_factor, longest_side = _adaptive_preprocess(image_path)

    if os.environ.get("SAVE_PREPROCESSED_IMAGES", "false").lower() == "true":
        img_dir = os.path.dirname(image_path)
        prep_dir = os.path.join(img_dir, "preprocessed")
        os.makedirs(prep_dir, exist_ok=True)
        prep_path = os.path.join(prep_dir, f"prep_{os.path.basename(image_path)}")
        preprocessed.save(prep_path)

    enable_context = os.environ.get("ENABLE_IMAGE_CONTEXT", "false").lower() == "true"
    context = get_image_context(model, processor, preprocessed, get_context_config()) if enable_context else ""

    all_detections = []

    # Pass 1: Full image (always)
    result = run_inference(model, processor, preprocessed, OCR_TASK, config)
    ocr_data = result.get(OCR_TASK, {})
    for quad, text in zip(ocr_data.get("quad_boxes", []), ocr_data.get("labels", [])):
        all_detections.append({"text": text, "bbox_xyxy": out.quad_to_bbox_xyxy(quad), "quad": quad})

    first_pass_count = len(all_detections)
    logger.debug(f"First pass: {first_pass_count} detections on full image ({longest_side}px)")

    # Pass 2: Adaptive tiling based on image size and detection density
    if longest_side <= 800:
        # Small image: no tiling needed, single pass is enough
        logger.debug("Small image. Skipping tiling.")
        tile_grid = 0
    elif longest_side > 1200 or first_pass_count >= 15:
        # Large or dense image: use 3x3 tiling for maximum coverage
        logger.debug(f"Dense map detected ({first_pass_count} detections, {longest_side}px). Using 3x3 tiling.")
        tile_grid = 3
    else:
        # Medium image: standard 2x2 tiling
        logger.debug(f"Medium image ({first_pass_count} detections, {longest_side}px). Using 2x2 tiling.")
        tile_grid = 2

    if tile_grid > 0:
        w, h = preprocessed.width, preprocessed.height
        tiles = _generate_tiles(w, h, tile_grid, overlap_pct=0.10)

        for x1, y1, x2, y2 in tiles:
            tile_img = preprocessed.crop((x1, y1, x2, y2))
            tile_result = run_inference(model, processor, tile_img, OCR_TASK, config)
            t_data = tile_result.get(OCR_TASK, {})

            for quad, text in zip(t_data.get("quad_boxes", []), t_data.get("labels", [])):
                shifted_quad = []
                # Fix IndexError by ensuring we don't read out of bounds if len(quad) is odd
                for i in range(0, len(quad) - 1, 2):
                    shifted_quad.extend([quad[i] + x1, quad[i + 1] + y1])

                if len(shifted_quad) >= 4:
                    all_detections.append({"text": text, "bbox_xyxy": out.quad_to_bbox_xyxy(shifted_quad), "quad": shifted_quad})

    # Pass 3: Multi-angle passes for diagonal/vertical text (Rivers, Lakes)
    # Rotating the image transforms vertical/diagonal text into horizontal text, which Florence can read.
    import math

    def _map_quad_back(quad, orig_w, orig_h, new_w, new_h, angle_deg):
        rad = math.radians(angle_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        cx_orig, cy_orig = orig_w / 2.0, orig_h / 2.0
        cx_new, cy_new = new_w / 2.0, new_h / 2.0

        mapped_quad = []
        for i in range(0, len(quad) - 1, 2):
            x, y = quad[i], quad[i + 1]
            x_sh, y_sh = x - cx_new, y - cy_new
            x_orig_sh = x_sh * cos_a - y_sh * sin_a
            y_orig_sh = x_sh * sin_a + y_sh * cos_a
            mapped_quad.extend([x_orig_sh + cx_orig, y_orig_sh + cy_orig])
        return mapped_quad

    angles = [90, -45]  # 90 catches vertical text, -45 catches diagonal rivers (like St-Laurent)
    image_area = preprocessed.width * preprocessed.height

    for angle in angles:
        logger.debug(f"Running multi-angle pass: {angle} degrees")
        # Pad with white to prevent Florence-2 hallucinating coordinate tokens > 999 (IndexError) on large black regions
        rot_img = preprocessed.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC, fillcolor=(255, 255, 255))
        rot_result = run_inference(model, processor, rot_img, OCR_TASK, config)
        r_data = rot_result.get(OCR_TASK, {})

        for quad, text in zip(r_data.get("quad_boxes", []), r_data.get("labels", [])):
            if len(quad) >= 4:
                mapped_quad = _map_quad_back(quad, preprocessed.width, preprocessed.height, rot_img.width, rot_img.height, angle)

                # Use exact polygon area to reject massive hallucinations (e.g., ocean/map boundaries)
                import shapely.geometry

                try:
                    poly = shapely.geometry.Polygon([(mapped_quad[0], mapped_quad[1]), (mapped_quad[2], mapped_quad[3]), (mapped_quad[4], mapped_quad[5]), (mapped_quad[6], mapped_quad[7])])
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    if poly.area > 0.1 * image_area:
                        continue
                except Exception:
                    pass

                all_detections.append({"text": text, "bbox_xyxy": out.quad_to_bbox_xyxy(mapped_quad), "quad": mapped_quad})

    # Remove duplicates from overlapping tiles
    unique_dets = _remove_duplicate_detections(all_detections)
    all_detections = out.merge_related_detections(unique_dets)

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
