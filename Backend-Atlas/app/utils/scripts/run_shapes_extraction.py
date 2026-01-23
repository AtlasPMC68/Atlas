import os
import shutil

from app.utils.shapes_extraction import extract_shapes

ASSETS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "tests", "assets"
)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "extracted_shapes")


# To run this script, use the command: python -m app.utils.run_shapes_extraction
def is_image_file(filename):
    return filename.lower().endswith(
        (
            ".jpg",
            ".jpeg",
            ".png",
            ".bmp",
            ".tif",
            ".tiff",
            ".webp",
            ".ppm",
            ".pgm",
            ".pbm",
        )
    )


def main():
    # Supprimer et recréer le dossier OUTPUT_DIR pour écraser les anciens fichiers
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for filename in os.listdir(ASSETS_DIR):
        file_path = os.path.join(ASSETS_DIR, filename)
        if os.path.isfile(file_path) and is_image_file(filename):
            print(f"Processing {filename}...")
            result = extract_shapes(file_path, output_dir=OUTPUT_DIR)
            print(f"Done: {result['metadata_path']}")


if __name__ == "__main__":
    main()
