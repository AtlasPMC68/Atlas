import gc
import logging
import os
from typing import Any, Tuple
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
_CACHED_MODEL: Any = None
_CACHED_PROCESSOR: Any = None
_CACHED_CONFIG: dict[str, Any] | None = None


def get_florence_model() -> Tuple[Any, Any, dict[str, Any]]:
    """Retrieve cached Florence model, processor, and runtime configuration or load them on first use."""
    global _CACHED_MODEL, _CACHED_PROCESSOR, _CACHED_CONFIG
    if _CACHED_MODEL is None or _CACHED_PROCESSOR is None:
        _CACHED_CONFIG = florence.get_runtime_config()
        _CACHED_MODEL, _CACHED_PROCESSOR = florence.load_model_and_processor(_CACHED_CONFIG)
    assert _CACHED_CONFIG is not None
    return _CACHED_MODEL, _CACHED_PROCESSOR, _CACHED_CONFIG


@app.task(name="florence.run_pipeline", soft_time_limit=840, time_limit=900)
def run_florence(image_path: str, intermediate_path: str) -> bool:
    """
    Run the Florence OCR extraction task, save intermediate JSON results, and manage memory.
    Executes Florence text-detection on input image_path, performs garbage collection,
    clears global model caches if memory retention is disabled, and persists output to intermediate_path.
    """
    logger.info(
        f"Received Florence OCR task to process image: {image_path}\nOutput JSON: {intermediate_path}"
    )

    model, processor, config = get_florence_model()
    result = florence.run_pipeline(model, processor, image_path, config)

    model = None
    processor = None
    gc.collect()

    if not KEEP_MODEL_IN_MEMORY:
        global _CACHED_MODEL, _CACHED_PROCESSOR
        _CACHED_MODEL = None
        _CACHED_PROCESSOR = None
        gc.collect()

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
