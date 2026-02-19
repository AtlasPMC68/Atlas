import os
import glob
import tempfile
from typing import Dict, Tuple

import numpy as np
import pytest
import imageio.v3 as iio

from app.utils.color_extraction import extract_colors


# Run with:
# docker-compose run --rm test-backend pytest tests/test_color_extraction.py -s --tb=short

def get_color_extraction_configs() -> Dict[str, Dict]:
    """
    Return test configurations for color extraction tests.
    
    To add a new map test, simply add a new entry to this dictionary.
    Each entry should contain:
    - source_image: path to the source image
    - etalons_dir: directory containing reference masks
    - ratio_tol: tolerance for ratio comparison (absolute value)
    - expected_colors: dict mapping color names to their expected ref_prefix and ratio
    """
    return {
        "nouvelle_france_1750": {
            "source_image": "tests/assets/Nouvelle-France1750.png",  
            "etalons_dir": "tests/assets/color_extraction",
            "ratio_tol": 0.02,
            "expected_colors": {
                "silver_1": {"ref_prefix": "color_1_silver", "ratio": 0.5010},
                "dodgerblue_2": {"ref_prefix": "color_2_dodgerblue", "ratio": 0.2173},
                "darksalmon_3": {"ref_prefix": "color_3_darksalmon", "ratio": 0.0829},
                "tomato_4": {"ref_prefix": "color_4_tomato", "ratio": 0.0619},
            }
        }
    }


def _read_mask_as_binary(path: str) -> np.ndarray:
    """
    Read a PNG mask and return a boolean array where True means "mask pixel is on".
    This avoids false diffs caused by PNG encoding or dtype differences.
    """
    arr = iio.imread(path)
    if arr.ndim == 3:
        # Some readers return (H, W, 4) or (H, W, 3) even for masks; take first channel
        arr = arr[:, :, 0]

    # Normalize to boolean: consider any non-zero value as "on"
    return arr.astype(np.uint8) > 0


def _assert_same_mask_pixels(generated_path: str, reference_path: str, color_name: str) -> None:
    """
    Compare two masks by pixels, not by raw bytes.
    """
    gen = _read_mask_as_binary(generated_path)
    ref = _read_mask_as_binary(reference_path)

    if gen.shape != ref.shape:
        raise AssertionError(
            f"{color_name}: mask shape differs "
            f"(gen={gen.shape}, ref={ref.shape})\n"
            f"Generated: {generated_path}\n"
            f"Reference: {reference_path}"
        )

    if not np.array_equal(gen, ref):
        # Provide a small metric to help debugging
        diff = np.mean(gen != ref) * 100.0
        raise AssertionError(
            f"{color_name}: mask pixels differ (diff={diff:.4f}%)\n"
            f"Generated: {generated_path}\n"
            f"Reference: {reference_path}"
        )


def _find_reference_by_prefix(directory: str, prefix: str) -> Tuple[str, list[str]]:
    """
    Find exactly one reference PNG that matches a prefix, e.g.:
    prefix='color_1_silver' matches 'color_1_silver_ratio_0.5010.png'

    Returns (path, matches) so callers can use matches for error reporting.
    """
    pattern = os.path.join(directory, f"{prefix}*.png")
    matches = sorted(glob.glob(pattern))
    if len(matches) != 1:
        return "", matches
    return matches[0], matches


def _run_color_extraction_test(
    source_image: str,
    etalons_dir: str,
    expected_colors: Dict[str, Dict],
    ratio_tol: float,
    test_name: str,
) -> None:
    """
    Generic function to test color extraction for a given map configuration.

    This function verifies:
    - expected color layers exist
    - generated masks match reference masks by pixels
    - ratios remain within tolerance (detects meaningful drift)

    If this test fails:
    1. Inspect generated images in temp_output_dir (path printed in failure)
    2. If correct: update reference masks and/or expected ratios in get_color_extraction_configs()
    3. If regression: revert or fix algorithm changes
    """
    assert os.path.exists(source_image), f"Source image missing: {source_image}"
    assert os.path.exists(etalons_dir), f"Reference directory missing: {etalons_dir}"

    # Keep output directory for inspection even on failure
    temp_output_dir = tempfile.mkdtemp(prefix=f"color_extraction_test_{test_name}_")

    result = extract_colors(image_path=source_image, output_dir=temp_output_dir)

    # Basic verifications
    for key in ("colors_detected", "masks", "ratios", "output_dir"):
        assert key in result, f"Missing key '{key}' in extract_colors() result"

    colors_detected = result["colors_detected"]
    assert len(colors_detected) > 0, "No colors detected"

    print(f"Test: {test_name}")
    print(f"Temp output dir: {temp_output_dir}")
    print(f"Colors detected: {colors_detected}")
    print(f"Number of colors: {len(colors_detected)}")

    issues = []

    # Check 1: expected color keys present
    expected_names = set(expected_colors.keys())
    detected_names = set(colors_detected)
    missing = expected_names - detected_names
    for color in sorted(missing):
        issues.append(f"  MISSING: {color} - Not detected in extracted colors")

    # Check 2: mask pixel comparison + ratio tolerance
    for color_name, spec in expected_colors.items():
        if color_name not in detected_names:
            continue  # already reported

        # Generated mask path
        if color_name not in result["masks"]:
            issues.append(f"  MASK_MISSING: {color_name} - Missing in result['masks']")
            continue

        generated_file = result["masks"][color_name]
        if not os.path.exists(generated_file):
            issues.append(f"  FILE_MISSING: {color_name} - Generated file not found: {generated_file}")
            continue

        # Reference file: match by prefix (ratio is ignored)
        ref_prefix = spec["ref_prefix"]
        ref_file, matches = _find_reference_by_prefix(etalons_dir, ref_prefix)
        if not ref_file:
            issues.append(
                f"  REF_MISSING_OR_AMBIGUOUS: {color_name} - Expected exactly 1 match for prefix '{ref_prefix}', "
                f"got {len(matches)}: {matches}"
            )
            continue

        # Pixel-level comparison (not raw bytes)
        try:
            _assert_same_mask_pixels(generated_file, ref_file, color_name)
            print(f" {color_name}: MASK OK")
        except AssertionError as e:
            issues.append(f"  MASK_DIFFERENT: {color_name} - {str(e)}")

        # Ratio check with tolerance
        expected_ratio = float(spec["ratio"])
        got_ratio = result["ratios"].get(color_name, None)
        if got_ratio is None:
            issues.append(f"  RATIO_MISSING: {color_name} - Missing in result['ratios']")
        else:
            got_ratio = float(got_ratio)
            if abs(got_ratio - expected_ratio) > ratio_tol:
                issues.append(
                    f"  RATIO_DRIFT: {color_name} - expected={expected_ratio:.4f}, got={got_ratio:.4f}, tol={ratio_tol:.4f}"
                )
            else:
                print(f" {color_name}: RATIO OK (expected={expected_ratio:.4f}, got={got_ratio:.4f})")

    if issues:
        error_msg = (
            f"\n{'='*60}\nCOLOR EXTRACTION TEST FAILED: {test_name}\n{'='*60}\n"
            f"Source image: {source_image}\n"
            f"Temp output dir (kept): {temp_output_dir}\n"
            f"Colors detected: {len(colors_detected)}\n"
            f"Issues found: {len(issues)}\n\n"
            "DETAILED ISSUES:\n"
            + "\n".join(issues)
            + f"\n\n{'='*60}\n"
            "ACTION REQUIRED:\n"
            "1. Inspect generated masks in temp_output_dir\n"
            "2. If masks are correct: update reference masks and/or expected ratios in get_color_extraction_configs()\n"
            "3. If regression: revert or fix extraction changes\n"
        )
        pytest.fail(error_msg)

    print(f"All {len(expected_colors)} expected colors verified successfully.")


@pytest.mark.parametrize(
    "test_name,config",
    [
        pytest.param(name, config, id=name)
        for name, config in get_color_extraction_configs().items()
    ]
)
def test_extract_colors(test_name: str, config: Dict):
    """
    Regression test for color extraction.

    This test is parameterized by test configurations from get_color_extraction_configs().
    To add a new map test, simply add a new entry to that function.

    This test verifies:
    - expected color layers exist
    - generated masks match reference masks by pixels
    - ratios remain within tolerance (detects meaningful drift)

    If this test fails:
    1. Inspect generated images in temp_output_dir (path printed in failure)
    2. If correct: update reference masks and/or expected ratios in get_color_extraction_configs()
    3. If regression: revert or fix algorithm changes
    """
    _run_color_extraction_test(
        source_image=config["source_image"],
        etalons_dir=config["etalons_dir"],
        expected_colors=config["expected_colors"],
        ratio_tol=config["ratio_tol"],
        test_name=test_name,
    )