import os
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import imageio.v3 as iio

from skimage.color import rgb2lab, lab2rgb, deltaE_ciede2000
from skimage.morphology import binary_opening, disk
from skimage.util import img_as_float
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import imageio.v3 as iio

from skimage.color import rgb2lab, lab2rgb, deltaE_ciede2000
from skimage.morphology import binary_opening, disk
from skimage.util import img_as_float
from matplotlib import colors as mcolors


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
        raise ValueError(f"Error loading image: {str(e)}")

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
    # Assumption: aq and bq stay < 1000 (true with typical bin sizes).
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


def detect_text_mask_rgb(
    rgb: np.ndarray,
    opaque_mask: np.ndarray,
    text_tolerance: int = 25,
    opening_radius: int = 2,
) -> np.ndarray:
    """
    Detect near-black text in RGB and return a boolean mask (H, W).
    Uses tolerance in RGB space and excludes transparent pixels.
    """
    black = np.array([0, 0, 0], dtype=np.int32)
    rgb_i = rgb.astype(np.int32)

    text_mask = np.all(np.abs(rgb_i - black) <= text_tolerance, axis=2)
    text_mask = text_mask & opaque_mask

    if opening_radius > 0:
        text_mask = binary_opening(text_mask, disk(opening_radius))

    return text_mask


def lab_center_to_rgb_u8(lab_center: Tuple[float, float, float]) -> Tuple[int, int, int]:
    """
    Convert a single LAB color to an approximate RGB uint8 tuple for naming/debug.
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


def extract_colors(
    image_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    top_n: int = 8,
    bin_L: float = 4.0,
    bin_a: float = 8.0,
    bin_b: float = 8.0,
    text_tolerance: int = 25,
    deltaE_threshold: float = 10.0,
    opening_radius: int = 1,
) -> Dict:
    """
    Extract dominant color layers using LAB binning + ΔE masks.
    Also extracts a near-black text layer.

    Returns a dict with detected colors, mask paths, and ratios.
    """
    rgb, alpha, opaque_mask = load_image_rgb_alpha_mask(image_path)
    lab = compute_lab(rgb)

    # Output folder
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    image_output_dir = os.path.join(output_dir, base_name)
    os.makedirs(image_output_dir, exist_ok=True)

    # Text layer (optional, near-black)
    text_mask = detect_text_mask_rgb(rgb, opaque_mask, text_tolerance=text_tolerance, opening_radius=2)
    text_path = os.path.join(image_output_dir, "text_layer_black.png")
    save_mask_png(text_mask, text_path)

    # Dominant LAB bins (computed on opaque pixels; you can also exclude text if desired)
    dom = dominant_bins_lab(lab, opaque_mask, top_n=top_n, bin_L=bin_L, bin_a=bin_a, bin_b=bin_b)

    masks: Dict[str, str] = {"text_layer": text_path}
    ratios: Dict[str, float] = {}

    color_index = 1
    for entry in dom:
        lab_center = entry["lab_center"]

        # Build ΔE mask against the LAB center.
        # deltaE_ciede2000 expects (...,3) arrays; we broadcast center to image shape.
        center = np.array(lab_center, dtype=np.float64).reshape(1, 1, 3)
        dE = deltaE_ciede2000(lab, center)  # shape (H, W)

        mask = (dE <= deltaE_threshold) & opaque_mask

        # Optional: remove text from color layers
        mask = mask & (~text_mask)

        # Clean small noise
        if opening_radius > 0:
            mask = binary_opening(mask, disk(opening_radius))

        # Name the layer based on approximate RGB -> nearest CSS name
        rgb_u8 = lab_center_to_rgb_u8(lab_center)
        color_name = get_nearest_css4_color_name(rgb_u8)

        file_name = f"color_{color_index}_{color_name}_ratio_{entry['ratio']:.4f}.png"
        out_path = os.path.join(image_output_dir, file_name)
        save_mask_png(mask, out_path)

        masks[color_name] = out_path
        ratios[color_name] = entry["ratio"]
        color_index += 1

    return {
        "colors_detected": list(masks.keys()),
        "masks": masks,
        "ratios": ratios,
        "dominant_bins": dom,
        "output_dir": image_output_dir,
    }


def save_mask_png(mask_bool: np.ndarray, out_path: str) -> None:
    """
    Save a boolean mask as an 8-bit PNG (0 or 255).
    """
    mask_u8 = (mask_bool.astype(np.uint8) * 255)
    iio.imwrite(out_path, mask_u8)


def extract_colors(
    image_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    top_n: int = 8,
    bin_L: float = 4.0,
    bin_a: float = 8.0,
    bin_b: float = 8.0,
    text_tolerance: int = 25,
    deltaE_threshold: float = 10.0,
    opening_radius: int = 1,
) -> Dict:
    """
    Extract dominant color layers using LAB binning + ΔE masks.
    Also extracts a near-black text layer.

    Returns a dict with detected colors, mask paths, and ratios.
    """
    rgb, alpha, opaque_mask = load_image_rgb_alpha_mask(image_path)
    lab = compute_lab(rgb)

    # Output folder
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    image_output_dir = os.path.join(output_dir, base_name)
    os.makedirs(image_output_dir, exist_ok=True)

    # Text layer (optional, near-black)
    text_mask = detect_text_mask_rgb(rgb, opaque_mask, text_tolerance=text_tolerance, opening_radius=2)
    text_path = os.path.join(image_output_dir, "text_layer_black.png")
    save_mask_png(text_mask, text_path)

    # Dominant LAB bins (computed on opaque pixels; you can also exclude text if desired)
    dom = dominant_bins_lab(lab, opaque_mask, top_n=top_n, bin_L=bin_L, bin_a=bin_a, bin_b=bin_b)

    masks: Dict[str, str] = {"text_layer": text_path}
    ratios: Dict[str, float] = {}

    color_index = 1
    for entry in dom:
        lab_center = entry["lab_center"]

        # Build ΔE mask against the LAB center.
        # deltaE_ciede2000 expects (...,3) arrays; we broadcast center to image shape.
        center = np.array(lab_center, dtype=np.float64).reshape(1, 1, 3)
        dE = deltaE_ciede2000(lab, center)  # shape (H, W)

        mask = (dE <= deltaE_threshold) & opaque_mask

        # Optional: remove text from color layers
        mask = mask & (~text_mask)

        # Clean small noise
        if opening_radius > 0:
            mask = binary_opening(mask, disk(opening_radius))

        # Name the layer based on approximate RGB -> nearest CSS name
        rgb_u8 = lab_center_to_rgb_u8(lab_center)
        color_name = get_nearest_css4_color_name(rgb_u8)

        file_name = f"color_{color_index}_{color_name}_ratio_{entry['ratio']:.4f}.png"
        out_path = os.path.join(image_output_dir, file_name)
        save_mask_png(mask, out_path)

        masks[color_name] = out_path
        ratios[color_name] = entry["ratio"]
        color_index += 1

    return {
        "colors_detected": list(masks.keys()),
        "masks": masks,
        "ratios": ratios,
        "dominant_bins": dom,
        "output_dir": image_output_dir,
    }
