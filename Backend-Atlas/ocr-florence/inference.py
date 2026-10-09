import os
import gc
import logging

import torch
import numpy as np
import preprocessing as preprocess
import output as out
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor, PreTrainedModel, ProcessorMixin
from transformers.utils import logging as hf_transformers_logging

logger = logging.getLogger(__name__)
hf_transformers_logging.disable_progress_bar()

OCR_TASK = "<OCR_WITH_REGION>"

def initialize_model() -> tuple[PreTrainedModel, ProcessorMixin, dict]:
    """Load the Florence runtime config, model and processor for OCR inference."""
    hf_home = os.environ.get("HF_HOME", "/app/models")
    logger.debug("Initializing Florence model from %s", hf_home)
    
    device = "cpu"
    config = {
        "model_id": os.environ["FLORENCE_REPO_ID"],
        "torch_dtype": torch.float32 if device == "cpu" else torch.bfloat16,
        "device": device,
        "max_new_tokens": int(os.environ["FLORENCE_MAX_NEW_TOKENS"]),
    }

    model = AutoModelForCausalLM.from_pretrained(
        config["model_id"],
        revision=os.environ["FLORENCE_COMMIT_ID"],
        torch_dtype=config["torch_dtype"],
        trust_remote_code=True,
        attn_implementation="eager",
        cache_dir=hf_home,
        local_files_only=True,
    ).to(config["device"])
    
    processor = AutoProcessor.from_pretrained(
        config["model_id"],
        revision=os.environ["FLORENCE_COMMIT_ID"],
        trust_remote_code=True,
        cache_dir=hf_home,
        local_files_only=True,
    )

    logger.debug("Florence model initialized.")
    return model, processor, config


def run_inference(model: PreTrainedModel, processor: ProcessorMixin, image: Image.Image, task_prompt: str, config: dict) -> dict:
    """Run Florence inference for one task prompt and return structured output."""

    inputs = processor(text=task_prompt, images=image, return_tensors="pt")
    pixel_values = inputs["pixel_values"].to(config["torch_dtype"])

    try:
        with torch.inference_mode():
            generated_ids = model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=pixel_values,
                max_new_tokens=config["max_new_tokens"],
                do_sample=False,
                num_beams=1,
                early_stopping=False,
            )
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        generated_text = generated_text.replace("</s>", "").replace("<s>", "")
    except IndexError as e:
        logger.warning(f"Florence-2 generation failed with IndexError (likely coordinate hallucination): {e}")
        return {}
    except Exception as e:
        logger.warning(f"Florence-2 generation failed: {e}")
        return {}

    del inputs
    if "generated_ids" in locals():
        del generated_ids
    gc.collect()
    return processor.post_process_generation(
        generated_text,
        task=task_prompt,
        image_size=(image.width, image.height),
    )


def _adaptive_preprocess(image_path: str) -> tuple[Image.Image, float, int]:
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

    target_dim = max(1000, min(2000, int(longest_side * 1.75)))
    img = preprocess.upscale_for_ocr(img, min_dimension=target_dim)

    h_new, w_new = img.shape[:2]
    scale_factor = h_new / float(h_orig) if h_orig > 0 else 1.0

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

    MAP_DICTIONARY_LOWER = set()

    def get_poly(d: dict) -> shapely.geometry.Polygon:
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
                text_clean = d.get("text", "").lower().strip()
                dict_score = 10 if text_clean in MAP_DICTIONARY_LOWER else 0
                polys.append({"det": d, "poly": p, "area": p.area, "score": dict_score})
        except Exception:
            pass

    polys.sort(key=lambda x: (x["score"], x["area"]), reverse=True)
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
                if ioa_small > 0.6 and ioa_large > 0.2:
                    is_dup = True
                    break
        if not is_dup:
            unique_dets.append(det)
            unique_polys.append((pA, areaA))

    return unique_dets


def run_pipeline(model: PreTrainedModel, processor: ProcessorMixin, image_path: str, config: dict) -> dict:
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

    all_detections = []

    result = run_inference(model, processor, preprocessed, OCR_TASK, config)
    ocr_data = result.get(OCR_TASK, {})
    for quad, text in zip(ocr_data.get("quad_boxes", []), ocr_data.get("labels", [])):
        all_detections.append({"text": text, "bbox_xyxy": out.quad_to_bbox_xyxy(quad), "quad": quad})

    first_pass_count = len(all_detections)
    logger.debug(f"First pass: {first_pass_count} detections on full image ({longest_side}px)")

    if longest_side <= 800:
        logger.debug("Small image. Skipping tiling.")
        tile_grid = 0
    elif longest_side > 1200 or first_pass_count >= 15:
        logger.debug(f"Dense map detected ({first_pass_count} detections, {longest_side}px). Using 3x3 tiling.")
        tile_grid = 3
    else:
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
                for i in range(0, len(quad) - 1, 2):
                    shifted_quad.extend([quad[i] + x1, quad[i + 1] + y1])

                if len(shifted_quad) >= 4:
                    all_detections.append({"text": text, "bbox_xyxy": out.quad_to_bbox_xyxy(shifted_quad), "quad": shifted_quad})



    unique_dets = _remove_duplicate_detections(all_detections)
    all_detections = out.merge_related_detections(unique_dets)

    if scale_factor != 1.0:
        for det in all_detections:
            det["quad"] = [v / scale_factor for v in det["quad"]]
            det["bbox_xyxy"] = out.quad_to_bbox_xyxy(det["quad"])

    orig_width = int(preprocessed.width / scale_factor)
    orig_height = int(preprocessed.height / scale_factor)

    return {
        "image_size": {"width": orig_width, "height": orig_height},
        "detections": all_detections,
    }
