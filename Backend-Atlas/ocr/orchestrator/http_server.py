from fastapi import FastAPI, Query
from celery import Celery
import os

app = FastAPI()

_broker = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
celery_app = Celery(
    "ocr_worker",
    broker=_broker,
    backend=_broker,
)

@app.post("/process")
def process_image(filename: str = Query(..., description="Image filename in input/ directory")):

    input_dir = os.environ.get("INPUT_DIR", "/data/input")
    intermediate_dir = os.environ.get("INTERMEDIATE_DIR", "/data/intermediate")
    intermediate_suffix = os.environ.get("INTERMEDIATE_SUFFIX", "-florence")
    output_dir = os.environ.get("OUTPUT_DIR", "/data/output")
    output_suffix = os.environ.get("OUTPUT_SUFFIX", "-qwen")


    image_path = os.path.join(input_dir, filename)
    intermediate_path = os.path.join(intermediate_dir, f"{os.path.splitext(filename)[0]}{intermediate_suffix}.json")
    output_path = os.path.join(output_dir, f"{os.path.splitext(filename)[0]}{output_suffix}.json")


    print(f"Received request to process {image_path}")
    print(f"Intermediate path: {intermediate_path}")
    print(f"Output path: {output_path}")

    if not os.path.exists(image_path):
        print(f"File {image_path} does not exist.")
        return {"error": f"File {filename} does not exist."}
    result = celery_app.signature("ocr.run", args=[image_path, intermediate_path, output_path]).set(queue="ocr").delay()
    output_path = result.get()
    return {"output_path": output_path}
