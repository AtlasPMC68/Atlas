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
        "x": 235,
        "y": 340,
        "width": 250,
        "height": 120,
    },
    "Sahel_Afrique.png": {
        "x": 0,
        "y": 90,
        "width": 88,
        "height": 162,
    },
    # "Sahel_Afrique.png": {"x": ..., "y": ..., "width": ..., "height": ...},
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

        for index, shape in enumerate(legend_shapes, start=1):
            print(
                f"Legend shape #{index} | "
                f"type={shape.get('shape_type')} | "
                f"bbox={shape.get('bounding_box')} | "
                f"original_color={shape.get('color_rgb')}"
            )

        colors_to_extract = extract_colors_from_legend_shapes(
            file_path,
            legend_shapes,
        )

        print(f"Extracted imposed colors: {colors_to_extract}")

        color_result = extract_colors(
            file_path,
            debug=True,
            imposed_colors=colors_to_extract if colors_to_extract else None,
        )

        print(
            f"Color extraction done | "
            f"normalized_features={len(color_result.get('normalized_features', []))} | "
            f"pixel_features={len(color_result.get('pixel_features', []))}"
        )


if __name__ == "__main__":
    extract_shapes_from_assets()