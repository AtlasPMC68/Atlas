from app.utils.text_extraction import extract_text
from pathlib import Path
import pytest
import cv2

def get_images() -> tuple[Path, Path]:

    current_dir = Path(__file__).resolve().parent
    assets_dir = current_dir / "assets"

    extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}

    if not assets_dir.exists():
        return []

    images = [
        p for p in assets_dir.iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    ]

    return images


@pytest.mark.parametrize(
    "image_path", "txt_path",
    get_images(),
    ids=lambda p: p.name  # Subtest name is the image name
)
def test_text_extraction(image_path):

    img = cv2.imread(str(image_path))
    results, clean_img = extract_text(img)

    for