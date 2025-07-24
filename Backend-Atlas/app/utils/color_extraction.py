from PIL import Image
import os
from matplotlib import colors as mcolors
import math
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "extracted_color")

def extract_colors(image_path: str, output_dir: str = DEFAULT_OUTPUT_DIR, nb_colors: int = 6):
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

    masks = {}
    pixels = list(quantized.getdata())

    for color_index, rgb in enumerate(palette_rgb[:quantized.getcolors().__len__()]):
        mask = Image.new("1", (width, height))  # 1-bit image (black/white)
        mask_pixels = mask.load()

        for y in range(height):
            for x in range(width):
                if quantized.getpixel((x, y)) == color_index:
                    mask_pixels[x, y] = 1  # white
                else:
                    mask_pixels[x, y] = 0  # black

        color_name = get_nearest_color_name(rgb)
        mask_path = os.path.join(image_output_dir, f"{color_name}.png")
        mask.save(mask_path)

        masks[color_name] = mask_path

    print(f"[EXTRACT] {len(masks)} couleurs extraites depuis {image_path}")
    return {
        "colors_detected": list(masks.keys()),
        "masks": masks
    }

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
