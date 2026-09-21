#!/usr/bin/env python
"""Write the georeferencing edge mask of one image to PNG, to eyeball it.

Runs exactly the edge step the alignment uses (`build_edge_map` in
`app/utils/georeferencing/evidence.py`), with the blur and Canny thresholds
overridable from the command line, so settings can be compared before any of
them becomes a default in `GeorefConfig`.

Usage, through the compose service (the image must be under a mounted folder,
e.g. Backend-Atlas/tests/ or Backend-Atlas/debug_runs/):

    docker compose run --rm georef-dev python scripts/edge_mask.py debug_runs/<run>/00_map.png
    docker compose run --rm georef-dev python scripts/edge_mask.py <image> --blur 3 --low 30 --high 90
    docker compose run --rm georef-dev python scripts/edge_mask.py <image> --sweep
    docker compose run --rm georef-dev python scripts/edge_mask.py <image> --ocr   # mask text too (slow once, cached)

Canny keeps a pixel as an edge when its gradient is above --high, or above
--low and connected to one above --high. Lower thresholds = more edges; a
smaller blur keeps thin, faint lines that a larger one smooths away.

Output, in --out (default debug_runs/edges/<image name>/):

    edges_<tag>.png      the mask, white edges on black
    overlay_<tag>.png    the mask in red over the dimmed map
    sweep.png            every preset side by side (--sweep only)
"""

import argparse
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.utils.georeferencing.config import DEFAULT_GEOREF_CONFIG  # noqa: E402
from app.utils.georeferencing.evidence import (  # noqa: E402
    build_edge_map,
    build_text_mask,
)

# (tag, blur, low, high), from strict towards permissive. The current default
# is whatever GeorefConfig says; "both" is the one it was set to.
SWEEP_PRESETS = [
    ("old_default", 5, 75, 175),
    ("less_blur", 3, 75, 175),
    ("lower_thresholds", 5, 40, 120),
    ("both", 3, 40, 120),
    ("very_permissive", 1, 20, 60),
]


def overlay(image_bgr: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Edges in red over a dimmed copy of the map."""
    out = (image_bgr.astype(np.float32) * 0.4).astype(np.uint8)
    out[edges] = (0, 0, 255)
    return out


def label(image: np.ndarray, text: str) -> np.ndarray:
    out = image.copy()
    scale = max(out.shape[1] / 1200.0, 0.6)
    cv2.putText(out, text, (10, int(40 * scale)), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (0, 255, 255), max(int(2 * scale), 1), cv2.LINE_AA)
    return out


def run_one(image_bgr, text_mask, blur, low, high):
    config = DEFAULT_GEOREF_CONFIG.with_overrides(
        edge_blur_ksize=blur, edge_canny_low=low, edge_canny_high=high
    )
    return build_edge_map(image_bgr, text_mask, config)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("image", help="Path to the map image")
    parser.add_argument("--blur", type=int, default=DEFAULT_GEOREF_CONFIG.edge_blur_ksize,
                        help="Gaussian kernel size, odd; 1 = no blur (default %(default)s)")
    parser.add_argument("--low", type=int, default=DEFAULT_GEOREF_CONFIG.edge_canny_low,
                        help="Canny low threshold (default %(default)s)")
    parser.add_argument("--high", type=int, default=DEFAULT_GEOREF_CONFIG.edge_canny_high,
                        help="Canny high threshold (default %(default)s)")
    parser.add_argument("--sweep", action="store_true",
                        help="Run every preset in SWEEP_PRESETS instead of one setting")
    parser.add_argument("--ocr", action="store_true",
                        help="Mask OCR text regions like the pipeline does (~2 min once, then cached)")
    parser.add_argument("--out", default=None,
                        help="Output folder (default debug_runs/edges/<image name>)")
    args = parser.parse_args()

    image_bgr = cv2.imread(args.image)
    if image_bgr is None:
        print(f"Could not read image: {args.image}")
        return 1

    name = os.path.splitext(os.path.basename(args.image))[0]
    out_dir = args.out or os.path.join(_BACKEND_ROOT, "debug_runs", "edges", name)
    os.makedirs(out_dir, exist_ok=True)

    text_mask = None
    if args.ocr:
        # Imported lazily: it pulls in colour extraction and EasyOCR.
        from run_georef_alignment import extract_text_regions_cached

        regions = extract_text_regions_cached(args.image, image_bgr, use_cache=True)
        text_mask = build_text_mask(
            image_bgr.shape[:2], regions, DEFAULT_GEOREF_CONFIG.text_mask_dilation_px
        )
        print(f"ocr: {len(regions)} text regions, {text_mask.mean():.1%} of the image masked")

    settings = (
        SWEEP_PRESETS if args.sweep
        else [(f"b{args.blur}_l{args.low}_h{args.high}", args.blur, args.low, args.high)]
    )

    tiles = []
    for tag, blur, low, high in settings:
        edges = run_one(image_bgr, text_mask, blur, low, high)
        cv2.imwrite(os.path.join(out_dir, f"edges_{tag}.png"), edges.astype(np.uint8) * 255)
        over = overlay(image_bgr, edges)
        cv2.imwrite(os.path.join(out_dir, f"overlay_{tag}.png"), over)
        tiles.append(label(over, f"{tag}  blur={blur} low={low} high={high}"))
        print(f"{tag:<18} blur={blur:<2} low={low:<3} high={high:<3} "
              f"edge pixels {edges.mean():.2%}")

    if args.sweep:
        # Two columns, padded with a blank tile when the count is odd.
        if len(tiles) % 2:
            tiles.append(np.zeros_like(tiles[0]))
        rows = [np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles), 2)]
        cv2.imwrite(os.path.join(out_dir, "sweep.png"), np.vstack(rows))

    print(f"written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
