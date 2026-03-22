import os

from app.utils.file_utils import validate_file_extension
from app.utils.color_extraction import extract_colors

# Run the script with:
# cd "C:\Users\zacha\OneDrive\Bureau\PMC\Atlas\Backend-Atlas"
# py "app\utils\scripts\run_color_extraction.py"

ASSETS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "tests", "assets"
)

def extract_color_from_assets():


    for filename in os.listdir(ASSETS_DIR):
        file_path = os.path.join(ASSETS_DIR, filename)
        if os.path.isfile(file_path) and validate_file_extension(file_path):
            print(f"Extracting color from {filename}...")
            extract_colors(file_path, debug=True)


extract_color_from_assets()
