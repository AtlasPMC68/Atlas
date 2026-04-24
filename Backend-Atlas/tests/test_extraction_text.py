import unicodedata
import logging
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from Levenshtein import distance as levenshtein_distance

from app.celery_app import celery_app
from app.utils.text_extraction import extract_text
from tests.utils.expected_text_results import MAP_EXPECTED_TEXTS

logger = logging.getLogger(__name__)


def get_image_paths() -> list[Path]:
    """Collect all image paths from tests/assets with supported extensions."""
    valid_extensions = (".jpg",".jpeg",".png",".bmp",".tif",".tiff",".webp",".ppm",".pgm",".pbm",)

    current_dir = Path(__file__).parent
    assets_dir = current_dir / "assets"

    if not assets_dir.exists():
        pytest.fail(UserWarning(f"Searching for assets in non-existent directory: {assets_dir}"))
        return []

    return [p for p in assets_dir.iterdir() if p.suffix.lower() in valid_extensions]


def get_test_data() -> list[tuple[Path, list[str]]]:
    images = get_image_paths()
    data: list[tuple[Path, list[str]]] = []
    for image in images:
        expected = MAP_EXPECTED_TEXTS.get(image.stem)
        if expected:
            data.append((image, expected))
    return data


def normalize_array_to_ascii_format(text: list[str]) -> dict[str, str]:
    """Replace all characters by their ASCII-normalized variant."""
    result: dict[str, str] = {}
    for word in text:
        result[word] = (unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode("ascii"))
    return result


def check_for_match(
    actual: list[str],
    expected: list[str],
) -> dict[str, tuple[str, float]]:
    """
    Map each OCR word to the closest expected word and distance. Expected refers to
    the ground truth text, while actual refers to the OCR output. The distance is a
    levenshtein distance between the ASCII-normalized versions of the actual and 
    expected strings.
    """
    actual_ascii_dict = normalize_array_to_ascii_format(actual)
    expected_ascii_dict = normalize_array_to_ascii_format(expected)
    result: dict[str, tuple[str, float]] = {}

    for ocr_word, ocr_word_ascii in actual_ascii_dict.items():
        min_dist: tuple[str, float] = ("", 1000.0)

        for expected_word, expected_word_ascii in expected_ascii_dict.items():
            if ocr_word == expected_word:
                min_dist = (expected_word, 0.0)
                break

            if ocr_word_ascii == expected_word_ascii:
                min_dist = (expected_word, 0.1)
                break

            tmp_dist = float(levenshtein_distance(ocr_word_ascii, expected_word_ascii))
            if tmp_dist < min_dist[1]:
                min_dist = (expected_word, tmp_dist)

        result[ocr_word] = min_dist
    return result


@pytest.mark.skip(reason="temporarily disabled")
@pytest.mark.parametrize(
    "image_path, expected_text",
    get_test_data(),
    ids=lambda val: val.name if isinstance(val, Path) else None,
)
def test_text_extraction(
    image_path: Path,
    expected_text: list[str],
    request: pytest.FixtureRequest,
) -> None:
    assert image_path.exists()

    # Extract text from image using the OCR pipeline
    with open(image_path, "rb") as input_file:
        file_content = input_file.read()
    extracted_text, _ = extract_text(
        map_id=uuid4(),
        filename=image_path.name,
        file_content=file_content,
        celery_app=celery_app,
    )

    # Pair every single OCR word with the closest word from the dictionary of exepected words
    unpaired_ocr_words: list[str] = [str(block.get("text", "")) for block in extracted_text]
    unpaired_expected_words: list[str] = deepcopy(expected_text)
    results = check_for_match(
        unpaired_ocr_words,
        unpaired_expected_words,
    )

    # Calculating average distance and box find rate
    total_distance = 0.0
    comparison_details: list[str] = []
    mismatch_details: list[str] = []
    for ocr_word, (expected_word, distance) in results.items():
        total_distance += distance

        if distance > 1.0:
            logger.warning(f"expected='{expected_word}' | ocr='{ocr_word}' | d={distance:.3f}")



    box_find_rate = len(unpaired_ocr_words)/len(unpaired_expected_words) * 100
    average_dist = total_distance / len(unpaired_ocr_words) if unpaired_ocr_words else 0.0
    request.node.user_metadata = {
        "average_distance": average_dist,
        "hit_rate": box_find_rate,
    }

    assert box_find_rate > 90.0, (
        f"Box find rate too low: {box_find_rate:.2f}%"
    )
    assert average_dist < 2.0, (
        f"Average distance too high: {average_dist:.2f}"
    )
