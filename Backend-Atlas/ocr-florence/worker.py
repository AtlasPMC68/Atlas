import logging
import os
from celery import Celery
from transformers import PreTrainedModel, ProcessorMixin

import inference
import output

logger = logging.getLogger(__name__)

# Setting up the OCR task queue optimally
app = Celery(
    "florence_worker",
    broker=os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL") or "redis://redis:6379/0",
    backend=os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL") or "redis://redis:6379/0",
)
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True

# Keep the model loaded in memory between each uses
_CACHED_MODEL: PreTrainedModel | None = None
_CACHED_PROCESSOR: ProcessorMixin | None = None
_CACHED_CONFIG: dict | None = None

def get_florence_model() -> tuple[PreTrainedModel, ProcessorMixin, dict]:
    """Florence2 data model singleton"""

    global _CACHED_MODEL, _CACHED_PROCESSOR, _CACHED_CONFIG
    if _CACHED_MODEL is None:
        _CACHED_MODEL, _CACHED_PROCESSOR, _CACHED_CONFIG = inference.initialize_model()
    return _CACHED_MODEL, _CACHED_PROCESSOR, _CACHED_CONFIG

@app.task(name="florence.run_pipeline", soft_time_limit=840, time_limit=900)
def run_florence(image_path: str, output_path: str) -> None:
    """
    Run the Florence OCR extraction task and return result.

    Args:
        image_path: Path of the map image to process, on the shared ocr-data volume.
        output_path: Json path where the text and textbox combinations are output, on a shared volume
    """
    logger.debug(f"Received Florence OCR task to process image: {image_path}")

    model, processor, config = get_florence_model()
    result = inference.run_pipeline(model, processor, image_path, config)

    output.save_result(image_path, output_path, result)
    logger.debug(f"Florence result saved: {output_path}")
