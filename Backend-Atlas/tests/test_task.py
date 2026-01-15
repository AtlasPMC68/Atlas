import numpy as np
import cv2
import uuid
import pytest
import os
from unittest.mock import patch, mock_open, MagicMock
from app.tasks import process_map_extraction


@pytest.fixture
def real_image_np():
    # OpenCV image (NumPy array)
    return np.zeros((100, 100, 3), dtype=np.uint8)

def get_mock_color_extraction():
    return {
    "colors_detected": ["royal-blue"],
    "masks": {
        "royal-blue": "/app/extracted_color/test_map/royal-blue.png"
    },
    "normalized_features": [
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "color_name": "royal-blue",
                        "color_rgb": (65, 105, 225),
                        "color_hex": "#4169e1",
                        "mapElementType": "zone",
                        "name": "Zone royal-blue",
                        "start_date": "1700-01-01",
                        "end_date": "2026-01-01",
                        "is_normalized": True,
                    },
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [
                            [[[0.1, 0.1], [0.1, 0.2], [0.2, 0.2], [0.2, 0.1], [0.1, 0.1]]]
                        ]
                    }
                }
            ]
        }
    ]
}

def test_process_map_extraction(real_image_np):
    filename = "test_map.png"
    # Dummy bytes for the "file_content" argument
    file_bytes = b"fake_image_data"
    map_id = str(uuid.uuid4())

    # Extract_text in your function expects a list of blocks: [ [box, "text", conf], ... ]
    mock_ocr_result = [
        ([0, 0], "Hello World", 0.99),
        ([1, 1], "World Map", 0.95)
    ]

    mock_colors = get_mock_color_extraction()
    mock_shapes = {"circles": 1, "lines": 5}

    with patch("app.tasks.process_map_extraction.update_state") as mock_update_state, \
         patch("app.tasks.cv2.imread", return_value=real_image_np), \
         patch("app.tasks.extract_text", return_value=(mock_ocr_result, real_image_np)), \
         patch("app.tasks.extract_colors", return_value=mock_colors), \
         patch("app.tasks.extract_shapes", return_value=mock_shapes), \
         patch("app.tasks.asyncio.run", return_value=None), \
         patch("tempfile.NamedTemporaryFile") as mock_tempfile, \
         patch("os.makedirs") as mock_makedirs, \
         patch("os.unlink") as mock_unlink, \
         patch("builtins.open", mock_open()) as mock_file:

        # Mock tempfile to return a file-like object
        mock_tmp_file = MagicMock()
        mock_tmp_file.name = "/tmp/test_map.png"
        mock_tmp_file.__enter__ = MagicMock(return_value=mock_tmp_file)
        mock_tmp_file.__exit__ = MagicMock(return_value=None)
        mock_tempfile.return_value = mock_tmp_file

        result = process_map_extraction.apply(args=[filename, file_bytes, map_id]).get(timeout=20)

    assert result["status"] == "completed"
    assert result["filename"] == filename
    assert "output_path" in result
    # extracted_text is a list of text blocks, so check if the text is in the list
    extracted_text_list = result["extracted_text"]
    assert isinstance(extracted_text_list, list)
    assert "Hello World" in extracted_text_list
    assert "World Map" in extracted_text_list
    assert result["color_result"] == mock_colors
    assert result["shapes_result"] == mock_shapes
    assert mock_update_state.call_count == 6
