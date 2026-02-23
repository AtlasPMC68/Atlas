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

    def _overlaps_text(contour: np.ndarray) -> bool:
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

    kept = [c for c in contours if not _overlaps_text(c)]
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
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
    )


def detect_contours(binary_mask: np.ndarray) -> List[np.ndarray]:
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    return list(contours) if contours else []


def filter_contours(
    contours: List[np.ndarray],
    min_area: int,
    max_area: int,
    image_area: int,
) -> List[np.ndarray]:
    """Keep contours whose area falls in [min_area, max_area] and whose
    ratio to the total image area is ≤ 50 %."""

    def _keep(contour: np.ndarray) -> bool:
        area = cv2.contourArea(contour)
        return (
            min_area <= area <= max_area
            and area / image_area <= 0.5
            and len(contour) >= 3
        )

    return [c for c in contours if _keep(c)]


def extract_contour_properties(
    contour: np.ndarray,
    original_image: np.ndarray,
    binary_mask: np.ndarray,
    shape_id: int,
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

    approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
    color_rgb = get_dominant_color_in_contour(original_image, contour)

    bounding_box = {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}

    return {
        "id": shape_id,
        "area": float(area),
        "perimeter": float(perimeter),
        "bounding_box": bounding_box,
        "center": {"x": int(cx), "y": int(cy)},
        "aspect_ratio": round(aspect_ratio, 2),
        "extent": round(extent, 3),
        "solidity": round(solidity, 3),
        "num_vertices": len(approx),
        "color_rgb": color_rgb,
        "color_name": get_nearest_css4_color_name(color_rgb),
        "color_hex": "#{:02x}{:02x}{:02x}".format(*color_rgb),
        "geometry": {
            "type": "Polygon",
            "pixel_coords": {
                "contour_points": [[int(pt[0][0]), int(pt[0][1])] for pt in contour],
                "bounding_box": bounding_box,
                "center": {"x": int(cx), "y": int(cy)},
            },
        },
    }


# ---------------------------------------------------------------------------
# Debug I/O helpers
# ---------------------------------------------------------------------------


def save_shape_image(
    image: np.ndarray, contour: np.ndarray, output_dir: str, shape_id: int
) -> str:
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [contour], 0, 255, -1)

    x, y, w, h = cv2.boundingRect(contour)
    cropped = cv2.bitwise_and(image, image, mask=mask)[y : y + h, x : x + w]

    shape_path = os.path.join(output_dir, f"shape_{shape_id:04d}.png")
    cv2.imwrite(shape_path, cropped)
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


def _build_feature_properties(shape: Dict, idx: int, **extra) -> Dict:
    """Shared base properties for every GeoJSON feature."""
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
        "name": f"Shape {idx}",
        "start_date": "1700-01-01",
        "end_date": "2026-01-01",
        **extra,
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
                "properties": _build_feature_properties(shape, idx, is_normalized=True),
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
                "properties": _build_feature_properties(
                    shape, idx, is_pixel_space=True
                ),
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
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    """Load, denoise, and binarise an image.

    Returns (image_bgr, gray, binary_mask, width, height).
    """
    image = preprocessing.read_image(image_path)
    if image is None:
        raise ValueError(f"Unable to load image: {image_path}")

    image_flat = preprocessing.flat_field_correction(image, sigma=100.0, normalize=True)
    image_denoised = preprocessing.denoise_bilateral(
        image_flat, sigma_color=0.03, sigma_spatial=5.0
    )

    height, width = image_denoised.shape[:2]
    image_uint8 = (image_denoised * 255).astype(np.uint8)
    image_bgr = cv2.cvtColor(image_uint8, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    binary_mask = preprocess_image(gray, threshold_value)

    return image_bgr, gray, binary_mask, width, height


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
    gray: np.ndarray,
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
) -> None:
    cv2.imwrite(os.path.join(image_output_dir, "DEBUG_mask.png"), binary_mask)
    cv2.imwrite(os.path.join(image_output_dir, "debug_1_preprocessing.png"), image_bgr)
    cv2.imwrite(os.path.join(image_output_dir, "debug_2_grayscale.png"), gray)

    for idx, (_, contour) in enumerate(shapes_with_contours, 1):
        save_shape_image(image_bgr, contour, image_output_dir, idx)

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
    max_area: int = 100_000,
    threshold_value: int = 127,
    text_regions: Optional[List[List[List[int]]]] = None,
    debug: bool = False,
) -> Dict:
    image_bgr, gray, binary_mask, width, height = _preprocess_for_contours(
        image_path, threshold_value
    )
    image_area = width * height

    contours = detect_contours(binary_mask)
    filtered = filter_contours(contours, min_area, max_area, image_area)

    if text_regions:
        filtered, n_removed = filter_text_overlapping_contours(filtered, text_regions)
        logger.info("Removed %d shape(s) overlapping with text regions.", n_removed)

    shapes_with_contours = [
        (shape, contour)
        for idx, contour in enumerate(filtered, 1)
        if (shape := extract_contour_properties(contour, image_bgr, binary_mask, idx))
    ]

    if debug:
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        image_output_dir = os.path.join(output_dir, base_name)
        os.makedirs(image_output_dir, exist_ok=True)

        shapes_metadata = _build_shapes_metadata(shapes_with_contours, image_area)
        _write_debug_outputs(
            image_bgr,
            gray,
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
        )

    return {
        "total_shapes": len(shapes_with_contours),
        "shapes": [shape for shape, _ in shapes_with_contours],
        "normalized_features": create_normalized_geojson_features(shapes_with_contours),
        "pixel_features": create_pixel_geojson_features(shapes_with_contours),
    }
