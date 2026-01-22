import os

from app.utils.shapes_extraction import extract_shapes

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "assets")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "extracted_shapes")


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
    for filename in os.listdir(ASSETS_DIR):
        file_path = os.path.join(ASSETS_DIR, filename)
        if os.path.isfile(file_path) and is_image_file(filename):
            print(f"Processing {filename}...")
            result = extract_shapes(file_path, output_dir=OUTPUT_DIR)
            print(f"Done: {result['metadata_path']}")


if __name__ == "__main__":
    main()
