import os

from celery import Celery, chain

_broker = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")

app = Celery(
    "ocr_worker",
    broker=_broker,
    backend=_broker,  # needed for .get() to retrieve subtask results
)

# Configure Celery to ensure tasks are acknowledged after completion and to avoid
# losing a task in the event of a crash.
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True

@app.task(name="ocr.run")
def run(image_path: str, intermediate_path, output_path) -> str:
    """
    Dispatch the full OCR pipeline for one image and wait for it to finish.
    """
    print(f"Received OCR task to process {image_path}")

    # Tell celery that both tasks are interdependant and should be executed in order.
    workflow = chain(
        app.signature("florence.run_pipeline", args=[image_path, intermediate_path]).set(queue="florence"),
        # The second task takes the returning value of the first task as a parameter.
        app.signature("qwen_gguf.run_pipeline", args=[image_path, intermediate_path, output_path]).set(queue="qwen_gguf")
    )
    result = workflow.apply_async()    
    return result.id

if __name__ == "__main__":
    app.worker_main(["worker", "--loglevel=debug", "--concurrency=1"])
