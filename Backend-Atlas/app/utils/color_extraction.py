import logging
import math
import os
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import shapely
from matplotlib import colors as mcolors
from scipy.ndimage import binary_fill_holes, distance_transform_edt
from shapely import affinity
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from skimage.color import deltaE_ciede2000, lab2rgb, rgb2lab
from skimage.measure import find_contours
from skimage.morphology import closing, disk, opening
from skimage.util import img_as_float

from app.utils.color_sampling import sample_color_at
from app.utils.legend import LegendBounds, legend_mask

from . import preprocessing

logger = logging.getLogger(__name__)

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


def relabel_text_pixels(
    best_idx: np.ndarray,
    valid: np.ndarray,
    text_regions: List,
    *,
    dilation_px: int = 2,
    min_context: float = 0.25,
    max_distance_px: float = 8.0,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    
    stats = {"boxesConsidered": 0, "boxesFilled": 0, "pixelsFilled": 0}
    if not text_regions or not valid.any():
        return best_idx, valid, stats

    height, width = valid.shape
    ring_px = max(int(dilation_px) + 4, 5)
    kernel_halo = np.ones((2 * max(int(dilation_px), 0) + 1,) * 2, np.uint8)
    kernel_ring = np.ones((2 * ring_px + 1,) * 2, np.uint8)

    fill_mask = np.zeros((height, width), dtype=bool)
    for polygon in text_regions:
        try:
            points = np.array(polygon, dtype=np.int32).reshape(-1, 2)
        except (TypeError, ValueError):
            continue
        if points.shape[0] < 3:
            continue

        stats["boxesConsidered"] += 1
        box = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(box, [points], 1)
        if dilation_px > 0:
            # The halo many atlases print around a label is not the glyph, but
            # it is just as far from the zone's colour.
            box = cv2.dilate(box, kernel_halo)
        box_mask = box.astype(bool)

        ring = cv2.dilate(box, kernel_ring).astype(bool) & ~box_mask
        if not ring.any() or (valid & ring).sum() / ring.sum() < min_context:
            continue

        stats["boxesFilled"] += 1
        fill_mask |= box_mask & ~valid

    if not fill_mask.any():
        return best_idx, valid, stats

    # One distance transform for the whole image: for every pixel, which
    # assigned pixel is nearest, and how far away it is.
    distance, (rows, cols) = distance_transform_edt(~valid, return_indices=True)
    fill_mask &= distance <= max_distance_px
    if not fill_mask.any():
        return best_idx, valid, stats

    best_idx = best_idx.copy()
    valid = valid.copy()
    best_idx[fill_mask] = best_idx[rows[fill_mask], cols[fill_mask]]
    valid[fill_mask] = True
    stats["pixelsFilled"] = int(fill_mask.sum())
    return best_idx, valid, stats


TEXT_FILL_METHODS = ("label", "inpaint")


def inpaint_text_ink(
    rgb: np.ndarray,
    lab: np.ndarray,
    centers_lab: np.ndarray,
    text_regions: List,
    *,
    protect_deltaE: float = 5.0,
    dilation_px: int = 1,
    inpaint_radius_px: float = 3.0,
    max_ink_ratio: float = 0.6,
    ring_px: int = 6,
    ring_min_share: float = 0.05,
) -> Tuple[np.ndarray, np.ndarray, Dict]:

    stats = {
        "method": "inpaint",
        "algo": "telea",
        "boxesConsidered": 0,
        "boxesFilled": 0,
        "pixelsFilled": 0,
    }
    if not text_regions:
        return rgb, lab, stats

    height, width = rgb.shape[:2]

    # Nearest zone colour for every pixel, and whether it is close enough to
    # count as that zone. Computed once for the whole image rather than per
    # box: boxes overlap, and ΔE2000 is the slow part.
    dists = np.stack(
        [deltaE_ciede2000(lab, c.reshape(1, 1, 3)) for c in centers_lab], axis=-1
    )
    nearest = np.argmin(dists, axis=-1)
    near_zone = np.min(dists, axis=-1) <= protect_deltaE
    del dists

    lightness = np.clip(lab[:, :, 0] * 2.55, 0, 255).astype(np.uint8)
    halo = np.ones((2 * max(int(dilation_px), 0) + 1,) * 2, np.uint8)
    pad = max(int(dilation_px), 0)
    ring_px = max(int(ring_px), 1)
    ring_kernel = np.ones((2 * ring_px + 1,) * 2, np.uint8)
    ink_mask = np.zeros((height, width), dtype=np.uint8)
    stats["zonesDroppedFromProtection"] = 0

    for polygon in text_regions:
        try:
            points = np.array(polygon, dtype=np.float64).reshape(-1, 2)
        except (TypeError, ValueError):
            continue
        if points.shape[0] < 3:
            continue

        # Work in the box's bounding rectangle, padded for the halo and the
        # ring around it.
        margin = pad + ring_px
        x0 = max(int(np.floor(points[:, 0].min())) - margin, 0)
        y0 = max(int(np.floor(points[:, 1].min())) - margin, 0)
        x1 = min(int(np.ceil(points[:, 0].max())) + margin + 1, width)
        y1 = min(int(np.ceil(points[:, 1].max())) + margin + 1, height)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        stats["boxesConsidered"] += 1

        box = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
        local = np.round(points - [x0, y0]).astype(np.int32)
        cv2.fillPoly(box, [local], 1)
        inside = box.astype(bool)

        # Only the zones actually around this label are protected. Labels are
        # often printed in a darker shade of their zone, which can sit within
        # ΔE of a *neighbouring* zone: protected globally, "HAUT-CANADA" kept
        # its letters and they were classified as Bas-Canada. The ring starts
        # past the halo so it reads the background, not the letters' fringe.
        grown = cv2.dilate(box, halo) if pad > 0 else box
        ring = cv2.dilate(grown, ring_kernel).astype(bool) & ~grown.astype(bool)
        near_local = near_zone[y0:y1, x0:x1]
        nearest_local = nearest[y0:y1, x0:x1]
        ring_zone = ring & near_local
        present = np.zeros(len(centers_lab), dtype=bool)
        if ring.any():
            counts = np.bincount(
                nearest_local[ring_zone], minlength=len(centers_lab)
            )
            present = counts >= ring_min_share * ring.sum()
        protected_local = near_local & present[nearest_local]
        stats["zonesDroppedFromProtection"] += int(
            (np.isin(nearest_local[inside & near_local], np.flatnonzero(~present))).any()
        )
        values = lightness[y0:y1, x0:x1][inside]
        if values.size < 8 or values.min() == values.max():
            continue

        threshold, _ = cv2.threshold(
            values.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        dark = lightness[y0:y1, x0:x1] <= threshold
        dark_share = float(dark[inside].mean())
        ink = (dark if dark_share <= 0.5 else ~dark) & inside

        ink &= ~protected_local
        if not ink.any() or ink[inside].mean() > max_ink_ratio:
            continue

        if pad > 0:
            ink = cv2.dilate(ink.astype(np.uint8), halo).astype(bool)
            ink &= ~protected_local

        ink_mask[y0:y1, x0:x1] |= ink.astype(np.uint8)
        stats["boxesFilled"] += 1

    if not ink_mask.any():
        return rgb, lab, stats

    rgb_u8 = (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    repaired = cv2.inpaint(rgb_u8, ink_mask, float(inpaint_radius_px), cv2.INPAINT_TELEA)

    # Only the ink is replaced: the 8-bit round trip cv2 needs would otherwise
    # shift every pixel of the map by up to half a level.
    ink = ink_mask.astype(bool)
    rebuilt = repaired[ink].astype(np.float64) / 255.0
    rgb_out = rgb.copy()
    rgb_out[ink] = rebuilt
    lab_out = lab.copy()
    lab_out[ink] = compute_lab(rebuilt.reshape(-1, 1, 3)).reshape(-1, 3)
    stats["pixelsFilled"] = int(ink.sum())
    return rgb_out, lab_out, stats


TEXT_INPAINT_ALGOS = ("palette", "telea")


def _ring_palette(
    ring_lab: np.ndarray, max_colors: int, min_share: float
) -> Optional[np.ndarray]:
    """The background colours around a label: k-means on the ring, small clusters dropped."""
    if ring_lab.shape[0] < 20:
        return None
    data = ring_lab.astype(np.float32)
    k = int(min(max_colors, data.shape[0]))
    cv2.setRNGSeed(0)  # same palette on every run of the same map
    _compactness, labels, centers = cv2.kmeans(
        data,
        k,
        None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5),
        3,
        cv2.KMEANS_PP_CENTERS,
    )
    shares = np.bincount(labels.ravel(), minlength=k) / float(labels.size)
    keep = shares >= min_share
    return centers[keep].astype(np.float64) if keep.any() else None


def repaint_text_ink_palette(
    rgb: np.ndarray,
    lab: np.ndarray,
    text_regions: List,
    *,
    ink_deltaE: float = 12.0,
    dilation_px: int = 1,
    max_ink_ratio: float = 0.6,
    ring_px: int = 6,
    palette_max_colors: int = 4,
    palette_min_share: float = 0.08,
    vote_window: int = 5,
    box_margin_px: int = 2,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """Erase each label's ink and repaint it with the colour that surrounds it.

    Three steps per OCR box, each replacing a weaker rule of the Telea path:

    * **Background palette** -- the ring around the box is clustered into at
      most ``palette_max_colors`` colours, keeping those that cover at least
      ``palette_min_share`` of it. Pixels inside *other* boxes are left out of
      the ring, so the next line of the same label cannot pass for background.
    * **Ink** -- a box pixel further than ``ink_deltaE`` from every palette
      colour. Replaces the Otsu split, whose "minority side is ink" rule
      picked Hudson Bay as the ink of "RUPERT" (82 % of that box is red
      background plus letters, all on the dark side).
    * **Fill by vote** -- from the outside in, one layer at a time, each ink
      pixel takes the palette colour most represented among its already
      known neighbours (a ``vote_window`` square). Replaces Telea's weighted
      mean, which blended sea and land into a violet no zone matches. Local,
      so a letter straddling a coast is split along the coast.

    The ink is grown by ``dilation_px`` for the anti-aliased fringe but never
    leaves the box (plus ``box_margin_px``): past it the fill would read
    colours from somewhere else, as the legend did with the sea below it.
    """
    stats = {
        "method": "inpaint",
        "algo": "palette",
        "boxesConsidered": 0,
        "boxesFilled": 0,
        "pixelsFilled": 0,
    }
    if not text_regions:
        return rgb, lab, stats

    height, width = rgb.shape[:2]

    polygons: List[np.ndarray] = []
    all_boxes = np.zeros((height, width), dtype=np.uint8)
    for polygon in text_regions:
        try:
            points = np.array(polygon, dtype=np.float64).reshape(-1, 2)
        except (TypeError, ValueError):
            continue
        if points.shape[0] < 3:
            continue
        polygons.append(points)
        cv2.fillPoly(all_boxes, [np.round(points).astype(np.int32)], 1)
    other_text = all_boxes.astype(bool)

    ring_kernel = np.ones((2 * max(int(ring_px), 1) + 1,) * 2, np.uint8)
    margin_kernel = np.ones((2 * max(int(box_margin_px), 0) + 1,) * 2, np.uint8)
    halo = np.ones((2 * max(int(dilation_px), 0) + 1,) * 2, np.uint8)
    window = max(int(vote_window), 3) | 1  # odd
    vote_kernel = np.ones((window, window), np.float32)

    rgb_out = rgb.copy()
    lab_out = lab.copy()
    filled = np.zeros((height, width), dtype=bool)

    for points in polygons:
        margin = max(int(ring_px), 1) + window
        x0 = max(int(np.floor(points[:, 0].min())) - margin, 0)
        y0 = max(int(np.floor(points[:, 1].min())) - margin, 0)
        x1 = min(int(np.ceil(points[:, 0].max())) + margin + 1, width)
        y1 = min(int(np.ceil(points[:, 1].max())) + margin + 1, height)
        if x1 - x0 < 3 or y1 - y0 < 3:
            continue
        stats["boxesConsidered"] += 1

        box = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
        cv2.fillPoly(box, [np.round(points - [x0, y0]).astype(np.int32)], 1)
        inside = box.astype(bool)
        if not inside.any():
            continue

        crop_lab = lab[y0:y1, x0:x1]
        ring = cv2.dilate(box, ring_kernel).astype(bool) & ~inside
        ring &= ~other_text[y0:y1, x0:x1]
        palette = _ring_palette(crop_lab[ring], palette_max_colors, palette_min_share)
        if palette is None:
            continue

        # ΔE to each palette colour, for the whole crop: the box decides what
        # is ink, the surroundings are the voters.
        dists = np.stack(
            [deltaE_ciede2000(crop_lab, c.reshape(1, 1, 3)) for c in palette], axis=-1
        )
        nearest = np.argmin(dists, axis=-1)
        near_palette = np.min(dists, axis=-1) <= ink_deltaE

        ink = inside & ~near_palette
        if not ink.any() or ink[inside].mean() > max_ink_ratio:
            continue
        allowed = cv2.dilate(box, margin_kernel).astype(bool)
        if dilation_px > 0:
            ink = cv2.dilate(ink.astype(np.uint8), halo).astype(bool)
        ink &= allowed

        # Voters: known pixels that match a palette colour. Anything else --
        # a border line, a neighbouring label -- neither votes nor is filled.
        labels = np.where(near_palette & ~ink, nearest, -1)
        todo = ink.copy()
        while todo.any():
            counts = np.stack(
                [
                    cv2.filter2D(
                        (labels == k).astype(np.float32), -1, vote_kernel,
                        borderType=cv2.BORDER_CONSTANT,
                    )
                    for k in range(len(palette))
                ],
                axis=-1,
            )
            frontier = todo & (counts.sum(axis=-1) > 0)
            if not frontier.any():
                break  # no voter reaches what is left
            labels[frontier] = np.argmax(counts[frontier], axis=-1)
            todo &= ~frontier

        repainted = ink & (labels >= 0)
        if not repainted.any():
            continue
        palette_rgb = np.clip(lab2rgb(palette.reshape(-1, 1, 3)).reshape(-1, 3), 0, 1)
        ys, xs = np.nonzero(repainted)
        chosen = labels[ys, xs]
        rgb_out[ys + y0, xs + x0] = palette_rgb[chosen]
        lab_out[ys + y0, xs + x0] = palette[chosen]
        filled[ys + y0, xs + x0] = True
        stats["boxesFilled"] += 1

    if not filled.any():
        return rgb, lab, stats
    stats["pixelsFilled"] = int(filled.sum())
    return rgb_out, lab_out, stats


def fill_gaps_between_zones(
    labels: np.ndarray, zone_count: int, max_gap_px: float
) -> Tuple[np.ndarray, int]:
    """Close the thin unassigned band between two different zones.

    A border drawn on the map (a solid or dashed line) belongs to no zone's
    colour, so two neighbouring zones come out separated by a strip of
    nothing. Every zone grows at the same rate into unassigned pixels, and a
    pixel is taken only when it is *between two different zones in a narrow
    gap*: ``d_A + d_B <= max_gap_px``, with A and B its two nearest zones.
    ``d_A + d_B`` is the local width of the gap, so a drawn line qualifies and
    a lake, the sea, or a real blank area between zones does not. A zone
    facing the sea has no second zone within reach, so coastlines are left
    alone. The pixel goes to the nearer zone: the two meet mid-line.

    Args:
        labels: (H, W) zone index per pixel, -1 where unassigned.

    Returns:
        ``(labels, pixels_filled)`` -- a copy with the gaps assigned.
    """
    if zone_count < 2 or max_gap_px <= 0:
        return labels, 0
    unassigned = labels < 0
    if not unassigned.any():
        return labels, 0

    # Distance from every pixel to each zone; the stack is (K, H, W) floats,
    # a few MB per zone on a large scan.
    distances = np.stack(
        [distance_transform_edt(labels != k) for k in range(zone_count)]
    )
    order = np.argsort(distances, axis=0)
    nearest = order[0]
    d1 = np.take_along_axis(distances, order[:1], axis=0)[0]
    d2 = np.take_along_axis(distances, order[1:2], axis=0)[0]

    fill = unassigned & (d1 + d2 <= max_gap_px)
    if not fill.any():
        return labels, 0
    out = labels.copy()
    out[fill] = nearest[fill]
    return out, int(fill.sum())


def resolve_zone_overlaps(masks: List[np.ndarray], labels: np.ndarray) -> np.ndarray:
    """One zone per pixel after per-zone morphology.

    Closing and hole filling run on each zone alone, so two zones can claim
    the same pixel: hole filling makes an enclave of B inside A part of A.
    A pixel claimed twice goes back to the zone it was classified as, and
    otherwise to the first claimant.
    """
    height, width = labels.shape
    stack = np.stack(masks) if masks else np.zeros((0, height, width), dtype=bool)
    claims = stack.sum(axis=0)
    final = np.full((height, width), -1, dtype=np.int32)
    if stack.shape[0] == 0:
        return final
    first = np.argmax(stack, axis=0)
    final[claims >= 1] = first[claims >= 1]
    contested = claims > 1
    if contested.any():
        own = labels[contested]
        rows, cols = np.nonzero(contested)
        valid_own = own >= 0
        keeps = np.zeros(own.shape, dtype=bool)
        keeps[valid_own] = stack[own[valid_own], rows[valid_own], cols[valid_own]]
        final[rows[keeps], cols[keeps]] = own[keeps]
    return final


def mask_to_pixel_edge_geometry(mask: np.ndarray) -> Optional[BaseGeometry]:
    """The mask as polygons that follow pixel *edges*, not pixel centres.

    ``mask_to_geometry`` traces contours through pixel centres, so two zones
    that touch in the raster end up a pixel apart as polygons -- a gap on
    every shared border, however clean the raster. Built from each row's runs
    of pixels, unioned, two neighbouring zones share exactly the same edges,
    which is what `coverage_simplify` needs to keep them shared.
    """
    if not mask.any():
        return None
    padded = np.zeros((mask.shape[0], mask.shape[1] + 2), dtype=np.int8)
    padded[:, 1:-1] = mask
    steps = np.diff(padded, axis=1)
    start_rows, start_cols = np.nonzero(steps == 1)
    _end_rows, end_cols = np.nonzero(steps == -1)
    # np.nonzero is row-major, so the n-th start and the n-th end of a row pair up.
    boxes = shapely.box(start_cols, start_rows, end_cols, start_rows + 1)
    geometry = shapely.union_all(boxes)
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    return None if geometry.is_empty else geometry


def mask_to_geometry(mask: np.ndarray) -> Optional[BaseGeometry]:
    
    if not np.any(mask):
        return None

    contours, hierarchy = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours or hierarchy is None:
        return None

    def _ring(contour) -> Optional[List[Tuple[float, float]]]:
        # (x=col, y=row), matching the previous convention.
        coords = [(float(p[0][0]), float(p[0][1])) for p in contour]
        if len(coords) < 3:
            return None
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        return coords

    # hierarchy is (1, n, 4): [next, previous, first_child, parent]. A contour
    # with no parent is an outer boundary; its children are its holes.
    hierarchy = hierarchy[0]
    polygons: List[Polygon] = []
    for index, contour in enumerate(contours):
        if hierarchy[index][3] != -1:
            continue  # a hole, handled with its parent

        shell = _ring(contour)
        if shell is None:
            continue

        holes = []
        child = hierarchy[index][2]
        while child != -1:
            hole = _ring(contours[child])
            if hole is not None:
                holes.append(hole)
            child = hierarchy[child][0]

        try:
            poly = Polygon(shell, holes)
            if not poly.is_valid:
                # Self-touching rings are common on a pixel boundary; buffer(0)
                # is the standard repair and keeps the holes.
                poly = poly.buffer(0)
            if not poly.is_empty and poly.area > 0:
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
    legend_bounds: Optional[LegendBounds] = None,
    imposed_click_positions: Optional[List[Tuple[float, float]]] = None,
    imposed_colors_names: Optional[List[Optional[str]]] = None,
    imposed_sampling_radii: Optional[List[int]] = None,
    # -----------------------------
    # Mask construction (pixel assignment)
    # -----------------------------
    mask_deltaE: float = 10.0,
    # Maximum ΔE distance for a pixel to be assigned to a color layer.
    # Larger value → thicker, more inclusive masks.
    # Smaller value → tighter masks, may leave holes/unassigned pixels.
    # -----------------------------
    # Post-processing
    # -----------------------------
    opening_radius: int = 1,  # Erosion then dilation to remove small noise/speckles
    closing_radius: int = 3,  # Dilation then erosion to fill small gaps
    simplify_tolerance: float = 1.0,
    sampling_radius: int = 20,  # Neighbourhood radius (px) used when sampling imposed click positions
    # -----------------------------
    # Text-aware assignment
    # -----------------------------
    # OCR polygons, when the caller has them. A label is drawn *over* a zone,
    # so without this its glyphs are holes the zone never recovers -- see
    # `relabel_text_pixels`. Passing None keeps the previous behaviour.
    text_regions: Optional[List] = None,
    text_dilation_px: int = 2,
    text_fill_min_context: float = 0.25,
    text_fill_max_distance_px: float = 8.0,
    # "label" repairs the assignment after the fact (`relabel_text_pixels`);
    # "inpaint" rebuilds the image under the ink before it (`inpaint_text_ink`).
    text_fill_method: str = "label",
    text_inpaint_dilation_px: int = 1,
    text_inpaint_radius_px: float = 3.0,
    text_inpaint_max_ink_ratio: float = 0.6,
    # "palette" (ring palette + vote) or "telea" (Otsu + cv2.inpaint).
    text_inpaint_algo: str = "palette",
    text_inpaint_ink_deltaE: float = 12.0,
    # -----------------------------
    # Shared borders between zones
    # -----------------------------
    # Close the drawn border line between two zones, keep one zone per pixel,
    # and vectorise every zone together so neighbours share their edges. Off
    # keeps the previous per-zone behaviour exactly.
    zone_gap_fill: bool = False,
    zone_gap_max_ratio_of_diagonal: float = 0.008,
) -> Dict:
    """
    Extract exclusive color layers using:
    - Imposed colors (pipette click positions)
    - Exclusive assignment: each pixel belongs to exactly one selected color (nearest ΔE)
    - The legend rectangle, when given, belongs to no color: its swatches are
      a key, not territory

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

    # Removed from both the assignment and the final masks: hole filling would
    # otherwise hand a legend enclosed by a zone back to that zone.
    legend_pixels = legend_mask(opaque_mask.shape, legend_bounds)
    opaque_mask = opaque_mask & ~legend_pixels

    if imposed_click_positions:
        # Sample the dominant (mode) colour in a neighbourhood around each click,
        # using the same logic as /sample-color so preview and extraction are consistent.
        # rgb is the preprocessed float [0,1] image; sample_color_at accepts both
        # float and uint8 inputs.
        sampled_rgb: List[Tuple[int, int, int]] = []
        for idx, (nx, ny) in enumerate(imposed_click_positions):
            radius_px = sampling_radius
            if imposed_sampling_radii and idx < len(imposed_sampling_radii):
                try:
                    radius_px = int(imposed_sampling_radii[idx])
                except (TypeError, ValueError):
                    radius_px = sampling_radius
            radius_px = max(1, min(200, radius_px))

            result = sample_color_at(rgb, nx, ny, radius_px=radius_px)
            if result is not None:
                r, g, b = result["rgb"]
                sampled_rgb.append((int(r), int(g), int(b)))
        imposed_dominants = prepare_imposed_dominants(
            sampled_rgb, names=imposed_colors_names
        )
    else:
        imposed_dominants = []

    # Colors are always imposed by the pipette.
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
    if text_fill_method not in TEXT_FILL_METHODS:
        raise ValueError(
            f"text_fill_method must be one of {TEXT_FILL_METHODS}, got {text_fill_method!r}"
        )

    # 5b) Inpaint mode: erase the labels' ink from the image before any pixel
    # is classified. After the colours are sampled, since it needs them to
    # know which pixels are already zone and must be kept.
    if text_inpaint_algo not in TEXT_INPAINT_ALGOS:
        raise ValueError(
            f"text_inpaint_algo must be one of {TEXT_INPAINT_ALGOS}, got {text_inpaint_algo!r}"
        )

    text_stats = None
    if text_regions and text_fill_method == "inpaint" and text_inpaint_algo == "palette":
        rgb, lab, text_stats = repaint_text_ink_palette(
            rgb,
            lab,
            text_regions,
            ink_deltaE=text_inpaint_ink_deltaE,
            dilation_px=text_inpaint_dilation_px,
            max_ink_ratio=text_inpaint_max_ink_ratio,
        )
        logger.info(
            f"[COLOR] text repaint (palette): {text_stats['pixelsFilled']} px in "
            f"{text_stats['boxesFilled']}/{text_stats['boxesConsidered']} label boxes"
        )
    elif text_regions and text_fill_method == "inpaint":
        rgb, lab, text_stats = inpaint_text_ink(
            rgb,
            lab,
            centers_lab,
            text_regions,
            # TODO this is a test for the protection to just put none
            #protect_deltaE=mask_deltaE,
            protect_deltaE=0,
            dilation_px=text_inpaint_dilation_px,
            inpaint_radius_px=text_inpaint_radius_px,
            max_ink_ratio=text_inpaint_max_ink_ratio,
        )
        logger.info(
            f"[COLOR] text inpaint: {text_stats['pixelsFilled']} px rebuilt in "
            f"{text_stats['boxesFilled']}/{text_stats['boxesConsidered']} label boxes"
        )

    best_idx, valid = build_exclusive_masks_by_nearest_center(
        lab, opaque_mask, centers_lab, mask_deltaE
    )

    # 6b) Label mode: give label pixels back to the zone they are written on,
    # before any mask is built from them: the morphology and hole filling
    # below cannot reach glyphs that touch the map's linework.
    if text_regions and text_fill_method == "label":
        best_idx, valid, text_stats = relabel_text_pixels(
            best_idx,
            valid,
            text_regions,
            dilation_px=text_dilation_px,
            min_context=text_fill_min_context,
            max_distance_px=text_fill_max_distance_px,
        )
        text_stats["method"] = "label"
        logger.info(
            f"[COLOR] text-aware fill: {text_stats['pixelsFilled']} px recovered in "
            f"{text_stats['boxesFilled']}/{text_stats['boxesConsidered']} label boxes"
        )

    def _morphology(mask: np.ndarray) -> np.ndarray:
        # 1. Opening: Remove small noise/speckles
        if opening_radius > 0:
            mask = opening(mask, disk(opening_radius))
        # 2. Closing: Bridge small gaps (useful for connecting fragmented regions)
        if closing_radius > 0:
            mask = closing(mask, disk(closing_radius))
        # 3. Fill holes: Remove interior holes (text, small waters, etc.)
        return binary_fill_holes(mask) & ~legend_pixels

    # 6c) Shared borders: close the line drawn between two zones, then settle
    # every pixel on one zone and vectorise all zones together, so that two
    # neighbours come out with the very same border instead of a strip.
    gap_stats = None
    shared_masks: Optional[List[np.ndarray]] = None
    shared_geometries: Dict[int, BaseGeometry] = {}
    if zone_gap_fill:
        labels = np.where(valid, best_idx, -1).astype(np.int32)
        height, width = labels.shape
        max_gap_px = zone_gap_max_ratio_of_diagonal * math.hypot(width, height)
        labels, gap_pixels = fill_gaps_between_zones(labels, len(dominants), max_gap_px)
        final = resolve_zone_overlaps(
            [_morphology(labels == k) for k in range(len(dominants))], labels
        )
        shared_masks = [final == k for k in range(len(dominants))]

        indexed = [
            (k, mask_to_pixel_edge_geometry(m)) for k, m in enumerate(shared_masks)
        ]
        indexed = [(k, g) for k, g in indexed if g is not None]
        if indexed:
            geoms = np.array([g for _k, g in indexed], dtype=object)
            if simplify_tolerance > 0:
                # Simplified as one coverage: a vertex dropped on a shared
                # border is dropped from both sides, so no sliver opens.
                geoms = shapely.coverage_simplify(geoms, simplify_tolerance)
            shared_geometries = {
                k: g for (k, _old), g in zip(indexed, geoms) if not g.is_empty
            }
        gap_stats = {"maxGapPx": round(max_gap_px, 2), "pixelsFilled": gap_pixels}
        logger.info(
            f"[COLOR] zone gaps: {gap_pixels} px filled (max width {max_gap_px:.1f} px)"
        )

    # 7) Build per-color masks and features
    seen_names: Dict[str, int] = {}
    color_index = 1
    for k, entry in enumerate(dominants):
        if shared_masks is not None:
            mask = shared_masks[k]
        else:
            mask = _morphology((best_idx == k) & valid)

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

        if shared_masks is not None:
            geometry = shared_geometries.get(k)
        else:
            geometry = mask_to_geometry(mask)
            if geometry:
                geometry = simplify_geometry(geometry, simplify_tolerance)

        if geometry and legend_bounds:
            # Contours are unioned without their holes, so a legend enclosed by
            # the zone comes back at this stage unless it is cut out again.
            geometry = geometry.difference(
                box(
                    legend_bounds["x"],
                    legend_bounds["y"],
                    legend_bounds["x"] + legend_bounds["width"],
                    legend_bounds["y"] + legend_bounds["height"],
                )
            )
            if geometry.is_empty:
                geometry = None
                
        if geometry:

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
        # None when the caller passed no OCR boxes, so "was it applied at all"
        # is answerable from the result rather than only from the logs.
        "text_fill": text_stats,
        # None when the shared-border step is off.
        "zone_gaps": gap_stats,
        # The image the pixels were classified on, when inpainting changed it:
        # preprocessed, labels erased. None otherwise. For the dev tool, which
        # shows it so a bad zone can be traced to a bad rebuild.
        "classified_rgb": (
            rgb if text_stats and text_stats.get("method") == "inpaint"
            and text_stats.get("pixelsFilled") else None
        ),
    }
