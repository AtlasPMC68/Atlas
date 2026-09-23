import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
 
import cv2
import numpy as np
from shapely import affinity
from shapely.geometry import Polygon
from skimage.measure import find_contours

from . import preprocessing
from .color_extraction import get_nearest_css4_color_name

LegendBounds = Dict[str, float]

logger = logging.getLogger(__name__)
 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "extracted_shapes")

SIMPLE_BINARY_UNIQUE_LEVELS = 3
MAX_SHAPE_IMAGE_AREA_RATIO = 0.5
CONTOUR_APPROX_EPSILON_RATIO = 0.001
CIRCLE_MIN_RADIUS_PX = 2
CIRCLE_MIN_STEPS = 32
CIRCLE_MAX_STEPS = 360
CIRCLE_TARGET_SEGMENT_LENGTH_PX = 3.0

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
 
 
 
 
 
 
# ---------------------------------------------------------------------------
# Contour filtering & property extraction
# ---------------------------------------------------------------------------
 
 
 
 
 
 
 
 
 
 
def extract_contour_properties(
    contour: np.ndarray,
    original_image: np.ndarray,
    shape_id: int,
    hough_circles: Optional[List[Tuple[int, int, int]]] = None,
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

    approx = cv2.approxPolyDP(contour, CONTOUR_APPROX_EPSILON_RATIO * perimeter, True)
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
        "rect_score": round(rect_score, 3),
        "color_rgb": color_rgb,
        "color_name": get_nearest_css4_color_name(color_rgb),
        "color_hex": "#{:02x}{:02x}{:02x}".format(*color_rgb),
        "num_vertices": len(approx),
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

    ideal_points = idealize_shape_points(
        contour,
        properties_dict["shape_type"],
        approx=approx,
    )

    properties_dict["geometry"]["pixel_coords"]["contour_points"] = ideal_points

    if "num_vertices" in properties_dict:
        try:
            properties_dict["num_vertices"] = int(len(ideal_points))
        except TypeError:
            logger.warning(
                "Idealized contour points are not iterable; num_vertices not updated."
            )

    return properties_dict


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

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





def idealize_shape_points(
    contour: np.ndarray,
    shape_type: str,
    approx: Optional[np.ndarray] = None,
) -> List[List[float]]:
    
    if shape_type == "Rectangle":
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        return [[round(float(pt[0]), 3), round(float(pt[1]), 3)] for pt in box]
        
    elif shape_type == "Circle":
        (x, y), radius = cv2.minEnclosingCircle(contour)
        r = max(float(CIRCLE_MIN_RADIUS_PX), float(radius))

        perimeter = 2.0 * np.pi * r
        steps = int(np.ceil(perimeter / CIRCLE_TARGET_SEGMENT_LENGTH_PX))
        steps = int(np.clip(steps, CIRCLE_MIN_STEPS, CIRCLE_MAX_STEPS))

        points: List[List[float]] = []
        for i in range(steps):
            angle = (i / steps) * 2.0 * np.pi
            px = x + r * np.cos(angle)
            py = y + r * np.sin(angle)
            points.append([round(float(px), 3), round(float(py), 3)])

        return points
        
    else:
        if approx is None:
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(
                contour,
                CONTOUR_APPROX_EPSILON_RATIO * perimeter,
                True,
            )
        return [[float(pt[0][0]), float(pt[0][1])] for pt in approx]


def _sync_shape_metrics_with_contour(
    shape: Dict,
    contour_int: np.ndarray,
) -> None:
    """Keep shape metrics consistent with the final idealized contour."""
    area = float(cv2.contourArea(contour_int))
    perimeter = float(cv2.arcLength(contour_int, True))
    shape["area"] = area
    shape["perimeter"] = perimeter

    x, y, w, h = cv2.boundingRect(contour_int)
    bbox = {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}

    moments = cv2.moments(contour_int)
    if moments["m00"] != 0:
        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])
    else:
        cx, cy = x + w // 2, y + h // 2
    center = {"x": int(cx), "y": int(cy)}

    if "bounding_box" in shape:
        shape["bounding_box"] = bbox
    if "center" in shape:
        shape["center"] = center

    pixel_coords = shape.get("geometry", {}).get("pixel_coords", {})
    if isinstance(pixel_coords, dict):
        if "bounding_box" in pixel_coords:
            pixel_coords["bounding_box"] = bbox
        if "center" in pixel_coords:
            pixel_coords["center"] = center

    bbox_area = float(w * h)
    if "aspect_ratio" in shape:
        shape["aspect_ratio"] = round(float(w) / h if h > 0 else 0.0, 2)
    if "extent" in shape:
        shape["extent"] = round(area / bbox_area if bbox_area > 0 else 0.0, 3)
    if "rect_score" in shape:
        shape["rect_score"] = round(compute_rect_score(contour_int), 3)

    if "solidity" in shape:
        hull_area = float(cv2.contourArea(cv2.convexHull(contour_int)))
        shape["solidity"] = round(area / hull_area if hull_area > 0 else 0.0, 3)


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
    # Create mask and crop region
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
        "opacity": 0.5,
        "stroke_color": shape.get("color_rgb"),
        "stroke_width": 2,
        "stroke_opacity": 1.0,
        "mapElementType": "shape",
        "name": shape.get("name") or f"{shape.get('shape_type') or 'Shape'} {idx}",
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
        "opacity": 0.5,
        "stroke_color": shape.get("color_rgb"),
        "stroke_width": 2,
        "stroke_opacity": 1.0,
        "mapElementType": "shape",
        "name": shape.get("name") or f"{shape.get('shape_type') or 'Shape'} {idx}",
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
 
 
# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------
 

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
 
 
# ---------------------------------------------------------------------------
# LAB perceptual distance extraction (point-and-click)
# ---------------------------------------------------------------------------

# Delta E thresholds for hysteresis masking in LAB color space.
# STRICT: confident core of the region (low tolerance).
# RELAX:  soft boundary that must overlap the strict core to be included.
LAB_STRICT_THRESH: float = 15.0
LAB_RELAX_THRESH: float = 45.0


def _perceptual_distance_mask(
    lab_image: np.ndarray,
    seed_x: int,
    seed_y: int,
    strict_thresh: float = LAB_STRICT_THRESH,
    relax_thresh: float = LAB_RELAX_THRESH,
) -> np.ndarray:
    """Return a binary mask (H×W, uint8 255/0) using LAB perceptual distance
    (Delta E) with hysteresis thresholding.

    Strategy:
    1. Sample the median LAB value from a 5×5 patch around the seed pixel.
    2. Compute per-pixel Delta E (Euclidean distance in LAB).
    3. Build a strict mask (dist < strict_thresh) and a relaxed mask
       (dist < relax_thresh).
    4. Select the connected component in the relaxed mask that contains the
       seed pixel, but only keep it if it overlaps the strict core region.
    """
    height, width = lab_image.shape[:2]

    # 1. Sample local 5×5 patch for a stable reference colour
    patch_size = 5
    half = patch_size // 2
    x_start, x_end = max(0, seed_x - half), min(width,  seed_x + half + 1)
    y_start, y_end = max(0, seed_y - half), min(height, seed_y + half + 1)

    patch_lab = lab_image[y_start:y_end, x_start:x_end]
    median_lab = np.median(patch_lab, axis=(0, 1))

    # 2. Delta E (Euclidean distance in LAB space)
    diff = lab_image - median_lab
    dist = np.sqrt(np.sum(diff ** 2, axis=2))

    # 3. Hysteresis masks
    strict_mask = (dist < strict_thresh).astype(np.uint8) * 255
    relax_mask  = (dist < relax_thresh).astype(np.uint8)  * 255

    # 4. Connected-component analysis on the relaxed mask
    _, labels_relax = cv2.connectedComponents(relax_mask, connectivity=8)

    relax_label = int(labels_relax[seed_y, seed_x])

    # If the exact seed pixel falls on background in the relaxed mask,
    # fall back to the most frequent label in the local patch.
    if relax_label == 0:
        neighborhood = labels_relax[y_start:y_end, x_start:x_end]
        valid_labels = neighborhood[neighborhood > 0]
        if len(valid_labels) > 0:
            counts = np.bincount(valid_labels.flatten())
            relax_label = int(np.argmax(counts))

    # Build the final mask: accept the relaxed region only if it overlaps
    # the strict core (hysteresis criterion).
    final_mask = np.zeros_like(relax_mask)
    if relax_label > 0:
        relax_region = (labels_relax == relax_label)
        if np.any(strict_mask[relax_region] > 0):
            final_mask[relax_region] = 255

    return final_mask




def extract_shapes_from_clicks(
    image_path: str,
    click_positions: List[Tuple[float, float]],  # list of (norm_x, norm_y)
    click_names: Optional[List[str]] = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    debug: bool = False,
    strict_thresh: float = LAB_STRICT_THRESH,
    relax_thresh: float = LAB_RELAX_THRESH,
) -> Dict:
    """Extract shapes via LAB perceptual distance at user-supplied click positions.

    Each (norm_x, norm_y) is in [0, 1] relative to image dimensions.
    Uses hysteresis thresholding in CIE LAB color space (Delta E) to accurately
    isolate the color region at each click without being fooled by slight
    lighting gradients.

    Returns the same dict shape as ``extract_shapes`` (normalized_features,
    pixel_features) so the caller can persist them without changes.
    """
    image = preprocessing.read_image(image_path)
    if image is None:
        raise ValueError(f"Unable to load image: {image_path}")

    height, width = image.shape[:2]
    image_uint8 = (image * 255).astype(np.uint8)
    image_bgr = cv2.cvtColor(image_uint8, cv2.COLOR_RGB2BGR)

    # Convert once to LAB float32 for perceptual distance calculations
    lab_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)

    shapes_with_contours: List[Tuple[Dict, np.ndarray]] = []

    for idx, (nx, ny) in enumerate(click_positions):
        # Convert normalised → pixel coordinates
        px = int(np.clip(nx * width,  0, width  - 1))
        py = int(np.clip(ny * height, 0, height - 1))

        # 1. Build a binary mask using LAB perceptual distance + hysteresis
        final_mask = _perceptual_distance_mask(
            lab_image, px, py,
            strict_thresh=strict_thresh,
            relax_thresh=relax_thresh,
        )

        if not np.any(final_mask):
            logger.warning(
                "LAB perceptual mask produced empty result at (%d, %d)", px, py
            )
            continue

        # 2. Extract polygon contours from the mask
        contours, _ = cv2.findContours(
            final_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            logger.warning(
                "No polygon contour found for click at (%d, %d)", px, py
            )
            continue

        largest_contour = max(contours, key=cv2.contourArea)

        if cv2.contourArea(largest_contour) < 5:
            logger.warning(
                "Contour area too small at (%d, %d), skipping", px, py
            )
            continue

        # 3. Build shape properties using the standard extraction pipeline
        # Sample the dominant colour from the seed patch for colour accuracy
        seed_color_bgr = image_bgr[py, px]
        color_rgb = (
            int(seed_color_bgr[2]),
            int(seed_color_bgr[1]),
            int(seed_color_bgr[0]),
        )

        properties_dict = extract_contour_properties(
            largest_contour,
            image_bgr,
            shape_id=idx + 1,
            hough_circles=None,
        )
        if not properties_dict:
            continue

        # Override colour with the exact seed-pixel colour
        properties_dict["color_rgb"] = color_rgb
        properties_dict["color_hex"] = "#{:02x}{:02x}{:02x}".format(*color_rgb)
        properties_dict["color_name"] = get_nearest_css4_color_name(color_rgb)
        properties_dict["stroke_color"] = color_rgb

        # Apply user-provided name if available
        user_name = (
            click_names[idx] if click_names and idx < len(click_names) else None
        )
        if user_name:
            properties_dict["name"] = user_name

        shapes_with_contours.append((properties_dict, largest_contour))

    if debug:
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        image_output_dir = os.path.join(output_dir, base_name + "_clicks")
        os.makedirs(image_output_dir, exist_ok=True)

        for idx, (shape, contour) in enumerate(shapes_with_contours, 1):
            save_shape_image(
                image_bgr,
                contour,
                image_output_dir,
                idx,
                shape.get("shape_type") or "Shape",
            )

        try:
            reconstruct_shapes_debug(image_bgr, shapes_with_contours, image_output_dir)
        except (cv2.error, OSError) as e:
            logger.error(
                "Error writing debug reconstruction for %s: %s", image_path, e
            )

    # Generate GeoJSON features using the standard pipeline
    normalized_features = create_normalized_geojson_features(shapes_with_contours)
    pixel_features = create_pixel_geojson_features(shapes_with_contours)

    return {
        "normalized_features": normalized_features,
        "pixel_features": pixel_features,
        "shapes": [shape for shape, _ in shapes_with_contours],
        "total_shapes": len(pixel_features),
    }


# ---------------------------------------------------------------------------
# Main pipeline (OpenCV global contour extraction — kept for legend shapes)
# ---------------------------------------------------------------------------

