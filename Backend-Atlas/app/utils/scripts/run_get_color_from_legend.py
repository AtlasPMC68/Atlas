import os
import shutil

from app.utils.file_utils import validate_file_extension
from app.utils.shapes_extraction import extract_shapes
from app.utils.color_in_legends_extraction import extract_colors_from_legend_shapes
from app.utils.color_extraction import extract_colors

ASSETS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "tests", "assets"
)

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "extracted_shapes"
)

MANUAL_LEGEND_BOUNDS_BY_FILE = {
    "Sols_Monde.png": {
        "x": 245,
        "y": 340,
        "width": 50,
        "height": 120,
    },
    "Pluie_Afrique.png": {
        "x": 30,
        "y": 165,
        "width": 28,
        "height": 58,
    },
    "Degrade_Afrique.png": {
        "x": 0,
        "y": 112,
        "width": 16,
        "height": 78,
    },
    "Quebec_Traite1783.png": {
        "x": 370,
        "y": 257,
        "width": 18,
        "height": 163,
    },
}


def extract_shapes_from_assets():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for filename in os.listdir(ASSETS_DIR):
        file_path = os.path.join(ASSETS_DIR, filename)

        if not os.path.isfile(file_path):
            continue

        if not validate_file_extension(file_path):
            continue

        print(f"\nExtracting shapes from {filename}...")

        legend_bounds = MANUAL_LEGEND_BOUNDS_BY_FILE.get(filename)

        if legend_bounds is not None:
            print(f"Using manual legend bounds: {legend_bounds}")
        else:
            print("No manual legend bounds provided for this file.")

        shapes_result = extract_shapes(
            file_path,
            output_dir=OUTPUT_DIR,
            debug=True,
            legend_bounds=legend_bounds,
        )

        all_shapes = shapes_result.get("shapes", [])

        if not all_shapes:
            print("No shapes found.")
            continue

        legend_shapes = [
            shape for shape in all_shapes
            if shape.get("isLegend", False)
        ]

        print(f"Legend shapes detected: {len(legend_shapes)}")

        if not legend_shapes:
            print("No legend shapes found inside the manual legend box.")
            continue

        color_result = extract_colors(
            file_path,
            debug=True,
            legend_shapes=legend_shapes,
        )

        print(
            f"Color extraction done | "
            f"normalized_features={len(color_result.get('normalized_features', []))} | "
            f"pixel_features={len(color_result.get('pixel_features', []))}"
        )


if __name__ == "__main__":
    extract_shapes_from_assets()