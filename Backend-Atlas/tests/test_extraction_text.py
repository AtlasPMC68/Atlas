import logging
import re
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from app.celery_app import celery_app
from app.utils.cities_validation import get_city_with_max_population
from app.utils.text_extraction import extract_text
from Levenshtein import distance as levenshtein_distance

from tests.utils.expected_text_results import MAP_EXPECTED_TEXTS, MAP_EXPECTED_DETECTION_COUNTS

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
        if expected is None:
            logger.warning(f"Skipping {image.name}: Missing expected text in MAP_EXPECTED_TEXTS.")
            continue
        data.append((image, expected))
    return data


def normalize_array_to_ascii_format(text: list[str]) -> list[str]:
    # Text normalization:
    # - Replaces with space: \n, -, (), :, ;, ?, !, ", «, », /, \
    # - Removes completely: ' (straight apostrophe), \u2019 (typographic apostrophe), ., ,

    res = []
    for word in text:
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

    for exp_idx, exp_word in enumerate(expected_ascii):
        if exp_word in actual_dict:
            available_ocr_indices = [idx for idx in actual_dict[exp_word] if idx not in used_ocr_indices]
            if available_ocr_indices:
                ocr_idx = available_ocr_indices[0]
                used_exp_indices.add(exp_idx)
                used_ocr_indices.add(ocr_idx)
                dist = 0.0 if actual[ocr_idx] == expected[exp_idx] else 0.1
                result.append((actual[ocr_idx], (expected[exp_idx], dist)))

    all_pairs = []
    for exp_idx, exp_word in enumerate(expected_ascii):
        if exp_idx in used_exp_indices:
            continue

        for ocr_idx, ocr_word in enumerate(actual_ascii):
            if ocr_idx in used_ocr_indices:
                continue

            dist = float(levenshtein_distance(ocr_word, exp_word))

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

    MAX_ALLOWED_DIST = 6.0

    for dist, exp_idx, ocr_idx in all_pairs:
        if exp_idx not in used_exp_indices and ocr_idx not in used_ocr_indices:
            if dist <= MAX_ALLOWED_DIST:
                used_exp_indices.add(exp_idx)
                used_ocr_indices.add(ocr_idx)
                result.append((actual[ocr_idx], (expected[exp_idx], dist)))

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

    logger.info(f"\n{CYAN}{BOLD}▶ [TESTING]{RESET} {YELLOW}{image_path.name}{RESET} (Attendu: {len(expected_text)} mots)")

    with open(image_path, "rb") as input_file:
        file_content = input_file.read()
    extracted_text, _ = extract_text(
        map_id=uuid4(),
        filename=image_path.name,
        file_content=file_content,
        celery_app=celery_app,
    )

    # Check Florence raw text zones count without blocking the rest of the pipeline
    expected_count = MAP_EXPECTED_DETECTION_COUNTS.get(image_path.stem)
    count_passed = True
    count_error_msg = ""
    if expected_count is not None:
        if len(extracted_text) != expected_count:
            count_passed = False
            count_error_msg = f"Zones: {len(extracted_text)} détectées vs {expected_count} attendues"
            logger.warning(f"⚠️ [{image_path.name}] {count_error_msg}")
    else:
        logger.warning(f"No expected detection count found for {image_path.name} in MAP_EXPECTED_DETECTION_COUNTS.")

    unpaired_ocr_words: list[str] = [str(block.get("text", "")) for block in extracted_text]
    unpaired_expected_words: list[str] = deepcopy(expected_text)

    results = check_for_match(
        unpaired_ocr_words,
        unpaired_expected_words,
    )

    mismatches = [
        (expected_word, ocr_word, distance)
        for ocr_word, (expected_word, distance) in results
        if distance > 1.0
    ]

    box_find_rate, average_dist = calculate_match_metrics(results, unpaired_expected_words)

    thresholds = CARD_THRESHOLDS.get(image_path.name, {"min_hit_rate": 40.0, "max_dist": 15.0})
    min_hit_rate = thresholds["min_hit_rate"]
    max_dist = thresholds["max_dist"]

    hit_rate_passed = round(box_find_rate, 2) >= min_hit_rate
    dist_passed = round(average_dist, 2) <= max_dist
    is_passed = hit_rate_passed and dist_passed and count_passed

    if is_passed:
        status_color, status_icon, status_text = GREEN, "✅", "PASS"
    elif (hit_rate_passed and dist_passed) or (hit_rate_passed and count_passed):
        status_color, status_icon, status_text = YELLOW, "⚠️", "WARNING"
    else:
        status_color, status_icon, status_text = RED, "❌", "FAIL"

    hit_color = GREEN if hit_rate_passed else RED
    dist_color = GREEN if dist_passed else RED
    card_name_fmt = f"{CYAN}{BOLD}{image_path.name}{RESET}"

    geocache_accepted = []
    geocache_unrecognized = []
    for word in unpaired_ocr_words:
        candidate = get_city_with_max_population(word, confidence_threshold=0.60)
        if candidate.get("found"):
            geocache_accepted.append(word)
        else:
            geocache_unrecognized.append(word)

    summary = (
        f"{status_icon} {status_color}{BOLD}[{status_text}] {card_name_fmt}{RESET} | "
        f"Hit: {hit_color}{box_find_rate:.1f}%{RESET} (min: {min_hit_rate}%) | "
        f"Dist: {dist_color}{average_dist:.2f}{RESET} (max: {max_dist}) | "
        f"Mots détectés par florence/ Mots non-rejetés: {BLUE}{len(unpaired_ocr_words)}{RESET}/{len(unpaired_expected_words)} | "
        f"Géocache: {GREEN}{len(geocache_accepted)} acceptés{RESET} vs {RED}{len(geocache_unrecognized)} non reconnus{RESET}"
    )

    if is_passed:
        logger.info(summary)
    else:
        log_fn = logger.warning if status_text == "WARNING" else logger.error
        log_fn(summary)
        if not count_passed:
            log_fn(f"  {YELLOW}Écart de détection :{RESET} {RED}{count_error_msg}{RESET}")
        if geocache_unrecognized:
            log_fn(f"  {YELLOW}Mots non reconnus par la géocache :{RESET} {RED}{', '.join(geocache_unrecognized)}{RESET}")
        if mismatches:
            mismatches.sort(key=lambda x: x[2], reverse=True)
            log_fn(f"  {YELLOW}Mots manquants ou mal reconnus :{RESET}")
            for expected_word, ocr_word, distance in mismatches:
                if distance > 500:
                    log_fn(f"    \u2022 Attendu: '{BOLD}{expected_word}{RESET}' | {RED}NON TROUVÉ{RESET}")
                else:
                    d_color = GREEN if distance <= 2.0 else (YELLOW if distance <= 4.0 else RED)
                    log_fn(f"    \u2022 Attendu: '{BOLD}{expected_word}{RESET}' | Trouvé: '{RED}{ocr_word}{RESET}' (dist: {d_color}{distance:.1f}{RESET})")

    from tests.conftest import metadata_key
    request.node.stash[metadata_key] = {
        "average_distance": average_dist,
        "hit_rate": box_find_rate,
    }

    reasons = []
    if not hit_rate_passed:
        reasons.append(f"Hit={box_find_rate:.1f}% (min {min_hit_rate}%)")
    if not dist_passed:
        reasons.append(f"Dist={average_dist:.2f} (max {max_dist})")
    if not count_passed:
        reasons.append(count_error_msg)

    error_msg = f"ÉCHEC {image_path.name}: " + ", ".join(reasons)
    assert is_passed, error_msg
