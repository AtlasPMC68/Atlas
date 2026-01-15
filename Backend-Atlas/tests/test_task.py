from unittest.mock import patch, mock_open
import io
import uuid
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
    
    mock_color_result = {
        "colors_detected": ["red", "blue"],
        "masks": {"red": "/path/red.png", "blue": "/path/blue.png"},
        "ratios": {"red": 0.6, "blue": 0.4}
    }

    with patch("app.tasks.process_map_extraction.update_state") as mock_update_state, \
         patch("pytesseract.image_to_string", return_value="Mocked OCR text"), \
         patch("PIL.Image.open", return_value=real_image), \
         patch("os.makedirs") as mock_makedirs, \
         patch("builtins.open", mock_open()) as mock_file, \
         patch("app.tasks.extract_colors", return_value=mock_color_result) as mock_extract_colors:
        
        result = process_map_extraction.apply(args=[filename, dummy_image_bytes]).get(timeout=20)

    mock_extract_colors.assert_called_once()
    assert result["filename"] == filename
    assert result["extracted_text"] == "Mocked OCR text"
    assert isinstance(result["text_length"], int)
    assert "output_path" in result
    assert result["status"] == "completed"
