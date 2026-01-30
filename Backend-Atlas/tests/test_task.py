import uuid
from unittest.mock import mock_open, patch

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


def get_mock_shape_extraction():
    return {
        "normalized_features": [
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "mapElementType": "shape",
                            "name": "Shape 1",
                            "is_normalized": True,
                            "start_date": "1700-01-01",
                            "end_date": "2026-01-01",
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [0.1, 0.1],
                                    [0.1, 0.2],
                                    [0.2, 0.2],
                                    [0.2, 0.1],
                                    [0.1, 0.1],
                                ]
                            ],
                        },
                    }
                ],
            }
        ]
    }


def test_process_map_extraction(real_image_np):
    filename = "test_map.png"
    # Dummy bytes for the "file_content" argument
    file_bytes = b"fake_image_data"
    map_id = str(uuid.uuid4())

    # Extract_text in your function expects a list of blocks: [ [box, "text", conf], ... ]
    mock_ocr_result = [([0, 0], "Hello World", 0.99), ([1, 1], "World Map", 0.95)]

    mock_colors = get_mock_color_extraction()
    mock_shapes = get_mock_shape_extraction()

    with (
        patch("app.tasks.process_map_extraction.update_state") as mock_update_state,
        patch("app.tasks.cv2.imread", return_value=real_image_np),
        patch("app.tasks.extract_text", return_value=(mock_ocr_result, real_image_np)),
        patch("app.tasks.extract_colors", return_value=mock_colors),
        patch("app.tasks.extract_shapes", return_value=mock_shapes),
        patch("app.tasks.persist_features", return_value=None),
        patch("os.makedirs"),
        patch("os.unlink"),
        patch("builtins.open", mock_open()),
    ):
        result = process_map_extraction.apply(args=[filename, file_bytes, map_id]).get(
            timeout=20
        )

    assert result["status"] == "completed"
    assert "Hello World" in result["extracted_text"]
    assert "World Map" in result["extracted_text"]
    assert result["color_result"] == mock_colors
    assert result["shapes_result"] == mock_shapes
    assert mock_update_state.call_count == 6
