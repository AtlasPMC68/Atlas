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

LegendBounds = Dict[str, float]

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "extracted_shapes")

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def get_dominant_color_in_contour(
    image_bgr: np.ndarray,
    contour: np.ndarray,
) -> Tuple[int, int, int]:
    """Return the dominant RGB color inside a contour via coarse 8×8×8 binning."""
    mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)

    pixels_bgr = image_bgr[mask == 255]
    if len(pixels_bgr) == 0:
        return (128, 128, 128)

    pixels_rgb = pixels_bgr[:, ::-1]
    quantized = (pixels_rgb // 32).astype(np.int32)
    bin_ids = quantized[:, 0] * 64 + quantized[:, 1] * 8 + quantized[:, 2]
    unique_bins, counts = np.unique(bin_ids, return_counts=True)
    dominant_bin = int(unique_bins[np.argmax(counts)])

    r_bin, g_bin, b_bin = dominant_bin // 64, (dominant_bin % 64) // 8, dominant_bin % 8
    return (r_bin * 32 + 16, g_bin * 32 + 16, b_bin * 32 + 16)


def _overlaps_text(
    contour: np.ndarray,
    text_bboxes: List[Tuple[int, int, int, int]],
    overlap_threshold: float,
) -> bool:
    """Check if a contour overlaps with a text region."""
    x, y, w, h = cv2.boundingRect(contour)
    shape_area = w * h
    if shape_area == 0:
        return False
    for tx, ty, tx2, ty2 in text_bboxes:
        ix1, iy1 = max(x, tx), max(y, ty)
        ix2, iy2 = min(x + w, tx2), min(y + h, ty2)
        if ix2 > ix1 and iy2 > iy1:
            if (ix2 - ix1) * (iy2 - iy1) / shape_area >= overlap_threshold:
                return True
    return False


def filter_text_overlapping_contours(
    contours: List[np.ndarray],
    text_regions: List[List[List[int]]],
    overlap_threshold: float = 0.5,
) -> Tuple[List[np.ndarray], int]:
    """Drop contours whose bounding box overlaps a text region by ≥ *overlap_threshold*."""
    if not text_regions:
        return contours, 0

    text_bboxes = [
        (
            min(p[0] for p in r),
            min(p[1] for p in r),
            max(p[0] for p in r),
            max(p[1] for p in r),
        )
        for r in text_regions
    ]

    kept = [
        c for c in contours if not _overlaps_text(c, text_bboxes, overlap_threshold)
    ]
    return kept, len(contours) - len(kept)


# ---------------------------------------------------------------------------
# Contour filtering & property extraction
# ---------------------------------------------------------------------------


def preprocess_image(gray: np.ndarray, threshold_value: int = 127) -> np.ndarray:
    """Binarise a grayscale image.  Uses a simple threshold for near-binary
    inputs and adaptive Gaussian thresholding otherwise."""
    if len(np.unique(gray)) <= 3:
        return (gray > 127).astype(np.uint8) * 255

    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 6
    )


def detect_contours(binary_mask: np.ndarray) -> List[np.ndarray]:
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    return list(contours) if contours else []


def _should_keep_contour(
    contour: np.ndarray,
    min_area: int,
    max_area: int,
    image_area: int,
) -> bool:
    """Check if a contour should be kept based on area criteria."""
    area = cv2.contourArea(contour)
    return (
        min_area <= area <= max_area and area / image_area <= 0.5 and len(contour) >= 3
    )


def filter_contours(
    contours: List[np.ndarray],
    min_area: int,
    max_area: int,
    image_area: int,
) -> List[np.ndarray]:
    """Keep contours whose area falls in [min_area, max_area] and whose
    ratio to the total image area is ≤ 50 %."""
    return [
        c for c in contours if _should_keep_contour(c, min_area, max_area, image_area)
    ]


def extract_contour_properties(
    contour: np.ndarray,
    original_image: np.ndarray,
    binary_mask: np.ndarray,
    shape_id: int,
    hough_circles: Optional[List[Tuple[int, int, int]]] = None,
    legend_bounds: Optional[LegendBounds] = None,
) -> Optional[Dict]:
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)

    x, y, w, h = cv2.boundingRect(contour)
    aspect_ratio = float(w) / h if h > 0 else 0.0
    extent = area / (w * h) if w * h > 0 else 0.0

    moments = cv2.moments(contour)
    if moments["m00"] != 0:
        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])
    else:
        cx, cy = x + w // 2, y + h // 2

    hull_area = cv2.contourArea(cv2.convexHull(contour))
    solidity = area / hull_area if hull_area > 0 else 0.0

    approx = cv2.approxPolyDP(contour, 0.001 * perimeter, True)
    color_rgb = get_dominant_color_in_contour(original_image, contour)

    bounding_box = {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}

    rect_score = compute_rect_score(contour)   

    properties_dict = {
        "id": shape_id,
        "area": float(area),
        "perimeter": float(perimeter),
        "bounding_box": bounding_box,
        "center": {"x": int(cx), "y": int(cy)},
        "aspect_ratio": round(aspect_ratio, 2),
        "extent": round(extent, 3),
        "solidity": round(solidity, 3),
        "num_vertices": len(approx),
        "rect_score": round(rect_score, 3),
        "color_rgb": color_rgb,
        "color_name": get_nearest_css4_color_name(color_rgb),
        "color_hex": "#{:02x}{:02x}{:02x}".format(*color_rgb),
        "geometry": {
            "type": "Polygon",
            "pixel_coords": {
                "contour_points": [[int(pt[0][0]), int(pt[0][1])] for pt in approx],
                "bounding_box": bounding_box,
                "center": {"x": int(cx), "y": int(cy)},
            },
        },
    }

    properties_dict["shape_type"] = classify_shape(
        properties_dict,
        hough_circles=hough_circles,
    )

    return properties_dict


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
def detect_circles_hough(image_bgr: np.ndarray) -> List[Tuple[int, int, int]]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray_blurred = cv2.medianBlur(gray, 5)

    circles = cv2.HoughCircles(
        gray_blurred,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=20,        
        param1=50,         
        param2=30,        
        minRadius=5,
        maxRadius=0,       
    )
    if circles is not None:
        return [(int(x), int(y), int(r)) for x, y, r in circles[0]]
    return []

def compute_rect_score(contour: np.ndarray) -> float:
    area = cv2.contourArea(contour)
    if area == 0:
        return 0.0

    _, (rw, rh), _ = cv2.minAreaRect(contour)
    rect_area = rw * rh
    return area / rect_area if rect_area > 0 else 0.0

def classify_shape(
    properties: dict,
    hough_circles: Optional[List[Tuple[int, int, int]]] = None,
) -> str:
    area       = properties.get("area", 0.0)
    perimeter  = properties.get("perimeter", 0.0)
    rect_score = properties.get("rect_score", 0.0)

    circularity = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0.0

    cx = properties.get("center", {}).get("x", -1)
    cy = properties.get("center", {}).get("y", -1)

    hough_confirms = any(
        abs(cx - hx) < 15 and abs(cy - hy) < 15
        for hx, hy, _ in (hough_circles or [])
    )

    if circularity > 0.85 and hough_confirms:
        return "Circle"

    if rect_score > 0.85:
        return "Rectangle"

    return "Shape unknown"


def _is_inside_legend_bounds(
    cx: float,
    cy: float,
    legend_bounds: Optional[LegendBounds],
) -> bool:
    if not legend_bounds:
        return False

    x = legend_bounds.get("x", 0.0)
    y = legend_bounds.get("y", 0.0)
    w = legend_bounds.get("width", 0.0)
    h = legend_bounds.get("height", 0.0)

    if w <= 0 or h <= 0:
        return False

    return x <= cx <= (x + w) and y <= cy <= (y + h)


def _contour_to_polygon(contour: np.ndarray) -> Optional[Polygon]:
    if contour is None or len(contour) < 3:
        return None

    points = contour.reshape(-1, 2)
    if len(points) < 3:
        return None

    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if polygon.is_empty:
        return None

    return polygon


def _is_duplicate_shape(
    candidate_contour: np.ndarray,
    candidate_area: float,
    kept_contour: np.ndarray,
    kept_area: float,
    overlap_threshold: float,
    area_similarity_threshold: float,
) -> bool:
    if candidate_area <= 0 or kept_area <= 0:
        return False

    area_similarity = min(candidate_area, kept_area) / max(candidate_area, kept_area)
    if area_similarity < area_similarity_threshold:
        return False

    candidate_poly = _contour_to_polygon(candidate_contour)
    kept_poly = _contour_to_polygon(kept_contour)
    if candidate_poly is None or kept_poly is None:
        return False

    intersection_area = candidate_poly.intersection(kept_poly).area
    if intersection_area <= 0:
        return False

    overlap_ratio = intersection_area / min(candidate_area, kept_area)
    return overlap_ratio >= overlap_threshold


def post_filter_shapes(
    shapes_with_contours: List[Tuple[Dict, np.ndarray]],
    unknown_min_area: float = 80.0,
    unknown_max_area: float = 3000.0,
    overlap_threshold: float = 0.7,
    area_similarity_threshold: float = 0.95,
    legend_bounds: Optional[LegendBounds] = None,
    legend_coverage_threshold: float = 0.9,
) -> List[Tuple[Dict, np.ndarray]]:
    """Final filtering pass:
    1) Remove Shape unknown outside configured area range.
    2) Remove shapes covering too much of selected legend zone.
    3) Remove near-duplicate overlapping shapes across all classes.
    """
    filtered_unknown_noise: List[Tuple[Dict, np.ndarray]] = []
    legend_area = 0.0
    if legend_bounds:
        legend_width = float(legend_bounds.get("width", 0.0))
        legend_height = float(legend_bounds.get("height", 0.0))
        if legend_width > 0 and legend_height > 0:
            legend_area = legend_width * legend_height

    for shape, contour in shapes_with_contours:
        shape_type = shape.get("shape_type")
        area = float(shape.get("area", 0.0))

        if shape_type == "Shape unknown" and (
            area < unknown_min_area or area > unknown_max_area
        ):
            continue

        if legend_area > 0:
            center = shape.get("center", {})
            cx = float(center.get("x", -1.0))
            cy = float(center.get("y", -1.0))
            if _is_inside_legend_bounds(cx, cy, legend_bounds):
                legend_coverage = area / legend_area
                if legend_coverage >= legend_coverage_threshold:
                    continue

        filtered_unknown_noise.append((shape, contour))

    sorted_candidates = sorted(
        filtered_unknown_noise,
        key=lambda item: float(item[0].get("area", 0.0)),
        reverse=True,
    )

    deduped: List[Tuple[Dict, np.ndarray]] = []
    for candidate_shape, candidate_contour in sorted_candidates:
        candidate_area = float(candidate_shape.get("area", 0.0))

        is_duplicate = False
        for kept_shape, kept_contour in deduped:
            kept_area = float(kept_shape.get("area", 0.0))
            if _is_duplicate_shape(
                candidate_contour,
                candidate_area,
                kept_contour,
                kept_area,
                overlap_threshold,
                area_similarity_threshold,
            ):
                is_duplicate = True
                break

        if not is_duplicate:
            deduped.append((candidate_shape, candidate_contour))

    return deduped


# ---------------------------------------------------------------------------
# Debug I/O helpers
# ---------------------------------------------------------------------------


def save_shape_image(
    image: np.ndarray,
    contour: np.ndarray,
    output_dir: str,
    shape_id: int,
    shape_type: str,
) -> str:
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [contour], 0, 255, -1)

    x, y, w, h = cv2.boundingRect(contour)
    cropped_bgr = cv2.bitwise_and(image, image, mask=mask)[y : y + h, x : x + w]
    alpha = mask[y : y + h, x : x + w]

    if cropped_bgr.size == 0:
        bgra = np.zeros((max(1, h), max(1, w), 4), dtype=np.uint8)
    else:
        bgra = cv2.cvtColor(cropped_bgr, cv2.COLOR_BGR2BGRA)
        if alpha.shape[:2] != bgra.shape[:2]:
            alpha = cv2.resize(alpha, (bgra.shape[1], bgra.shape[0]))
        bgra[:, :, 3] = alpha

    shape_path = os.path.join(output_dir, f"{shape_type}_{shape_id:04d}.png")
    cv2.imwrite(shape_path, bgra)
    return shape_path


def reconstruct_shapes_debug(
    image: np.ndarray,
    shapes_with_contours: List[Tuple[Dict, np.ndarray]],
    output_dir: str,
) -> Tuple[str, str]:
    h, w = image.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    color_img = np.full((h, w, 3), 255, dtype=np.uint8)

    for idx, (_, contour) in enumerate(shapes_with_contours, 1):
        cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
        color = tuple(int(c) for c in np.random.RandomState(idx).randint(50, 230, 3))
        cv2.drawContours(color_img, [contour], -1, color, thickness=cv2.FILLED)

    mask_path = os.path.join(output_dir, "reconstructed_mask.png")
    cv2.imwrite(mask_path, mask)

    inv_mask = cv2.bitwise_not(mask)
    background = cv2.bitwise_and(image, image, mask=inv_mask)
    colored = cv2.bitwise_and(color_img, color_img, mask=mask)
    composed = cv2.addWeighted(background, 0.3, colored, 0.7, 0, dtype=cv2.CV_8U)

    overlay_path = os.path.join(output_dir, "reconstructed_overlay.png")
    cv2.imwrite(overlay_path, composed)
    return mask_path, overlay_path


# ---------------------------------------------------------------------------
# GeoJSON helpers
# ---------------------------------------------------------------------------


def _build_normalized_feature_properties(shape: Dict, idx: int) -> Dict:
    """Properties for normalized GeoJSON features ([0,1]² space)."""
    return {
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
        "name": f"{shape.get('shape_type') or 'Shape'} {idx}",
        "is_normalized": True,
    }


def _build_pixel_feature_properties(shape: Dict, idx: int) -> Dict:
    """Properties for pixel-space GeoJSON features (original image coordinates)."""
    return {
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
        "name": f"{shape.get('shape_type') or 'Shape'} {idx}",
        "is_normalized": False,
    }


def _normalize_contour_polygon(shape: Dict) -> Optional[Polygon]:
    """Return a [0, 1]² normalised and centred Shapely Polygon, or None."""
    bbox = shape["bounding_box"]
    w, h = bbox["width"], bbox["height"]
    if w == 0 or h == 0:
        return None

    x_min, y_min = bbox["x"], bbox["y"]
    pts = shape["geometry"]["pixel_coords"]["contour_points"]
    coords = [((p[0] - x_min) / w, (p[1] - y_min) / h) for p in pts]

    if len(coords) < 3:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    polygon = Polygon(coords)
    minx, miny, maxx, maxy = polygon.bounds
    scale = 1.0 / max(maxx - minx, maxy - miny, 1e-9)

    translated = affinity.translate(polygon, xoff=-minx, yoff=-miny)
    scaled = affinity.scale(translated, xfact=scale, yfact=scale, origin=(0.0, 0.0))

    sx, sy = (maxx - minx) * scale, (maxy - miny) * scale
    return affinity.translate(scaled, xoff=(1.0 - sx) / 2.0, yoff=(1.0 - sy) / 2.0)


def create_normalized_geojson_features(
    shapes_with_contours: List[Tuple[Dict, np.ndarray]],
) -> List[Dict]:
    """GeoJSON FeatureCollection with each shape normalised to [0, 1]²."""
    features = []
    for idx, (shape, _) in enumerate(shapes_with_contours, 1):
        polygon = _normalize_contour_polygon(shape)
        if polygon is None:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": _build_normalized_feature_properties(shape, idx),
                "geometry": polygon.__geo_interface__,
            }
        )

    return [{"type": "FeatureCollection", "features": features}]


def create_pixel_geojson_features(
    shapes_with_contours: List[Tuple[Dict, np.ndarray]],
) -> List[Dict]:
    """GeoJSON FeatureCollection in original pixel space (for georeferencing)."""
    features = []
    for idx, (shape, _) in enumerate(shapes_with_contours, 1):
        coords = [
            [p[0], p[1]] for p in shape["geometry"]["pixel_coords"]["contour_points"]
        ]
        if len(coords) < 3:
            continue
        if coords[0] != coords[-1]:
            coords.append(coords[0])

        features.append(
            {
                "type": "Feature",
                "properties": _build_pixel_feature_properties(shape, idx),
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }
        )

    return [{"type": "FeatureCollection", "features": features}]


def export_shapes_to_normalized_geojson(
    shapes_with_contours: List[Tuple[Dict, np.ndarray]],
    image_output_dir: str,
) -> str:
    """Write normalized GeoJSON to disk and return the path."""
    geojson_path = os.path.join(image_output_dir, "shapes_normalized.geojson")
    feature_collection = create_normalized_geojson_features(shapes_with_contours)[0]
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, indent=2, ensure_ascii=False)
    return geojson_path


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _preprocess_for_contours(
    image_path: str,
    threshold_value: int,
) -> Dict:
    """Load, denoise, enhance contrast on L channel, and binarise an image.

    Returns a dict with all intermediate images and dimensions.
    """
    image = preprocessing.read_image(image_path)
    if image is None:
        raise ValueError(f"Unable to load image: {image_path}")

    height, width = image.shape[:2]
    image_uint8 = (image * 255).astype(np.uint8)
    image_bgr = cv2.cvtColor(image_uint8, cv2.COLOR_RGB2BGR)

    image_denoised = cv2.bilateralFilter(image_bgr, d=11, sigmaColor=75, sigmaSpace=75)

    lab = cv2.cvtColor(image_denoised, cv2.COLOR_BGR2LAB)
    lightness, _, _ = cv2.split(lab)

    l_norm = cv2.normalize(lightness, np.empty_like(lightness), alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(64, 64))
    l_enhanced = clahe.apply(l_norm)

    binary_mask = preprocess_image(l_enhanced, threshold_value)

    return {
        "image_bgr": image_bgr,
        "clahe": l_enhanced,
        "binary_mask": binary_mask,
        "width": width,
        "height": height,
        "image_denoised": image_denoised,
        "lightness": lightness,
        "l_norm": l_norm,
    }


def _build_shapes_metadata(
    shapes_with_contours: List[Tuple[Dict, np.ndarray]],
    image_area: int,
) -> List[Dict]:
    return [
        {
            "shape_id": idx,
            "morphology": {
                "area": shape["area"],
                "relative_size": shape["area"] / image_area if image_area else 0,
                "aspect_ratio": shape["aspect_ratio"],
                "solidity": shape["solidity"],
                "extent": shape["extent"],
                "num_vertices": shape.get("num_vertices", 0),
                "perimeter": shape.get("perimeter", 0),
            },
            "bounding_box": shape.get("bounding_box", {}),
            "center": shape.get("center", {}),
            "geometry": shape.get("geometry", {}),
        }
        for idx, (shape, _) in enumerate(shapes_with_contours, 1)
    ]


def _write_debug_outputs(
    image_bgr: np.ndarray,
    binary_mask: np.ndarray,
    shapes_with_contours: List[Tuple[Dict, np.ndarray]],
    image_path: str,
    image_output_dir: str,
    width: int,
    height: int,
    min_area: int,
    max_area: int,
    threshold_value: int,
    shapes_metadata: List[Dict],
    intermediate_images: Optional[Dict[str, np.ndarray]] = None,
) -> None:
    if intermediate_images:
        cv2.imwrite(
            os.path.join(image_output_dir, "debug_0_original_converted.png"),
            intermediate_images.get("image_bgr", image_bgr),
        )
        if "image_denoised" in intermediate_images:
            cv2.imwrite(
                os.path.join(image_output_dir, "debug_1_denoised.png"),
                intermediate_images["image_denoised"],
            )
        if "lightness" in intermediate_images:
            cv2.imwrite(
                os.path.join(image_output_dir, "debug_2_lightness.png"),
                intermediate_images["lightness"],
            )
        if "l_norm" in intermediate_images:
            cv2.imwrite(
                os.path.join(image_output_dir, "debug_3_l_normalized.png"),
                intermediate_images["l_norm"],
            )
        if "clahe" in intermediate_images:
            cv2.imwrite(
                os.path.join(image_output_dir, "debug_4_clahe.png"),
                intermediate_images["clahe"],
            )
    else:
        cv2.imwrite(
            os.path.join(image_output_dir, "debug_0_original_converted.png"), image_bgr
        )

    cv2.imwrite(os.path.join(image_output_dir, "debug_6_binary.png"), binary_mask)

    for idx, (shape, contour) in enumerate(shapes_with_contours, 1):
        save_shape_image(
            image_bgr,
            contour,
            image_output_dir,
            idx,
            shape.get("shape_type") or "Shape",
        )

    metadata_path = os.path.join(image_output_dir, "shapes_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "image_info": {
                    "source_path": image_path,
                    "dimensions": f"{width}x{height}",
                    "total_area": width * height,
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

    export_shapes_to_normalized_geojson(shapes_with_contours, image_output_dir)

    try:
        reconstruct_shapes_debug(image_bgr, shapes_with_contours, image_output_dir)
    except (cv2.error, OSError) as e:
        logger.error("Error writing debug reconstruction for %s: %s", image_path, e)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def extract_shapes(
    image_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    min_area: int = 50,
    max_area: int = 5000,
    threshold_value: int = 127,
    text_regions: Optional[List[List[List[int]]]] = None,
    legend_bounds: Optional[LegendBounds] = None,
    unknown_min_area_post: float = 500.0,
    unknown_max_area_post: float = 4000.0,
    overlap_threshold_post: float = 0.6,
    area_similarity_threshold_post: float = 0.6,
    debug: bool = False,
    legend_coverage_threshold_post: float = 0.9,
) -> Dict:
    preprocess_result = _preprocess_for_contours(image_path, threshold_value)
    image_bgr = preprocess_result["image_bgr"]
    binary_mask = preprocess_result["binary_mask"]
    width = preprocess_result["width"]
    height = preprocess_result["height"]
    image_area = width * height

    hough_circles = detect_circles_hough(image_bgr)

    contours = detect_contours(binary_mask)
    filtered = filter_contours(contours, min_area, max_area, image_area)

    if text_regions:
        filtered, n_removed = filter_text_overlapping_contours(filtered, text_regions)
        logger.info("Removed %d shape(s) overlapping with text regions.", n_removed)

    shapes_with_contours = [
        (shape, contour)
        for idx, contour in enumerate(filtered, 1)
        if (
            shape := extract_contour_properties(
                contour,
                image_bgr,
                binary_mask,
                idx,
                hough_circles=hough_circles,
                legend_bounds=legend_bounds,
            )
        )
    ]

    shapes_with_contours = post_filter_shapes(
        shapes_with_contours,
        unknown_min_area=unknown_min_area_post,
        unknown_max_area=unknown_max_area_post,
        overlap_threshold=overlap_threshold_post,
        area_similarity_threshold=area_similarity_threshold_post,
        legend_bounds=legend_bounds,
        legend_coverage_threshold=legend_coverage_threshold_post,
    )

    for shape, _ in shapes_with_contours:
        center = shape.get("center", {})
        cx = float(center.get("x", -1.0))
        cy = float(center.get("y", -1.0))
        shape["isLegend"] = _is_inside_legend_bounds(cx, cy, legend_bounds)

    legend_shapes_with_contours = [
        (shape, contour)
        for shape, contour in shapes_with_contours
        if shape.get("isLegend", False)
    ]
    non_legend_shapes_with_contours = [
        (shape, contour)
        for shape, contour in shapes_with_contours
        if not shape.get("isLegend", False)
    ]

    if debug:
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        image_output_dir = os.path.join(output_dir, base_name)
        os.makedirs(image_output_dir, exist_ok=True)

        shapes_metadata = _build_shapes_metadata(shapes_with_contours, image_area)
        _write_debug_outputs(
            image_bgr,
            binary_mask,
            shapes_with_contours,
            image_path,
            image_output_dir,
            width,
            height,
            min_area,
            max_area,
            threshold_value,
            shapes_metadata,
            intermediate_images=preprocess_result,
        )

    return {
        "total_shapes": len(shapes_with_contours),
        "shapes": [shape for shape, _ in shapes_with_contours],
        "normalized_features": create_normalized_geojson_features(
            non_legend_shapes_with_contours
        ),
        "pixel_features": create_pixel_geojson_features(non_legend_shapes_with_contours),
        "legend_pixel_features": create_pixel_geojson_features(
            legend_shapes_with_contours
        ),
    }
