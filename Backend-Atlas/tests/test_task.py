import uuid
from unittest.mock import patch, MagicMock, mock_open

import numpy as np
import pytest
from app.tasks import process_map_extraction


@pytest.fixture
def real_image_np():
    # OpenCV image (NumPy array)
    return np.zeros((100, 100, 3), dtype=np.uint8)


def get_mock_color_extraction():
    return {
        "colors_detected": ["royal-blue"],
        "masks": {"royal-blue": "/app/extracted_color/test_map/royal-blue.png"},
        "ratios": {"royal-blue": 0.5},
        "dominant_bins": [],
        "output_dir": "/app/extracted_color/test_map",
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
                                [
                                    [
                                        [0.1, 0.1],
                                        [0.1, 0.2],
                                        [0.2, 0.2],
                                        [0.2, 0.1],
                                        [0.1, 0.1],
                                    ]
                                ]
                            ],
                        },
                    }
                ],
            }
        ],
    }

def test_process_map_extraction(real_image_np):
    filename = "test_map.png"
    file_bytes = b"fake_image_data"
    map_id = str(uuid.uuid4())

    mock_ocr_result = [([0, 0], "Hello World", 0.99), ([1, 1], "World Map", 0.95)]
    mock_colors = get_mock_color_extraction()
    mock_shapes = {"circles": 1, "lines": 5, "normalized_features": []}

    with patch("app.tasks.process_map_extraction.update_state") as mock_update_state, \
         patch("app.tasks.cv2.imread", return_value=real_image_np), \
         patch("app.tasks.extract_text", return_value=(mock_ocr_result, real_image_np)), \
         patch("app.tasks.extract_colors", return_value=mock_colors), \
         patch("app.tasks.extract_shapes", return_value=mock_shapes), \
         patch("app.tasks.asyncio.run") as mock_asyncio_run, \
         patch("app.tasks.find_first_city", return_value={
             "found": False, "query": "test", "name": "test", "lat": 0.0, "lon": 0.0
         }), \
         patch("tempfile.NamedTemporaryFile") as mock_tempfile, \
         patch("os.makedirs"), \
         patch("os.unlink"), \
         patch("builtins.open", mock_open()):

        mock_tmp_file = MagicMock()
        mock_tmp_file.name = "/tmp/test_map.png"
        mock_tmp_file.__enter__ = MagicMock(return_value=mock_tmp_file)
        mock_tmp_file.__exit__ = MagicMock(return_value=None)
        mock_tempfile.return_value = mock_tmp_file

        # Call with all extraction options enabled
        result = process_map_extraction.apply(
            args=[filename, file_bytes, map_id],
            kwargs={
                "pixel_points": None,
                "geo_points_lonlat": None,
                "enable_color_extraction": True,
                "enable_shapes_extraction": True,
                "enable_text_extraction": True,
            }
        ).get(timeout=20)

    # Verify result structure
    assert result["status"] == "completed"
    assert result["filename"] == filename
    assert "output_path" in result
    assert result["color_result"] == mock_colors
    assert result["shapes_result"] == mock_shapes
    
    # Verify extractions_performed flags
    assert "extractions_performed" in result
    assert result["extractions_performed"]["georeferencing"] is False  # No points provided
    assert result["extractions_performed"]["color_extraction"] is True
    assert result["extractions_performed"]["shapes_extraction"] is True
    assert result["extractions_performed"]["text_extraction"] is True
    
    # Verify mocks were called appropriately
    assert mock_update_state.call_count >= 5  # At least 5 progress updates
    assert mock_asyncio_run.call_count >= 1  # At least one async persist call


def test_process_map_extraction_minimal(real_image_np):
    """Test with all extractions disabled"""
    filename = "test_map.png"
    file_bytes = b"fake_image_data"
    map_id = str(uuid.uuid4())

    with patch("app.tasks.process_map_extraction.update_state"), \
         patch("app.tasks.cv2.imread", return_value=real_image_np), \
         patch("app.tasks.extract_text") as mock_extract_text, \
         patch("app.tasks.extract_colors") as mock_extract_colors, \
         patch("app.tasks.extract_shapes") as mock_extract_shapes, \
         patch("tempfile.NamedTemporaryFile") as mock_tempfile, \
         patch("os.unlink"):

        mock_tmp_file = MagicMock()
        mock_tmp_file.name = "/tmp/test_map.png"
        mock_tmp_file.__enter__ = MagicMock(return_value=mock_tmp_file)
        mock_tmp_file.__exit__ = MagicMock(return_value=None)
        mock_tempfile.return_value = mock_tmp_file

        # Call with all extraction options disabled
        result = process_map_extraction.apply(
            args=[filename, file_bytes, map_id],
            kwargs={
                "enable_color_extraction": False,
                "enable_shapes_extraction": False,
                "enable_text_extraction": False,
            }
        ).get(timeout=20)

    # Verify extractions were skipped
    assert result["extractions_performed"]["color_extraction"] is False
    assert result["extractions_performed"]["shapes_extraction"] is False
    assert result["extractions_performed"]["text_extraction"] is False
    
    # Verify extraction functions were not called
    mock_extract_text.assert_not_called()
    mock_extract_colors.assert_not_called()
    mock_extract_shapes.assert_not_called()
