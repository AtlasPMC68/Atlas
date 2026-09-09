
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
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
)
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True


@app.task(name="florence.run_pipeline")
def run_florence(image_path: str, intermediate_path: str) -> bool:
    """
    Run the Florence OCR extraction stage and save its intermediate JSON output.

    Loads the Florence model, runs OCR/text-detection on image_path, frees model
    memory after inference, then writes the intermediate result consumed by Qwen.

    Returns:
        bool: True when the Florence result is successfully saved.
    """
    logger.info(f"Received Florence OCR task to process image: {image_path}\nOutput JSON: {intermediate_path}")

    config = florence.get_runtime_config()
    model, processor = florence.load_model_and_processor(config)
    result = florence.run_pipeline(model, processor, image_path, config)

    # Explicit deletion and garbage collection to free RAM, since qwen runs immediately after.
    del model, processor
    gc.collect()

    # Use save_result from output.py
    save_result(image_path, intermediate_path, result)
    logger.debug(f"Florence result saved: {intermediate_path}")
    return True


if __name__ == "__main__":
    app.worker_main(["worker", "--loglevel=debug", "--concurrency=1", "--queues=florence", "-n", "florence@%h"])
