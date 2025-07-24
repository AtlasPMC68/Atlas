from unittest.mock import patch, mock_open
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

def test_process_map_extraction(dummy_image_bytes, real_image):
    filename = "dummy.png"

    with patch("app.tasks.process_map_extraction.update_state") as mock_update_state, \
         patch("pytesseract.image_to_string", return_value="Mocked OCR text"), \
         patch("PIL.Image.open", return_value=real_image), \
         patch("os.makedirs") as mock_makedirs, \
         patch("builtins.open", mock_open()) as mock_file:
        
        result = process_map_extraction.apply(args=[filename, dummy_image_bytes]).get(timeout=20)

    assert result["filename"] == filename
    assert result["extracted_text"] == "Mocked OCR text"
    assert isinstance(result["text_length"], int)
    assert "output_path" in result
    assert result["status"] == "completeded"
