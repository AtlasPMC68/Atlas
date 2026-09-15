import os
import gc
import logging
from celery import Celery

import inference as florence
from output import save_result

logger = logging.getLogger(__name__)
os.environ.setdefault("HF_HOME", "/app/models")

app = Celery(
    "florence_worker",
    broker=os.environ.get("CELERY_BROKER_URL")
    or os.environ.get("REDIS_URL")
    or "redis://redis:6379/0",
)
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True


KEEP_MODEL_IN_MEMORY = os.environ.get("KEEP_MODEL_IN_MEMORY", "true").lower() == "true"
_CACHED_MODEL = None
_CACHED_PROCESSOR = None
_CACHED_CONFIG = None


def get_florence_model():
    """Get cached Florence model and processor or load them if not cached."""
    global _CACHED_MODEL, _CACHED_PROCESSOR, _CACHED_CONFIG
    if _CACHED_MODEL is None or _CACHED_PROCESSOR is None:
        _CACHED_CONFIG = florence.get_runtime_config()
        _CACHED_MODEL, _CACHED_PROCESSOR = florence.load_model_and_processor(
            _CACHED_CONFIG
        )
    return _CACHED_MODEL, _CACHED_PROCESSOR, _CACHED_CONFIG


@app.task(name="florence.run_pipeline", soft_time_limit=840, time_limit=900)
def run_florence(image_path: str, intermediate_path: str) -> bool:
    """
    Run the Florence OCR extraction stage and save its intermediate JSON output.

    Loads the Florence model, runs OCR/text-detection on image_path, frees model
    memory after inference, then writes the intermediate result consumed by Qwen.

    Returns:
        bool: True when the Florence result is successfully saved.
    """
    logger.info(
        f"Received Florence OCR task to process image: {image_path}\nOutput JSON: {intermediate_path}"
    )

    config = florence.get_runtime_config()
    model, processor = florence.load_model_and_processor(config)
    model, processor, config = get_florence_model()
    result = florence.run_pipeline(model, processor, image_path, config)

    # Explicit deletion and garbage collection to free RAM, since qwen runs immediately after.
    del model, processor
    gc.collect()
    if not KEEP_MODEL_IN_MEMORY:
        global _CACHED_MODEL, _CACHED_PROCESSOR
        del model, processor
        _CACHED_MODEL = None
        _CACHED_PROCESSOR = None
        gc.collect()

    # Use save_result from output.py
    save_result(image_path, intermediate_path, result)
    logger.debug(f"Florence result saved: {intermediate_path}")
    return True


if __name__ == "__main__":
    app.worker_main(
        [
            "worker",
            "--loglevel=debug",
            "--concurrency=1",
            "--queues=florence",
            "-n",
            "florence@%h",
        ]
    )
