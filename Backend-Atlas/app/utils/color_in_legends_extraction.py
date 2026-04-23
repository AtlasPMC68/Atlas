import os
from typing import Dict, List, Optional, Optional, Tuple
import cv2
import numpy as np
from skimage.color import rgb2lab


def sample_color_at(
    image_rgb: np.ndarray,
    x_norm: float,
    y_norm: float,
    radius_px: int = 20,
) -> Optional[Dict]:
    """
    Sample the dominant color in a square neighbourhood around a normalised
    click point (x_norm, y_norm both in [0, 1]).

    Returns a dict with:
        rgb  — (r, g, b) uint8 tuple
        lab  — [L, a, b] float list  (CIELAB, same space used by extraction)
        hex  — CSS hex string e.g. "#a3c45f"

    Returns None if the coordinates are out of range or the region is empty.
    """
    if not (0.0 <= x_norm <= 1.0 and 0.0 <= y_norm <= 1.0):
        return None

    if image_rgb.dtype != np.uint8:
        image_rgb = (np.clip(image_rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)

    h, w = image_rgb.shape[:2]

    # Map normalized coords into valid pixel indices.
    # Using (w-1)/(h-1) ensures x_norm==1.0 maps to the last pixel, not w/h.
    if w <= 0 or h <= 0:
        return None

    cx = int(round(x_norm * (w - 1))) if w > 1 else 0
    cy = int(round(y_norm * (h - 1))) if h > 1 else 0
    cx = max(0, min(w - 1, cx))
    cy = max(0, min(h - 1, cy))

    try:
        radius_px_int = int(radius_px)
    except (TypeError, ValueError):
        radius_px_int = 20
    radius_px_int = max(0, radius_px_int)

    x1 = max(0, cx - radius_px_int)
    x2 = min(w, cx + radius_px_int + 1)
    y1 = max(0, cy - radius_px_int)
    y2 = min(h, cy + radius_px_int + 1)

    roi = image_rgb[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    # Most-frequent RGB colour in the neighbourhood (mode)
    pixels = roi.reshape(-1, 3)
    unique_colors, counts = np.unique(pixels, axis=0, return_counts=True)
    dominant = unique_colors[np.argmax(counts)]
    r, g, b = int(dominant[0]), int(dominant[1]), int(dominant[2])

    # Convert to LAB for the extraction pipeline
    rgb_norm = np.array([[[r, g, b]]], dtype=np.float32) / 255.0
    lab = rgb2lab(rgb_norm)[0, 0]  # [L, a, b]

    return {
        "rgb": [r, g, b],
        "lab": [float(lab[0]), float(lab[1]), float(lab[2])],
        "hex": "#{:02x}{:02x}{:02x}".format(r, g, b),
    }


def extract_colors_from_legend_shapes(
    image_rgb: np.ndarray,
    legend_shapes: List[Dict],
    debug: bool = False,
    debug_dir: Optional[str] = None,
) -> List[Tuple[int, int, int]]:
    """
    Returns one RGB color (uint8) per legend shape by sampling pixels
    inside the shape region and computing the median RGB value.

    - erode_px: removes borders to avoid edges, antialiasing, or text
    - sample_max_pixels: subsamples pixels if the region is very large
    """

    if image_rgb.dtype != np.uint8:
        image_rgb = (np.clip(image_rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)

    img_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)

    if debug and debug_dir is not None:
        os.makedirs(debug_dir, exist_ok=True)

    colors: List[Tuple[int, int, int]] = []

    for shape in legend_shapes:
        shape_id = shape.get("id", "unknown")

        # 1) Retrieve contour_points (format used in shapes_extraction.py)
        contour_points = (
            shape.get("geometry", {})
            .get("pixel_coords", {})
            .get("contour_points", None)
        )

        if debug:
            bb = shape.get("bounding_box") or shape.get("geometry", {}).get("pixel_coords", {}).get("bounding_box")
            print(f"Legend shape {shape_id}")
            if bb:
                print(
                    f"  bbox: x={bb.get('x')} y={bb.get('y')} "
                    f"w={bb.get('width')} h={bb.get('height')}"
                )
            if contour_points:
                print(f"  contour_points: {len(contour_points)} points")

        if not contour_points:
            # Fallback: if no contour, use bounding box
            bb = shape.get("bounding_box") or shape.get("geometry", {}).get(
                "pixel_coords", {}
            ).get("bounding_box")
            if not bb:
                continue

            x, y, w, h = int(bb["x"]), int(bb["y"]), int(bb["width"]), int(bb["height"])
            roi = img_bgr[max(0, y) : y + h, max(0, x) : x + w]
            if roi.size == 0:
                continue

            # Median color in BGR → convert to RGB
            med = np.median(roi.reshape(-1, 3), axis=0)
            b, g, r = [int(round(v)) for v in med]
            if debug:
                print(f"  sampled_rgb: ({r}, {g}, {b}) [bbox fallback]")
                if debug_dir is not None:
                    debug_path = os.path.join(debug_dir, f"legend_shape_{shape_id}.png")
                    cv2.imwrite(debug_path, roi)
            colors.append((r, g, b))
            continue

        pts = np.array(contour_points, dtype=np.int32).reshape(-1, 1, 2)  # (N,1,2)

        # 2) Create filled mask of the shape
        mask = np.zeros(img_bgr.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [pts], 255)

        ys, xs = np.where(mask == 255)

        pixels = img_bgr[ys, xs]

        if debug:
            print(f"  pixels_in_shape: {pixels.shape[0]}")

        if pixels.size == 0:
            continue

        # Median color in BGR -> convert to RGB
        med = np.median(pixels.reshape(-1, 3), axis=0)
        b, g, r = [int(round(v)) for v in med]
        if debug:
            print(f"  sampled_rgb: ({r}, {g}, {b})")
            if debug_dir is not None:
                x, y = np.where(mask == 255)
                if x.size > 0 and y.size > 0:
                    min_y, max_y = int(np.min(x)), int(np.max(x))
                    min_x, max_x = int(np.min(y)), int(np.max(y))
                    preview = img_bgr[min_y:max_y + 1, min_x:max_x + 1].copy()
                    preview_mask = mask[min_y:max_y + 1, min_x:max_x + 1]
                    preview[preview_mask == 0] = 0
                    debug_path = os.path.join(debug_dir, f"legend_shape_{shape_id}.png")
                    cv2.imwrite(debug_path, preview)
        colors.append((r, g, b))

    return colors
