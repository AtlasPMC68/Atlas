import math
import os
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from matplotlib import colors as mcolors
from scipy.ndimage import binary_fill_holes
from shapely import affinity
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from skimage.color import deltaE_ciede2000, lab2rgb, rgb2lab
from skimage.measure import find_contours
from skimage.morphology import closing, disk, opening
from skimage.util import img_as_float

from app.utils.color_in_legends_extraction import (
    extract_colors_from_legend_shapes,
    sample_color_at,
)

from . import preprocessing

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "extracted_color")


def load_image_rgb_alpha_mask(
    image_path: str,
) -> Tuple[np.ndarray, Optional[np.ndarray], np.ndarray]:
    """
    Load an image and return (rgb, alpha, opaque_mask).

    rgb: (H, W, 3)
    alpha: (H, W) or None
    opaque_mask: (H, W) bool
    """

    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)

    if img is None:
        raise ValueError(f"Image file not found: {image_path}")

    # grayscale
    if img.ndim == 2:
        rgb = np.stack([img, img, img], axis=-1)
        alpha = None
        opaque_mask = np.ones(img.shape, dtype=bool)

    # BGR
    elif img.ndim == 3 and img.shape[2] == 3:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        alpha = None
        opaque_mask = np.ones(rgb.shape[:2], dtype=bool)

    # BGRA
    elif img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        rgb = img[:, :, :3]
        alpha = img[:, :, 3]
        opaque_mask = alpha > 0

    else:
        raise ValueError("Unsupported image format")

    return rgb, alpha, opaque_mask


def debug_save_rgb(
    img_rgb: np.ndarray,
    alpha: Optional[np.ndarray],
    debug_dir: str,
    step_name: str,
) -> None:
    """Save float RGB [0,1] (optionally with alpha) as PNG for debugging."""
    os.makedirs(debug_dir, exist_ok=True)
    out_path = os.path.join(debug_dir, f"{step_name}.png")

    img = np.clip(img_rgb, 0.0, 1.0)
    rgb_u8 = (img * 255.0 + 0.5).astype(np.uint8)  # (H, W, 3)

    if alpha is not None:
        alpha_u8 = (
            (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
            if alpha.dtype != np.uint8
            else alpha
        )
        if alpha_u8.ndim == 3 and alpha_u8.shape[-1] == 1:
            alpha_u8 = alpha_u8[:, :, 0]
        rgba = np.dstack([rgb_u8, alpha_u8])
        bgra = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)
        cv2.imwrite(out_path, bgra)
    else:
        bgr_u8 = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2BGR)
        cv2.imwrite(out_path, bgr_u8)


def preprocess(
    rgb: np.ndarray,
    alpha: Optional[np.ndarray],
    opaque_mask: np.ndarray,
    enable_linearize: bool = True,
    enable_percentile_norm: bool = True,
    norm_p_low: float = 1.0,
    norm_p_high: float = 99.0,
    enable_denoise: bool = True,
    debug: bool = False,
    debug_dir: Optional[str] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Full-image preprocessing for color extraction.

    If debug=True, saves intermediate RGB + masks into debug_dir at each step.
    """
    rgb = np.clip(img_as_float(rgb), 0.0, 1.0)
    mask = opaque_mask.astype(bool)

    if debug and debug_dir is None:
        debug_dir = os.path.join(os.getcwd(), "debug_preprocess")

    if debug:
        debug_save_rgb(rgb, alpha, debug_dir, "00_input_rgb")

    # 1) Optional linearization
    if enable_linearize:
        work = preprocessing.srgb_to_linear(rgb)
        if debug:
            debug_save_rgb(np.clip(work, 0.0, 1.0), alpha, debug_dir, "01_linear_rgb")
    else:
        work = rgb
        if debug:
            debug_save_rgb(work, alpha, debug_dir, "01_linear_skipped")

    # 2) Denoise
    if enable_denoise:
        work_u8 = (np.clip(work, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        work_u8 = cv2.bilateralFilter(work_u8, d=11, sigmaColor=75, sigmaSpace=75)
        work = work_u8.astype(np.float32) / 255.0

    # TODO: Try fast mean denoizing color and try dynamic parameters

    if debug:
        debug_save_rgb(work, alpha, debug_dir, "02_denoise")

    # 3) Percentile normalization
    if enable_percentile_norm:
        work = preprocessing.percentile_normalize(
            work, p_low=norm_p_low, p_high=norm_p_high, mask=mask
        )
        if debug:
            debug_save_rgb(work, alpha, debug_dir, "03_percentile_norm")

    elif debug:
        debug_save_rgb(work, alpha, debug_dir, "03_percentile_norm_skipped")

    # 4) Convert back to sRGB
    if enable_linearize:
        rgb_out = preprocessing.linear_to_srgb(work)
        if debug:
            debug_save_rgb(rgb_out, alpha, debug_dir, "04_back_to_srgb")
    else:
        rgb_out = work

    rgb_out = np.clip(rgb_out, 0.0, 1.0)

    if debug:
        debug_save_rgb(rgb_out, alpha, debug_dir, "05_output_rgb")

    return rgb_out, mask


def compute_lab(rgb: np.ndarray) -> np.ndarray:
    """
    Convert RGB image to LAB (float).
    """
    rgb_f = img_as_float(rgb)
    return rgb2lab(rgb_f)


def prepare_imposed_dominants(
    imposed_colors: List[Tuple[int, int, int]],
    names: Optional[List[Optional[str]]] = None,
) -> List[Dict]:
    imposed_entries: List[Dict] = []

    for idx, rgb in enumerate(imposed_colors):
        rgb_arr = np.array([[rgb]], dtype=np.uint8)  # shape (1,1,3)
        rgb_f = rgb_arr.astype(np.float32) / 255.0
        lab = rgb2lab(rgb_f)[0, 0]
        user_name = (names[idx] if names and idx < len(names) else None) or None

        imposed_entries.append(
            {
                "bin_id": None,
                "ratio": 0.0,
                "count": 0,
                "lab_center": (float(lab[0]), float(lab[1]), float(lab[2])),
                "bin_index": None,
                "source": "imposed",
                "kind": "dominant",
                "rgb_center": rgb,
                "label": f"imposed_{idx + 1:02d}",
                "user_name": user_name,
            }
        )

    return imposed_entries


def build_exclusive_masks_by_nearest_center(
    # TODO: ignore pixels that are in the legend box
    lab: np.ndarray,
    opaque_mask: np.ndarray,
    centers_lab: np.ndarray,
    mask_deltaE: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Assign each pixel to exactly one color (exclusive layers) by nearest ΔE.

    Returns:
        best_idx: (H, W) int index of selected center for each pixel (undefined where invalid=False)
        valid: (H, W) bool pixels that are within mask_deltaE of at least one center and opaque
    """
    # centers_lab: (K, 3)
    # We compute ΔE for each center and stack into (H, W, K).
    dists = []
    for k in range(centers_lab.shape[0]):
        center = centers_lab[k].reshape(1, 1, 3)
        dE_k = deltaE_ciede2000(lab, center)  # (H, W)
        dists.append(dE_k)

    dist_stack = np.stack(dists, axis=-1)  # (H, W, K)

    best_idx = np.argmin(dist_stack, axis=-1).astype(np.int32)
    best_dE = np.min(dist_stack, axis=-1)

    valid = (best_dE <= mask_deltaE) & opaque_mask

    return best_idx, valid


def lab_center_to_rgb_u8(
    lab_center: Tuple[float, float, float],
) -> Tuple[int, int, int]:
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
        distance = math.sqrt(
            (rgb_tuple[0] - r_c) ** 2
            + (rgb_tuple[1] - g_c) ** 2
            + (rgb_tuple[2] - b_c) ** 2
        )
        if distance < min_distance:
            min_distance = distance
            closest_name = name

    return closest_name


def save_mask_png(
    mask_bool: np.ndarray,
    rgb: np.ndarray,
    out_path: str,
) -> None:
    if rgb.dtype != np.uint8:
        rgb_u8 = (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    else:
        rgb_u8 = rgb

    alpha = np.zeros(mask_bool.shape, dtype=np.uint8)
    alpha[mask_bool] = 255

    rgba = np.dstack([rgb_u8, alpha])
    bgra = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)

    cv2.imwrite(out_path, bgra)


def mask_to_geometry(mask: np.ndarray) -> Optional[BaseGeometry]:
    """
    Convert a boolean numpy mask to a Shapely geometry (Polygon or MultiPolygon).
    Uses skimage.measure.find_contours to extract contours from the mask.
    """
    if not np.any(mask):
        return None

    contours = find_contours(mask.astype(float), 0.5)
    if not contours:
        return None

    polygons = []
    for contour in contours:
        coords = [
            (float(point[1]), float(point[0])) for point in contour
        ]  # (x=col, y=row)

        if len(coords) < 3:
            continue

        if coords[0] != coords[-1]:
            coords.append(coords[0])

        try:
            poly = Polygon(coords)
            if poly.is_valid and poly.area > 0:
                polygons.append(poly)
        except Exception:
            continue

    if not polygons:
        return None

    return unary_union(polygons)


def build_feature(color_name: str, rgb: tuple, merged_geometry: BaseGeometry):
    """From pixel-space polygons, build GeoJSON feature and write it to disk.

    - Merges all pixel polygons into a single geometry (possibly MultiPolygon).
    """
    pixel_feature = {
        "type": "Feature",
        "properties": {
            "color_name": color_name,
            "color_rgb": rgb,
            "color_hex": "#{:02x}{:02x}{:02x}".format(*rgb),
            "mapElementType": "zone",
            "name": f"{color_name}",
            "is_pixel_space": True,
            "opacity": 0.5,
            "stroke_color": rgb,
            "stroke_width": 2,
            "stroke_opacity": 1.0,
        },
        "geometry": merged_geometry.__geo_interface__,
    }
    return pixel_feature


# Used to not have crazy amount of vertices so it is not too nasty looking
def simplify_geometry(geometry: BaseGeometry, tolerance: float = 0.5) -> BaseGeometry:
    if tolerance > 0 and geometry is not None:
        return geometry.simplify(tolerance, preserve_topology=True)
    return geometry


def build_normalized_feature(
    color_name: str, rgb: Tuple[int, int, int], merged_geometry: BaseGeometry
) -> Dict:
    """
    Build a normalized GeoJSON feature from a pixel-space geometry.

    - Keeps aspect ratio
    - Scales so max dimension becomes 1
    - Centers in [0,1]x[0,1]
    """
    minx, miny, maxx, maxy = merged_geometry.bounds
    width_px = maxx - minx
    height_px = maxy - miny

    max_dim = max(width_px, height_px)
    scale = 1.0 / max_dim if max_dim != 0 else 1.0

    translated = affinity.translate(merged_geometry, xoff=-minx, yoff=-miny)
    scaled = affinity.scale(translated, xfact=scale, yfact=scale, origin=(0.0, 0.0))

    width_norm = width_px * scale
    height_norm = height_px * scale
    offset_x = (1.0 - width_norm) / 2.0
    offset_y = (1.0 - height_norm) / 2.0

    normalized_geom = affinity.translate(scaled, xoff=offset_x, yoff=offset_y)

    return {
        "type": "Feature",
        "properties": {
            "color_name": color_name,
            "color_rgb": rgb,
            "color_hex": "#{:02x}{:02x}{:02x}".format(*rgb),
            "mapElementType": "zone",
            "name": f"Zone {color_name}",
            "is_normalized": True,
            "opacity": 0.5,
            "stroke_color": rgb,
            "stroke_width": 2,
            "stroke_opacity": 1.0,
        },
        "geometry": normalized_geom.__geo_interface__,
    }


def _sanitize_name(name: str, max_length: int = 64) -> str:
    """Strip whitespace, replace filesystem-unsafe characters, and enforce a max length."""
    name = name.strip()
    for ch in ("/", "\\", "\0"):
        name = name.replace(ch, "-")
    name = name[:max_length]
    return name or "unnamed"


def extract_colors(
    image_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    debug: bool = False,
    legend_shapes: Optional[List[Dict]] = None,
    imposed_click_positions: Optional[List[Tuple[float, float]]] = None,
    imposed_colors_names: Optional[List[Optional[str]]] = None,
    # -----------------------------
    # Mask construction (pixel assignment)
    # -----------------------------
    mask_deltaE: float = 5.0,
    # Maximum ΔE distance for a pixel to be assigned to a color layer.
    # Larger value → thicker, more inclusive masks.
    # Smaller value → tighter masks, may leave holes/unassigned pixels.
    # -----------------------------
    # Post-processing
    # -----------------------------
    opening_radius: int = 1,  # Erosion then dilation to remove small noise/speckles
    closing_radius: int = 3,  # Dilation then erosion to fill small gaps
    simplify_tolerance: float = 0.5,
    sampling_radius: int = 20,  # Neighbourhood radius (px) used when sampling imposed click positions
) -> Dict:
    """
    Extract exclusive color layers using:
    - Imposed colors (from click positions or legend-derived colors)
    - Exclusive assignment: each pixel belongs to exactly one selected color (nearest ΔE)

    Returns:
      - pixel_features (GeoJSON FeatureCollections with pixel-space geometries)
      - normalized_features (GeoJSON FeatureCollections)
      - masks (paths to debug PNGs of each mask, if debug=True) *For futurs tests*
    """

    # 0) Prepare output directory
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    image_output_dir = os.path.join(output_dir, base_name)

    if debug:
        os.makedirs(image_output_dir, exist_ok=True)

    # 1) Load raw image and alpha mask
    rgb_u8, alpha, opaque_mask = load_image_rgb_alpha_mask(image_path)
    original_rgb = img_as_float(rgb_u8)

    # 2) Preprocess full image for color extraction (keeps/updates mask)
    rgb, opaque_mask = preprocess(
        rgb=original_rgb,
        alpha=alpha,
        opaque_mask=opaque_mask,
        enable_linearize=True,
        enable_denoise=True,
        enable_percentile_norm=True,
        norm_p_low=1.0,
        norm_p_high=99.0,
        debug=debug,
        debug_dir=image_output_dir,
    )

    # 3) Convert preprocessed image to LAB
    lab = compute_lab(rgb)

    if imposed_click_positions:
        # Sample the dominant (mode) colour in a neighbourhood around each click,
        # using the same logic as /sample-color so preview and extraction are consistent.
        # rgb is the preprocessed float [0,1] image; sample_color_at accepts both
        # float and uint8 inputs.
        sampled_rgb: List[Tuple[int, int, int]] = []
        for nx, ny in imposed_click_positions:
            result = sample_color_at(rgb, nx, ny, radius_px=sampling_radius)
            if result is not None:
                r, g, b = result["rgb"]
                sampled_rgb.append((int(r), int(g), int(b)))
        imposed_dominants = prepare_imposed_dominants(
            sampled_rgb, names=imposed_colors_names
        )
    elif legend_shapes:
        imposed_colors = extract_colors_from_legend_shapes(rgb, legend_shapes)
        imposed_dominants = (
            prepare_imposed_dominants(imposed_colors) if imposed_colors else []
        )
    else:
        imposed_dominants = []

    # Colors are always imposed (click positions or legend-derived colors).
    dominants = imposed_dominants

    masks: Dict[str, str] = {}
    normalized_features: List[Dict] = []
    pixel_features: List[Dict] = []

    # Early exit if nothing was selected
    if not dominants:
        return {
            "normalized_features": normalized_features,
            "pixel_features": pixel_features,
            "masks": masks,
        }

    # 6) Build exclusive masks by nearest LAB center
    centers_lab = np.array(
        [entry["lab_center"] for entry in dominants], dtype=np.float64
    )
    best_idx, valid = build_exclusive_masks_by_nearest_center(
        lab, opaque_mask, centers_lab, mask_deltaE
    )

    # 7) Build per-color masks and features
    seen_names: Dict[str, int] = {}
    color_index = 1
    for k, entry in enumerate(dominants):
        mask = (best_idx == k) & valid

        # 1. Opening: Remove small noise/speckles
        if opening_radius > 0:
            mask = opening(mask, disk(opening_radius))

        # 2. Closing: Bridge small gaps (useful for connecting fragmented regions)
        if closing_radius > 0:
            mask = closing(mask, disk(closing_radius))

        # 3. Fill holes: Remove interior holes (text, small waters, etc.)
        mask = binary_fill_holes(mask)

        if not np.any(mask):
            continue

        rgb_u8_center = lab_center_to_rgb_u8(entry["lab_center"])
        user_name = entry.get("user_name")
        if user_name:
            base_name = _sanitize_name(user_name)
        else:
            color_name = get_nearest_css4_color_name(rgb_u8_center)
            base_name = f"{color_name}-{color_index}"
        count = seen_names.get(base_name, 0) + 1
        seen_names[base_name] = count
        unique_color_name = base_name if count == 1 else f"{base_name}_{count}"
        L, a, b = entry["lab_center"]

        if debug:
            opaque_count = max(1, int(np.count_nonzero(opaque_mask)))
            ratio_value = float(np.count_nonzero(mask)) / float(opaque_count)

            file_name = (
                f"{unique_color_name}"
                f"_ratio_{ratio_value:.4f}"
                f"_lab_{L:.1f}_{a:.1f}_{b:.1f}"
                f".png"
            )
            out_path = os.path.join(image_output_dir, file_name)
            save_mask_png(mask, original_rgb, out_path)
            masks[unique_color_name] = out_path

        geometry = mask_to_geometry(mask)
        if geometry:
            geometry = simplify_geometry(geometry, simplify_tolerance)

            # build_features expects a list of polygons, so wrap the geometry in a list
            pixel_feature = build_feature(
                unique_color_name,
                rgb_u8_center,
                geometry,
            )
            pixel_features.append(
                {"type": "FeatureCollection", "features": [pixel_feature]}
            )

            normalized_feature = build_normalized_feature(
                unique_color_name,
                rgb_u8_center,
                geometry,
            )
            normalized_features.append(
                {"type": "FeatureCollection", "features": [normalized_feature]}
            )

        color_index += 1

    return {
        "normalized_features": normalized_features,
        "pixel_features": pixel_features,
        "masks": masks,
    }
