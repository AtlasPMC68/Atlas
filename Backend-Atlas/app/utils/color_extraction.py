from PIL import Image
import os
from matplotlib import colors as mcolors
import math
from collections import defaultdict
from typing import Dict, Any
import json

import numpy as np
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
            normalized_features.append(normalized_feature)

    normalized_geojson = {
        "type": "FeatureCollection",
        "features": normalized_features,
    }

    print(f"[EXTRACT] {len(masks)} couleurs extraites depuis {image_path}")
    return {
        "colors_detected": list(masks.keys()),
        "masks": masks,
        "normalized_geojson": normalized_geojson,
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
        },
        "geometry": normalized_geom.__geo_interface__,
    }

    normalized_color_geojson_path = os.path.join(
        image_output_dir, f"{color_name}_normalized.geojson"
    )
    # NOTE: In a future iteration, this on-disk GeoJSON export will be
    # replaced by persisting the normalized geometry to the database
    # (one feature/FeatureCollection per color) via an API or direct call.
    with open(normalized_color_geojson_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "type": "FeatureCollection",
                "features": [normalized_feature],
            },
            f,
        )

    return normalized_feature

def get_nearest_color_name(rgb_tuple):
    min_distance = float('inf')
    closest_name = None

    for name, hex_value in mcolors.CSS4_COLORS.items():
        r_c, g_c, b_c = mcolors.to_rgb(hex_value)
        r_c, g_c, b_c = [int(x * 255) for x in (r_c, g_c, b_c)]

        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(rgb_tuple, (r_c, g_c, b_c))))
        if distance < min_distance:
            min_distance = distance
            closest_name = name

    return closest_name
