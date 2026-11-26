from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from app.utils.ocr import preprocessing
from app.utils.text_extraction import OcrPipelineError, extract_text


def _header(width, height):
    """A mocked Image.open() whose header gives this size."""
    header = MagicMock()
    header.__enter__.return_value.size = (width, height)
    return MagicMock(return_value=header)


@pytest.mark.parametrize("width, height", [(4000, 4000), (3000, 4000), (4000, 10)])
def test_decode_image_decodes_images_up_to_the_max_side(width, height):
    decoded = np.zeros((height, width, 3), dtype=np.uint8)
    with (
        patch.object(preprocessing.Image, "open", _header(width, height)),
        patch.object(preprocessing.cv2, "imdecode", MagicMock(return_value=decoded)) as imdecode,
    ):
        image = preprocessing.decode_image(b"image")

    imdecode.assert_called_once()
    assert image.shape == (height, width, 3)


@pytest.mark.parametrize("width, height", [(4001, 4000), (4000, 4001), (20000, 20000)])
def test_decode_image_refuses_too_large_images_before_decoding(width, height):
    with (
        patch.object(preprocessing.Image, "open", _header(width, height)),
        patch.object(preprocessing.cv2, "imdecode") as imdecode,
    ):
        with pytest.raises(IOError, match="too large"):
            preprocessing.decode_image(b"image")

    imdecode.assert_not_called()


def test_decode_image_refuses_an_unreadable_header_before_decoding():
    with (
        patch.object(preprocessing.Image, "open", MagicMock(side_effect=ValueError("bad header"))),
        patch.object(preprocessing.cv2, "imdecode") as imdecode,
    ):
        with pytest.raises(IOError, match="header"):
            preprocessing.decode_image(b"image")

    imdecode.assert_not_called()


def test_decode_image_refuses_undecodable_pixels():
    with (
        patch.object(preprocessing.Image, "open", _header(100, 100)),
        patch.object(preprocessing.cv2, "imdecode", MagicMock(return_value=None)),
    ):
        with pytest.raises(IOError, match="decode"):
            preprocessing.decode_image(b"image")


def test_extract_text_fails_visibly_when_the_image_is_refused():
    with (
        patch.object(preprocessing, "decode_image", MagicMock(side_effect=IOError("Image too large"))),
        patch("app.utils.text_extraction._run_ocr_pipeline") as run_ocr,
    ):
        with pytest.raises(OcrPipelineError, match="too large"):
            extract_text(uuid4(), b"image")

    run_ocr.assert_not_called()


def test_extract_text_runs_the_ocr_on_the_decoded_image():
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    blocks = [{"text": "Québec", "bbox": [], "prob": 0.9}]
    with (
        patch.object(preprocessing, "decode_image", MagicMock(return_value=image)),
        patch("app.utils.text_extraction._run_ocr_pipeline", MagicMock(return_value=blocks)) as run_ocr,
    ):
        assert extract_text(uuid4(), b"image") == blocks

    assert run_ocr.call_args.kwargs["image"] is image
