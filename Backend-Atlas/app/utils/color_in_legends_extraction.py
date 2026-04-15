import os
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np

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