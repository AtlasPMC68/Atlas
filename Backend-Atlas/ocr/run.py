"""
Run the backend's OCR pipeline (app/utils/ocr) on every test image and save the outputs.

Usage (inside the container, see README): ``python3 run.py [name filter ...]``
With filters, only images whose path contains one of them are processed.
"""
import os
import time

import report
from app.utils.ocr import OCR_REC_MODEL, inference, preprocessing

_models = {}


def load() -> None:
    _models["detector"], _models["recognizer"] = inference.initialize_models()


def process(image_path: str) -> dict:
    started = time.monotonic()
    result = inference.run_pipeline(_models["detector"], _models["recognizer"], preprocessing.read_image(image_path))
    # Boxes the recognizer could not read are left out, there is nothing to score
    labels = [
        {"new_text": det["text"], "score": det["score"], "quad": det["quad"]} for det in result["detections"] if det["text"]
    ]
    return {
        "image_size": result["image_size"],
        "timings_s": {"ocr": round(time.monotonic() - started, 2)},
        "labels": labels,
    }


if __name__ == "__main__":
    report.run_batch(f"ocr-{OCR_REC_MODEL}", load, process, stages=["ocr"])
