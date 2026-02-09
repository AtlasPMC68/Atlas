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
    Convert RGB image to LAB (float).
    """
    rgb_f = img_as_float(rgb)  # ensures float in [0, 1]
    return rgb2lab(rgb_f)


def dominant_bins_lab(
    lab: np.ndarray,
    opaque_mask: np.ndarray,
    top_n: int = 200,
    bin_L: float = 3.0,
    bin_a: float = 6.0,
    bin_b: float = 6.0,
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


def select_colors_by_ratio_and_distance(
    bins: List[Dict],
    dominant_ratio: float = 0.05,
    accent_min_ratio: float = 0.001,
    accent_min_deltaE_from_dominants: float = 18.0,
    min_colors_fallback: Optional[int] = None,
    merge_similar: bool = True,
    merge_deltaE_threshold: float = 5.0,
) -> List[Dict]:
    """
    Selection strategy:
    1) Keep all dominants (ratio >= dominant_ratio).
    2) Keep accents if:
       - ratio >= accent_min_ratio
       - and min ΔE to any dominant >= accent_min_deltaE_from_dominants
    3) Optional fallback to ensure at least N colors.
    4) Optional merge of similar colors.
    """
    if not bins:
        return []

    dominants = [b for b in bins if b["ratio"] >= dominant_ratio]
    if not dominants:
        dominants = [bins[0]]

    dominant_centers = [
        np.array(d["lab_center"], dtype=np.float64).reshape(1, 1, 3)
        for d in dominants
    ]

    selected = list(dominants)

    candidates = [b for b in bins if b["ratio"] < dominant_ratio and b["ratio"] >= accent_min_ratio]

    for c in candidates:
        c_lab = np.array(c["lab_center"], dtype=np.float64).reshape(1, 1, 3)
        min_dE = min(
            float(deltaE_ciede2000(c_lab, d_lab)[0, 0])
            for d_lab in dominant_centers
        )
        if min_dE >= accent_min_deltaE_from_dominants:
            c2 = dict(c)
            c2["min_dE_to_dominants"] = float(min_dE)
            selected.append(c2)

    if min_colors_fallback is not None and len(selected) < min_colors_fallback:
        selected_ids = {s["bin_id"] for s in selected}
        for b in bins:
            if len(selected) >= min_colors_fallback:
                break
            if b["bin_id"] in selected_ids:
                continue

            b_lab = np.array(b["lab_center"], dtype=np.float64).reshape(1, 1, 3)
            min_dE = min(
                float(deltaE_ciede2000(b_lab, d_lab)[0, 0])
                for d_lab in dominant_centers
            )
            relaxed = accent_min_deltaE_from_dominants * 0.5
            if min_dE >= relaxed:
                b2 = dict(b)
                b2["min_dE_to_dominants"] = float(min_dE)
                selected.append(b2)
                selected_ids.add(b["bin_id"])

    selected.sort(key=lambda e: -e["ratio"])

    if merge_similar:
        selected = merge_similar_colors(selected, merge_deltaE_threshold)

    return selected


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

    accent_min_ratio: float = 0.0001, # Minimum ratio for a non-dominant (accent) color to be considered.

    accent_min_deltaE_from_dominants: float = 18.0, # Minimum ΔE distance from ALL dominant colors for an accent to be accepted.

    min_colors_fallback: Optional[int] = None, # If set, ensures at least this many colors are selected.

    merge_similar: bool = True, # If True, merges selected colors that are perceptually too close (ΔE-based).

    merge_deltaE_threshold: float = 10.0,
    # ΔE threshold below which two selected colors are merged.
    # Larger value → more aggressive merging.
    # Smaller value → keep more distinct but similar-looking layers.


    # -----------------------------
    # Mask construction (pixel assignment)
    # -----------------------------

    mask_deltaE: float = 18.0,
    # Maximum ΔE distance for a pixel to be assigned to a color layer.
    # Larger value → thicker, more inclusive masks.
    # Smaller value → tighter masks, may leave holes/unassigned pixels.

    opening_radius: int = 0,
    # Morphological opening radius (noise removal).
    # 0 disables morphology completely (preserves small shapes).
    # >0 removes small isolated pixels but can destroy fine details (stars, dots).
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
    rgb, alpha, opaque_mask = load_image_rgb_alpha_mask(image_path)
    lab = compute_lab(rgb)

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    image_output_dir = os.path.join(output_dir, base_name)
    os.makedirs(image_output_dir, exist_ok=True)

    # 1) Build many candidate bins
    bins = dominant_bins_lab(
        lab=lab,
        opaque_mask=opaque_mask,
        top_n=top_n_bins,
        bin_L=bin_L,
        bin_a=bin_a,
        bin_b=bin_b,
    )

    # 2) Select dominants + accents (+ merge)
    selected = select_colors_by_ratio_and_distance(
        bins=bins,
        dominant_ratio=dominant_ratio,
        accent_min_ratio=accent_min_ratio,
        accent_min_deltaE_from_dominants=accent_min_deltaE_from_dominants,
        min_colors_fallback=min_colors_fallback,
        merge_similar=merge_similar,
        merge_deltaE_threshold=merge_deltaE_threshold,
    )

    # If selection is empty (shouldn't happen), fall back to top bin
    if not selected:
        selected = [bins[0]]

    # 3) Exclusive pixel assignment to nearest selected center
    centers_lab = np.array([s["lab_center"] for s in selected], dtype=np.float64)  # (K, 3)
    best_idx, valid = build_exclusive_masks_by_nearest_center(
        lab=lab,
        opaque_mask=opaque_mask,
        centers_lab=centers_lab,
        mask_deltaE=mask_deltaE,
    )

    # 4) Optional cleanup: opening per mask (keeps exclusivity because each mask is derived from best_idx)
    masks: Dict[str, str] = {}
    ratios: Dict[str, float] = {}
    normalized_features: List[Dict] = []

    color_index = 1
    for k, entry in enumerate(selected):
        mask = (best_idx == k) & valid

        if opening_radius > 0:
            mask = binary_opening(mask, disk(opening_radius))

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

        out_path = os.path.join(image_output_dir, file_name)
        save_mask_png(mask, out_path)

        masks[unique_color_name] = out_path
        ratios[unique_color_name] = float(entry["ratio"])

        geom = mask_to_geometry(mask)
        if geom is not None:
            feature = build_normalized_feature(unique_color_name, rgb_u8, geom)
            normalized_features.append({"type": "FeatureCollection", "features": [feature]})

        color_index += 1

    return {
        "colors_detected": list(masks.keys()),
        "masks": masks,
        "ratios": ratios,
        "selected_bins": selected,
        "output_dir": image_output_dir,
        "normalized_features": normalized_features,
        "params": {
            "top_n_bins": top_n_bins,
            "bin_L": bin_L,
            "bin_a": bin_a,
            "bin_b": bin_b,
            "dominant_ratio": dominant_ratio,
            "accent_min_ratio": accent_min_ratio,
            "accent_min_deltaE_from_dominants": accent_min_deltaE_from_dominants,
            "merge_similar": merge_similar,
            "merge_deltaE_threshold": merge_deltaE_threshold,
            "mask_deltaE": mask_deltaE,
            "opening_radius": opening_radius,
        },
    }
