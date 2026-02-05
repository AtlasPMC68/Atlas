import cv2
import json
import pytest
import warnings
import unicodedata
import numpy as np
from pathlib import Path
from copy import deepcopy
from tests.utils.expected_results import MAP_EXPECTED_TEXTS
from app.utils.text_extraction import extract_text
from weighted_levenshtein import lev

def custom_formatwarning(message, category, filename, lineno, line=None):
    """Returns the warning with a custom format"""
    return f"{category.__name__}: {message}\n"

warnings.formatwarning = custom_formatwarning

def get_image_paths():
    """
    Locates the assets folder relative to this file and
    collects all images paths with supported extensions.
    """
    valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp', '.ppm', '.pgm', '.pbm')

    current_dir = Path(__file__).parent
    assets_dir = current_dir / "assets"

    if not assets_dir.exists():
        # Using a warning here ensures visibility during collection
        pytest.fail(
            UserWarning("Searching for assets in non-existent directory: {assets_dir}")
        )
        return []

    return [
        p for p in assets_dir.iterdir()
        if p.suffix.lower() in valid_extensions
    ]

def get_test_data():
    """"""
    images = get_image_paths()
    data = []
    for img in images:
        expected = MAP_EXPECTED_TEXTS.get(img.stem)
        if expected:
            # For each image, pull: (image path, word list)
            data.append((img, expected))
    return data

def normalize_array_to_ascii_format(text: list[str]) -> dict[str, str]:
    """Replace all characters to ASCII format"""

    res: dict[str, str] = {}
    for word in text:
        res[word] = (unicodedata
                     .normalize('NFKD', word)
                     .encode('ascii', 'ignore')
                     .decode('ascii'))
    return res

def check_for_match(actual: list[str], expected: list[str], levenshtein_params: dict[str, np.ndarray]) -> dict[str, tuple[str, int]]:
    """
    For every `expected` word given in an array, return a tuple composed of the
    OCR word that matches the most, and the weighted levenshtein distance between
    both strings.

    :param actual: list of strings read by the OCR in this test instance
    :param expected: list of expected strings. Hardcoded.
    :param levenshtein_params: dictionary with weighted distance cost for each operation on ASCII characters
    :return: dict of (word, levenshtein distance), using exepected as keys
    """
    actual_ascii_dict = normalize_array_to_ascii_format(actual)
    expected_ascii_dict = normalize_array_to_ascii_format(expected)
    res: dict[str, tuple[str, float]] = {}

    # Try to find the closest match for every read wor
    for expected_word, expected_word_ascii in expected_ascii_dict.items():

        min_dist: tuple[str, float] = ("a", 1000.0)
        for ocr_word, ocr_word_ascii in actual_ascii_dict.items():

            # Perfect match
            if ocr_word == expected_word:
                min_dist = (ocr_word, 0.0)
                break

            # Pefect ASCII match
            elif ocr_word_ascii == expected_word_ascii and min_dist[1] < 0.1:
                min_dist = (ocr_word, 0.1)
                break

            # Partial match
            else:
                tmp_dist = lev(ocr_word_ascii,expected_word_ascii,**levenshtein_params)
                if tmp_dist < min_dist[1]:
                    min_dist = (ocr_word, tmp_dist)

        # After checking all possible match, save the closest match
        res[expected_word] = min_dist
    return res


# Load once in RAM during each test in THIS file. Simply adding
# the file name as an argument to a function will inject the reference.
@pytest.fixture(scope="module")
def levenshtein_params():
    current_dir = Path(__file__).parent
    json_dir = current_dir / "utils" / "weighted_levenshtein.json"

    with open(json_dir, "r") as f:
        leven_params = json.load(f)

    for k in leven_params.keys():
        leven_params[k] = np.array(leven_params[k], dtype=np.float64)
    return leven_params

@pytest.mark.parametrize(
    "image_path, expected_text",
    get_test_data(),
    ids=lambda val: val.name if isinstance(val, Path) else None
)
def test_text_extraction(image_path, expected_text, levenshtein_params):

    assert image_path.exists()
    img = cv2.imread(str(image_path))
    found_texts, _ = extract_text(image=img, languages=['en', 'fr'], gpu_acc=False)

    # Prepare text lists
    remaining_ocr_words: list[str] = [res[1] for res in found_texts]
    remaining_expected_words: list[str] = deepcopy(expected_text)

    # Critical failure in case we cannot find EVERY bounding box of text!
    #assert len(remaining_ocr_words) == len(remaining_expected_words)

    res: dict[str, tuple[str, float]] = check_for_match(remaining_ocr_words, remaining_expected_words, levenshtein_params)

    # For anything other than
    for expected_word, (ocr_word, distance) in res.items():
        if distance >= 0.0:
            warnings.warn(UserWarning( f"Partial match for expected: '{expected_word}', and found '{ocr_word}' (d = {distance})."))

