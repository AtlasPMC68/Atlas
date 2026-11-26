import logging
import unicodedata
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from app.utils.place_resolution import match_ocr_label
from app.utils.text_extraction import extract_text
from Levenshtein import distance as levenshtein_distance

from tests.utils.expected_text_results import (
    CARD_THRESHOLDS,
    COUNT_TOLERANCE_RATIO,
    DEFAULT_THRESHOLDS,
    MAP_EXPECTED_TEXTS,
    MAP_EXPECTED_ZONE_DETECTION_COUNTS,
)

logger = logging.getLogger(__name__)

CYAN = "\033[96m"
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


@pytest.fixture(autouse=True)
def clean_log_format_for_extraction(request: pytest.FixtureRequest):
    """Format logs without module prefixes and set log level configured in pytest.ini."""
    if request.node.name.startswith("test_ocr_raw_detection_count"):
        target_level = logging.WARNING
    else:
        show_info = request.config.getini("extraction_log_info")
        target_level = logging.INFO if show_info else logging.WARNING

    clean_formatter = logging.Formatter("%(levelname)-8s %(message)s")

    captured_handlers = []
    old_levels = []
    for handler in logging.root.handlers:
        captured_handlers.append((handler, handler.formatter))
        old_levels.append((handler, handler.level))
        handler.setFormatter(clean_formatter)
        handler.setLevel(target_level)

    ocr_logger = logging.getLogger("app.utils.text_extraction")
    old_ocr_level = ocr_logger.level
    ocr_logger.setLevel(target_level)

    old_root_level = logging.root.level
    logging.root.setLevel(target_level)

    yield

    ocr_logger.setLevel(old_ocr_level)
    for handler, original_formatter in captured_handlers:
        handler.setFormatter(original_formatter)
    for handler, original_level in old_levels:
        handler.setLevel(original_level)
    logging.root.setLevel(old_root_level)


def get_image_paths() -> list[Path]:
    """Retrieve all test image paths from the tests/assets directory."""
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
        pytest.fail(f"Directory not found: {assets_dir}")
        return []

    return [p for p in assets_dir.iterdir() if p.suffix.lower() in valid_extensions]


_TEST_DATA_CACHE: list[tuple[Path, list[str]]] | None = None


def get_test_data() -> list[tuple[Path, list[str]]]:
    """Load map paths and their corresponding expected ground truth texts."""
    global _TEST_DATA_CACHE
    if _TEST_DATA_CACHE is not None:
        return _TEST_DATA_CACHE

    images = get_image_paths()
    data: list[tuple[Path, list[str]]] = []
    for image in images:
        expected = MAP_EXPECTED_TEXTS.get(image.stem)
        if expected is None:
            logger.warning(f"Skipping {image.name}: expected text missing in MAP_EXPECTED_TEXTS.")
            continue
        data.append((image, expected))
    _TEST_DATA_CACHE = data
    return _TEST_DATA_CACHE


def normalize_array_to_ascii_format(text: list[str]) -> list[str]:
    """Normalize a list of strings into lowercase ASCII without punctuation."""
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


# An expected text is found when its character error is at most this
HIT_MAX_ERROR = 0.20

# Beyond HIT_MAX_ERROR, a block is still paired with an expected text up to this
# error, to show the near misses
PAIR_MAX_ERROR = 0.50


def text_error(found: str, expected: str) -> float:
    """Character error of a normalized text against the expected one: 0 when exact, up to 1."""
    return min(1.0, levenshtein_distance(found, expected) / max(len(expected), 1))


def check_for_match(
    actual: list[str],
    expected: list[str],
) -> list[tuple[str, str, float]]:
    """
    Pair each expected text with at most one OCR block, the closest pairs first.
    Texts are compared lowercase, without accents nor punctuation.

    Returns: one (expected text, OCR block, error) per expected text, in order.
    The block is "" and the error 1.0 when no block is close enough.
    """
    actual_ascii = normalize_array_to_ascii_format(actual)
    expected_ascii = normalize_array_to_ascii_format(expected)
    pairs = sorted(
        (text_error(found, wanted), exp_idx, ocr_idx)
        for exp_idx, wanted in enumerate(expected_ascii)
        for ocr_idx, found in enumerate(actual_ascii)
    )

    paired: dict[int, tuple[int, float]] = {}
    used_ocr_indices = set()
    for error, exp_idx, ocr_idx in pairs:
        if error > PAIR_MAX_ERROR:
            break
        if exp_idx in paired or ocr_idx in used_ocr_indices:
            continue
        paired[exp_idx] = (ocr_idx, error)
        used_ocr_indices.add(ocr_idx)

    return [
        (wanted, actual[paired[exp_idx][0]], paired[exp_idx][1]) if exp_idx in paired else (wanted, "", 1.0)
        for exp_idx, wanted in enumerate(expected)
    ]


def calculate_match_metrics(
    matches: list[tuple[str, str, float]],
    block_count: int,
) -> tuple[float, float, float]:
    """
    Metrics of check_for_match results, over every expected text:
        - hit rate: % of the expected texts found
        - precision: % of the OCR blocks that are an expected text
        - average error: mean character error, a missing text counting as 1
    """
    if not matches:
        return 0.0, 0.0, 0.0
    hits = sum(1 for _, _, error in matches if error <= HIT_MAX_ERROR)
    hit_rate = hits / len(matches) * 100
    precision = hits / block_count * 100 if block_count else 0.0
    average_error = sum(error for _, _, error in matches) / len(matches)
    return hit_rate, precision, average_error


def test_check_for_match_pairs_each_block_once() -> None:
    """Each expected text gets its own block, and a text without a close block is missing."""
    actual = ["Quebec", "Quebec", "Bostn", "Légende: territoires"]
    expected = ["Québec", "Boston", "New York"]

    assert check_for_match(actual, expected) == [
        ("Québec", "Quebec", 0.0),
        ("Boston", "Bostn", 1 / 6),
        ("New York", "", 1.0),
    ]


def test_match_metrics_count_every_expected_text() -> None:
    """Missing texts lower the hit rate and count as an error of 1, extra blocks lower the precision."""
    matches = [("Québec", "Quebec", 0.0), ("Boston", "Bostn", 1 / 6), ("New York", "", 1.0)]

    hit_rate, precision, average_error = calculate_match_metrics(matches, block_count=4)

    assert round(hit_rate, 1) == 66.7
    assert precision == 50.0
    assert round(average_error, 3) == round((0.0 + 1 / 6 + 1.0) / 3, 3)


_OCR_RESULT_CACHE: dict[Path, list[dict[str, Any]]] = {}


def get_extracted_text_cached(image_path: Path) -> list[dict[str, Any]]:
    """Execute the OCR pipeline once per image and cache result across tests."""
    if image_path not in _OCR_RESULT_CACHE:
        with open(image_path, "rb") as input_file:
            file_content = input_file.read()
        extracted_text = extract_text(
            map_id=uuid4(),
            image_bytes=file_content,
        )
        _OCR_RESULT_CACHE[image_path] = extracted_text
    return _OCR_RESULT_CACHE[image_path]


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize(
    "image_path, expected_text",
    get_test_data(),
    ids=lambda val: val.name if isinstance(val, Path) else None,
)
def test_ocr_raw_detection_count(
    image_path: Path,
    expected_text: list[str],
) -> None:
    """
    Test the count of text zones given by the OCR, without evaluating textual accuracy:
    within COUNT_TOLERANCE_RATIO of the expected count.
    """
    assert image_path.exists()
    expected_count = MAP_EXPECTED_ZONE_DETECTION_COUNTS.get(image_path.stem)
    if expected_count is None:
        pytest.skip(f"No expected detection count in MAP_EXPECTED_DETECTION_COUNTS for {image_path.name}")

    extracted_text = get_extracted_text_cached(image_path)
    actual_count = len(extracted_text)

    count_ratio = actual_count / expected_count
    if abs(count_ratio - 1) > COUNT_TOLERANCE_RATIO:
        error_msg = (
            f"Text zones (OCR): {actual_count} detected vs {expected_count} expected in "
            f"MAP_EXPECTED_ZONE_DETECTION_COUNTS ({count_ratio:.0%}, "
            f"{1 - COUNT_TOLERANCE_RATIO:.0%} to {1 + COUNT_TOLERANCE_RATIO:.0%} allowed)"
        )
        pytest.fail(error_msg, pytrace=False)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize(
    "image_path, expected_text",
    get_test_data(),
    ids=lambda val: val.name if isinstance(val, Path) else None,
)
def test_text_extraction_accuracy(
    image_path: Path,
    expected_text: list[str],
    request: pytest.FixtureRequest,
) -> None:
    """
    Validate text extraction accuracy over every expected text: hit rate and character
    error. The precision is reported only, test_ocr_raw_detection_count checks the extra blocks.
    """
    assert image_path.exists()

    logger.info(f"\n{CYAN}{BOLD}▶ [TESTING]{RESET} {YELLOW}{image_path.name}{RESET} (Expected: {len(expected_text)} texts)")

    extracted_text = get_extracted_text_cached(image_path)

    unpaired_ocr_words: list[str] = [str(block.get("text", "")) for block in extracted_text]
    unpaired_expected_words: list[str] = deepcopy(expected_text)

    results = check_for_match(
        unpaired_ocr_words,
        unpaired_expected_words,
    )

    box_find_rate, precision, average_dist = calculate_match_metrics(results, len(unpaired_ocr_words))

    # Expected texts not exact, the worst first, and blocks matching no expected text
    mismatches = sorted(
        ((expected_word, ocr_word, error) for expected_word, ocr_word, error in results if error > 0),
        key=lambda mismatch: mismatch[2],
        reverse=True,
    )
    hit_blocks = Counter(ocr_word for _, ocr_word, error in results if error <= HIT_MAX_ERROR)
    extra_blocks = []
    for word in unpaired_ocr_words:
        if hit_blocks[word]:
            hit_blocks[word] -= 1
        else:
            extra_blocks.append(" ".join(word.split()))

    thresholds = {**DEFAULT_THRESHOLDS, **CARD_THRESHOLDS.get(image_path.stem, {})}
    min_hit_rate = thresholds["min_hit_rate"]
    max_dist = thresholds["max_dist"]

    hit_rate_passed = round(box_find_rate, 1) >= round(min_hit_rate, 1)
    dist_passed = round(average_dist, 2) <= round(max_dist, 2)
    is_passed = hit_rate_passed and dist_passed

    if is_passed:
        status_color, status_icon, status_text = GREEN, "✅", "PASS"
    elif hit_rate_passed or dist_passed:
        status_color, status_icon, status_text = YELLOW, "⚠️", "WARNING"
    else:
        status_color, status_icon, status_text = RED, "❌", "FAIL"

    hit_color = GREEN if hit_rate_passed else RED
    dist_color = GREEN if dist_passed else RED
    card_name_fmt = f"{CYAN}{BOLD}{image_path.name}{RESET}"

    geocache_accepted = []
    geocache_unrecognized = []
    seen_accepted = set()
    seen_unrecognized = set()
    for word in unpaired_ocr_words:
        candidate = match_ocr_label(word)
        display_word = " ".join(str(word).split())
        if candidate is not None:
            matched_name = " ".join(str(candidate.get("name") or "").split())
            entry = f"'{display_word}' -> '{matched_name}'"
            if entry not in seen_accepted:
                seen_accepted.add(entry)
                geocache_accepted.append(entry)
        else:
            if display_word not in seen_unrecognized:
                seen_unrecognized.add(display_word)
                geocache_unrecognized.append(display_word)

    summary_lines = [
        f"\n{status_icon} {status_color}{BOLD}[{status_text}] {card_name_fmt}{RESET}",
        f"   • Hit Rate : {hit_color}{box_find_rate:.1f}%{RESET} (min: {min_hit_rate}%)",
        f"   • Precision: {BLUE}{precision:.1f}%{RESET} (reported only)",
        f"   • Distance : {dist_color}{average_dist:.2f}{RESET} (max: {max_dist})",
        f"   • OCR Texts: {BLUE}{len(unpaired_ocr_words)}{RESET} detected / {len(unpaired_expected_words)} expected",
        f"   • GeoNames : {GREEN}{len(geocache_accepted)} accepted{RESET} vs {RED}{len(geocache_unrecognized)} unrecognized{RESET}",
    ]

    show_detailed_mismatches = request.config.getini("extraction_log_info")
    if show_detailed_mismatches:
        if geocache_accepted:
            summary_lines.append(f"   {GREEN}• Accepted GeoNames: {' | '.join(geocache_accepted)}{RESET}")
        if geocache_unrecognized:
            summary_lines.append(f"   {YELLOW}• Unrecognized GeoNames: {' | '.join(geocache_unrecognized)}{RESET}")
        if mismatches:
            summary_lines.append(f"   • {YELLOW}Detection mismatches (approximate or missing texts):{RESET}")
            for expected_word, ocr_word, distance in mismatches:
                if not ocr_word:
                    summary_lines.append(f"       - Expected: '{BOLD}{expected_word}{RESET}' | {RED}NOT FOUND{RESET}")
                else:
                    d_color = GREEN if distance <= HIT_MAX_ERROR else (YELLOW if distance <= 0.35 else RED)
                    found = " ".join(ocr_word.split())
                    summary_lines.append(
                        f"       - Expected: '{BOLD}{expected_word}{RESET}' | Found: '{RED}{found}{RESET}' (dist: {d_color}{distance:.2f}{RESET})"
                    )
        if extra_blocks:
            summary_lines.append(f"   • {YELLOW}OCR blocks matching no expected text:{RESET} {' | '.join(extra_blocks)}")

    log_fn = logger.error if status_text == "FAIL" else logger.warning
    log_fn("\n".join(summary_lines))

    from tests.conftest import metadata_key

    request.node.stash[metadata_key] = {
        "card_name": image_path.name,
        "average_distance": average_dist,
        "hit_rate": box_find_rate,
        "precision": precision,
        "min_hit_rate": min_hit_rate,
        "max_dist": max_dist,
    }

    reasons = []
    if not hit_rate_passed:
        reasons.append(f"Hit={box_find_rate:.1f}% (min {min_hit_rate}%)")
    if not dist_passed:
        reasons.append(f"Dist={average_dist:.2f} (max {max_dist})")

    error_msg = f"FAILED {image_path.name}: " + ", ".join(reasons)
    if not is_passed:
        pytest.fail(error_msg, pytrace=False)
