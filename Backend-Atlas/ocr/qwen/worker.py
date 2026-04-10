import os
import gc
import json
import logging
from typing import Any
from celery import Celery
from PIL import Image

import inference as qwen

logger = logging.getLogger(__name__)
os.environ.setdefault("HF_HOME", "/app/models")

app = Celery(
    "qwen_worker",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
)
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True


def _strip_quad_fields(detections: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize Qwen detections to valid {text, bbox_xyxy} entries only."""
    cleaned = []
    for det in detections or []:
        if not isinstance(det, dict):
            continue
        text = det.get("text", "")
        bbox = det.get("bbox_xyxy", [])
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        cleaned.append(
            {
                "text": text,
                "bbox_xyxy": [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])],
            }
        )
    return cleaned


@app.task(name="qwen.run_pipeline")
def run_qwen(
    florence_result: bool,
    input_path: str,
    intermediate_path: str,
    output_path: str,
) -> str:
    """
    Run the Qwen OCR refinement stage using Florence intermediate detections.

    Loads Florence output, optionally resizes the image to fit Qwen pixel limits,
    applies per-detection text correction, post-processes detections, then writes
    the final JSON payload to output_path.

    Returns:
        str: output_path on success, or "florence_failed" when upstream failed.
    """

    if not florence_result:
        logger.error("Florence OCR task failed. Skipping Qwen processing.")
        return "florence_failed"

    # Load Florence JSON
    with open(intermediate_path, "r", encoding="utf-8") as f:
        florence_data = json.load(f)

    image_size = florence_data.get("image_size", {})
    context = florence_data.get("context", "")
    detections = florence_data.get("detections", [])

    # Load image and resize if too large for Qwen while keeping aspect ratio.
    image = Image.open(input_path).convert("RGB")
    w, h = image.size
    if w * h > qwen.MAX_IMAGE_PIXELS:
        scale = (qwen.MAX_IMAGE_PIXELS / (w * h)) ** 0.5
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    config = qwen.get_runtime_config()
    model, processor = qwen.load_model_and_processor(config)

    logger.debug(f"Qwen initialized for ({len(detections)} detections)")
    raw_detections = qwen.run_per_detection(model, processor, image, detections, config, context)
    detections = _strip_quad_fields(raw_detections)
    detections = qwen.merge_same_text_bboxes_keep_first(detections)

    # Forcing model loaded in memory to be cleared
    del model, processor
    gc.collect()

    # Use save_result from main.py for consistent output
    qwen.save_result(
        input_path,
        output_path,
        {"image_size": image_size, "detections": detections, "context": context}
    )
    logger.info(f"Qwen result Saved: {output_path}")

    return output_path


if __name__ == "__main__":
    app.worker_main(["worker", "--loglevel=info", "--concurrency=1"])
