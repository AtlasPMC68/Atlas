import os
import gc
import json

from celery import Celery
from PIL import Image

import main as qwen

os.environ.setdefault("HF_HOME", "/app/models")

app = Celery(
    "qwen_worker",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
)
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True


def _normalize_image_size(image_size_value, fallback_image):
    """Return image_size as {'width': int, 'height': int} to match intermediate JSON format."""
    if isinstance(image_size_value, dict):
        w = int(image_size_value.get("width", fallback_image.size[0]))
        h = int(image_size_value.get("height", fallback_image.size[1]))
        return {"width": w, "height": h}
    if isinstance(image_size_value, (list, tuple)) and len(image_size_value) == 2:
        return {"width": int(image_size_value[0]), "height": int(image_size_value[1])}
    return {"width": int(fallback_image.size[0]), "height": int(fallback_image.size[1])}


def _strip_quad_fields(detections):
    """Keep qwen output aligned with florence format minus quad boxes."""
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
def run_qwen(florence_result: bool, input_path: str, intermediate_path: str, output_path: str) -> str:
    """
    input_path: absolute path to the image (.png, .jpg, etc)
    intermediate_path: absolute path to the Florence JSON
    output_path: absolute path to the resulting Qwen JSON
    """
    print(f"Received Qwen OCR task to process image: {input_path}\nFlorence JSON: {intermediate_path}\nOutput JSON: {output_path}")

    if not florence_result:
        print("Florence OCR task failed. Skipping Qwen processing.")
        return "florence_failed"

    # Load Florence JSON
    with open(intermediate_path, "r", encoding="utf-8") as f:
        florence_data = json.load(f)

    image_size = florence_data.get("image_size", {})
    context = florence_data.get("context", "")
    detections = florence_data.get("detections", [])
    # Resizing image
    image = Image.open(input_path).convert("RGB")

    # Load image and resize if too large for Qwen. Precision loss should be minimal since we
    # only need a general understanding of the layout for the cleaning pass.
    image = Image.open(input_path).convert("RGB")
    w, h = image.size
    if w * h > qwen.MAX_IMAGE_PIXELS:
        scale = (qwen.MAX_IMAGE_PIXELS / (w * h)) ** 0.5
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    config = qwen.get_runtime_config()
    model, processor = qwen.load_model_and_processor(config)

    print(f"Running per-detection Qwen inference ({len(detections)} detections)")
    raw_detections = qwen.run_per_detection(model, processor, image, detections, config, context)
    detections = _strip_quad_fields(raw_detections)
    detections = qwen.merge_same_text_bboxes_keep_first(detections)
    image_size = _normalize_image_size(image_size, image)

    del model, processor
    gc.collect()

    # Use save_result from main.py for consistent output
    qwen.save_result(input_path,
                     output_path,
                     {"image_size": image_size, "detections": detections, "context": context}
                     )
    print(f"[Qwen] Saved: {output_path}")

    return output_path


if __name__ == "__main__":
    app.worker_main(["worker", "--loglevel=info", "--concurrency=1"])
