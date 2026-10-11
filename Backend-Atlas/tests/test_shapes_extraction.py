import cv2
import json
import os
from typing import Dict

import pytest
from app.utils.shapes_extraction import extract_shapes_from_clicks
from shapely.geometry import Polygon


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

    for golden_shape in golden_data["expected_shape"]:
        label = golden_shape["label"]
        iou_threshold = golden_shape.get("iou_threshold", 0.7)

        # 1. Reconstruct golden polygon
        golden_pts = golden_shape["expected_pixel_geometry"]["pixel_coords"][
            "contour_points"
        ]
        golden_poly = Polygon(flatten_points(golden_pts))
        if not golden_poly.is_valid:
            golden_poly = golden_poly.buffer(0)
            
        assert not golden_poly.is_empty, f"Golden polygon for {label} is empty."

        # 2. Get the click point that was used to extract this shape
        # Fallback to representative point if click_point is not stored
        if "click_point" in golden_shape:
            click_x = golden_shape["click_point"]["x"]
            click_y = golden_shape["click_point"]["y"]
        else:
            rep_point = golden_poly.representative_point()
            
            # Load image to get dimensions for normalization
            img = cv2.imread(image_path)
            height, width = img.shape[:2]
            
            click_x, click_y = float(rep_point.x) / width, float(rep_point.y) / height

        # 3. Simulate a click at that point
        result = extract_shapes_from_clicks(
            image_path,
            click_positions=[(click_x, click_y)],
            click_names=[label],
            debug=False,
        )

        extracted_shapes = result.get("shapes", [])
        
        # 4. Check if a shape was extracted
        assert len(extracted_shapes) > 0, f"No shape extracted for click at ({click_x}, {click_y}) for {label}"
        
        # The first shape extracted corresponds to the click
        extracted = extracted_shapes[0]
        pts = extracted["geometry"]["pixel_coords"]["contour_points"]
        extracted_poly = Polygon(flatten_points(pts))
        if not extracted_poly.is_valid:
            extracted_poly = extracted_poly.buffer(0)

        # 5. Calculate IoU
        best_iou = calculate_iou(golden_poly, extracted_poly)

        assert best_iou > iou_threshold, (
            f"Shape '{label}' extracted via click did not match expected shape closely enough. "
            f"IoU was {best_iou:.3f}, threshold was {iou_threshold}"
        )
