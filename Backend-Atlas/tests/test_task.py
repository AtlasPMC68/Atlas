from unittest.mock import patch, mock_open, MagicMock
import io
from PIL import Image
import pytest
from app.tasks import process_map_extraction

@pytest.fixture
def dummy_image_bytes():
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

@pytest.fixture
def real_image():
    return Image.new("RGB", (100, 100), color="white")


def test_process_map_extraction(dummy_image_bytes):
    filename = "dummy.png"

    # 1. Create a "fake" image object that has a .flags attribute
    mock_image = MagicMock()
    # This allows image.flags.writeable = False to work without crashing
    mock_image.flags.writeable = True

    mock_ocr_return = ([([0, 0], "Mocked OCR text", 0.9)], "fake_clean_image_object")
    mock_color_return = {"main_color": "#ffffff"}

    with patch("app.tasks.process_map_extraction.update_state") as mock_update_state, \
            patch("app.tasks.extract_text", return_value=mock_ocr_return), \
            patch("app.tasks.extract_colors", return_value=mock_color_return), \
            patch("cv2.imread", return_value=mock_image), \
            patch("builtins.open", mock_open()) as mock_file:
        result = process_map_extraction.apply(args=[filename, dummy_image_bytes]).get(timeout=20)

    # 2. Fixed Assertions
    assert result["filename"] == filename
    assert result["extracted_text"] == ["Mocked OCR text"]
    assert result["status"] == "completed"
