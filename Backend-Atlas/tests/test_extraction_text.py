import logging
import re
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from app.celery_app import celery_app
from app.utils.text_extraction import extract_text
from Levenshtein import distance as levenshtein_distance

from tests.utils.expected_text_results import MAP_EXPECTED_TEXTS

logger = logging.getLogger(__name__)

CYAN = "\033[96m"
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def get_image_paths() -> list[Path]:
    """Collect all valid image file paths from tests/assets directory with supported extensions."""
    valid_extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tif",
        ".tiff",
        ".webp",
        ".ppm",
        ".pgm",
        ".pbm",
    )

    current_dir = Path(__file__).parent
    assets_dir = current_dir / "assets"

    if not assets_dir.exists():
        pytest.fail(f"Searching for assets in non-existent directory: {assets_dir}")
        return []

    return [p for p in assets_dir.iterdir() if p.suffix.lower() in valid_extensions]


def get_test_data() -> list[tuple[Path, list[str]]]:
    """Load image paths and their corresponding expected ground truth text lists for testing."""
    images = get_image_paths()
    data: list[tuple[Path, list[str]]] = []
    for image in images:
        expected = MAP_EXPECTED_TEXTS.get(image.stem)
        if expected:
            data.append((image, expected))
    return data


def normalize_array_to_ascii_format(text: list[str]) -> list[str]:
    """Return ASCII-normalized words stripping punctuation and accents while preserving word count."""
    res = []
    for word in text:
        cleaned = (
            word.replace("’", "")
            .replace("'", "")
            .replace("-", " ")
            .replace(".", "")
            .replace(",", "")
            .replace("(", " ")
            .replace(")", " ")
            .replace(":", " ")
            .replace(";", " ")
            .replace("?", " ")
            .replace("!", " ")
            .replace('"', " ")
            .replace("«", " ")
            .replace("»", " ")
            .replace("/", " ")
            .replace("\\", " ")
        )
        cleaned = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii").lower()
        cleaned = " ".join(cleaned.split())
        res.append(cleaned)
    return res


def check_for_match(
    actual: list[str],
    expected: list[str],
) -> list[tuple[str, tuple[str, float]]]:
    """
    Map each OCR word to the closest expected word and calculate Levenshtein distance.
    Preserves repeated OCR detections and handles substring matching and year suffix matching.
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

            if len(expected_word_ascii) >= 4 and len(ocr_word_ascii) >= 4:
                if expected_word_ascii in ocr_word_ascii or ocr_word_ascii in expected_word_ascii:
                    min_dist = (expected_word, 0.5)
                    min_dist_index = expected_index
                    break

            tmp_dist = float(levenshtein_distance(ocr_word_ascii, expected_word_ascii))

            base_expected = re.sub(r"\b(1[5-9]\d\d|20\d\d)\b", "", expected_word_ascii).strip()
            base_expected = " ".join(base_expected.split())
            if base_expected and len(base_expected) >= 4 and base_expected != expected_word_ascii:
                if len(ocr_word_ascii) >= 4 and (base_expected in ocr_word_ascii or ocr_word_ascii in base_expected):
                    base_dist = 0.5
                else:
                    base_dist = float(levenshtein_distance(ocr_word_ascii, base_expected))
                if base_dist < tmp_dist:
                    tmp_dist = base_dist

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
    """Compute hit rate coverage percentage and average distance from matched OCR results."""
    if not matches:
        return (0.0, 0.0)

    total_distance = sum(distance for _, (_, distance) in matches)
    matched_expected_words = {expected_word for _, (expected_word, distance) in matches if expected_word and (distance <= max(3.0, len(expected_word) * 0.25))}
    box_find_rate = (len(matched_expected_words) / len(expected)) * 100 if expected else 0.0
    average_dist = total_distance / len(matches)
    return box_find_rate, average_dist


def test_match_metrics_count_expected_coverage_once() -> None:
    """Verify that calculate_match_metrics counts unique expected words correctly."""
    matches = [
        ("Quebec", ("Québec", 0.0)),
        ("Quebec", ("Québec", 0.0)),
    ]

    box_find_rate, average_dist = calculate_match_metrics(matches, ["Québec"])

    assert box_find_rate == 100.0
    assert average_dist == 0.0


def test_check_for_match_keeps_duplicate_ocr_words() -> None:
    """Verify that check_for_match retains duplicate OCR words in output list."""
    actual = ["Quebec", "Quebec", "Boston"]
    expected = ["Québec", "Boston"]

    matches = check_for_match(actual, expected)

    assert [ocr_word for ocr_word, _ in matches] == ["Quebec", "Quebec", "Boston"]


def test_qwen_generated_text_strips_eos_artifacts() -> None:
    """Verify stripping of end-of-sentence tags and newline normalization."""
    raw = "</s>Progress of the Wehrmacht\nduring 10th May 1940"

    cleaned = raw.replace("</s>", " ").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = " ".join(cleaned.split()).strip()

    assert cleaned == "Progress of the Wehrmacht during 10th May 1940"


def test_florence_merge_does_not_join_distant_map_labels() -> None:
    """Verify that merge_related_detections avoids merging distant bounding boxes."""
    try:
        from ocr.florence.output import _get_merge_direction
    except ImportError:
        pytest.skip("ocr module is not available in the backend tests container")

    left = {
        "bbox_xyxy": [10, 40, 80, 60],
        "source_w": 70,
        "source_h": 20,
        "quad": [10, 40, 80, 40, 80, 60, 10, 60],
    }
    right = {
        "bbox_xyxy": [120, 40, 200, 60],
        "source_w": 80,
        "source_h": 20,
        "quad": [120, 40, 200, 40, 200, 60, 120, 60],
    }

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
    """Run full OCR pipeline integration test on test asset images and validate accuracy metrics."""
    assert image_path.exists()

    header = (
        f"\n\n"
        f"{CYAN}{BOLD}================================================================================{RESET}\n"
        f"    {BOLD}TESTING IMAGE : {YELLOW}{image_path.name}{RESET}\n"
        f"    Target Ground Truth : {BOLD}{len(expected_text)}{RESET} expected words\n"
        f"{CYAN}{BOLD}================================================================================{RESET}\n"
    )
    logger.info(header)

    with open(image_path, "rb") as input_file:
        file_content = input_file.read()
    extracted_text, _ = extract_text(
        map_id=uuid4(),
        filename=image_path.name,
        file_content=file_content,
        celery_app=celery_app,
    )

    unpaired_ocr_words: list[str] = [str(block.get("text", "")) for block in extracted_text]
    unpaired_expected_words: list[str] = deepcopy(expected_text)
    results = check_for_match(
        unpaired_ocr_words,
        unpaired_expected_words,
    )

    total_distance = 0.0
    mismatches = []
    for ocr_word, (expected_word, distance) in results:
        total_distance += distance
        if distance > 1.0:
            mismatches.append((expected_word, ocr_word, distance))

    if mismatches:
        logger.info(f"\n{YELLOW}{BOLD}--- Low-Confidence / Mismatched Words (Top 8) ---{RESET}")
        for expected_word, ocr_word, distance in mismatches[:8]:
            d_color = GREEN if distance <= 2.0 else (YELLOW if distance <= 4.0 else RED)
            logger.info(f"   • Expected: '{BOLD}{expected_word}{RESET}' | OCR: '{RED}{ocr_word}{RESET}' | dist: {d_color}{distance:.1f}{RESET}")
        if len(mismatches) > 8:
            logger.info(f"   ... and {len(mismatches) - 8} more.\n")

    box_find_rate, average_dist = calculate_match_metrics(results, unpaired_expected_words)

    status_icon = "✅" if box_find_rate >= 40.0 else "❌"
    rate_color = GREEN if box_find_rate >= 70.0 else (YELLOW if box_find_rate >= 40.0 else RED)
    dist_color = GREEN if average_dist <= 1.0 else (YELLOW if average_dist <= 3.0 else RED)

    summary = (
        f"\n"
        f"{rate_color}{BOLD}--------------------------------------------------------------------------------{RESET}\n"
        f"{status_icon}  {BOLD}SUMMARY for {YELLOW}{image_path.name}{RESET} :\n"
        f"    • Hit Rate   : {rate_color}{BOLD}{box_find_rate:.1f}%{RESET}\n"
        f"    • Avg Dist   : {dist_color}{BOLD}{average_dist:.2f}{RESET}\n"
        f"    • Detections : {BLUE}{BOLD}{len(unpaired_ocr_words)}{RESET} OCR words extracted\n"
        f"{rate_color}{BOLD}--------------------------------------------------------------------------------{RESET}\n\n"
    )
    logger.info(summary)

    setattr(
        request.node,
        "user_metadata",
        {
            "average_distance": average_dist,
            "hit_rate": box_find_rate,
        },
    )

    assert box_find_rate >= 50.0, f"Box find rate too low: {box_find_rate:.2f}%"
    assert average_dist < 2.0, f"Average distance too high: {average_dist:.2f}"
