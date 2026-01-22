from PIL import Image
import os
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
    pixel_features = []

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
            pixel_feature, normalized_feature = build_features(
                color_name, rgb, pixel_polygons, width, height
            )
            pixel_features.append({
                "type": "FeatureCollection",
                "features": [pixel_feature]
            })
            normalized_features.append({
                "type": "FeatureCollection",
                "features": [normalized_feature]
            })


    print(f"[EXTRACT] {len(masks)} couleurs extraites depuis {image_path}")
    return {
        "colors_detected": list(masks.keys()),
        "masks": masks,
        "normalized_features": normalized_features,
        "pixel_features": pixel_features,
    }

def build_features(
    color_name: str,
    rgb: tuple,
    pixel_polygons,
    image_width: int,
    image_height: int,
):
    merged: BaseGeometry = unary_union(pixel_polygons)

    pixel_feature = {
        "type": "Feature",
        "properties": {
            "color_name": color_name,
            "color_rgb": rgb,
            "color_hex": "#{:02x}{:02x}{:02x}".format(*rgb),
            "mapElementType": "zone",
            "name": f"Zone {color_name}",
            "is_pixel_space": True,
            "image_width": image_width,
            "image_height": image_height,
            "start_date": "1700-01-01",
            "end_date": "2026-01-01",
        },
        "geometry": merged.__geo_interface__,
    }

    # Keep your normalized feature if you want, but DON'T use it for georeferencing
    normalized_feature = build_normalized_feature_from_merged(color_name, rgb, merged)

    return pixel_feature, normalized_feature

def build_normalized_feature_from_merged(
    color_name: str,
    rgb: tuple,
    merged,
):
    """From pixel-space polygons, build a normalized GeoJSON feature and write it to disk.

    - Merges all pixel polygons into a single geometry (possibly MultiPolygon).
    - Scales it uniformly so the largest dimension becomes 1.
    - Recenters it into the [0, 1] x [0, 1] box.
    - Returns the normalized GeoJSON feature dict.
    """
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
