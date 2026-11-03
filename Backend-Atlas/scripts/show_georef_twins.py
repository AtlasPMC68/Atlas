#!/usr/bin/env python
"""A map's twins side by side, each over the undeformed map, to see what each
deformation does (dev-docs/georeferencing-synthetic.md §3.2):

    docker compose run --rm georef-dev python scripts/show_georef_twins.py --seeds 300,307

Writes ablations/twins/<map id>.png: one row per twin. Left, the twin as drawn
(what the user sees). Right, the same with the undeformed twin's coast and
borders over it in magenta, first moved by the best affine fit of the
displacement, since the control-point affine (``A0``) takes that part out on
its own; arrows from there to where the twin draws each place, at true scale:
what is left for alignment and the piecewise step. The header gives the whole
displacement's RMS and that non-affine part.
"""

import argparse
import math
import os
import sys
from typing import List

import cv2
import numpy as np
import shapely

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.utils.georef_synthetic import DEFORMATIONS, generate_twins  # noqa: E402
from app.utils.georef_synthetic.case import SyntheticMap  # noqa: E402
from app.utils.georef_synthetic.render import stroke  # noqa: E402

OUT_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ablations", "twins")

PANEL_WIDTH = 900
HEADER_PX = 64
ARROWS_ACROSS = 16
MAGENTA = (255, 0, 255)
ARROW = (0, 0, 220)


def _overlay(twin: SyntheticMap, undeformed: SyntheticMap) -> np.ndarray:
    image = twin.image.copy()
    coef = twin.warp.displacement_affine_fit() if twin.warp.displacements else np.zeros((3, 2))
    fitted = lambda q: q + np.column_stack((q, np.ones(len(q)))) @ coef  # noqa: E731
    stroke(image, shapely.transform(undeformed.layers.coastline, fitted), MAGENTA, 2)
    for zone in undeformed.zones:
        stroke(image, shapely.transform(zone.drawn, fitted), MAGENTA, 1)
    if twin.warp.displacements:
        w, h = twin.image_size
        step = w / ARROWS_ACROSS
        xs, ys = np.meshgrid(np.arange(step / 2, w, step), np.arange(step / 2, h, step))
        q = np.column_stack((xs.ravel(), ys.ravel()))
        for a, b in zip(fitted(q), twin.warp.displace(q)):
            cv2.arrowedLine(image, tuple(int(round(v)) for v in a), tuple(int(round(v)) for v in b),
                            ARROW, 2, cv2.LINE_AA, tipLength=0.25)
    return image


def _panel(image: np.ndarray, lines: List[str]) -> np.ndarray:
    scale = PANEL_WIDTH / image.shape[1]
    body = cv2.resize(image, (PANEL_WIDTH, int(round(image.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    header = np.full((HEADER_PX, PANEL_WIDTH, 3), 255, dtype=np.uint8)
    for i, line in enumerate(lines):
        cv2.putText(header, line, (8, 24 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    return np.vstack((header, body, np.full((12, PANEL_WIDTH, 3), 255, dtype=np.uint8)))


def _describe(twin: SyntheticMap) -> List[str]:
    w, h = twin.image_size
    diagonal = math.hypot(w, h)
    q = np.column_stack([v.ravel() for v in np.meshgrid(np.linspace(0, w, 32), np.linspace(0, h, 32))])
    d = twin.warp.displace(q) - q if twin.warp.displacements else np.zeros_like(q)
    rms = float(np.sqrt(np.mean(np.sum(d * d, axis=1))))
    non_affine = twin.warp.non_affine_rms_px()
    kinds = [k for k in twin.warp.families[2:]] or ["no displacement"]
    softened = f", strength {twin.stress['strength']:.2f}" if twin.stress else ""
    return [
        f"{twin.deformation}: {', '.join(kinds)}{softened}",
        f"moved {rms:.0f} px RMS, {non_affine:.0f} px non-affine ({non_affine / diagonal:.1%} of diagonal, "
        f"{non_affine * twin.km_per_pixel:.0f} km)",
    ]


def sheet(seed: int) -> np.ndarray:
    twins = generate_twins(seed)
    undeformed = twins["none"]
    w, h = undeformed.image_size
    rows = []
    for name in DEFORMATIONS:
        twin = twins[name]
        left = _panel(twin.image, _describe(twin))
        if name == "none":
            right = _panel(_overlay(twin, undeformed), [
                f"{twin.map_id}  {w}x{h} px  {twin.km_per_pixel:.2f} km/px",
                "magenta: the undeformed coast and borders, overlaid on every row",
            ])
        else:
            right = _panel(_overlay(twin, undeformed), [
                "over the undeformed map moved by the best affine (magenta)",
                "arrows: what no affine takes out, true scale",
            ])
        rows.append(np.hstack((left, np.full((left.shape[0], 12, 3), 255, dtype=np.uint8), right)))
    return np.vstack(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeds", required=True, help="map seeds, comma-separated")
    parser.add_argument("--out", default=OUT_ROOT, help="output folder")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for seed in (int(s) for s in args.seeds.split(",") if s.strip()):
        path = os.path.join(args.out, f"m{seed:05d}.png")
        cv2.imwrite(path, sheet(seed))
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
