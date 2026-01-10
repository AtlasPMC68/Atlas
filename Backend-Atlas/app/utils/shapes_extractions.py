import cv2
import numpy as np
import os
from typing import List, Dict, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "extracted_shapes")

def extract_shapes(image_path: str, output_dir: str = DEFAULT_OUTPUT_DIR, 
                   min_area: int = 100, max_area: int = 100000,
                   threshold_value: int = 127):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Unable to load image: {image_path}")
    
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    image_output_dir = os.path.join(output_dir, base_name)
    os.makedirs(image_output_dir, exist_ok=True)
    
    binary_mask = preprocess_image(gray, threshold_value)
    
    contours = detect_contours(binary_mask)
    
    filtered_contours = filter_contours(contours, min_area, max_area, width * height)
    
    shapes = []
    for idx, contour in enumerate(filtered_contours, 1):
        shape_data = extract_contour_properties(contour, image, binary_mask, idx)
        if shape_data:
            saved_path = save_shape_image(image, contour, image_output_dir, idx)
            shape_data["image_path"] = saved_path
            shapes.append(shape_data)
    
    print(f"[EXTRACT] {len(shapes)} shapes extracted from {image_path}")
    
    return {
        "total_shapes": len(shapes),
        "shapes": shapes,
        "output_directory": image_output_dir
    }

def preprocess_image(gray: np.ndarray, threshold_value: int = 127) -> np.ndarray:
    _, binary = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY_INV)
    
    kernel = np.ones((3, 3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    
    return binary

def detect_contours(binary_mask: np.ndarray) -> List[np.ndarray]:
    contours, hierarchy = cv2.findContours(
        binary_mask, 
        cv2.RETR_EXTERNAL, 
        cv2.CHAIN_APPROX_SIMPLE
    )
    
    return contours if contours else []

def filter_contours(contours: List[np.ndarray], min_area: int, 
                   max_area: int, image_area: int) -> List[np.ndarray]:
    filtered = []
    
    for contour in contours:
        area = cv2.contourArea(contour)
        
        if area < min_area or area > max_area:
            continue
        
        if area / image_area > 0.5:
            continue
        
        if len(contour) < 3:
            continue
        
        filtered.append(contour)
    
    return filtered

def extract_contour_properties(contour: np.ndarray, original_image: np.ndarray,
                               binary_mask: np.ndarray, shape_id: int) -> Optional[Dict]:
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)
    
    x, y, w, h = cv2.boundingRect(contour)
    aspect_ratio = float(w) / h if h > 0 else 0
    extent = area / (w * h) if (w * h) > 0 else 0
    
    moments = cv2.moments(contour)
    if moments["m00"] != 0:
        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])
    else:
        cx, cy = x + w // 2, y + h // 2
    
    hull = cv2.convexHull(contour)
    hull_area = cv2.contourArea(hull)
    solidity = area / hull_area if hull_area > 0 else 0
    
    epsilon = 0.02 * perimeter
    approx = cv2.approxPolyDP(contour, epsilon, True)
    num_vertices = len(approx)
    
    return {
        "id": shape_id,
        "area": float(area),
        "perimeter": float(perimeter),
        "bounding_box": {
            "x": int(x),
            "y": int(y),
            "width": int(w),
            "height": int(h)
        },
        "center": {
            "x": int(cx),
            "y": int(cy)
        },
        "aspect_ratio": round(aspect_ratio, 2),
        "extent": round(extent, 3),
        "solidity": round(solidity, 3),
        "num_vertices": num_vertices,
        "geometry": {
            "type": "Polygon",
            "pixel_coords": {
                "contour_points": contour.tolist(),
                "bounding_box": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                "center": {"x": int(cx), "y": int(cy)}
            }
        },
        "properties": {
            "area": float(area),
            "perimeter": float(perimeter),
            "bounding_box": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}
        }
    }

def save_shape_image(image: np.ndarray, contour: np.ndarray, 
                    output_dir: str, shape_id: int) -> str:
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [contour], 0, 255, -1)
    
    shape_image = cv2.bitwise_and(image, image, mask=mask)
    
    x, y, w, h = cv2.boundingRect(contour)
    cropped = shape_image[y:y+h, x:x+w]
    
    shape_filename = f"shape_{shape_id:04d}.png"
    shape_path = os.path.join(output_dir, shape_filename)
    
    cv2.imwrite(shape_path, cropped)
    
    return shape_path