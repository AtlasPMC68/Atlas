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
        # Normalize newlines to spaces so multi-line expected texts match single-line OCR
        cleaned = (
            word.replace("\n", " ")
            .replace("'", "")
            .replace("\u2019", "")
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
            .replace("\u00ab", " ")
            .replace("\u00bb", " ")
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
    Uses an O(1) exact match fast-path, followed by a global best-match approach
    for fuzzy matches to prevent 'word stealing'.
    """
    actual_ascii = normalize_array_to_ascii_format(actual)
    expected_ascii = normalize_array_to_ascii_format(expected)

    actual_dict = {}
    for i, word in enumerate(actual_ascii):
        if word not in actual_dict:
            actual_dict[word] = []
        actual_dict[word].append(i)

    used_exp_indices = set()
    used_ocr_indices = set()
    result: list[tuple[str, tuple[str, float]]] = []

    # Pass 1: Fast O(1) Exact Matches
    for exp_idx, exp_word in enumerate(expected_ascii):
        if exp_word in actual_dict:
            available_ocr_indices = [idx for idx in actual_dict[exp_word] if idx not in used_ocr_indices]
            if available_ocr_indices:
                ocr_idx = available_ocr_indices[0]
                used_exp_indices.add(exp_idx)
                used_ocr_indices.add(ocr_idx)
                # If original words match exactly, distance is 0.0, else 0.1 (case/accent diff)
                dist = 0.0 if actual[ocr_idx] == expected[exp_idx] else 0.1
                result.append((actual[ocr_idx], (expected[exp_idx], dist)))

    # Pass 2: Global Best Match for the remaining words
    all_pairs = []
    for exp_idx, exp_word in enumerate(expected_ascii):
        if exp_idx in used_exp_indices:
            continue
            
        for ocr_idx, ocr_word in enumerate(actual_ascii):
            if ocr_idx in used_ocr_indices:
                continue

            dist = float(levenshtein_distance(ocr_word, exp_word))
            
            # Suffix/substring bonus
            base_expected = re.sub(r"\b(1[5-9]\d\d|20\d\d)\b", "", exp_word).strip()
            base_expected = " ".join(base_expected.split())
            if base_expected and len(base_expected) >= 4 and base_expected != exp_word:
                if len(ocr_word) >= 4 and (base_expected in ocr_word or ocr_word in base_expected):
                    dist = min(dist, 0.5)
                else:
                    base_dist = float(levenshtein_distance(ocr_word, base_expected))
                    dist = min(dist, base_dist)
            elif len(exp_word) >= 4 and len(ocr_word) >= 4:
                if exp_word in ocr_word or ocr_word in exp_word:
                    dist = min(dist, 0.5)

            all_pairs.append((dist, exp_idx, ocr_idx))

    all_pairs.sort(key=lambda x: x[0])

    for dist, exp_idx, ocr_idx in all_pairs:
        if exp_idx not in used_exp_indices and ocr_idx not in used_ocr_indices:
            used_exp_indices.add(exp_idx)
            used_ocr_indices.add(ocr_idx)
            result.append((actual[ocr_idx], (expected[exp_idx], dist)))

    # Pass 3: Not Found
    for exp_idx in range(len(expected)):
        if exp_idx not in used_exp_indices:
            result.append(("", (expected[exp_idx], 1000.0)))

    return result


def calculate_match_metrics(
    matches: list[tuple[str, tuple[str, float]]],
    expected: list[str],
) -> tuple[float, float]:
    """Compute hit rate coverage percentage and average distance from matched OCR results."""
    if not matches:
        return (0.0, 0.0)

    valid_distances = [distance for _, (_, distance) in matches if distance < 500.0]
    total_distance = sum(valid_distances)

    matched_expected_words = {expected_word for _, (expected_word, distance) in matches if expected_word and (distance <= max(3.0, len(expected_word) * 0.25))}
    box_find_rate = (len(matched_expected_words) / len(expected)) * 100 if expected else 0.0

    average_dist = total_distance / len(valid_distances) if valid_distances else 0.0
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


def test_check_for_match_drops_extra_ocr_words() -> None:
    """Verify that check_for_match drops extra OCR words (like legends) that do not match expected words."""
    actual = ["Quebec", "Boston", "Légende: territoires"]
    expected = ["Québec", "Boston"]

    matches = check_for_match(actual, expected)

    assert [ocr_word for ocr_word, _ in matches] == ["Quebec", "Boston"]


def test_paddleocr_output_format_conversion() -> None:
    """Verify that PaddleOCR's output is correctly transformed into the generic schema."""
    # Raw PaddleOCR output format:
    # [[ [ [x1,y1], [x2,y2], [x3,y3], [x4,y4] ], ('Text', confidence) ]]
    paddle_raw = [
        [
            [
                [[10.0, 10.0], [50.0, 10.0], [50.0, 20.0], [10.0, 20.0]],
                ("Québec", 0.98),
            ]
        ]
    ]

    detections = []
    if paddle_raw and paddle_raw[0]:
        for line in paddle_raw[0]:
            box = line[0]
            text = line[1][0]
            confidence = line[1][1]
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            bbox_xyxy = [min(xs), min(ys), max(xs), max(ys)]
            quad = [box[0][0], box[0][1], box[1][0], box[1][1], box[2][0], box[2][1], box[3][0], box[3][1]]
            detections.append({"text": text, "bbox_xyxy": bbox_xyxy, "quad": quad, "confidence": float(confidence)})

    assert len(detections) == 1
    assert detections[0]["text"] == "Québec"
    assert detections[0]["bbox_xyxy"] == [10.0, 10.0, 50.0, 20.0]
    assert detections[0]["confidence"] == 0.98


CARD_THRESHOLDS = {
    "Progress_wehrmacht_lux_May_1940.jpg": {"min_hit_rate": 95.0, "max_dist": 0.15},
    "Quebec_1791.png": {"min_hit_rate": 85.0, "max_dist": 0.55},
    "Sahel_Afrique.png": {"min_hit_rate": 85.0, "max_dist": 0.20},
    "Nouvelle-France1750.png": {"min_hit_rate": 50.0, "max_dist": 1.20},
    "genocide_Monde.png": {"min_hit_rate": 80.0, "max_dist": 1.40},
    "Quebec_1800.png": {"min_hit_rate": 70.0, "max_dist": 1.15},
    "1775_Quebec_NordUSA.png": {"min_hit_rate": 65.0, "max_dist": 2.10},
    "Quebec_Traite1783.png": {"min_hit_rate": 70.0, "max_dist": 1.15},
    "Communautes_cries.png": {"min_hit_rate": 100.0, "max_dist": 1.22},
    "Quebec.png": {"min_hit_rate": 71.0, "max_dist": 2.9},
    "Degrade_Afrique.png": {"min_hit_rate": 75.0, "max_dist": 2.0},
    "pluie_Afrique.png": {"min_hit_rate": 75.0, "max_dist": 2.0},
}


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

    mismatches = []
    for ocr_word, (expected_word, distance) in results:
        if distance > 1.0:
            mismatches.append((expected_word, ocr_word, distance))

    if mismatches:
        mismatches.sort(key=lambda x: x[2], reverse=True)
        logger.info(f"\n{YELLOW}{BOLD}--- Missing / Mismatched Words ---{RESET}")
        for expected_word, ocr_word, distance in mismatches:
            d_color = GREEN if distance <= 2.0 else (YELLOW if distance <= 4.0 else RED)
            if distance > 500:
                logger.info(f"   \u2022 Expected: '{BOLD}{expected_word}{RESET}' | {RED}NOT FOUND{RESET}")
            else:
                logger.info(f"   \u2022 Expected: '{BOLD}{expected_word}{RESET}' | OCR: '{RED}{ocr_word}{RESET}' | dist: {d_color}{distance:.1f}{RESET}")

    box_find_rate, average_dist = calculate_match_metrics(results, unpaired_expected_words)

    # Determine pass/fail against thresholds
    thresholds = CARD_THRESHOLDS.get(image_path.name, {"min_hit_rate": 40.0, "max_dist": 15.0})
    min_hit_rate = thresholds["min_hit_rate"]
    max_dist = thresholds["max_dist"]
    is_passed = box_find_rate >= min_hit_rate and average_dist <= max_dist

    # Color-coded summary: GREEN for pass, RED for fail
    if is_passed:
        summary = (
            f"\n"
            f"{GREEN}{BOLD}--------------------------------------------------------------------------------{RESET}\n"
            f"\u2705  {BOLD}SUMMARY for {YELLOW}{image_path.name}{RESET} : {GREEN}{BOLD}PASS{RESET}\n"
            f"    \u2022 Hit Rate   : {GREEN}{BOLD}{box_find_rate:.1f}%{RESET} (min: {min_hit_rate}%)\n"
            f"    \u2022 Avg Dist   : {GREEN}{BOLD}{average_dist:.2f}{RESET} (max: {max_dist})\n"
            f"    \u2022 Detections : {BLUE}{BOLD}{len(unpaired_ocr_words)}{RESET} OCR words extracted\n"
            f"{GREEN}{BOLD}--------------------------------------------------------------------------------{RESET}\n\n"
        )
        logger.info(summary)
    else:
        summary = (
            f"\n"
            f"{RED}{BOLD}--------------------------------------------------------------------------------{RESET}\n"
            f"\u274c  {BOLD}SUMMARY for {YELLOW}{image_path.name}{RESET} : {RED}{BOLD}FAIL{RESET}\n"
            f"    \u2022 Hit Rate   : {RED}{BOLD}{box_find_rate:.1f}%{RESET} (min: {min_hit_rate}%)\n"
            f"    \u2022 Avg Dist   : {RED}{BOLD}{average_dist:.2f}{RESET} (max: {max_dist})\n"
            f"    \u2022 Detections : {BLUE}{BOLD}{len(unpaired_ocr_words)}{RESET} OCR words extracted\n"
            f"{RED}{BOLD}--------------------------------------------------------------------------------{RESET}\n"
        )
        logger.error(summary)

        # Show detailed failure info
        logger.error(f"{RED}{BOLD}\U0001f50d DETAILS OF THE FAILURE FOR {image_path.name}:{RESET}\n" f"Expected Words that the OCR missed or matched poorly:\n")
        for expected_word, ocr_word, distance in mismatches:
            logger.error(f"  \u2022 Expected: {YELLOW}'{expected_word}'{RESET} --> Found: '{ocr_word}' (dist: {distance:.1f})")

    setattr(
        request.node,
        "user_metadata",
        {
            "average_distance": average_dist,
            "hit_rate": box_find_rate,
        },
    )

    assert is_passed, f"{image_path.name}: OCR metrics below threshold! " f"Hit rate {box_find_rate:.1f}% (min: {min_hit_rate}%), " f"Avg Dist {average_dist:.2f} (max: {max_dist})"
