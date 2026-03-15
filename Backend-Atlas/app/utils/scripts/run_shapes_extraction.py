import os
import shutil

from app.utils.file_utils import validate_file_extension
from app.utils.shapes_extraction import extract_shapes

ASSETS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "tests", "assets"
)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "extracted_shapes")


def extract_shapes_from_assets():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for filename in os.listdir(ASSETS_DIR):
        file_path = os.path.join(ASSETS_DIR, filename)
        if os.path.isfile(file_path) and validate_file_extension(file_path):
            print(f"Extracting shapes from {filename}...")
            extract_shapes(file_path, output_dir=OUTPUT_DIR, debug=False)


extract_shapes_from_assets()
