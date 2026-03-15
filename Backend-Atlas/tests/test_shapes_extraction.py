import json
import os
from typing import Dict, List

import pytest
from app.utils.shapes_extraction import extract_shapes
from shapely.geometry import Polygon
from shapely.strtree import STRtree


def flatten_points(points):
    result = []
    for pt in points:
        if isinstance(pt[0], (list, tuple)):
            result.append([pt[0][0], pt[0][1]])
        else:
            result.append([pt[0], pt[1]])
    return result


def calculate_iou(poly1: Polygon, poly2: Polygon) -> float:
    try:
        if not poly1.is_valid:
            poly1 = poly1.buffer(0)
        if not poly2.is_valid:
            poly2 = poly2.buffer(0)

        if not poly1.is_valid or not poly2.is_valid:
            return 0.0

        if not poly1.intersects(poly2):
            return 0.0

        intersection = poly1.intersection(poly2).area
        union = poly1.union(poly2).area

        return intersection / union if union > 0 else 0.0
    except Exception:
        return 0.0


def find_matching_shape(
    golden_shape: Dict,
    extracted_polys: List[Polygon],
    tree: STRtree,
    iou_threshold: float = 0.7,
) -> tuple[bool, float]:
    golden_pts = golden_shape["expected_pixel_geometry"]["pixel_coords"][
        "contour_points"
    ]
    golden_poly = Polygon(flatten_points(golden_pts))

    if not golden_poly.is_valid:
        golden_poly = golden_poly.buffer(0)

    if not extracted_polys:
        return False, 0.0

    candidates = tree.query(golden_poly)

    best_iou = 0.0
    for candidate_idx in candidates:
        candidate_poly = extracted_polys[candidate_idx]
        iou = calculate_iou(golden_poly, candidate_poly)
        best_iou = max(best_iou, iou)

        if iou > iou_threshold:
            return True, iou

    return best_iou > iou_threshold, best_iou


@pytest.mark.parametrize(
    "golden_file,image_path",
    [
        (
            "tests/assets/expected_shapes/1775_Quebec_NordUSA.json",
            "tests/assets/1775_Quebec_NordUSA.png",
        ),
        (
            "tests/assets/expected_shapes/Quebec.json",
            "tests/assets/Quebec.png",
        ),
    ],
)
def test_shape_extraction_golden_master(golden_file, image_path):
    assert os.path.exists(golden_file), f"Golden file not found: {golden_file}"
    with open(golden_file, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    assert os.path.exists(image_path), f"Image not found: {image_path}"

    result = extract_shapes(image_path, debug=False)
    extracted_shapes = result["shapes"]

    extracted_polys = []
    for extracted in extracted_shapes:
        pts = extracted["geometry"]["pixel_coords"]["contour_points"]
        poly = Polygon(flatten_points(pts))
        if not poly.is_valid:
            poly = poly.buffer(0)
        extracted_polys.append(poly)

    tree = STRtree(extracted_polys)

    results = []
    for golden_shape in golden_data["expected_shape"]:
        label = golden_shape["label"]
        iou_threshold = golden_shape.get("iou_threshold", 0.7)

        found, best_iou = find_matching_shape(
            golden_shape, extracted_polys, tree, iou_threshold
        )
        results.append(
            {
                "label": label,
                "found": found,
                "iou": best_iou,
                "threshold": iou_threshold,
            }
        )

        assert found, (
            f"Shape '{label}' not found in extracted shapes. "
            f"Best IoU was {best_iou:.3f}, threshold was {iou_threshold}"
        )
