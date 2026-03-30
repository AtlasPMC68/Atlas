import os
import math

from typing import Dict, List, Optional, Tuple, Literal

import numpy as np
import cv2
import skimage.util
import skimage.restoration

from skimage import exposure
from skimage.color import rgb2lab, lab2rgb, deltaE_ciede2000
from skimage.morphology import opening, binary_closing, disk
from skimage.util import img_as_float
from skimage.measure import find_contours
from scipy.ndimage import binary_fill_holes
from matplotlib import colors as mcolors

from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.geometry.base import BaseGeometry
from shapely import affinity

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


def _debug_save_rgb(
    img_rgb: np.ndarray,
    alpha: Optional[np.ndarray],
    debug_dir: str,
    step_idx: int,
    step_name: str,
) -> None:
    """Save float RGB [0,1] (optionally with alpha) as PNG for debugging."""
    os.makedirs(debug_dir, exist_ok=True)
    # Clamp and convert RGB to uint8
    img = np.clip(img_rgb, 0.0, 1.0)
    rgb_u8 = (img * 255.0 + 0.5).astype(np.uint8)  # (H, W, 3)
    out_path = os.path.join(debug_dir, f"{step_idx:02d}_{step_name}.png")
    if alpha is not None:
        alpha_u8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8) if alpha.dtype != np.uint8 else alpha
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
    rgb = np.clip(skimage.util.img_as_float(rgb), 0.0, 1.0)
    mask = opaque_mask.astype(bool)

    if debug and debug_dir is None:
        debug_dir = os.path.join(os.getcwd(), "debug_preprocess")

    step = 0
    if debug:
        _debug_save_rgb(rgb, alpha, debug_dir, step, "00_input_rgb")
        step += 1

    # 1) Optional linearization
    if enable_linearize:
        work = preprocessing.srgb_to_linear(rgb)
        if debug:
            _debug_save_rgb(np.clip(work, 0.0, 1.0), alpha, debug_dir, step, "01_linear_rgb")
            step += 1
    else:
        work = rgb
        if debug:
            _debug_save_rgb(work, alpha, debug_dir, step, "01_linear_skipped")
            step += 1

    # 2) Denoise
    if enable_denoise:
        work_u8 = (np.clip(work, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        work_u8 = cv2.bilateralFilter(work_u8, d=9, sigmaColor=30, sigmaSpace=5)
        work = work_u8.astype(np.float32) / 255.0

    if debug:
        _debug_save_rgb(work, alpha, debug_dir, step, "02_denoise")
        step += 1

    # 3) Percentile normalization
    if enable_percentile_norm:
        work = preprocessing.percentile_normalize(
            work, p_low=norm_p_low, p_high=norm_p_high, mask=mask
        )
        if debug:
            _debug_save_rgb(work, alpha, debug_dir, step, "03_percentile_norm")
            step += 1
    elif debug:
        _debug_save_rgb(work, alpha, debug_dir, step, "03_percentile_norm_skipped")
        step += 1

    # 4) Convert back to sRGB if needed
    if enable_linearize:
        rgb_out = preprocessing.linear_to_srgb(work)
        if debug:
            _debug_save_rgb(rgb_out, alpha, debug_dir, step, "04_back_to_srgb")
            step += 1
    else:
        rgb_out = work

    rgb_out = np.clip(rgb_out, 0.0, 1.0)

    if debug:
        _debug_save_rgb(rgb_out, alpha, debug_dir, step, "05_output_rgb")

    return rgb_out, mask


def compute_lab(rgb: np.ndarray) -> np.ndarray:
    """
    Convert RGB image to LAB (float).
    """
    rgb_f = img_as_float(rgb)  # ensures float in [0, 1]
    return rgb2lab(rgb_f)

def dominant_bins_lab(
    lab: np.ndarray,
    opaque_mask: np.ndarray,
    top_n: int,
    bin_L: float,
    bin_a: float,
    bin_b: float,
) -> List[Dict]:
    """
    Find frequent LAB bins using 3D quantization (binning).
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
        coords = [(float(point[1]), float(point[0])) for point in contour]  # (x=col, y=row)

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

    # Merge all polygons into a single geometry
    merged = unary_union(polygons)
    return merged

# Used to not have crazy amount of vertices so it is not too nasty looking
def simplify_geometry(geometry: BaseGeometry, tolerance: float = 0.5) -> BaseGeometry:
    if tolerance > 0 and geometry is not None:
        return geometry.simplify(tolerance, preserve_topology=True)
    return geometry


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
            "name": f"Zone {color_name}",
            "is_pixel_space": True,
            "start_date": "1700-01-01",
            "end_date": "2026-01-01",
        },
        "geometry": merged_geometry.__geo_interface__,
    }
    return pixel_feature


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
            "start_date": "1700-01-01",
            "end_date": "2026-01-01",
            "is_normalized": True,
        },
        "geometry": normalized_geom.__geo_interface__,
    }


def extract_colors(
    image_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    debug: bool = False,
    imposed_colors: Optional[List[Tuple[int, int, int]]] = None, # If set, the color (RGB) will be used for the extraction. Ex: Colors in Legends or selected by user
    
    # -----------------------------
    # LAB binning (color candidates discovery)
    # -----------------------------

    top_n_bins: int = 200,
    # Maximum number of LAB bins kept after quantization.
    # Higher value → more candidate colors discovered (useful for complex maps).
    # Lower value → faster, but may miss rare colors (e.g. small symbols, stars).
    bin_L: float = 4.0,
    # Quantization step on the L (lightness) axis.
    # Larger value → bins cover wider lightness range (fewer, broader colors).
    # Smaller value → more precise separation of light/dark variants.
    bin_a: float = 8.0,
    # Quantization step on the a (green–red) axis.
    # Larger value → merge nearby reds/greens into same bin.
    # Smaller value → finer separation of hue variations.
    bin_b: float = 8.0,
    deltaE_threshold: float = 10.0,
    opening_radius: int = 1,
    closing_radius: int = 3,
    simplify_tolerance: float = 0.5,
) -> Dict:
    """
    Extract dominant color layers using LAB binning + ΔE masks.
    
    Returns:
        Dict with detected colors, mask paths, ratios, and normalized_features.
    """
    rgb, _, opaque_mask = load_image_rgb_alpha_mask(image_path)
    lab = compute_lab(rgb)

    # Output folder
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
        enable_linearize=True,  # Work in linear RGB for illumination-like ops
        enable_denoise=True,  # Denoise BEFORE CLAHE
        enable_percentile_norm=True,  # Do percentile normalization on sRGB (consistent with LAB next)
        norm_p_low=1.0,
        norm_p_high=99.0,
        debug=debug,
        debug_dir=image_output_dir,
    )

    # 3) Convert preprocessed image to LAB
    lab = compute_lab(rgb)

    imposed_dominants = prepare_imposed_dominants(imposed_colors) if imposed_colors else []

    # 4) Dominant LAB bins (computed on opaque pixels)
    dom = dominant_bins_lab(
        lab,
        opaque_mask,
        top_n=top_n_bins,
        bin_L=bin_L,
        bin_a=bin_a,
        bin_b=bin_b,
    )

    # 5) Select colors (dominants + accents)
    selection = select_dominants_and_accents(
        bins=dom,
        imposed_dominants=imposed_dominants,
        dominant_ratio=dominant_ratio,
        accent_min_ratio=accent_min_ratio,
        dominant_min_deltaE_from_existing=10.0,
        accent_min_deltaE_from_dominants=15.0,
        accent_min_deltaE_from_accents=12.0,
        min_accents_fallback=min_colors_fallback,
    )
    dominants = selection["dominants"]
    accents = selection["accents"]
    selected = selection["selected"]

    masks: Dict[str, str] = {}
    mask_paths: Dict[str, str] = {}
    ratios: Dict[str, float] = {}
    normalized_features: List[Dict] = []
    pixel_features: List[Dict] = []

    # Early exit if nothing was selected
    if not dominants:
        return {
            "colors_detected": [],
            "masks": masks,
            "mask_paths": mask_paths if debug else {},
            "ratios": ratios,
            "selected_bins": [],
            "output_dir": image_output_dir,
            "normalized_features": normalized_features,
            "pixel_features": pixel_features,
        }

    # 6) Build exclusive masks by nearest LAB center
    centers_lab = np.array(
        [entry["lab_center"] for entry in dominants], dtype=np.float64
    )
    best_idx, valid = build_exclusive_masks_by_nearest_center(
        lab, opaque_mask, centers_lab, mask_deltaE
    )

    # 7) Build per-color masks and features
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

        # 1. Opening: Remove small noise/speckles
        if opening_radius > 0:
            mask = opening(mask, disk(opening_radius))

        # Name the layer based on approximate RGB -> nearest CSS name
        rgb_u8 = lab_center_to_rgb_u8(lab_center)
        color_name = get_nearest_css4_color_name(rgb_u8)
        # Ensure uniqueness of dictionary keys even if multiple bins share the same CSS4 color name
        unique_color_name = f"{color_name}_{color_index}"
        L, a, b = entry["lab_center"]

        file_name = (
            f"color_{color_index:02d}_{unique_color_name}"
            f"_ratio_{entry['ratio']:.4f}"
            f"_lab_{L:.1f}_{a:.1f}_{b:.1f}"
            f".png"
        )

        ratios[unique_color_name] = float(entry["ratio"])

        # Build normalized feature from mask
        # Convert mask to geometry first (like the old RGB version did with pixel_polygons)
        geometry = mask_to_geometry(mask)
        if geometry:

            geometry = simplify_geometry(geometry, simplify_tolerance)
            
            # build_features expects a list of polygons, so wrap the geometry in a list
            pixel_feature = build_feature(unique_color_name, rgb_u8, geometry)
            pixel_features.append(
                {"type": "FeatureCollection", "features": [pixel_feature]}
            )

            normalized_feature = build_normalized_feature(
                unique_color_name, rgb_u8, geometry
            )
            normalized_features.append(
                {"type": "FeatureCollection", "features": [feature]}
            )

        color_index += 1
    
    return {
        "colors_detected": list(masks.keys()),
        "masks": masks,
        "mask_paths": mask_paths if debug else {},
        "ratios": ratios,
        "selected_bins": dominants,
        "output_dir": image_output_dir,
        "normalized_features": normalized_features,
        "pixel_features": pixel_features,
    }