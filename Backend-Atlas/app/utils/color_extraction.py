import os
import math

from typing import Dict, List, Optional, Tuple, Literal

import numpy as np
import imageio.v3 as iio
import skimage.util
import skimage.restoration

from skimage.color import rgb2lab, lab2rgb, deltaE_ciede2000
from skimage.morphology import binary_opening
from skimage.util import img_as_float
from skimage.measure import find_contours
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

def _debug_save_rgb(
    img_rgb: np.ndarray,
    debug_dir: str,
    step_idx: int,
    step_name: str,
) -> None:
    """Save float RGB [0,1] as PNG for debugging."""
    os.makedirs(debug_dir, exist_ok=True)
    img = np.clip(img_rgb, 0.0, 1.0)
    img_u8 = (img * 255.0 + 0.5).astype(np.uint8)
    out_path = os.path.join(debug_dir, f"{step_idx:02d}_{step_name}.png")
    iio.imwrite(out_path, img_u8)

def preprocess(
    rgb: np.ndarray,
    opaque_mask: np.ndarray,
    *,
    enable_linearize: bool = True,
    enable_flat_field: bool = True,
    flat_field_sigma: float = 120.0,
    enable_white_balance: bool = True,
    white_balance_method: Literal["gray_world", "percentile"] = "percentile",
    wb_percentile: float = 99.5,
    enable_percentile_norm: bool = True,
    norm_p_low: float = 1.0,
    norm_p_high: float = 99.0,
    enable_background_mask: bool = True,
    bg_method: Literal["paper", "none"] = "paper",
    paper_threshold_deltaE: float = 10.0,
    enable_denoise: bool = True,
    denoise_method: Literal["bilateral", "nl_means"] = "bilateral",
    bilateral_sigma_color: float = 0.04,
    bilateral_sigma_spatial: float = 2.0,
    enable_clahe: bool = True,
    clahe_clip_limit: float = 0.02,
    clahe_kernel_size: Tuple[int, int] = (8, 8),
    debug: bool = False,
    debug_dir: Optional[str] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Full-image preprocessing for color extraction.

    If debug=True, saves intermediate RGB + masks into debug_dir at each step.
    """
    rgb = np.clip(skimage.util.img_as_float(rgb), 0.0, 1.0)
    mask = opaque_mask.astype(bool)

    # Decide debug folder
    if debug and debug_dir is None:
        debug_dir = os.path.join(os.getcwd(), "debug_preprocess")

    step = 0
    if debug:
        _debug_save_rgb(rgb, debug_dir, step, "00_input_rgb")
        step += 1

    # 1) Linearize
    if enable_linearize:
        work = preprocessing.srgb_to_linear(rgb)
        if debug:
            _debug_save_rgb(np.clip(work, 0.0, 1.0), debug_dir, step, "01_linear_rgb")
            step += 1
    else:
        work = rgb
        if debug:
            _debug_save_rgb(work, debug_dir, step, "01_linear_skipped")
            step += 1

    # 2) Flat-field
    if enable_flat_field:
        work = preprocessing.flat_field_correction(
            work,
            sigma=flat_field_sigma,
            normalize=False,
            assume_linear=enable_linearize,
        )
        if debug:
            _debug_save_rgb(work, debug_dir, step, "02_flat_field")
            step += 1
    elif debug:
        _debug_save_rgb(work, debug_dir, step, "02_flat_field_skipped")
        step += 1

    # 3) White balance
    if enable_white_balance:
        if white_balance_method == "gray_world":
            work = preprocessing.white_balance_gray_world(work, mask=mask)
        else:
            work = preprocessing.white_balance_percentile_white_patch(
                work, percentile=wb_percentile, mask=mask
            )
        if debug:
            _debug_save_rgb(work, debug_dir, step, f"03_white_balance_{white_balance_method}")
            step += 1
    elif debug:
        _debug_save_rgb(work, debug_dir, step, "03_white_balance_skipped")
        step += 1

    # 4) Denoise 
    if enable_denoise:
        if denoise_method == "bilateral":
            work = skimage.restoration.denoise_bilateral(
                work,
                sigma_color=bilateral_sigma_color,
                sigma_spatial=bilateral_sigma_spatial,
                channel_axis=-1,
            )
        else:
            work = preprocessing.denoise_nl_means_rgb(work)

        if debug:
            _debug_save_rgb(work, debug_dir, step, f"04_denoise_{denoise_method}")
            step += 1
    elif debug:
        _debug_save_rgb(work, debug_dir, step, "04_denoise_skipped")
        step += 1

    # 5) Convert to LAB for CLAHE (work directly in LAB space)
    if enable_clahe:
        # Convert linear RGB to LAB directly (no need to go through sRGB)
        if enable_linearize:
            # Convert linear RGB to sRGB first (LAB expects sRGB-like input)
            work_srgb = preprocessing.linear_to_srgb(work)
        else:
            work_srgb = work
        
        work_srgb = np.clip(work_srgb, 0.0, 1.0)
        lab = skimage.color.rgb2lab(work_srgb)
        
        # Apply CLAHE directly on LAB L channel
        l = lab[:, :, 0] / 100.0
        l_clahe = skimage.exposure.equalize_adapthist(
            l, 
            kernel_size=clahe_kernel_size, 
            clip_limit=clahe_clip_limit
        )
        lab[:, :, 0] = l_clahe * 100.0
        
        # Convert back to RGB
        rgb_srgb = skimage.color.lab2rgb(lab)
        rgb_srgb = np.clip(rgb_srgb, 0.0, 1.0)
        
        if debug:
            _debug_save_rgb(rgb_srgb, debug_dir, step, "05_clahe_on_lab")
            step += 1
    else:
        # No CLAHE: just convert to sRGB
        if enable_linearize:
            rgb_srgb = preprocessing.linear_to_srgb(work)
        else:
            rgb_srgb = work
        rgb_srgb = np.clip(rgb_srgb, 0.0, 1.0)
        
        if debug:
            _debug_save_rgb(rgb_srgb, debug_dir, step, "05_back_to_srgb_no_clahe")
            step += 1

    # 6) Percentile normalization (robust global) - maintenant en sRGB
    if enable_percentile_norm:
        rgb_srgb = preprocessing.percentile_normalize(
            rgb_srgb, p_low=norm_p_low, p_high=norm_p_high, mask=mask
        )
        if debug:
            _debug_save_rgb(rgb_srgb, debug_dir, step, "06_percentile_norm")
            step += 1
    elif debug:
        _debug_save_rgb(rgb_srgb, debug_dir, step, "06_percentile_norm_skipped")
        step += 1

    # 7) Percentile normalization (robust global)
    if enable_percentile_norm:
        rgb_srgb = preprocessing.percentile_normalize(
            rgb_srgb, p_low=norm_p_low, p_high=norm_p_high, mask=mask
        )
        if debug:
            _debug_save_rgb(rgb_srgb, debug_dir, step, "07_percentile_norm")
            step += 1
    elif debug:
        _debug_save_rgb(rgb_srgb, debug_dir, step, "07_percentile_norm_skipped")
        step += 1

    # 8) Background mask refinement
    if enable_background_mask and bg_method == "paper":
        mask = preprocessing.build_paper_background_mask(
            rgb_srgb, mask, paper_threshold_deltaE=paper_threshold_deltaE
        )
        if debug:
            _debug_save_rgb(rgb_srgb, debug_dir, step, "08_rgb_after_mask")
            step += 1
    elif debug:
        _debug_save_rgb(rgb_srgb, debug_dir, step, "08_background_mask_skipped")
        step += 1

    rgb_out = np.clip(rgb_srgb, 0.0, 1.0)
    if debug:
        _debug_save_rgb(rgb_out, debug_dir, step, "99_output_rgb")

    return np.clip(work, 0.0, 1.0), mask


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

    top_n should be high if you want to later select by ratios + ΔE rather than a fixed max.
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

def select_colors_by_ratio_and_distance(
    bins: List[Dict],
    dominant_ratio: float = 0.05,
    accent_min_ratio: float = 0.001,
    accent_min_deltaE_from_selected: float = 18.0, 
    min_colors_fallback: Optional[int] = None,
    merge_similar: bool = True,
    merge_deltaE_threshold: float = 5.0,
) -> List[Dict]:
    if not bins:
        return []

    # Make selection stable
    bins = sorted(bins, key=lambda e: -e["ratio"])

    dominants = [b for b in bins if b["ratio"] >= dominant_ratio]
    if not dominants:
        dominants = [bins[0]]

    selected = list(dominants)

    selected_lab_centers = [
        np.array(d["lab_center"], dtype=np.float64).reshape(1, 1, 3)
        for d in selected
    ]

    candidates = [b for b in bins if b["ratio"] < dominant_ratio and b["ratio"] >= accent_min_ratio]
    candidates.sort(key=lambda e: -e["ratio"])

    for c in candidates:
        c_lab = np.array(c["lab_center"], dtype=np.float64).reshape(1, 1, 3)
        min_dE = min(
            float(deltaE_ciede2000(c_lab, s_lab)[0, 0])
            for s_lab in selected_lab_centers
        )
        if min_dE >= accent_min_deltaE_from_selected:
            c2 = dict(c)
            c2["min_dE_to_selected"] = float(min_dE)
            selected.append(c2)
            selected_lab_centers.append(c_lab)

    if min_colors_fallback is not None and len(selected) < min_colors_fallback:
        selected_ids = {s["bin_id"] for s in selected}
        for b in bins:
            if len(selected) >= min_colors_fallback:
                break
            if b["bin_id"] in selected_ids:
                continue

            b_lab = np.array(b["lab_center"], dtype=np.float64).reshape(1, 1, 3)
            min_dE = min(
                float(deltaE_ciede2000(b_lab, s_lab)[0, 0])
                for s_lab in selected_lab_centers
            )
            relaxed = accent_min_deltaE_from_selected * 0.5
            if min_dE >= relaxed:
                b2 = dict(b)
                b2["min_dE_to_selected"] = float(min_dE)
                selected.append(b2)
                selected_ids.add(b["bin_id"])
                selected_lab_centers.append(b_lab)

    selected.sort(key=lambda e: -e["ratio"])

    if merge_similar:
        selected = merge_similar_colors(selected, merge_deltaE_threshold)

    return selected

def merge_similar_colors(selected: List[Dict], merge_deltaE_threshold: float = 5.0) -> List[Dict]:
    """
    Merge colors that are too similar (ΔE < threshold).
    Representative = highest ratio among merged, ratios are summed.
    """
    if not selected:
        return []

    merged: List[Dict] = []
    used = set()

    for i in range(len(selected)):
        if i in used:
            continue

        rep = dict(selected[i])
        total_ratio = float(rep["ratio"])
        used.add(i)

        rep_lab = np.array(rep["lab_center"], dtype=np.float64).reshape(1, 1, 3)

        for j in range(i + 1, len(selected)):
            if j in used:
                continue

            c = selected[j]
            c_lab = np.array(c["lab_center"], dtype=np.float64).reshape(1, 1, 3)
            dE = float(deltaE_ciede2000(rep_lab, c_lab)[0, 0])

            if dE < merge_deltaE_threshold:
                total_ratio += float(c["ratio"])
                used.add(j)

                # Update representative if needed
                if float(c["ratio"]) > float(rep["ratio"]):
                    rep = dict(c)
                    rep_lab = c_lab

        rep["ratio"] = total_ratio
        merged.append(rep)

    merged.sort(key=lambda e: -e["ratio"])
    return merged

def build_exclusive_masks_by_nearest_center(
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

def save_mask_png(mask_bool: np.ndarray, out_path: str) -> None:
    """
    Save a boolean mask as an 8-bit PNG (0 or 255).
    Can be used for debug or final output.
    """
    mask_u8 = mask_bool.astype(np.uint8) * 255
    iio.imwrite(out_path, mask_u8)


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

    return unary_union(polygons)


def build_normalized_feature(color_name: str, rgb: Tuple[int, int, int], merged_geometry: BaseGeometry) -> Dict:
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
    # Quantization step on the b (blue–yellow) axis.
    # Larger value → merge nearby blues/yellows.
    # Smaller value → more sensitive to color differences.


    # -----------------------------
    # Color selection logic (which bins become layers)
    # -----------------------------

    dominant_ratio: float = 0.001, # Minimum pixel ratio for a color to be considered dominant.
    accent_min_ratio: float = 0.00005, # Minimum ratio for a non-dominant (accent) color to be considered.
    accent_min_deltaE_from_selected: float = 20.0, # Minimum ΔE distance from ALL dominant colors for an accent to be accepted.
    min_colors_fallback: Optional[int] = None, # If set, ensures at least this many colors are selected.
    merge_similar: bool = True, # If True, merges selected colors that are perceptually too close (ΔE-based).

    merge_deltaE_threshold: float = 12.0,
    # ΔE threshold below which two selected colors are merged.
    # Larger value → more aggressive merging.
    # Smaller value → keep more distinct but similar-looking layers.


    # -----------------------------
    # Mask construction (pixel assignment)
    # -----------------------------

    mask_deltaE: float = 10.0,
    # Maximum ΔE distance for a pixel to be assigned to a color layer.
    # Larger value → thicker, more inclusive masks.
    # Smaller value → tighter masks, may leave holes/unassigned pixels.

) -> Dict:
    """
    Extract exclusive color layers using:
    - LAB binning (frequency estimate)
    - Dominants: ratio >= dominant_ratio
    - Accents: low ratio but far (ΔE) from dominants
    - Merge similar selected colors (ΔE < merge_deltaE_threshold)
    - Exclusive assignment: each pixel belongs to exactly one selected color (nearest ΔE)

    Returns:
      - colors_detected (keys of masks)
      - masks (name -> png path)
      - ratios (name -> ratio)
      - selected_bins (metadata)
      - normalized_features (GeoJSON FeatureCollections)
    """

    debug = True

    # 0) Load raw image (keeps alpha mask)
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    image_output_dir = os.path.join(output_dir, base_name)

    rgb_u8, _, opaque_mask = load_image_rgb_alpha_mask(image_path)
    rgb = img_as_float(rgb_u8)

    if debug:
        os.makedirs(image_output_dir, exist_ok=True)    

    # Preprocess full image for color extraction (keeps/updates mask)
    rgb, opaque_mask = preprocess(
        rgb=rgb,
        opaque_mask=opaque_mask,
        enable_linearize=True,          # Work in linear RGB for illumination-like ops
        enable_flat_field=False,         # Flat-field in linear RGB
        flat_field_sigma=120.0,
        enable_white_balance=False,      # WB in linear RGB (stats on mask)
        white_balance_method="percentile",
        wb_percentile=99.5,
        enable_denoise=True,            # Denoise BEFORE CLAHE
        denoise_method="bilateral",
        bilateral_sigma_color=0.04,
        bilateral_sigma_spatial=2.0,
        enable_clahe=False,              # CLAHE in LAB, but on sRGB input (handled by preprocess)
        clahe_clip_limit=0.005,
        clahe_kernel_size=(8, 8),
        enable_percentile_norm=True,    # Do percentile normalization on sRGB (consistent with LAB next)
        norm_p_low=1.0,
        norm_p_high=99.0,
        enable_background_mask=True,    # If you want to remove "paper"
        bg_method="none",               # <-- keep your current behavior; set to "paper" to enable
        paper_threshold_deltaE=10.0,
        debug=debug,
        debug_dir=image_output_dir,
    )

    lab = compute_lab(rgb)


    base_name = os.path.splitext(os.path.basename(image_path))[0]
    image_output_dir = os.path.join(output_dir, base_name)

    rgb_u8, _, opaque_mask = load_image_rgb_alpha_mask(image_path)
    rgb = img_as_float(rgb_u8)

    if debug:
        os.makedirs(image_output_dir, exist_ok=True)    

    # Dominant LAB bins (computed on opaque pixels; you can also exclude text if desired)
    dom = dominant_bins_lab(
        lab, opaque_mask, top_n=top_n, bin_L=bin_L, bin_a=bin_a, bin_b=bin_b
    )

    masks: Dict[str, str] = {}
    mask_paths: Dict[str, str] = {}
    mask_paths: Dict[str, str] = {}
    ratios: Dict[str, float] = {}
    normalized_features: List[Dict] = []
    normalized_features = []
    pixel_features = []

    color_index = 1
    for k, entry in enumerate(selected):
        mask = (best_idx == k) & valid
        #mask = binary_opening(mask, disk(opening_radius))
    for k, entry in enumerate(selected):
        mask = (best_idx == k) & valid
        #mask = binary_opening(mask, disk(opening_radius))

        if not np.any(mask):
            continue

        rgb_u8 = lab_center_to_rgb_u8(entry["lab_center"])
        color_name = get_nearest_css4_color_name(rgb_u8)
        unique_color_name = f"{color_name}_{color_index}"
        L, a, b = entry["lab_center"]

        file_name = (
            f"color_{color_index:02d}_{unique_color_name}"
            f"_ratio_{entry['ratio']:.4f}"
            f"_lab_{L:.1f}_{a:.1f}_{b:.1f}"
            f".png"
        )

        ratios[unique_color_name] = float(entry["ratio"])

        if debug:
            out_path = os.path.join(image_output_dir, file_name)
            save_mask_png(mask, out_path)
            masks[unique_color_name] = out_path
            mask_paths[unique_color_name] = out_path
        
        geom = mask_to_geometry(mask)
        if geom is not None:
            feature = build_normalized_feature(unique_color_name, rgb_u8, geom)
            normalized_features.append({"type": "FeatureCollection", "features": [feature]})

        color_index += 1

    return {
        "colors_detected": list(masks.keys()),
        "masks": masks,
        "mask_paths": mask_paths if debug else {},
        "ratios": ratios,
        "selected_bins": selected,
        "output_dir": image_output_dir,
        "normalized_features": normalized_features,
        "pixel_features": pixel_features,
    }
