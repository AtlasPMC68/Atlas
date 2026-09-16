import gc
import json
import logging
import os
from typing import Any, Tuple
from celery import Celery
from PIL import Image

import inference as qwen
from merge import merge_same_text_bboxes_keep_first

logger = logging.getLogger(__name__)
os.environ.setdefault("HF_HOME", "/app/models")

app = Celery(
    "qwen_worker",
    broker=os.environ.get("CELERY_BROKER_URL")
    or os.environ.get("REDIS_URL")
    or "redis://redis:6379/0",
)
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True

KEEP_MODEL_IN_MEMORY = os.environ.get("KEEP_MODEL_IN_MEMORY", "true").lower() == "true"
_CACHED_MODEL: Any = None
_CACHED_PROCESSOR: Any = None
_CACHED_CONFIG: dict[str, Any] | None = None


def get_qwen_model() -> Tuple[Any, Any, dict[str, Any]]:
    """Retrieve cached Qwen model, processor, and runtime configuration or load them on first use."""
    global _CACHED_MODEL, _CACHED_PROCESSOR, _CACHED_CONFIG
    if _CACHED_MODEL is None or _CACHED_PROCESSOR is None:
        _CACHED_CONFIG = qwen.get_runtime_config()
        _CACHED_MODEL, _CACHED_PROCESSOR = qwen.load_model_and_processor(_CACHED_CONFIG)
    return _CACHED_MODEL, _CACHED_PROCESSOR, _CACHED_CONFIG


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


@app.task(name="qwen.run_pipeline", soft_time_limit=840, time_limit=900)
def run_qwen(
    florence_result: bool,
    input_path: str,
    intermediate_path: str,
    output_path: str,
) -> str:
    """
    Run the Qwen OCR refinement stage using Florence intermediate detections.
    Loads Florence JSON output, aligns detection coordinates with Qwen image bounds,
    resizes images exceeding pixel thresholds, executes per-detection correction,
    performs memory cleanup, and saves final OCR results.
    """
    if not florence_result:
        logger.error("Florence OCR task failed. Skipping Qwen processing.")
        return "florence_failed"

    with open(intermediate_path, "r", encoding="utf-8") as f:
        florence_data = json.load(f)

    image_size = florence_data.get("image_size", {})
    context = florence_data.get("context", "")
    detections = florence_data.get("detections", [])

    image = Image.open(input_path).convert("RGB")
    w, h = image.size

    florence_w = image_size.get("width")
    florence_h = image_size.get("height")
    if florence_w and florence_h and (florence_w != w or florence_h != h):
        scale_x = w / float(florence_w)
        scale_y = h / float(florence_h)
        for det in detections:
            bbox = det.get("bbox_xyxy")
            if isinstance(bbox, list) and len(bbox) == 4:
                det["bbox_xyxy"] = [
                    int(bbox[0] * scale_x),
                    int(bbox[1] * scale_y),
                    int(bbox[2] * scale_x),
                    int(bbox[3] * scale_y),
                ]

    if w * h > qwen.MAX_IMAGE_PIXELS:
        scale = (qwen.MAX_IMAGE_PIXELS / (w * h)) ** 0.5
        image = image.resize(
            (int(w * scale), int(h * scale)),
            Image.Resampling.LANCZOS,
        )
        for det in detections:
            bbox = det.get("bbox_xyxy")
            if isinstance(bbox, list) and len(bbox) == 4:
                det["bbox_xyxy"] = [
                    int(bbox[0] * scale),
                    int(bbox[1] * scale),
                    int(bbox[2] * scale),
                    int(bbox[3] * scale),
                ]

    model, processor, config = get_qwen_model()
    config = config or {}

    logger.debug(f"Qwen initialized for ({len(detections)} detections)")
    raw_detections = qwen.run_per_detection(
        model, processor, image, detections, config, context
    )
    detections = _strip_quad_fields(raw_detections)
    detections = merge_same_text_bboxes_keep_first(detections)

    del model, processor
    gc.collect()

    if not KEEP_MODEL_IN_MEMORY:
        global _CACHED_MODEL, _CACHED_PROCESSOR
        del model, processor
        _CACHED_MODEL = None
        _CACHED_PROCESSOR = None
        gc.collect()

    qwen.save_result(
        input_path,
        output_path,
        {"image_size": image_size, "detections": detections, "context": context},
    )
    logger.info(f"Qwen result Saved: {output_path}")

    return output_path


if __name__ == "__main__":
    app.worker_main(
        [
            "worker",
            "--loglevel=info",
            "--concurrency=1",
            "--queues=qwen",
            "-n",
            "qwen@%h",
        ]
    )
