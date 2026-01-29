import json
import os
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "extracted_shapes")


def extract_shapes(
    image_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    min_area: int = 10,
    max_area: int = 100000,
    threshold_value: int = 127,
    min_confidence: float = 0.6,
):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Unable to load image: {image_path}")

    height, width = image.shape[:2]
    image_area = width * height

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    image_output_dir = os.path.join(output_dir, base_name)
    os.makedirs(image_output_dir, exist_ok=True)

    binary_mask = preprocess_image(gray, threshold_value)

    debug_mask_path = os.path.join(image_output_dir, "DEBUG_mask.png")
    cv2.imwrite(debug_mask_path, binary_mask)

    contours = detect_contours(binary_mask)

    filtered_contours, filter_stats = filter_contours(
        contours, min_area, max_area, image_area
    )

    shapes_with_contours = []
    for idx, contour in enumerate(filtered_contours, 1):
        shape_data = extract_contour_properties(contour, image, binary_mask, idx)
        if shape_data:
            shapes_with_contours.append((shape_data, contour))

    # Skip classification: keep all detected shapes after contour filtering
    final_shapes_with_contours = shapes_with_contours

    print(
        f"[SHAPE EXTRACT] Saving debug images and metadata for {len(final_shapes_with_contours)} shapes..."
    )

    # Prepare detailed metadata for each shape (no classification)
    shapes_metadata = []
    for idx, (shape, contour) in enumerate(final_shapes_with_contours, 1):
        saved_path = save_shape_image(image, contour, image_output_dir, idx)
        shape["image_path"] = saved_path

        # Calculate relative size for metadata
        relative_size = shape["area"] / image_area if image_area else 0

        metadata = {
            "shape_id": idx,
            "image_path": saved_path,
            # Morphological properties
            "morphology": {
                "area": shape["area"],
                "relative_size": relative_size,
                "aspect_ratio": shape["aspect_ratio"],
                "solidity": shape["solidity"],
                "extent": shape["extent"],
                "num_vertices": shape.get("num_vertices", 0),
                "perimeter": shape.get("perimeter", 0),
            },
            # Bounding box
            "bounding_box": shape.get("bounding_box", {}),
            # Center of mass
            "center": shape.get("center", {}),
            # Geometry for GeoJSON
            "geometry": shape.get("geometry", {}),
            # Calculated properties
            "properties": shape.get("properties", {}),
        }

        shapes_metadata.append(metadata)
        print(
            f"[SHAPE EXTRACT] Saved shape {idx}: id={shape['id']} (area={shape['area']:.1f})"
        )

    # Save metadata to a JSON file
    metadata_path = os.path.join(image_output_dir, "shapes_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "image_info": {
                    "source_path": image_path,
                    "dimensions": f"{width}x{height}",
                    "total_area": image_area,
                    "extraction_date": "2024-01-14",  # ou datetime.now().isoformat()
                },
                "extraction_params": {
                    "min_area": min_area,
                    "max_area": max_area,
                    "threshold_value": threshold_value,
                },
                "total_shapes_extracted": len(shapes_metadata),
                "shapes": shapes_metadata,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"[SHAPE EXTRACT] Metadata saved to: {metadata_path}")

    # Export shapes to normalized GeoJSON format
    geojson_path = export_shapes_to_normalized_geojson(
        final_shapes_with_contours, image_output_dir
    )

    print(
        f"[EXTRACT] {len(final_shapes_with_contours)} shapes extracted from {image_path}"
    )

    final_shapes = [shape for shape, contour in final_shapes_with_contours]
    # Reconstruct debug images from the final shapes and contours
    try:
        reconstructed_mask_path, reconstructed_overlay_path = reconstruct_shapes_debug(
            image, final_shapes_with_contours, image_output_dir
        )
    except Exception:
        reconstructed_mask_path, reconstructed_overlay_path = None, None

    # Read the generated GeoJSON file to get normalized features
    normalized_features = []
    if geojson_path and os.path.exists(geojson_path):
        try:
            with open(geojson_path, "r", encoding="utf-8") as f:
                geojson_data = json.load(f)
                # Format correct : une seule FeatureCollection avec toutes les features
                normalized_features = [geojson_data]  # FeatureCollection complète
        except Exception as e:
            print(f"[ERROR] Failed to read GeoJSON file {geojson_path}: {e}")

    return {
        "total_shapes": len(final_shapes_with_contours),
        "shapes": final_shapes,
        "output_directory": image_output_dir,
        "debug_mask_path": debug_mask_path,
        "metadata_path": metadata_path,
        "geojson_path": geojson_path,
        "reconstructed_mask_path": reconstructed_mask_path,
        "reconstructed_overlay_path": reconstructed_overlay_path,
        "normalized_features": normalized_features,
    }


def export_shapes_to_normalized_geojson(
    final_shapes_with_contours: List[Tuple[Dict, np.ndarray]],
    image_output_dir: str,
) -> str:
    """Convert extracted shapes with contours to normalized GeoJSON format.

    Each shape is normalized into a [0,1] x [0,1] coordinate space while preserving
    aspect ratio, similar to the color extraction workflow.

    Args:
        final_shapes_with_contours: List of (shape_dict, contour) tuples
        image_output_dir: Directory to save the GeoJSON file

    Returns:
        Path to the saved GeoJSON file
    """
    from shapely import affinity
    from shapely.geometry import Polygon

    geojson_features = []

    for idx, (shape, contour) in enumerate(final_shapes_with_contours, 1):
        # Get bounding box dimensions for normalization
        bbox = shape["bounding_box"]
        x_min, y_min = bbox["x"], bbox["y"]
        w, h = bbox["width"], bbox["height"]

        # Prevent division by zero
        if w == 0 or h == 0:
            continue

        # Convert contour points to normalized coordinates in [0,1] x [0,1]
        normalized_coords = []
        for pt in contour:
            x_norm = (pt[0][0] - x_min) / w
            y_norm = (pt[0][1] - y_min) / h
            normalized_coords.append([x_norm, y_norm])

        # Ensure coordinates form a valid polygon (close the ring if needed)
        if len(normalized_coords) >= 3:
            if normalized_coords[0] != normalized_coords[-1]:
                normalized_coords.append(normalized_coords[0])

        # Scale to preserve aspect ratio and center in [0,1] box
        polygon = Polygon(normalized_coords)

        # Get bounds of the normalized polygon
        minx, miny, maxx, maxy = polygon.bounds
        width_norm = maxx - minx
        height_norm = maxy - miny
        max_dim = max(width_norm, height_norm)

        # Scale uniformly so largest dimension = 1
        if max_dim > 0:
            scale = 1.0 / max_dim
        else:
            scale = 1.0

        # Translate to origin and scale
        translated = affinity.translate(polygon, xoff=-minx, yoff=-miny)
        scaled = affinity.scale(
            translated,
            xfact=scale,
            yfact=scale,
            origin=(0.0, 0.0),
        )

        # Center in [0,1] box
        width_scaled = width_norm * scale
        height_scaled = height_norm * scale
        offset_x = (1.0 - width_scaled) / 2.0
        offset_y = (1.0 - height_scaled) / 2.0

        normalized_geom = affinity.translate(
            scaled,
            xoff=offset_x,
            yoff=offset_y,
        )

        # Create GeoJSON feature
        feature = {
            "type": "Feature",
            "properties": {
                "shape_id": idx,
                "area": shape["area"],
                "perimeter": shape["perimeter"],
                "aspect_ratio": shape["aspect_ratio"],
                "solidity": shape["solidity"],
                "extent": shape["extent"],
                "num_vertices": shape["num_vertices"],
                "mapElementType": "shape",
                "name": f"Shape {idx}",
                "is_normalized": True,
                "start_date": "1700-01-01",
                "end_date": "2026-01-01",
            },
            "geometry": normalized_geom.__geo_interface__,
        }

        geojson_features.append(feature)

    # Create and save FeatureCollection
    feature_collection = {
        "type": "FeatureCollection",
        "features": geojson_features,
    }

    geojson_path = os.path.join(image_output_dir, "shapes_normalized.geojson")
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, indent=2, ensure_ascii=False)

    print(f"[SHAPE EXTRACT] Normalized GeoJSON saved to: {geojson_path}")

    return geojson_path


def preprocess_image(gray: np.ndarray, threshold_value: int = 127) -> np.ndarray:
    unique_values = np.unique(gray)

    if len(unique_values) <= 3:
        binary = (gray > 127).astype(np.uint8) * 255
    else:
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )

    # kernel = np.ones((2, 2), np.uint8)
    # binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    return binary


def detect_contours(binary_mask: np.ndarray) -> List[np.ndarray]:
    contours, hierarchy = cv2.findContours(
        binary_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )

    return contours if contours else []


def filter_contours(
    contours: List[np.ndarray], min_area: int, max_area: int, image_area: int
) -> Tuple[List[np.ndarray], Dict]:
    filtered = []
    stats = {
        "total": len(contours),
        "filtered_by_min_area": 0,
        "filtered_by_max_area": 0,
        "filtered_by_ratio": 0,
        "filtered_by_points": 0,
        "kept": 0,
    }

    for contour in contours:
        area = cv2.contourArea(contour)

        if area < min_area:
            stats["filtered_by_min_area"] += 1
            continue

        if area > max_area:
            stats["filtered_by_max_area"] += 1
            continue

        ratio = area / image_area
        if ratio > 0.5:
            stats["filtered_by_ratio"] += 1
            continue

        if len(contour) < 3:
            stats["filtered_by_points"] += 1
            continue

        stats["kept"] += 1
        filtered.append(contour)

    return filtered, stats


def extract_contour_properties(
    contour: np.ndarray,
    original_image: np.ndarray,
    binary_mask: np.ndarray,
    shape_id: int,
) -> Optional[Dict]:
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
        "bounding_box": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
        "center": {"x": int(cx), "y": int(cy)},
        "aspect_ratio": round(aspect_ratio, 2),
        "extent": round(extent, 3),
        "solidity": round(solidity, 3),
        "num_vertices": num_vertices,
        "geometry": {
            "type": "Polygon",
            "pixel_coords": {
                "contour_points": contour.tolist(),
                "bounding_box": {
                    "x": int(x),
                    "y": int(y),
                    "width": int(w),
                    "height": int(h),
                },
                "center": {"x": int(cx), "y": int(cy)},
            },
        },
        "properties": {
            "area": float(area),
            "perimeter": float(perimeter),
            "bounding_box": {
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
            },
        },
    }


def save_shape_image(
    image: np.ndarray, contour: np.ndarray, output_dir: str, shape_id: int
) -> str:
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [contour], 0, 255, -1)

    shape_image = cv2.bitwise_and(image, image, mask=mask)

    x, y, w, h = cv2.boundingRect(contour)
    cropped = shape_image[y : y + h, x : x + w]

    shape_filename = f"shape_{shape_id:04d}.png"
    shape_path = os.path.join(output_dir, shape_filename)

    cv2.imwrite(shape_path, cropped)

    return shape_path


def reconstruct_shapes_debug(
    image: np.ndarray,
    final_shapes_with_contours: List[Tuple[Dict, np.ndarray]],
    output_dir: str,
) -> Tuple[str, str]:
    """Reconstruct a debug image from extracted contours.

    Produces:
      - reconstructed_mask.png : binary mask of all filled contours
      - reconstructed_overlay.png : colored overlay of shapes blended with original

    Returns paths (mask_path, overlay_path).
    """
    h, w = image.shape[:2]

    # Binary mask (grayscale)
    mask = np.zeros((h, w), dtype=np.uint8)

    # Color image where each shape gets a random color
    color_img = np.full((h, w, 3), 255, dtype=np.uint8)

    for idx, (shape, contour) in enumerate(final_shapes_with_contours, 1):
        # draw filled contour on mask
        cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)

        # random but reproducible color per shape (seeded by id for stability)
        rng = np.random.RandomState(idx)
        color = tuple(int(c) for c in rng.randint(50, 230, size=3))
        cv2.drawContours(color_img, [contour], -1, color, thickness=cv2.FILLED)

    # Save mask
    mask_path = os.path.join(output_dir, "reconstructed_mask.png")
    cv2.imwrite(mask_path, mask)

    # Blend color_img with original for overlay (keep background white where no shape)
    overlay = image.copy()
    colored_only = cv2.bitwise_and(color_img, color_img, mask=mask)
    inv_mask = cv2.bitwise_not(mask)
    background = cv2.bitwise_and(overlay, overlay, mask=inv_mask)
    composed = cv2.addWeighted(background, 0.3, colored_only, 0.7, 0)

    overlay_path = os.path.join(output_dir, "reconstructed_overlay.png")
    cv2.imwrite(overlay_path, composed)

    return mask_path, overlay_path
