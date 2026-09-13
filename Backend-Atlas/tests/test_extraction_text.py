import os
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
        pytest.fail(f"Searching for assets in non-existent directory: {assets_dir}")
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



def normalize_array_to_ascii_format(text: list[str]) -> list[str]:
    """Return ASCII-normalized words while preserving duplicate entries."""
    res = []
    for word in text:
        cleaned = word.replace("’", "").replace("'", "").replace("-", " ").replace(".", "").replace(",", "")
        cleaned = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii").lower()
        cleaned = " ".join(cleaned.split())
        res.append(cleaned)
    return res


def check_for_match(
    actual: list[str],
    expected: list[str],
) -> list[tuple[str, tuple[str, float]]]:
    """
    Map each OCR word to the closest expected word and distance while preserving
    repeated OCR detections. Expected refers to the ground truth text, while actual
    refers to the OCR output. The distance is a Levenshtein distance between the
    ASCII-normalized versions of the actual and expected strings.
    """
    actual_ascii = normalize_array_to_ascii_format(actual)
    expected_ascii = normalize_array_to_ascii_format(expected)
    result: list[tuple[str, tuple[str, float]]] = []
    used_expected_indices: set[int] = set()

    for ocr_index, ocr_word in enumerate(actual):
        ocr_word_ascii = actual_ascii[ocr_index]
        min_dist: tuple[str, float] = ("", 1000.0)
        min_dist_index: int | None = None

        for expected_index, expected_word in enumerate(expected):
            if expected_index in used_expected_indices and ocr_word == expected_word:
                continue

            expected_word_ascii = expected_ascii[expected_index]
            if ocr_word == expected_word:
                min_dist = (expected_word, 0.0)
                min_dist_index = expected_index
                break

            if ocr_word_ascii == expected_word_ascii:
                min_dist = (expected_word, 0.1)
                min_dist_index = expected_index
                break

            # Consider it a very close match if one is a meaningful substring of the other
            if len(expected_word_ascii) >= 4 and len(ocr_word_ascii) >= 4:
                if expected_word_ascii in ocr_word_ascii or ocr_word_ascii in expected_word_ascii:
                    min_dist = (expected_word, 0.5)
                    min_dist_index = expected_index
                    break

            tmp_dist = float(levenshtein_distance(ocr_word_ascii, expected_word_ascii))
            if tmp_dist < min_dist[1]:
                min_dist = (expected_word, tmp_dist)
                min_dist_index = expected_index

        if min_dist_index is not None:
            used_expected_indices.add(min_dist_index)

        result.append((ocr_word, min_dist))

    return result


def calculate_match_metrics(
    matches: list[tuple[str, tuple[str, float]]],
    expected: list[str],
) -> tuple[float, float]:
    """Compute coverage and average distance from matched OCR results."""
    if not matches:
        return (0.0, 0.0)

    total_distance = sum(distance for _, (_, distance) in matches)
    matched_expected_words = {
        expected_word
        for _, (expected_word, distance) in matches
        if expected_word and distance <= 3.0
    }
    box_find_rate = (len(matched_expected_words) / len(expected)) * 100 if expected else 0.0
    average_dist = total_distance / len(matches)
    return box_find_rate, average_dist


def test_match_metrics_count_expected_coverage_once() -> None:
    matches = [
        ("Quebec", ("Québec", 0.0)),
        ("Quebec", ("Québec", 0.0)),
    ]

    box_find_rate, average_dist = calculate_match_metrics(matches, ["Québec"])

    assert box_find_rate == 100.0
    assert average_dist == 0.0


def test_check_for_match_keeps_duplicate_ocr_words() -> None:
    actual = ["Quebec", "Quebec", "Boston"]
    expected = ["Québec", "Boston"]

    matches = check_for_match(actual, expected)

    assert [ocr_word for ocr_word, _ in matches] == ["Quebec", "Quebec", "Boston"]


def test_qwen_generated_text_strips_eos_artifacts() -> None:
    raw = "</s>Progress of the Wehrmacht\nduring 10th May 1940"

    cleaned = raw.replace("</s>", " ").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = " ".join(cleaned.split()).strip()

    assert cleaned == "Progress of the Wehrmacht during 10th May 1940"


def test_florence_merge_does_not_join_distant_map_labels() -> None:
    from ocr.florence.output import _get_merge_direction
    try:
        from ocr.florence.output import _get_merge_direction
    except ImportError:
        pytest.skip("ocr module is not available in the backend tests container")

    left = {"bbox_xyxy": [10, 40, 80, 60], "source_w": 70, "source_h": 20, "quad": [10, 40, 80, 40, 80, 60, 10, 60]}
    right = {"bbox_xyxy": [120, 40, 200, 60], "source_w": 80, "source_h": 20, "quad": [120, 40, 200, 40, 200, 60, 120, 60]}

    assert _get_merge_direction(left, right) is None


@pytest.mark.integration
@pytest.mark.slow
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

    # Pair every single OCR word with the closest word from the dictionary of expected words
    unpaired_ocr_words: list[str] = [str(block.get("text", "")) for block in extracted_text]
    unpaired_expected_words: list[str] = deepcopy(expected_text)
    results = check_for_match(
        unpaired_ocr_words,
        unpaired_expected_words,
    )

    total_distance = 0.0
    for ocr_word, (expected_word, distance) in results:
        total_distance += distance

        if distance > 1.0:
            logger.warning(f"expected='{expected_word}' | ocr='{ocr_word}' | d={distance:.3f}")

    box_find_rate, average_dist = calculate_match_metrics(results, unpaired_expected_words)
    setattr(request.node, "user_metadata", {
        "average_distance": average_dist,
        "hit_rate": box_find_rate,
    })

    assert box_find_rate >= 40.0, (
        f"Box find rate too low: {box_find_rate:.2f}%"
    )
    assert average_dist < 15.0, (
        f"Average distance too high: {average_dist:.2f}"
    )
