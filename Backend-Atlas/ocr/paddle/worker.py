import gc
import json
import logging
import os
from celery import Celery
from paddleocr import PaddleOCR

logger = logging.getLogger(__name__)

app = Celery(
    "paddle_worker",
    broker=os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL") or "redis://redis:6379/0",
)
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True

# Initialize PaddleOCR
# use_angle_cls=True to rotate text if needed
# lang='fr' to optimize for French mapping
_CACHED_OCR = None


def get_ocr():
    global _CACHED_OCR
    if _CACHED_OCR is None:
        _CACHED_OCR = PaddleOCR(use_angle_cls=True, lang="fr", enable_mkldnn=False)
    return _CACHED_OCR


@app.task(name="paddle.run_pipeline", soft_time_limit=300, time_limit=360)
def run_paddle(image_path: str, intermediate_path: str) -> bool:
    """
    Run PaddleOCR extraction task and save JSON results compatible with Florence output format.
    """
    logger.info(f"Received PaddleOCR task to process image: {image_path}")

    ocr = get_ocr()
    result = ocr.ocr(image_path)

    detections = []

    if result and result[0]:
        for line in result[0]:
            if not isinstance(line, (list, tuple)) or len(line) < 2:
                logger.warning(f"Unexpected line format from PaddleOCR: {line}")
                continue
                
            try:
                box = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text_info = line[1]
                
                if not isinstance(text_info, (list, tuple)) or len(text_info) < 2:
                    logger.warning(f"Unexpected text_info format from PaddleOCR: {text_info}")
                    continue
                    
                text = str(text_info[0])
                confidence = float(text_info[1])

                xs = [pt[0] for pt in box]
                ys = [pt[1] for pt in box]

                bbox_xyxy = [min(xs), min(ys), max(xs), max(ys)]
                quad = box

                detections.append({"text": text, "bbox_xyxy": bbox_xyxy, "quad": quad, "confidence": confidence})
            except Exception as e:
                logger.error(f"Error parsing line {line}: {e}")
                continue

    output_data = {"detections": detections}

    os.makedirs(os.path.dirname(intermediate_path), exist_ok=True)
    with open(intermediate_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    logger.info(f"PaddleOCR result saved: {intermediate_path} with {len(detections)} detections.")
    return True


if __name__ == "__main__":
    app.worker_main(
        [
            "worker",
            "--loglevel=info",
            "--concurrency=1",
            "--queues=paddle",
            "-n",
            "paddle@%h",
        ]
    )
