from typing import Dict, List, Tuple, Optional
import cv2
import numpy as np

def extract_colors_from_legend_shapes(
    image_path: str,
    legends_shapes: List[Dict],
    *,
    erode_px: int = 2,
    sample_max_pixels: int = 50_000,
) -> List[Tuple[int, int, int]]:
    """
    Returns one RGB color (uint8) per legend shape by sampling pixels
    inside the shape region and computing the median RGB value.

    - erode_px: removes borders to avoid edges, antialiasing, or text
    - sample_max_pixels: subsamples pixels if the region is very large
    """
    img_bgr = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError(f"Image not found: {image_path}")

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

        # 3) Erode mask to remove borders (avoid edges/text)
        if erode_px > 0:
            k = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (2 * erode_px + 1, 2 * erode_px + 1)
            )
            mask = cv2.erode(mask, k, iterations=1)

        ys, xs = np.where(mask == 255)
        if len(xs) == 0:
            continue

        # 4) Subsample if too many pixels
        if len(xs) > sample_max_pixels:
            idx = np.random.choice(len(xs), size=sample_max_pixels, replace=False)
            xs, ys = xs[idx], ys[idx]

        pixels = img_bgr[ys, xs]  # (M,3) in BGR

        # 5) Filter near-black AND near-white pixels
        min_rgb = np.min(pixels, axis=1)
        max_rgb = np.max(pixels, axis=1)

        is_black = max_rgb < 15
        is_white = min_rgb > 240

        keep = ~(is_black | is_white)

        pixels = pixels[keep] if np.any(keep) else pixels

        # Median color → robust to noise
        med = np.median(pixels.astype(np.float32), axis=0)
        b, g, r = [int(round(v)) for v in med]
        colors.append((r, g, b)) 
    
    print(f"Colors extracted: {colors}")
    return colors