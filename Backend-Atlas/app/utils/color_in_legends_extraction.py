from typing import Dict, List, Tuple, Optional
import cv2
import numpy as np

def extract_colors_from_legend_shapes(
    image_rgb: np.ndarray,
    legends_shapes: List[Dict],
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
    if img_bgr is None:
        raise ValueError("Image not found")

    colors: List[Tuple[int, int, int]] = []

    for shape in legends_shapes:
        # 1) Retrieve contour_points (format used in shapes_extraction.py)
        contour_points = (
            shape.get("geometry", {})
                 .get("pixel_coords", {})
                 .get("contour_points", None)
        )

        if not contour_points:
            # Fallback: if no contour, use bounding box
            bb = shape.get("bounding_box") or shape.get("geometry", {}).get("pixel_coords", {}).get("bounding_box")
            if not bb:
                continue

            x, y, w, h = int(bb["x"]), int(bb["y"]), int(bb["width"]), int(bb["height"])
            roi = img_bgr[max(0, y):y+h, max(0, x):x+w]
            if roi.size == 0:
                continue

            # Median color in BGR → convert to RGB
            med = np.median(roi.reshape(-1, 3), axis=0)
            b, g, r = [int(round(v)) for v in med]
            colors.append((r, g, b))
            continue

        pts = np.array(contour_points, dtype=np.int32).reshape(-1, 1, 2)  # (N,1,2)

        # 2) Create filled mask of the shape
        mask = np.zeros(img_bgr.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [pts], 255)

        ys, xs = np.where(mask == 255)

        pixels = img_bgr[ys, xs]

        if pixels.size == 0:
            continue

        # Most frequent color (mode)
        unique_colors, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)
        most_frequent_idx = np.argmax(counts)
        most_frequent_bgr = unique_colors[most_frequent_idx]
        b, g, r = most_frequent_bgr
        colors.append((r, g, b))
    
    return colors