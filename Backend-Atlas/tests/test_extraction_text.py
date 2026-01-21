from app.utils.text_extraction import extract_text
from pathlib import Path
import pytest

def get_images():
    """
    Locates the assets folder relative to this file and
    collects all images with supported extensions.
    """
    # Path of the current test file
    current_dir = Path(__file__).parent
    assets_dir = current_dir / "assets"
    print(assets_dir)
    print("testing printing")

    # Define supported extensions
    extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp', '.ppm', '.pgm', '.pbm')

    images = []
    if assets_dir.exists():
        for ext in extensions:
            images.extend(assets_dir.glob(ext))

    return images


@pytest.mark.parametrize(
    "image_path",
    get_images(),
    ids=lambda p: p.name  # Subtest name is the image name
)
def test_text_extraction(image_path):

    assert image_path.exists()

