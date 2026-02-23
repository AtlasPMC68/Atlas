import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from shapely import affinity
from shapely.geometry import Polygon

from . import preprocessing
from .color_extraction import get_nearest_css4_color_name

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "extracted_shapes")


def get_dominant_color_in_contour(
    image_bgr: np.ndarray,
    contour: np.ndarray,
) -> Tuple[int, int, int]:
    """Find the dominant RGB color inside a contour region.

    Creates a filled mask for the contour, extracts the pixels within it,
    then finds the most frequent color using coarse RGB binning (8x8x8).
    """
    mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)

    pixels_bgr = image_bgr[mask == 255]  # shape (N, 3)

    if len(pixels_bgr) == 0:
        return (128, 128, 128)  # fallback gray

    # Convert BGR -> RGB
    pixels_rgb = pixels_bgr[:, ::-1]

    # Coarse quantization into an 8×8×8 grid (each channel split into 8 bins of 32)
    quantized = (pixels_rgb // 32).astype(np.int32)
    bin_ids = quantized[:, 0] * 64 + quantized[:, 1] * 8 + quantized[:, 2]
    unique_bins, counts = np.unique(bin_ids, return_counts=True)
    dominant_bin = int(unique_bins[np.argmax(counts)])

    r_bin = dominant_bin // 64
    g_bin = (dominant_bin % 64) // 8
    b_bin = dominant_bin % 8

    # Return the center of the dominant bin
    return (r_bin * 32 + 16, g_bin * 32 + 16, b_bin * 32 + 16)


def filter_text_overlapping_contours(
    contours: List[np.ndarray],
    text_regions: List[List[List[int]]],
    overlap_threshold: float = 0.5,
) -> Tuple[List[np.ndarray], int]:
    """
    Filter out contours that overlap significantly with text bounding boxes.

    :param contours: List of OpenCV contours to filter.
    :param text_regions: List of text bounding quads from EasyOCR,
        each is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]].
    :param overlap_threshold: Fraction of the shape's bounding box that must
        overlap a text region to be discarded (default 0.5 = 50%).
    :return: Tuple of (filtered contours, number of contours removed).
    """
    if not text_regions:
        return contours, 0

    # Pre-compute axis-aligned bounding boxes for all text regions
    text_bboxes = []
    for coords in text_regions:
        tx = min(pt[0] for pt in coords)
        ty = min(pt[1] for pt in coords)
        tx2 = max(pt[0] for pt in coords)
        ty2 = max(pt[1] for pt in coords)
        text_bboxes.append((tx, ty, tx2, ty2))

    kept = []
    removed = 0
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        shape_area = w * h
        if shape_area == 0:
            kept.append(contour)
            continue

        in_text_zone = False
        for tx, ty, tx2, ty2 in text_bboxes:
            ix1 = max(x, tx)
            iy1 = max(y, ty)
            ix2 = min(x + w, tx2)
            iy2 = min(y + h, ty2)
            if ix2 > ix1 and iy2 > iy1:
                intersection = (ix2 - ix1) * (iy2 - iy1)
                if intersection / shape_area >= overlap_threshold:
                    in_text_zone = True
                    break

        if in_text_zone:
            removed += 1
        else:
            kept.append(contour)

    return kept, removed


def extract_shapes(
    image_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    min_area: int = 50,
    max_area: int = 100000,
    threshold_value: int = 127,
    min_confidence: float = 0.6,
    text_regions: Optional[List[List[List[int]]]] = None,
    debug: bool = False,
):
    image = preprocessing.read_image(image_path)
    if image is None:
        raise ValueError(f"Unable to load image: {image_path}")

    image_flat = preprocessing.flat_field_correction(image, sigma=100.0, normalize=True)

    image_denoised = preprocessing.denoise_bilateral(
        image_flat, sigma_color=0.03, sigma_spatial=5.0
    )

    height, width = image_denoised.shape[:2]
    image_area = width * height

    image_uint8 = (image_denoised * 255).astype(np.uint8)

    image_bgr = cv2.cvtColor(image_uint8, cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    if debug:
        image_output_dir = os.path.join(output_dir, base_name)
        os.makedirs(image_output_dir, exist_ok=True)

    binary_mask = preprocess_image(gray, threshold_value)

    if debug:
        debug_mask_path = os.path.join(image_output_dir, "DEBUG_mask.png")
        cv2.imwrite(debug_mask_path, binary_mask)
        prepro_path = os.path.join(image_output_dir, "debug_1_preprocessing.png")
        cv2.imwrite(prepro_path, image_bgr)
        gray_path = os.path.join(image_output_dir, "debug_2_grayscale.png")
        cv2.imwrite(gray_path, gray)

    contours = detect_contours(binary_mask)

    filtered_contours, filter_stats = filter_contours(
        contours, min_area, max_area, image_area
    )

    # Filter out contours that fall inside detected text regions
    if text_regions:
        filtered_contours, n_removed = filter_text_overlapping_contours(
            filtered_contours, text_regions
        )
        logger.info(f"Removed {n_removed} shape(s) overlapping with text regions.")

    shapes_with_contours = []
    for idx, contour in enumerate(filtered_contours, 1):
        shape_data = extract_contour_properties(contour, image_bgr, binary_mask, idx)
        if shape_data:
            shapes_with_contours.append((shape_data, contour))

    final_shapes_with_contours = shapes_with_contours

    shapes_metadata = []
    for idx, (shape, contour) in enumerate(final_shapes_with_contours, 1):
        if debug:
            save_shape_image(image_bgr, contour, image_output_dir, idx)

        relative_size = shape["area"] / image_area if image_area else 0

        metadata = {
            "shape_id": idx,
            "morphology": {
                "area": shape["area"],
                "relative_size": relative_size,
                "aspect_ratio": shape["aspect_ratio"],
                "solidity": shape["solidity"],
                "extent": shape["extent"],
                "num_vertices": shape.get("num_vertices", 0),
                "perimeter": shape.get("perimeter", 0),
            },
            "bounding_box": shape.get("bounding_box", {}),
            "center": shape.get("center", {}),
            "geometry": shape.get("geometry", {}),
            "properties": shape.get("properties", {}),
        }

        shapes_metadata.append(metadata)

    if debug:
        metadata_path = os.path.join(image_output_dir, "shapes_metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "image_info": {
                        "source_path": image_path,
                        "dimensions": f"{width}x{height}",
                        "total_area": image_area,
                        "extraction_date": datetime.now().isoformat(),
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

        export_shapes_to_normalized_geojson(
            final_shapes_with_contours, image_output_dir
        )

    final_shapes = [shape for shape, contour in final_shapes_with_contours]

    normalized_features = create_normalized_geojson_features(final_shapes_with_contours)
    pixel_features = create_pixel_geojson_features(final_shapes_with_contours)

    if debug:
        try:
            reconstruct_shapes_debug(
                image_bgr, final_shapes_with_contours, image_output_dir
            )
        except cv2.error as e:
            logger.error(
                f"OpenCV error while reconstructing debug images for {image_path}: {e}"
            )
        except OSError as e:
            logger.error(
                f"I/O error while reconstructing debug images for {image_path}: {e}"
            )

    return {
        "total_shapes": len(final_shapes_with_contours),
        "shapes": final_shapes,
        "normalized_features": normalized_features,
        "pixel_features": pixel_features,
    }


def create_normalized_geojson_features(
    final_shapes_with_contours: List[Tuple[Dict, np.ndarray]],
) -> List[Dict]:
    """Create normalized GeoJSON features in memory without writing to file."""
    geojson_features = []

    for idx, (shape, contour) in enumerate(final_shapes_with_contours, 1):
        bbox = shape["bounding_box"]
        x_min, y_min = bbox["x"], bbox["y"]
        w, h = bbox["width"], bbox["height"]
        if w == 0 or h == 0:
            continue

        simple_points = shape["geometry"]["pixel_coords"]["contour_points"]
        normalized_coords = []
        for pt in simple_points:
            x_norm = (pt[0] - x_min) / w
            y_norm = (pt[1] - y_min) / h
            normalized_coords.append([x_norm, y_norm])

        if len(normalized_coords) >= 3:
            if normalized_coords[0] != normalized_coords[-1]:
                normalized_coords.append(normalized_coords[0])

        polygon = Polygon(normalized_coords)

        minx, miny, maxx, maxy = polygon.bounds
        width_norm = maxx - minx
        height_norm = maxy - miny
        max_dim = max(width_norm, height_norm)

        if max_dim > 0:
            scale = 1.0 / max_dim
        else:
            scale = 1.0

        translated = affinity.translate(polygon, xoff=-minx, yoff=-miny)
        scaled = affinity.scale(
            translated,
            xfact=scale,
            yfact=scale,
            origin=(0.0, 0.0),
        )

        width_scaled = width_norm * scale
        height_scaled = height_norm * scale
        offset_x = (1.0 - width_scaled) / 2.0
        offset_y = (1.0 - height_scaled) / 2.0

        normalized_geom = affinity.translate(
            scaled,
            xoff=offset_x,
            yoff=offset_y,
        )

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
                "color_rgb": shape.get("color_rgb"),
                "color_name": shape.get("color_name"),
                "color_hex": shape.get("color_hex"),
                "mapElementType": "shape",
                "name": f"Shape {idx}",
                "is_normalized": True,
                "start_date": "1700-01-01",
                "end_date": "2026-01-01",
            },
            "geometry": normalized_geom.__geo_interface__,
        }

        geojson_features.append(feature)

    feature_collection = {
        "type": "FeatureCollection",
        "features": geojson_features,
    }

    return [feature_collection]


def create_pixel_geojson_features(
    final_shapes_with_contours: List[Tuple[Dict, np.ndarray]],
) -> List[Dict]:
    """Create pixel-space GeoJSON features (non-normalized) for georeferencing."""
    geojson_features = []

    for idx, (shape, contour) in enumerate(final_shapes_with_contours, 1):
        simple_points = shape["geometry"]["pixel_coords"]["contour_points"]

        pixel_coords = [[pt[0], pt[1]] for pt in simple_points]

        if len(pixel_coords) < 3:
            continue

        if pixel_coords[0] != pixel_coords[-1]:
            pixel_coords.append(pixel_coords[0])

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
                "color_rgb": shape.get("color_rgb"),
                "color_name": shape.get("color_name"),
                "color_hex": shape.get("color_hex"),
                "mapElementType": "shape",
                "name": f"Shape {idx}",
                "is_pixel_space": True,
                "start_date": "1700-01-01",
                "end_date": "2026-01-01",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [pixel_coords],
            },
        }

        geojson_features.append(feature)

    feature_collection = {
        "type": "FeatureCollection",
        "features": geojson_features,
    }

    return [feature_collection]


def export_shapes_to_normalized_geojson(
    final_shapes_with_contours: List[Tuple[Dict, np.ndarray]],
    image_output_dir: str,
) -> str:
    """Export shapes to normalized GeoJSON file on disk."""
    features = create_normalized_geojson_features(final_shapes_with_contours)
    geojson_path = os.path.join(image_output_dir, "shapes_normalized.geojson")
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(features[0], f, indent=2, ensure_ascii=False)
    return geojson_path


def preprocess_image(gray: np.ndarray, threshold_value: int = 127) -> np.ndarray:
    unique_values = np.unique(gray)

    if len(unique_values) <= 3:
        binary = (gray > 127).astype(np.uint8) * 255
    else:
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )

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

    color_rgb = get_dominant_color_in_contour(original_image, contour)
    color_name = get_nearest_css4_color_name(color_rgb)
    color_hex = "#{:02x}{:02x}{:02x}".format(*color_rgb)

    simple_points = [[int(pt[0][0]), int(pt[0][1])] for pt in contour]
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
        "color_rgb": color_rgb,
        "color_name": color_name,
        "color_hex": color_hex,
        "geometry": {
            "type": "Polygon",
            "pixel_coords": {
                "contour_points": simple_points,
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
    h, w = image.shape[:2]

    mask = np.zeros((h, w), dtype=np.uint8)

    color_img = np.full((h, w, 3), 255, dtype=np.uint8)

    for idx, (shape, contour) in enumerate(final_shapes_with_contours, 1):
        cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)

        rng = np.random.RandomState(idx)
        color = tuple(int(c) for c in rng.randint(50, 230, size=3))
        cv2.drawContours(color_img, [contour], -1, color, thickness=cv2.FILLED)

    mask_path = os.path.join(output_dir, "reconstructed_mask.png")
    cv2.imwrite(mask_path, mask)

    overlay = image.copy()
    colored_only = cv2.bitwise_and(color_img, color_img, mask=mask)
    inv_mask = cv2.bitwise_not(mask)
    background = cv2.bitwise_and(overlay, overlay, mask=inv_mask)
    composed = cv2.addWeighted(background, 0.3, colored_only, 0.7, 0, dtype=cv2.CV_8U)

    overlay_path = os.path.join(output_dir, "reconstructed_overlay.png")
    cv2.imwrite(overlay_path, composed)

    return mask_path, overlay_path
