#!/usr/bin/env python
"""How much of a map's bend could a coastline fit take out? An upper bound
for step 4 (dev-docs/georeferencing-synthetic.md §10.4), on the generator's
truth: nothing here runs the pipeline.

    docker compose run --rm -T georef-dev python scripts/georef_coast_ceiling.py \
        --maps 50 --seed 300 --workers 7 --out coast-ceiling-2026-10-28

Every method starts from the run's control-point affine (``A0``, the
pipeline's baseline) and adds a smooth correction in pixels, ``c(p)``: the
model is ``A0(p + c(p))``. ``c`` is an affine part plus Gaussians on a grid of
knots, fitted by ridge least squares to the correction each observation
needs, ``u = A0^-1(X) - p`` for a pixel ``p`` the map draws at Web Mercator
``X``:

    gcp                the control points, as clicked (the piecewise step's ceiling)
    coast              the true correction at points along the drawn coast:
                       perfect correspondences, the bound
    coast-normal       only its component across the coast, what a curve
                       matcher can see (the coast slides along itself freely)
    coast-normal+gcp   that, and the control points
    affine-oracle      the best affine of the true correction over the dense
                       points: perfect alignment, as alignment is now
    smooth-oracle      the knots fitted to the true correction over the dense
                       points: what the basis itself can express

The fit is the coast bend's (app/utils/georeferencing/bend.py).
Each method is tried at every knot spacing, ridge and weight (``CONFIGS``);
the summary gives the best per map (an oracle) and the best single setting.
Scored as the runs score: ``denseMeanPx`` on the map's 20,000 dense samples,
split by distance from the drawn coast.

Writes ablations/<out>/results.csv (one row per map, twin, method and
setting) and summary.md.
"""

import os

# One BLAS thread per worker, set before numpy loads: with several workers,
# OpenBLAS's own threads fight over the cores, and a 118 x 118 solve took
# 0.3 s instead of well under a millisecond (2026-10-30).
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import csv
import math
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import shapely
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.utils.georef_synthetic import DEFORMATIONS, Rejected, generate_case, generate_twins  # noqa: E402
from app.utils.georef_synthetic.case import SyntheticMap  # noqa: E402
from app.utils.georef_synthetic.metrics import DenseSamples, dense_samples  # noqa: E402
from app.utils.georeferencing.affine import fit_affine_from_control_points  # noqa: E402
from app.utils.georeferencing.bend import (  # noqa: E402
    BendBasis as Basis,
    across_observations as across,
    full_observations as full,
    solve_bend as solve,
)
from app.utils.georeferencing.projection import lonlat_arrays_to_webmercator  # noqa: E402
from app.utils.georeferencing.reference import COASTLINE_FILE, load_reference_linework  # noqa: E402

ABLATIONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ablations")

KNOTS_ACROSS = (6, 12, 24)
RIDGE = (1e-4, 1e-3, 1e-2, 1e-1)
#: The coast's share of the weight when the control points are fitted too.
COAST_SHARE = (0.5, 0.9, 0.99)
COAST_POINTS = 4000
#: Points per pixel of drawn coast before resampling to COAST_POINTS.
COAST_STEP_PX = 2.0
ORACLE_POINTS = 4000
#: Distance from the drawn coast, as a share of the diagonal: the bins' edges.
COAST_BINS = (0.02, 0.05, 0.10)

METHODS = ("A0", "affine-oracle", "smooth-oracle", "gcp", "coast", "coast-normal", "coast-normal+gcp")


# --- observations ------------------------------------------------------------


class Baseline:
    """The run's control-point affine, pixel -> EPSG:3857, and its inverse."""

    def __init__(self, matrix: np.ndarray):
        self.matrix = matrix
        self.inverse_matrix = np.linalg.inv(matrix)

    def forward(self, p: np.ndarray) -> np.ndarray:
        return p @ self.matrix[:2, :2].T + self.matrix[:2, 2]

    def correction(self, p: np.ndarray, x: np.ndarray) -> np.ndarray:
        """``u = A0^-1(X) - p``: what ``c`` must add at p."""
        return x @ self.inverse_matrix[:2, :2].T + self.inverse_matrix[:2, 2] - p


def coast_points(synthetic: SyntheticMap, count: int = COAST_POINTS) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Points evenly along the coast as the map draws it, inside the image:
    (pixels, Web Mercator, unit normals in pixels). Empty for a map with no
    coast."""
    w, h = synthetic.image_size
    west, south, east, north = synthetic.visible.bounds
    coast = shapely.clip_by_rect(load_reference_linework(COASTLINE_FILE), west - 1, south - 1, east + 1, north + 1)
    step_deg = COAST_STEP_PX * synthetic.km_per_pixel / 111.32
    lines = []
    for line in shapely.get_parts(shapely.segmentize(coast, step_deg)):
        if line.geom_type != "LineString" or line.is_empty:
            continue
        lonlat = np.asarray(line.coords)
        p = synthetic.warp.forward_xy(lonlat)
        inside = (p[:, 0] >= 0) & (p[:, 0] <= w) & (p[:, 1] >= 0) & (p[:, 1] <= h)
        # Each run of points inside the image is a line of its own.
        for run in np.split(np.arange(len(p)), np.flatnonzero(np.diff(inside.astype(int))) + 1):
            if inside[run[0]] and len(run) >= 2:
                lines.append(lonlat[run])
    if not lines:
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros((0, 2))

    drawn = [synthetic.warp.forward_xy(ll) for ll in lines]
    arcs = [np.concatenate(([0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T)))) for p in drawn]
    total = sum(a[-1] for a in arcs)
    spacing = total / count
    lonlat_out = []
    for ll, arc in zip(lines, arcs):
        at = np.arange(spacing / 2, arc[-1], spacing)
        if len(at) >= 2:
            lonlat_out.append(np.column_stack((np.interp(at, arc, ll[:, 0]), np.interp(at, arc, ll[:, 1]))))
    if not lonlat_out:
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros((0, 2))

    pixels, normals = [], []
    for ll in lonlat_out:
        p = synthetic.warp.forward_xy(ll)
        tangent = np.gradient(p, axis=0)
        normal = np.column_stack((-tangent[:, 1], tangent[:, 0]))
        normals.append(normal / np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-9))
        pixels.append(p)
    lonlat = np.vstack(lonlat_out)
    x = np.column_stack(lonlat_arrays_to_webmercator(lonlat[:, 0], lonlat[:, 1]))
    return np.vstack(pixels), x, np.vstack(normals)


# --- scoring -----------------------------------------------------------------


def score(
    synthetic: SyntheticMap,
    samples: DenseSamples,
    baseline: Baseline,
    correction: np.ndarray,
    coast_distance: np.ndarray,
) -> Dict[str, Optional[float]]:
    """``denseMeanPx`` of ``A0(p + c(p))``, and by distance from the coast."""
    p = np.column_stack((samples.px, samples.py))
    x = baseline.forward(p + correction)
    km = np.hypot(x[:, 0] - samples.x_3857, x[:, 1] - samples.y_3857) * np.cos(np.radians(samples.lat)) / 1000.0
    px = km / synthetic.km_per_pixel
    out: Dict[str, Optional[float]] = {
        "meanPx": round(float(px.mean()), 3),
        "coastalMeanPx": round(float(px[samples.coastal].mean()), 3) if samples.coastal.any() else None,
    }
    edges = (0.0, *COAST_BINS, math.inf)
    for lo, hi in zip(edges[:-1], edges[1:]):
        inside = (coast_distance >= lo) & (coast_distance < hi)
        out[_bin_name(lo, hi)] = round(float(px[inside].mean()), 3) if inside.any() else None
    return out


def _bin_name(lo: float, hi: float) -> str:
    return f"coast{lo:.0%}-{hi:.0%}Px" if math.isfinite(hi) else f"coast{lo:.0%}+Px"


BIN_COLUMNS = [_bin_name(lo, hi) for lo, hi in zip((0.0, *COAST_BINS), (*COAST_BINS, math.inf))]


# --- one map ---------------------------------------------------------------------


def _twin_rows(synthetic: SyntheticMap) -> List[Dict[str, Any]]:
    try:
        case = generate_case(synthetic, 0)
    except Rejected:
        return []
    control_points = case.layout.control_points()
    baseline = Baseline(fit_affine_from_control_points(control_points).matrix)
    samples = dense_samples(synthetic)
    dense_p = np.column_stack((samples.px, samples.py))
    dense_x = np.column_stack((samples.x_3857, samples.y_3857))
    dense_u = baseline.correction(dense_p, dense_x)
    oracle = np.random.default_rng(synthetic.seed).choice(len(dense_p), min(ORACLE_POINTS, len(dense_p)), replace=False)

    gcp_p = np.array([cp.pixel for cp in control_points], dtype=float)
    gcp_x = np.column_stack(lonlat_arrays_to_webmercator(*np.array([cp.geo for cp in control_points]).T))
    gcp_u = baseline.correction(gcp_p, gcp_x)
    coast_p, coast_x, coast_n = coast_points(synthetic)
    coast_u = baseline.correction(coast_p, coast_x)

    diagonal = math.hypot(*synthetic.image_size)
    if len(coast_p):
        coast_distance = cKDTree(coast_p).query(dense_p)[0] / diagonal
    else:
        coast_distance = np.full(len(dense_p), math.inf)

    common = {
        "seed": synthetic.seed,
        "twin": synthetic.deformation,
        "nonAffineRmsPx": round(synthetic.warp.non_affine_rms_px(), 3),
        "kmPerPixel": round(synthetic.km_per_pixel, 4),
        "longSide": max(synthetic.image_size),
        "controlPoints": len(control_points),
        "coastPoints": len(coast_p),
    }
    rows = []

    def add(method: str, correction: np.ndarray, **setting: Any) -> None:
        rows.append({**common, "method": method, "knots": None, "ridge": None, "coastShare": None, **setting,
                     **score(synthetic, samples, baseline, correction, coast_distance)})

    add("A0", np.zeros_like(dense_p))
    affine = Basis(synthetic.image_size, 0)
    coef = solve(affine, [(1.0, full(affine(dense_p[oracle]), dense_u[oracle]))], 0.0)
    add("affine-oracle", affine(dense_p) @ coef)

    for knots in KNOTS_ACROSS:
        basis = Basis(synthetic.image_size, knots)
        phi_dense = basis(dense_p)
        add("smooth-oracle", phi_dense @ solve(basis, [(1.0, full(phi_dense[oracle], dense_u[oracle]))], 1e-6), knots=knots)
        gcp = full(basis(gcp_p), gcp_u)
        coast = coast_normal = None
        if len(coast_p):
            phi_coast = basis(coast_p)
            coast, coast_normal = full(phi_coast, coast_u), across(phi_coast, coast_u, coast_n)
        for ridge in RIDGE:
            setting = dict(knots=knots, ridge=ridge)
            add("gcp", phi_dense @ solve(basis, [(1.0, gcp)], ridge), **setting)
            if coast is None:
                continue
            add("coast", phi_dense @ solve(basis, [(1.0, coast)], ridge), **setting)
            add("coast-normal", phi_dense @ solve(basis, [(1.0, coast_normal)], ridge), **setting)
            for share in COAST_SHARE:
                parts = [(share, coast_normal), (1.0 - share, gcp)]
                add("coast-normal+gcp", phi_dense @ solve(basis, parts, ridge), coastShare=share, **setting)
    return rows


def process_seed(seed: int, deformations: Sequence[str]) -> List[Dict[str, Any]]:
    twins = generate_twins(seed, deformations=tuple(deformations))
    return [row for twin in twins.values() for row in _twin_rows(twin)]


# --- summary ---------------------------------------------------------------------


def _median(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _fmt(v: Optional[float], digits: int = 1) -> str:
    return "–" if v is None else f"{v:.{digits}f}"


def _setting(row: Dict[str, Any]) -> Tuple:
    return (row["knots"], row["ridge"], row["coastShare"])


def best_rows(rows: List[Dict[str, Any]]) -> Dict[Tuple[int, str, str], Dict[str, Any]]:
    """Per map, twin and method: the setting that scored best (the oracle)."""
    out: Dict[Tuple[int, str, str], Dict[str, Any]] = {}
    for r in rows:
        key = (r["seed"], r["twin"], r["method"])
        if key not in out or r["meanPx"] < out[key]["meanPx"]:
            out[key] = r
    return out


def fixed_rows(rows: List[Dict[str, Any]], twin: str) -> Dict[str, Tuple[Tuple, Dict[Tuple[int, str], Dict[str, Any]]]]:
    """Per method: the one setting with the lowest median over *twin*'s maps,
    and its rows."""
    out = {}
    for method in METHODS:
        by_setting: Dict[Tuple, Dict[Tuple[int, str], Dict[str, Any]]] = {}
        for r in rows:
            if r["method"] == method and r["twin"] == twin:
                by_setting.setdefault(_setting(r), {})[(r["seed"], r["twin"])] = r
        if by_setting:
            setting = min(by_setting, key=lambda s: _median(r["meanPx"] for r in by_setting[s].values()))
            out[method] = (setting, by_setting[setting])
    return out


def summary(rows: List[Dict[str, Any]], args: argparse.Namespace) -> str:
    best = best_rows(rows)
    twins = [t for t in DEFORMATIONS if any(r["twin"] == t for r in rows)]
    lines = [
        f"# Coast-fit ceiling {args.out}",
        "",
        f"Seeds {args.seed}–{args.seed + args.maps - 1}, layout 0, twins {', '.join(twins)}. "
        f"denseMeanPx, median over maps; each method at its best setting per map, then (in brackets) "
        f"at the one setting best over the twin's maps. Methods: see the script's docstring.",
        "",
        "## Per twin",
        "",
        "| Method | " + " | ".join(twins) + " |",
        "|---|" + "---|" * len(twins),
    ]
    fixed = {t: fixed_rows(rows, t) for t in twins}
    for method in METHODS:
        cells = []
        for t in twins:
            per_map = [b["meanPx"] for (s, tw, m), b in best.items() if tw == t and m == method]
            f = fixed[t].get(method)
            fixed_median = _median(r["meanPx"] for r in f[1].values()) if f else None
            cells.append(f"{_fmt(_median(per_map))} ({_fmt(fixed_median)})")
        lines.append(f"| {method} | " + " | ".join(cells) + " |")
    lines += ["", "Best single setting (knots, ridge, coast share):", ""]
    for t in twins:
        settings = ", ".join(f"{m} {s}" for m, (s, _) in fixed[t].items() if s != (None, None, None))
        lines.append(f"- {t}: {settings}")

    for t in twins:
        lines += ["", f"## {t}: share of A0's error taken out, median over maps (best setting per map)", ""]
        lines.append("| Method | All | Coastal (< 50 km) | " + " | ".join(BIN_COLUMNS) + " |")
        lines.append("|---|---|---|" + "---|" * len(BIN_COLUMNS))
        a0 = {s: b for (s, tw, m), b in best.items() if tw == t and m == "A0"}
        for method in METHODS[1:]:
            mine = {s: b for (s, tw, m), b in best.items() if tw == t and m == method}
            cells = []
            for col in ["meanPx", "coastalMeanPx", *BIN_COLUMNS]:
                cut = [1 - mine[s][col] / a0[s][col] for s in mine if mine[s][col] is not None and a0[s][col]]
                cells.append(f"{_median(cut):.0%} · {len(cut)}" if cut else "–")
            lines.append(f"| {method} | " + " | ".join(cells) + " |")
        lines += ["", "A0's own error, px, median: " + ", ".join(
            f"{col} {_fmt(_median(a0[s][col] for s in a0))}" for col in ["meanPx", "coastalMeanPx", *BIN_COLUMNS])]

        lines += ["", f"By control points ({t}): median px, best setting per map", ""]
        lines.append("| Control points | Maps | " + " | ".join(METHODS) + " |")
        lines.append("|---|---|" + "---|" * len(METHODS))
        for lo, hi in [(3, 3), (4, 7), (8, 10), (11, 99)]:
            seeds = [s for s, b in a0.items() if lo <= b["controlPoints"] <= hi]
            if not seeds:
                continue
            cells = [_fmt(_median(best[(s, t, m)]["meanPx"] for s in seeds if (s, t, m) in best)) for m in METHODS]
            lines.append(f"| {lo}–{hi if hi < 99 else '+'} | {len(seeds)} | " + " | ".join(cells) + " |")
        no_coast = sum(1 for b in a0.values() if b["coastPoints"] == 0)
        lines += ["", f"{no_coast} of {len(a0)} maps show no coast (coast methods missing there)."]
    return "\n".join(lines) + "\n"


# --- main ------------------------------------------------------------------------


COLUMNS = ["seed", "twin", "method", "knots", "ridge", "coastShare", "meanPx", "coastalMeanPx", *BIN_COLUMNS,
           "nonAffineRmsPx", "kmPerPixel", "longSide", "controlPoints", "coastPoints"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--maps", type=int, default=50)
    parser.add_argument("--seed", type=int, default=300)
    parser.add_argument("--deformation", default=",".join(DEFORMATIONS), help="twins, comma-separated")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", required=True, help="folder under ablations/")
    args = parser.parse_args()
    deformations = [d for d in args.deformation.split(",") if d]
    out_dir = os.path.join(ABLATIONS, args.out)
    os.makedirs(out_dir, exist_ok=True)

    seeds = range(args.seed, args.seed + args.maps)
    rows: List[Dict[str, Any]] = []
    # Written as each map finishes, so a run that dies keeps what it did.
    with open(os.path.join(out_dir, "results.csv"), "w", newline="", encoding="utf-8") as f, \
            ProcessPoolExecutor(max_workers=args.workers) as pool:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        futures = {pool.submit(process_seed, s, deformations): s for s in seeds}
        for done, future in enumerate(as_completed(futures), 1):
            mine = future.result()
            writer.writerows(mine)
            f.flush()
            rows.extend(mine)
            print(f"m{futures[future]:05d}  {done}/{len(seeds)}", flush=True)

    text = summary(rows, args)
    with open(os.path.join(out_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
