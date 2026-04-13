from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

import cv2
import numpy as np
import pytest

from app.utils.color_extraction import extract_colors
from app.utils.shapes_extraction import extract_shapes


ASSETS_DIR = Path("tests/assets")
EXPECTED_COLOR_ROOT = ASSETS_DIR / "expected_color"
MIN_MASK_IOU = 0.65

# Run with:
# docker compose run --rm test-backend pytest tests/test_color_extraction.py -v --tb=short


def get_color_extraction_cases() -> list[Dict[str, Any]]:
    """
    Multi-image test cases.

    Required keys per case:
    - name: pytest id
    - image_path: input image path
    - expected_masks_dir: expected masks subfolder

    Optional keys:
    - attributes: extra extraction options. If attributes contains legend_bounds,
      legend_shapes are automatically computed from extract_shapes before calling
      extract_colors.
    """
    return [
        {
            "name": "nouvelle_france_1750_test1",
            "image_path": ASSETS_DIR / "Nouvelle-France1750.png",
            "expected_masks_dir": EXPECTED_COLOR_ROOT / "test1",
            "attributes": {},
        },
    ]


def load_binary_mask(path: Path) -> np.ndarray:
    """Load a mask image and convert it to a boolean mask."""
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise AssertionError(f"Unable to load mask image: {path}")

    if img.ndim == 2:
        return img > 0

    if img.ndim == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3]
        if np.any(alpha > 0):
            return alpha > 0

    rgb = img[:, :, :3]
    return np.any(rgb > 0, axis=2)


def mask_iou(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    intersection = np.logical_and(mask_a, mask_b).sum()
    union = np.logical_or(mask_a, mask_b).sum()
    return float(intersection) / float(union) if union > 0 else 0.0


def extract_color_name_from_expected(path: Path) -> str:
    """
    Extract color token from expected file names.

    Supported examples:
    - color_01_silver_1_ratio_0.50.png -> silver
    - silver.png -> silver
    """
    stem = path.stem.lower()
    match = re.search(r"color_\d+_([a-z0-9]+)_\d+", stem)
    if match:
        return match.group(1)
    return stem.split("_")[0]


def extract_color_name_from_generated_key(key: str) -> str:
    # Current generated format: "dodgerblue-2"
    return key.split("-", maxsplit=1)[0].lower()


def build_extract_colors_kwargs(
    image_path: Path,
    tmp_path: Path,
    attributes: Dict[str, Any],
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "image_path": str(image_path),
        "output_dir": str(tmp_path),
        "debug": True,
    }

    attrs = dict(attributes)
    legend_bounds = attrs.pop("legend_bounds", None)

    if legend_bounds is not None:
        shapes_result = extract_shapes(
            str(image_path),
            debug=False,
            legend_bounds=legend_bounds,
        )
        legend_shapes = [
            shape for shape in shapes_result.get("shapes", []) if shape.get("isLegend", False)
        ]

        assert legend_shapes, (
            "legend_bounds was provided but no legend shapes were detected. "
            "Adjust legend_bounds in the test case."
        )
        kwargs["legend_shapes"] = legend_shapes

    kwargs.update(attrs)
    return kwargs


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=case["name"])
        for case in get_color_extraction_cases()
    ],
)
def test_extract_colors(case: Dict[str, Any], tmp_path: Path) -> None:
    test_name = case["name"]
    source_image: Path = case["image_path"]
    expected_dir: Path = case["expected_masks_dir"]
    attributes: Dict[str, Any] = case.get("attributes", {})

    assert source_image.exists(), f"Source image missing: {source_image}"
    assert expected_dir.exists(), f"Expected folder missing: {expected_dir}"

    expected_mask_paths = sorted(expected_dir.glob("*.png"))
    assert expected_mask_paths, f"No expected masks found in: {expected_dir}"

    extract_kwargs = build_extract_colors_kwargs(
        image_path=source_image,
        tmp_path=tmp_path,
        attributes=attributes,
    )
    result = extract_colors(**extract_kwargs)
    generated_masks = result.get("masks", {})
    assert generated_masks, f"No masks generated for test case: {test_name}"

    generated_by_color = {
        extract_color_name_from_generated_key(mask_key): Path(mask_path)
        for mask_key, mask_path in generated_masks.items()
    }

    missing = []
    for expected_path in expected_mask_paths:
        expected_color = extract_color_name_from_expected(expected_path)
        generated_path = generated_by_color.get(expected_color)

        if generated_path is None:
            missing.append(expected_color)
            continue

        expected_mask = load_binary_mask(expected_path)
        generated_mask = load_binary_mask(generated_path)
        iou = mask_iou(expected_mask, generated_mask)

        assert iou >= MIN_MASK_IOU, (
            f"[{test_name}] mask mismatch for '{expected_color}' | "
            f"IoU={iou:.3f}, expected >= {MIN_MASK_IOU:.2f}\n"
            f"Expected: {expected_path}\n"
            f"Generated: {generated_path}"
        )

    assert not missing, (
        f"[{test_name}] missing generated masks for expected colors: {sorted(missing)}"
    )