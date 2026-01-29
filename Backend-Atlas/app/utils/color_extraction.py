import os
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import imageio.v3 as iio

from skimage.color import rgb2lab, lab2rgb, deltaE_ciede2000
from skimage.morphology import binary_opening, disk
from skimage.util import img_as_float
from skimage.measure import find_contours
from matplotlib import colors as mcolors

from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.geometry.base import BaseGeometry
from shapely import affinity

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "extracted_color")

def load_image_rgb_alpha_mask(image_path: str) -> Tuple[np.ndarray, Optional[np.ndarray], np.ndarray]:
    """
    Load an image and return (rgb, alpha, opaque_mask).

    rgb: (H, W, 3)
    alpha: (H, W) or None
    opaque_mask: (H, W) bool
    """
    try:
        img = iio.imread(image_path)
    except FileNotFoundError:
        raise ValueError(f"Image file not found: {image_path}")
    except Exception as e:
        raise ValueError(f"Error loading image '{image_path}'") from e

    if img.ndim == 2:
        # Grayscale -> replicate into RGB
        rgb = np.stack([img, img, img], axis=-1)
        alpha = None
        opaque_mask = np.ones(img.shape, dtype=bool)

    elif img.ndim == 3 and img.shape[2] == 4:
        # RGBA
        rgb = img[:, :, :3]
        alpha = img[:, :, 3]
        opaque_mask = alpha > 0

    elif img.ndim == 3 and img.shape[2] == 3:
        # RGB
        rgb = img
        alpha = None
        opaque_mask = np.ones(rgb.shape[:2], dtype=bool)

    else:
        raise ValueError("Unsupported image format (expected grayscale, RGB, or RGBA).")

    return rgb, alpha, opaque_mask


def compute_lab(rgb: np.ndarray) -> np.ndarray:
    """
    Convert RGB image to LAB.
    Assumes rgb is uint8 0..255 or float; output is LAB float.
    """
    rgb_f = img_as_float(rgb)  # ensures float in [0, 1]
    lab = rgb2lab(rgb_f)
    return lab


def dominant_bins_lab(
    lab: np.ndarray,
    opaque_mask: np.ndarray,
    top_n: int = 8,
    bin_L: float = 4.0,
    bin_a: float = 8.0,
    bin_b: float = 8.0,
) -> List[Dict]:
    """
    Find dominant LAB bins using 3D quantization (binning).
    Returns a list of dicts with bin_id, ratio, count, and lab_center.
    """
    lab_px = lab[opaque_mask]  # (N, 3)

    Lq = np.floor(lab_px[:, 0] / bin_L).astype(np.int32)
    aq = np.floor((lab_px[:, 1] + 128.0) / bin_a).astype(np.int32)
    bq = np.floor((lab_px[:, 2] + 128.0) / bin_b).astype(np.int32)

    # Pack (Lq, aq, bq) into a single integer for fast counting.
    # Assumption: aq and bq stay < 1000
    ids = (Lq * 1_000_000) + (aq * 1_000) + bq

    unique_ids, counts = np.unique(ids, return_counts=True)
    ratios = counts / counts.sum()

    order = np.argsort(-ratios)
    unique_ids = unique_ids[order]
    counts = counts[order]
    ratios = ratios[order]

    dom: List[Dict] = []
    for k in range(min(top_n, len(unique_ids))):
        uid = int(unique_ids[k])

        Lq_k = uid // 1_000_000
        aq_k = (uid % 1_000_000) // 1_000
        bq_k = uid % 1_000

        # Bin center in LAB
        L_center = (Lq_k + 0.5) * bin_L
        a_center = (aq_k + 0.5) * bin_a - 128.0
        b_center = (bq_k + 0.5) * bin_b - 128.0

        dom.append(
            {
                "bin_id": uid,
                "ratio": float(ratios[k]),
                "count": int(counts[k]),
                "lab_center": (float(L_center), float(a_center), float(b_center)),
                "bin_index": (int(Lq_k), int(aq_k), int(bq_k)),
            }
        )

    return dom

def lab_center_to_rgb_u8(lab_center: Tuple[float, float, float]) -> Tuple[int, int, int]:
    """
    Convert a single LAB color to an approximate RGB uint8.
    """
    lab_arr = np.array([[lab_center]], dtype=np.float64)  # shape (1, 1, 3)
    rgb = lab2rgb(lab_arr)  # float [0,1], shape (1,1,3)
    rgb_u8 = np.clip(np.round(rgb[0, 0] * 255.0), 0, 255).astype(np.uint8)
    return int(rgb_u8[0]), int(rgb_u8[1]), int(rgb_u8[2])


def get_nearest_css4_color_name(rgb_tuple: Tuple[int, int, int]) -> str:
    """
    Find the closest CSS4 color name for a given RGB tuple.
    """
    min_distance = float("inf")
    closest_name = "unknown"

    for name, hex_value in mcolors.CSS4_COLORS.items():
        r_c, g_c, b_c = mcolors.to_rgb(hex_value)
        r_c, g_c, b_c = [int(x * 255) for x in (r_c, g_c, b_c)]
        distance = math.sqrt((rgb_tuple[0] - r_c) ** 2 + (rgb_tuple[1] - g_c) ** 2 + (rgb_tuple[2] - b_c) ** 2)
        if distance < min_distance:
            min_distance = distance
            closest_name = name

    return closest_name


def save_mask_png(mask_bool: np.ndarray, out_path: str) -> None:
    """
    Save a boolean mask as an 8-bit PNG (0 or 255).
    """
    mask_u8 = (mask_bool.astype(np.uint8) * 255)
    iio.imwrite(out_path, mask_u8)


def mask_to_geometry(mask: np.ndarray) -> Optional[BaseGeometry]:
    """
    Convert a boolean numpy mask to a Shapely geometry (Polygon or MultiPolygon).
    Uses skimage.measure.find_contours to extract contours from the mask.
    """
    if not np.any(mask):
        return None
    
    # Find contours (returns list of (n, 2) arrays with (row, col) coordinates)
    contours = find_contours(mask.astype(float), 0.5)
    
    if not contours:
        return None
    
    polygons = []
    height, width = mask.shape
    
    for contour in contours:
        # Convert from (row, col) to (x, y) coordinates
        # Note: skimage uses (row, col) but we want (x, y) = (col, row)
        coords = [(point[1], point[0]) for point in contour]
        
        # Ensure polygon is closed
        if len(coords) < 3:
            continue
            
        # Close the polygon if not already closed
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        
        try:
            poly = Polygon(coords)
            if poly.is_valid and poly.area > 0:
                polygons.append(poly)
        except Exception:
            # Skip invalid polygons
            continue
    
    if not polygons:
        return None
    
    # Merge all polygons into a single geometry
    merged = unary_union(polygons)
    return merged


def build_normalized_feature(
    color_name: str,
    rgb: tuple,
    pixel_polygons,
    image_output_dir: str,
):
    """From pixel-space polygons, build a normalized GeoJSON feature and write it to disk.

    - Merges all pixel polygons into a single geometry (possibly MultiPolygon).
    - Scales it uniformly so the largest dimension becomes 1.
    - Recenters it into the [0, 1] x [0, 1] box.
    - Returns the normalized GeoJSON feature dict.
    """

    merged: BaseGeometry = unary_union(pixel_polygons)

    # Preserve original aspect ratio while normalizing into a unit box
    minx, miny, maxx, maxy = merged.bounds
    width_px = maxx - minx
    height_px = maxy - miny

    max_dim = max(width_px, height_px)
    scale = 1.0 / max_dim if max_dim != 0 else 1.0

    translated = affinity.translate(merged, xoff=-minx, yoff=-miny)

    scaled = affinity.scale(
        translated,
        xfact=scale,
        yfact=scale,
        origin=(0.0, 0.0),
    )

    width_norm = width_px * scale
    height_norm = height_px * scale
    offset_x = (1.0 - width_norm) / 2.0
    offset_y = (1.0 - height_norm) / 2.0

    normalized_geom = affinity.translate(
        scaled,
        xoff=offset_x,
        yoff=offset_y,
    )

    normalized_feature = {
        "type": "Feature",
        "properties": {
            "color_name": color_name,
            "color_rgb": rgb,
            # Hex string for direct styling usage on the frontend
            "color_hex": "#{:02x}{:02x}{:02x}".format(*rgb),
            "mapElementType": "zone",
            "name": f"Zone {color_name}",
            "start_date": "1700-01-01",
            "end_date": "2026-01-01",
            "is_normalized": True,
        },
        "geometry": normalized_geom.__geo_interface__,
    }

    normalized_color_geojson_path = os.path.join(
        image_output_dir, f"{color_name}_normalized.geojson"
    )

    return normalized_feature


def extract_colors(
    image_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    top_n: int = 8,
    bin_L: float = 4.0,
    bin_a: float = 8.0,
    bin_b: float = 8.0,
    deltaE_threshold: float = 10.0,
    opening_radius: int = 1,
) -> Dict:
    """
    Extract dominant color layers using LAB binning + ΔE masks.


    Returns a dict with detected colors, mask paths, ratios, and normalized_features.
    """
    rgb, alpha, opaque_mask = load_image_rgb_alpha_mask(image_path)
    lab = compute_lab(rgb)

    # Output folder
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    image_output_dir = os.path.join(output_dir, base_name)
    os.makedirs(image_output_dir, exist_ok=True)

    # Dominant LAB bins (computed on opaque pixels; you can also exclude text if desired)
    dom = dominant_bins_lab(lab, opaque_mask, top_n=top_n, bin_L=bin_L, bin_a=bin_a, bin_b=bin_b)

    masks: Dict[str, str] = {}
    ratios: Dict[str, float] = {}
    normalized_features = []

    color_index = 1
    for entry in dom:
        lab_center = entry["lab_center"]

        # Build ΔE mask against the LAB center.
        # deltaE_ciede2000 expects (...,3) arrays; we broadcast center to image shape.
        # NOTE: This computes a full (H, W) distance map for each dominant color bin,
        # so the overall complexity is roughly O(H * W * top_n). For very large images
        # or many bins, consider downsampling earlier in the pipeline if full resolution
        # is not required for color extraction.
        center = np.array(lab_center, dtype=np.float64).reshape(1, 1, 3)
        dE = deltaE_ciede2000(lab, center)  # shape (H, W)

        mask = (dE <= deltaE_threshold) & opaque_mask

        # Clean small noise
        if opening_radius > 0:
            mask = binary_opening(mask, disk(opening_radius))

        # Name the layer based on approximate RGB -> nearest CSS name
        rgb_u8 = lab_center_to_rgb_u8(lab_center)
        color_name = get_nearest_css4_color_name(rgb_u8)
        # Ensure uniqueness of dictionary keys even if multiple bins share the same CSS4 color name
        unique_color_name = f"{color_name}_{color_index}"

        file_name = f"color_{color_index}_{color_name}_ratio_{entry['ratio']:.4f}.png"
        out_path = os.path.join(image_output_dir, file_name)
        save_mask_png(mask, out_path)

        masks[unique_color_name] = out_path
        ratios[unique_color_name] = entry["ratio"]
        
        # Build normalized feature from mask
        # Convert mask to geometry first (like the old RGB version did with pixel_polygons)
        geometry = mask_to_geometry(mask)
        if geometry:
            # build_normalized_feature expects a list of polygons, so wrap the geometry in a list
            normalized_feature = build_normalized_feature(
                unique_color_name, rgb_u8, [geometry], image_output_dir
            )
            if normalized_feature:
                normalized_features.append({
                    "type": "FeatureCollection",
                    "features": [normalized_feature]
                })
        
        color_index += 1

    return {
        "colors_detected": list(masks.keys()),
        "masks": masks,
        "ratios": ratios,
        "dominant_bins": dom,
        "output_dir": image_output_dir,
        "normalized_features": normalized_features,
    }