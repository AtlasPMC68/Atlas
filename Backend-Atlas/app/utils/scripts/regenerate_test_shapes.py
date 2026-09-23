import cv2
import json
import os
import sys

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

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

ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..", "tests", "assets"))

files_to_process = [
    (
        os.path.join(ASSETS_DIR, "expected_shapes", "1775_Quebec_NordUSA.json"),
        os.path.join(ASSETS_DIR, "1775_Quebec_NordUSA.png"),
    ),
    (
        os.path.join(ASSETS_DIR, "expected_shapes", "Quebec.json"),
        os.path.join(ASSETS_DIR, "Quebec.png"),
    ),
]

def main():
    for json_path, image_path in files_to_process:
        print(f"Processing {json_path}...")
        
        with open(json_path, "r", encoding="utf-8") as f:
            golden_data = json.load(f)
            
        new_golden_shapes = []
        
        for golden_shape in golden_data["expected_shape"]:
            label = golden_shape["label"]
            print(f"  Extracting {label}...")
            
            golden_pts = golden_shape["expected_pixel_geometry"]["pixel_coords"]["contour_points"]
            golden_poly = Polygon(flatten_points(golden_pts))
            if not golden_poly.is_valid:
                golden_poly = golden_poly.buffer(0)
                
            rep_point = golden_poly.representative_point()
            
            img = cv2.imread(image_path)
            height, width = img.shape[:2]
            
            click_x, click_y = float(rep_point.x) / width, float(rep_point.y) / height
            
            result = extract_shapes_from_clicks(
                image_path,
                click_positions=[(click_x, click_y)],
                click_names=[label],
                debug=False,
            )
            
            extracted_shapes = result.get("shapes", [])
            if not extracted_shapes:
                print(f"    WARNING: No shape found at ({click_x}, {click_y}) for {label}")
                new_golden_shapes.append(golden_shape)
                continue
                
            # Replace the old geometry with the new geometry
            extracted = extracted_shapes[0]
            new_pts = extracted["geometry"]["pixel_coords"]["contour_points"]
            
            # Update the JSON object
            golden_shape["expected_pixel_geometry"]["pixel_coords"]["contour_points"] = new_pts
            golden_shape["expected_pixel_geometry"]["pixel_coords"]["bounding_box"] = extracted["geometry"]["pixel_coords"]["bounding_box"]
            golden_shape["click_point"] = {"x": click_x, "y": click_y}
            
            new_golden_shapes.append(golden_shape)
            
        golden_data["expected_shape"] = new_golden_shapes
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(golden_data, f, indent=4, ensure_ascii=False)
            
        print(f"Successfully updated {json_path}")

if __name__ == "__main__":
    main()
