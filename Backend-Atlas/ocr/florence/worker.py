
import os
import gc

from celery import Celery

import main as florence
from output import save_result

os.environ.setdefault("HF_HOME", "/app/models")

app = Celery(
    "florence_worker",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
)
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True


@app.task(name="florence.run_pipeline")
def run_florence(image_path: str, intermediate_path: str) -> str:
    print(f"Received Florence OCR task to process {image_path}")

    config = florence.get_runtime_config()
    model, processor = florence.load_model_and_processor(config)
    result = florence.run_pipeline(model, processor, image_path, config)

    # Explicit deletion and garbage collection to free RAM, since qwen runs immediately after.
    del model, processor
    gc.collect()

    # Use save_result from output.py
    save_result(image_path, intermediate_path, result)
    print(f"[Florence] Saved: {intermediate_path}")
    return True


if __name__ == "__main__":
    app.worker_main(["worker", "--loglevel=debug", "--concurrency=1"])
