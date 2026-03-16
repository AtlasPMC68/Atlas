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

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "extracted_shapes")


def extract_shapes(
    image_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    min_area: int = 100,
    max_area: int = 100000,
    threshold_value: int = 127,
    min_confidence: float = 0.6,
    debug: bool = True,
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

    legend_bbox = detect_legend_bbox(image_bgr, debug_dir=image_output_dir if debug else None)

    legend_swatches = []
    if legend_bbox is not None:
        legend_swatches = detect_legend_swatches(
            image_bgr,
            legend_bbox,
            debug_dir=image_output_dir if debug else None,
        )

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    if debug:
        image_output_dir = os.path.join(output_dir, base_name)
        os.makedirs(image_output_dir, exist_ok=True)

    binary_mask = preprocess_image(gray, threshold_value)

    if debug:
        debug_mask_path = os.path.join(image_output_dir, "DEBUG_mask.png")
        cv2.imwrite(debug_mask_path, binary_mask)

    contours = detect_contours(binary_mask)

    filtered_contours, filter_stats = filter_contours(
        contours, min_area, max_area, image_area
    )

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
        "legend": {
            "bbox": legend_bbox,
            "swatches": legend_swatches,
        },  
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

def _rect_from_contour(contour: np.ndarray, min_area: float) -> Optional[Dict]:
    area = cv2.contourArea(contour)
    if area < min_area:
        return None

    peri = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

    if len(approx) != 4 or not cv2.isContourConvex(approx):
        return None

    x, y, w, h = cv2.boundingRect(approx)
    if w <= 0 or h <= 0:
        return None

    extent = area / float(w * h)
    if extent < 0.85:
        return None

    return {
        "contour": contour,
        "approx": approx,
        "bbox": (x, y, w, h),
        "area": float(area),
        "extent": float(extent),
        "aspect_ratio": float(w / h),
    }


def detect_legend_bbox(
    image_bgr: np.ndarray,
    *,
    min_area_ratio: float = 0.002,
    max_area_ratio: float = 0.25,
    debug_dir: Optional[str] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """
    Detect the most likely legend rectangle bbox (x,y,w,h).
    Uses edge-based rectangle detection + heuristic scoring.
    """
    h, w = image_bgr.shape[:2]
    img_area = float(h * w)

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    # Close gaps in rectangle borders
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=1)

    if debug_dir is not None:
        cv2.imwrite(os.path.join(debug_dir, "DEBUG_legend_edges.png"), edges)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = img_area * min_area_ratio
    max_area = img_area * max_area_ratio

    rects = []
    for c in contours:
        info = _rect_from_contour(c, min_area=min_area)
        if info is None:
            continue
        if info["area"] > max_area:
            continue
        rects.append(info)

    if not rects:
        return None

    def score_candidate(bbox: Tuple[int, int, int, int]) -> float:
        x, y, bw, bh = bbox
        roi = image_bgr[y:y+bh, x:x+bw]
        if roi.size == 0:
            return -1e9

        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        roi_edges = cv2.Canny(roi_gray, 50, 150)
        edge_density = float(np.mean(roi_edges > 0))  # [0..1]

        # Count small rectangle-like blobs inside ROI (legend often has swatches/boxes)
        th = cv2.adaptiveThreshold(
            roi_gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 21, 7
        )
        th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        roi_area = float(bw * bh)
        small_rects = 0
        for cc in cnts:
            a = cv2.contourArea(cc)
            if a < roi_area * 0.001 or a > roi_area * 0.20:
                continue
            peri = cv2.arcLength(cc, True)
            approx = cv2.approxPolyDP(cc, 0.03 * peri, True)
            if len(approx) == 4:
                small_rects += 1

        # Tune weights here
        return 2.0 * edge_density + 0.05 * small_rects

    best_bbox = None
    best_score = -1e9
    for r in rects:
        s = score_candidate(r["bbox"])
        if s > best_score:
            best_score = s
            best_bbox = r["bbox"]

    if best_bbox is None:
        return None

    if debug_dir is not None:
        x, y, bw, bh = best_bbox
        roi = image_bgr[y:y+bh, x:x+bw]
        cv2.imwrite(os.path.join(debug_dir, "DEBUG_legend_roi.png"), roi)

    return best_bbox


def detect_legend_swatches(
    image_bgr: np.ndarray,
    legend_bbox: Tuple[int, int, int, int],
    *,
    debug_dir: Optional[str] = None,
) -> List[Dict]:
    """
    Detect colored sub-rectangles (swatches) inside the legend ROI.
    Returns list of {bbox, mean_bgr}.
    """
    x, y, w, h = legend_bbox
    roi = image_bgr[y:y+h, x:x+w]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)

    # "Colored" pixels: high saturation, not too dark
    mask = ((S > 40) & (V > 40)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=1)

    if debug_dir is not None:
        cv2.imwrite(os.path.join(debug_dir, "DEBUG_legend_color_mask.png"), mask)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    swatches: List[Dict] = []
    roi_area = float(w * h)

    for c in cnts:
        a = cv2.contourArea(c)
        if a < roi_area * 0.002 or a > roi_area * 0.30:
            continue

        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.03 * peri, True)
        if len(approx) != 4:
            continue

        bx, by, bw, bh = cv2.boundingRect(approx)
        extent = a / float(bw * bh + 1e-6)
        if extent < 0.75:
            continue

        cmask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(cmask, [c], -1, 255, thickness=cv2.FILLED)
        mean_bgr = cv2.mean(roi, mask=cmask)[:3]

        swatches.append(
            {
                "bbox": (x + bx, y + by, bw, bh),
                "mean_bgr": mean_bgr,
                "area": float(a),
            }
        )

    # Sort top-to-bottom then left-to-right (useful for pairing with text later)
    swatches.sort(key=lambda s: (s["bbox"][1], s["bbox"][0]))

    if debug_dir is not None:
        dbg = image_bgr.copy()
        for i, s in enumerate(swatches, 1):
            sx, sy, sw, sh = s["bbox"]
            cv2.rectangle(dbg, (sx, sy), (sx + sw, sy + sh), (0, 255, 0), 2)
            cv2.putText(dbg, str(i), (sx, sy - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imwrite(os.path.join(debug_dir, "DEBUG_legend_swatches.png"), dbg)

    return swatches


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
