import os
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import imageio.v3 as iio

from skimage.color import rgb2lab, lab2rgb, deltaE_ciede2000
from skimage.morphology import binary_opening, disk
from skimage.util import img_as_float
from matplotlib import colors as mcolors
import math
from collections import defaultdict
from typing import Dict, Any
import json


from shapely.geometry import box
from shapely.ops import unary_union
from shapely.geometry.base import BaseGeometry
from shapely import affinity

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "extracted_color")


def extract_colors(image_path: str, output_dir: str = DEFAULT_OUTPUT_DIR, nb_colors: int = 6) -> Dict[str, Any]:
    # Load the image and convert to standard RGB format
    image = Image.open(image_path).convert("RGB")

    # Reduce the number of colors to extract dominant zones ***Needs test***
    quantized = image.quantize(colors=nb_colors, method=2)

    # Extract the color palette from the quantized image
    palette = quantized.getpalette()
    palette_rgb = [tuple(palette[i:i+3]) for i in range(0, len(palette), 3)]

    width, height = image.size

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    image_output_dir = os.path.join(output_dir, base_name)
    os.makedirs(image_output_dir, exist_ok=True)

    masks: Dict[str, str] = {}
    # Normalized geometries (each shape scaled into a 0-1 box)
    normalized_features = []

    for color_index, rgb in enumerate(palette_rgb[:quantized.getcolors().__len__()]):
        mask = Image.new("1", (width, height))  # 1-bit image (black/white)
        mask_pixels = mask.load()

        pixel_polygons = []

        for y in range(height):
            for x in range(width):
                if quantized.getpixel((x, y)) == color_index:
                    mask_pixels[x, y] = 1  # white
                    # In simple CRS, treat each pixel as a 1x1 square at (x, y)
                    #TODO: optmize because could be very slow for large images
                    pixel_polygons.append(box(x, y, x + 1, y + 1))
                else:
                    mask_pixels[x, y] = 0  # black

        color_name = get_nearest_color_name(rgb)
        mask_path = os.path.join(image_output_dir, f"{color_name}.png")
        mask.save(mask_path)

        masks[color_name] = mask_path

        # Build a vector geometry (possibly MultiPolygon) for this color in pixel space
        if pixel_polygons:
            normalized_feature = build_normalized_feature(
                color_name, rgb, pixel_polygons, image_output_dir
            )
            normalized_features.append({
                "type": "FeatureCollection",
                "features": [normalized_feature]
            })


    print(f"[EXTRACT] {len(masks)} couleurs extraites depuis {image_path}")
    return {
        "colors_detected": list(masks.keys()),
        "masks": masks,
        "normalized_features": normalized_features,
    }

def build_normalized_feature(
    color_name: str,
    rgb: tuple,
    pixel_polygons,
    image_output_dir: str,
):
    """From pixel-space polygons, build a normalized GeoJSON feature and write it to disk.

    - Merges all pixel polygons into a single geometry (possibly MultiPolygon).
    - Scales it uniformly so the largest dimension becomes 1.
    - Recenters it into the [0, 1] x [0, 1] box.
    - Returns the normalized GeoJSON feature dict.
    """

    merged: BaseGeometry = unary_union(pixel_polygons)

    # Preserve original aspect ratio while normalizing into a unit box
    minx, miny, maxx, maxy = merged.bounds
    width_px = maxx - minx
    height_px = maxy - miny

    max_dim = max(width_px, height_px)
    scale = 1.0 / max_dim if max_dim != 0 else 1.0

    translated = affinity.translate(merged, xoff=-minx, yoff=-miny)

    scaled = affinity.scale(
        translated,
        xfact=scale,
        yfact=scale,
        origin=(0.0, 0.0),
    )

    width_norm = width_px * scale
    height_norm = height_px * scale
    offset_x = (1.0 - width_norm) / 2.0
    offset_y = (1.0 - height_norm) / 2.0

    normalized_geom = affinity.translate(
        scaled,
        xoff=offset_x,
        yoff=offset_y,
    )

    normalized_feature = {
        "type": "Feature",
        "properties": {
            "color_name": color_name,
            "color_rgb": rgb,
            # Hex string for direct styling usage on the frontend
            "color_hex": "#{:02x}{:02x}{:02x}".format(*rgb),
            "mapElementType": "zone",
            "name": f"Zone {color_name}",
            "start_date": "1700-01-01",
            "end_date": "2026-01-01",
            "is_normalized": True,
        },
        "geometry": normalized_geom.__geo_interface__,
    }

    normalized_color_geojson_path = os.path.join(
        image_output_dir, f"{color_name}_normalized.geojson"
    )

    return normalized_feature

def get_nearest_color_name(rgb_tuple):
    min_distance = float('inf')
    closest_name = None

    for name, hex_value in mcolors.CSS4_COLORS.items():
        r_c, g_c, b_c = mcolors.to_rgb(hex_value)
        r_c, g_c, b_c = [int(x * 255) for x in (r_c, g_c, b_c)]
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
