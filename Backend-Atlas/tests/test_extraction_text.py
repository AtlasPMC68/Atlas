import cv2
import json
import pytest
import unicodedata
import numpy as np
from pathlib import Path
from copy import deepcopy
from tests.utils.expected_results import MAP_EXPECTED_TEXTS
from app.utils.text_extraction import extract_text
from weighted_levenshtein import lev

def get_image_paths():
    """
    Locates the assets folder relative to this file and
    collects all images paths with supported extensions.
    """
    # Path of the current test file
    current_dir = Path(__file__).parent
    assets_dir = current_dir / "assets"
    print(assets_dir)
    print("testing printing")

    # Define supported extensions
    extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp', '.ppm', '.pgm', '.pbm')

    images = []
    if assets_dir.exists():
        for ext in extensions:
            images.extend(assets_dir.glob(ext))

    return images

def get_test_data():
    """"""
    images = get_image_paths()
    data = []
    for img in images:
        expected = MAP_EXPECTED_TEXTS.get(img.stem)
        if expected:
            # On crée un tuple (path, list) pour chaque test
            data.append((img, expected))
    return data

def normalize_to_ascii_format(text: str) -> str:
    """Remove accents from words, then encore to ascii"""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')

def check_for_perfect_match(actual: list[str], expected: list[str]):
    # First try to match perfectly the words
    for target in expected:
        if target in actual:
            expected.remove(target)
            actual.remove(target)

def check_for_partial_match(actual: list[str], expected: list[str]) -> float:
    best_match_idx = -1
    min_dist = float('inf')

    for i, text in actual:

        # Check if ASCII conversion matches
        if text in expected:
            min_dist = 0
            best_match_idx = i
            break


        # Calculate weighted distance between words
        current_dist = lev(found_ascii, target_ascii, **levenshtein_params)
        if current_dist < min_dist:
            min_dist = current_dist
            best_match_idx = i

# Load once in RAM during each test in THIS file. Simply adding
# the file name as an argument to a function will inject the reference.
@pytest.fixture(scope="module")
def levenshtein_params():
    current_dir = Path(__file__).parent
    json_dir = current_dir / "utils" / "weighted_levenshtein.json"

    with open("json_dir", "r") as f:
        leven_params = json.load(f)

    for k in leven_params.keys():
        leven_params[k] = np.array(leven_params[k], dtype=np.float64)
    return leven_params

@pytest.mark.parametrize(
    "image_path, expected_text",
    get_test_data(),
    ids=lambda val: val[0].name
)
def test_text_extraction(image_path, expected_text, levenshtein_params):

    assert image_path.exists()
    img = cv2.imread(str(image_path))
    found_texts, _ = extract_text(image=img, languages=['en', 'fr'], gpu_acc=False)

    # Prepare text lists
    remaining_found = [res[1] for res in found_texts]
    remaining_expected = deepcopy(expected_text)
    assert len(remaining_found) == len(remaining_expected)

    # Check for perfect match. Pop values from arrays if found
    check_for_perfect_match(actual=remaining_found, expected=remaining_expected)

    # Convert remaining text to ASCII. Necessary to calculate the Levenshtein
    # distance between the OCR text and the expected one
    remaining_found_ascii = []
    remaining_expected_ascii = []
    for text in remaining_found:
        remaining_found_ascii.append(normalize_to_ascii_format(text))
    for text in remaining_expected:
        remaining_expected_ascii.append(normalize_to_ascii_format(text))

    # Check for partial ASCII match. Pop values from text with the closest distance.
    distance, len = check_for_partial_match(actual=remaining_found_ascii, expected=remaining_expected_ascii)


    # Then pass again, and try to match as best as possible
    for target in list(remaining_expected):
        target_ascii = normalize_to_ascii_format(target)

        # Best match
        threshold = len(target_ascii) * 0.25
        if min_dist <= threshold:
            remaining_expected.remove(target)
            # Finally remove the word since we consider it a match, even if only partial
            if best_match_idx != -1:
                remaining_found.pop(best_match_idx)

        # --- ASSERTION FINALE ---
    if len(remaining_expected) > 0:
        pytest.fail(
            f"Mots non trouvés dans {image_path.name}: {remaining_expected}\n"
            f"Mots OCR restants : {remaining_found}"
        )

