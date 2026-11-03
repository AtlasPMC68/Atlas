#!/usr/bin/env python
"""Q5 of the quality estimator (dev-docs/georeferencing-synthetic.md §4.3):
does one more click where it predicts the largest error help more than one
anywhere else?

    python scripts/run_georef_add_point.py --seed 700 --maps 50 --layouts 2 \\
        --deformation none,field,local,stress --workers 4 \\
        --model ablations/georef-quality-q4-2026-11-01/model.json \\
        --out ablations/synthetic-addpoint-v11-2026-11-01

Each case is placed by production as the user's layout has it, then again
with one more control point, clicked as carefully as the layout's (the same
noise draw for every strategy) on a candidate the user could click: a SIFT
suggestion or a gazetteer city the map shows, not already a control or check
point, apart from the clicked points, near the zones. Cities are the
``CITY_CANDIDATES`` largest in the frame: a user asked for one more point
clicks a town they can find, not one of the gazetteer's thousands of
villages. Which one:

- ``estimator``: the largest predicted error (the point model's median);
- ``random``: uniform among the candidates;
- ``farthest``: the farthest from every control point, no estimator;
- ``oracle``: the largest true error under the first placement, the ceiling
  of choosing by error.

Writes ``results.csv`` (one row per case and strategy) and ``summary.md``.
The gain is the relative drop in dense mean error, ``1 - after / before``,
and the change of snapped IoU.

**Guarded rerun** (``guard_`` columns, ``GUARDS``): what the run could read,
blind, to keep the placement with the new click or the one without it. The
predicted IoU (``errors.predictedQuality``) and the coast fit
(``snapMisfitPx``) before and after, and how far the new placement moves the
map from the old one, in the old affine's pixels: at the new click, at the
old control points, and at ``ZONE_SAMPLES`` pixels of the zones farther than
``NEARBY_RATIO`` of the diagonal from the click. The summary scores each
guard as a policy, and only where the predicted IoU says to ask
(``ASK_BELOW``).

**Local correction** (``local_`` columns, ``LOCALS``): instead of placing the
map again, the old placement corrected. ``bNN``: a Gaussian bump at the new
click (``InlandCorrectionModel``) pulling it to where it was clicked, fading
out over NN% of the diagonal, widened until it does not fold the map; ``hNN``
also stays at zero on the old control points. ``warm``: the old applied model
bent to the coast again (``bend_to_coast``) with the new click among the
control points, so the bend's search starts where the old one ended; the old
placement where the bend refuses.

``--asked-only`` places again only where the first placement's predicted IoU
is below ``ASK_BELOW``; ``--strategies`` picks a subset (``estimator`` is
always kept: the summary's tables read it).
"""

import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import csv
import math
import sys
import time
import traceback
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Sequence, Tuple

import numpy as np
import shapely

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
for _path in (_BACKEND_ROOT, _SCRIPT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.utils.georef_synthetic import Rejected, generate_case, generate_twins  # noqa: E402
from app.utils.georef_synthetic.metrics import dense_samples  # noqa: E402
from app.utils.georef_synthetic.run import measure, place_case, run_columns  # noqa: E402
from app.utils.georef_synthetic.user import (  # noqa: E402
    CHECK_ZONE_MARGIN_RATIO,
    MIN_POINT_SEPARATION_RATIO,
    SOURCE_CITY,
    SOURCE_SIFT,
    extra_click,
)
from app.utils.georeferencing import (  # noqa: E402
    DEFAULT_GEOREF_CONFIG,
    RunRecord,
    georeference_features,
    record_signals,
)
from app.utils.georeferencing.bend import CHECK_GRID, InlandCorrectionModel, bend_to_coast  # noqa: E402
from app.utils.georeferencing.post_align import coast_misfit_px  # noqa: E402
from app.utils.georeferencing.projection import lonlat_arrays_to_webmercator, lonlat_to_webmercator  # noqa: E402
from app.utils.georeferencing.quality import (  # noqa: E402
    NEARBY_RATIO,
    ZONE_SAMPLES,
    coast_evidence,
    point_features,
    zone_sample_pixels,
    zone_sizes,
)
from fit_georef_quality import Estimator  # noqa: E402
from georef_variants import BY_NAME  # noqa: E402

STRATEGIES = ("estimator", "random", "farthest", "oracle")
#: The stream of the random pick and the click's noise, apart from the layout's.
_STREAM = 5
#: Cities a user could add: the largest in the frame.
CITY_CANDIDATES = 40
METRICS = ("denseMeanKm", "denseMedianKm", "denseP90Km", "snappedMeanIou")
#: Where the predicted IoU says to ask for a click (§10.13).
ASK_BELOW = 0.80
#: An IoU change that counts as helping or hurting.
IOU_MATTERS = 0.01


def _ge(a: Any, b: Any, slack: float = 0.0) -> bool:
    """a ≥ b − slack, True where either is unknown: a guard that cannot read
    keeps the new click."""
    return a is None or b is None or a >= b - slack


#: Keep the placement with the new click when (the row's ``guard_`` columns):
GUARDS = {
    "plain rerun": lambda r: True,
    "predicted IoU not lower": lambda r: _ge(r["guard_predIouAfter"], r["guard_predIouBefore"]),
    "predicted IoU not lower by 0.02": lambda r: _ge(r["guard_predIouAfter"], r["guard_predIouBefore"], 0.02),
    "coast fit not worse by 25%": lambda r: _ge(1.25 * (r["guard_coastBeforePx"] or 0) + 0.5, r["guard_coastAfterPx"]),
    "far change ≤ change at the click": lambda r: _ge(r["guard_clickShiftPx"], r["guard_farShiftP90Px"]),
    "old points move ≤ 2 px": lambda r: _ge(2.0, r["guard_oldPointShiftPx"]),
    # The old placement already within 12 px of the new click: it adds little.
    "click surprise ≥ 12 px": lambda r: _ge(r["guard_clickSurprisePx"], 12.0),
}


#: How much a folding bump is widened at a time.
WIDEN = 1.25


def local_correction(model: Any, click: Any, old_points: Sequence[Any], ratio: float, held: bool,
                     image_size: Tuple[int, int]) -> Tuple[Any, float]:
    """*model* with a bump at *click* (module docstring), and its radius."""
    w, h = image_size
    X, Y = lonlat_to_webmercator(*click.geo)
    qx, qy = model.inverse()(np.array([X]), np.array([Y]))
    needed = np.array([[float(qx[0]), float(qy[0])]]) - np.array([click.pixel], dtype=float)
    centres = np.array([click.pixel], dtype=float)
    if held:
        old = np.array([p.pixel for p in old_points], dtype=float)
        centres, needed = np.vstack((old, centres)), np.vstack((np.zeros_like(old), needed))
    xs, ys = np.meshgrid(np.linspace(0, w, CHECK_GRID), np.linspace(0, h, CHECK_GRID))
    grid = np.column_stack((xs.ravel(), ys.ravel()))
    gap = ((centres[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
    radius = ratio * math.hypot(w, h)
    while True:
        kernel = np.exp(-gap / (2.0 * radius**2))
        weights = np.linalg.solve(kernel + 1e-9 * np.eye(len(centres)), needed)
        bumped = InlandCorrectionModel(model, image_size, centres, weights, radius)
        if np.linalg.det(bumped.warp_jacobian(grid)).min() > 0 or radius > math.hypot(w, h):
            return bumped, radius
        radius *= WIDEN


def _bump(ratio: float, held: bool) -> Callable[..., Tuple[Any, Dict[str, Any]]]:
    def correct(result: Any, placement: Any, click: Any, points: Sequence[Any], config: Any) -> Tuple[Any, Dict[str, Any]]:
        model, radius = local_correction(result.model, click, placement.control_points, ratio, held,
                                         placement.image_size)
        return model, {"radiusRatio": round(radius / math.hypot(*placement.image_size), 4)}
    return correct


def warm_bend(result: Any, placement: Any, click: Any, points: Sequence[Any], config: Any) -> Tuple[Any, Dict[str, Any]]:
    """The old applied model bent again with the new click (module docstring)."""
    if placement.alignment_context is None:
        return result.model, {"applied": False}
    record = RunRecord()
    model = bend_to_coast(result.model, list(points), placement.alignment_context, placement.image_size, config, record)
    return model, {"applied": bool((record.errors.get("coastBend") or {}).get("applied"))}


#: The local corrections (module docstring): each returns the model and its own columns.
LOCALS: Dict[str, Callable[..., Tuple[Any, Dict[str, Any]]]] = {
    "b05": _bump(0.05, False),
    "warm": warm_bend,
}


def place_fixed(case: Any, placement: Any, model: Any, points: Sequence[Any], config: Any) -> Any:
    """The zones placed with *model* as it is, cleaned as production would."""
    context = placement.alignment_context
    return georeference_features(
        case.pixel_zones(), list(points), frame_bounds=placement.frame_bounds, image_size=placement.image_size,
        config=replace(config, coast_bend=False, transform_model="affine", align_after_piecewise=False,
                       coast_bend_fallback_piecewise=False),
        record=RunRecord(), model=model,
        coast_misfit_px=(lambda m: coast_misfit_px(m, context)) if context is not None else None,
        score_snapping=True,
    )


def _candidates(case: Any) -> List[Tuple[str, Dict[str, Any]]]:
    """What the user could click next (module docstring)."""
    synthetic, layout = case.map, case.layout
    w, h = synthetic.image_size
    diagonal = math.hypot(w, h)
    used = {(p["lon"], p["lat"]) for p in layout.points + layout.check_points}
    clicked = np.array([p["pixel"] for p in layout.points])
    area = shapely.union_all([z.drawn for z in synthetic.zones]).buffer(CHECK_ZONE_MARGIN_RATIO * diagonal)
    out = []
    cities = sorted(synthetic.city_candidates, key=lambda c: -c["population"])[:CITY_CANDIDATES]
    for source, pool in ((SOURCE_SIFT, synthetic.sift_candidates), (SOURCE_CITY, cities)):
        for c in pool:
            if (c["lon"], c["lat"]) in used:
                continue
            if float(np.hypot(*(clicked - np.array(c["pixel"])).T).min()) < MIN_POINT_SEPARATION_RATIO * diagonal:
                continue
            if not area.covers(shapely.Point(*c["pixel"])):
                continue
            out.append((source, c))
    return out


def _guard(
    before_record: Dict[str, Any],
    after_record: Dict[str, Any],
    before: Any,
    after: Any,
    click: Any,
    old_points: Sequence[Any],
    zone_pixels: np.ndarray,
    diagonal: float,
) -> Dict[str, Any]:
    """What a guarded rerun could read (module docstring)."""
    signals = [record_signals(r) for r in (before_record, after_record)]
    mpp = before.baseline.meters_per_pixel

    def shift(px: np.ndarray) -> np.ndarray:
        bx, by = before.model(px[:, 0], px[:, 1])
        ax, ay = after.model(px[:, 0], px[:, 1])
        return np.hypot(np.asarray(ax) - bx, np.asarray(ay) - by) / mpp

    at = np.array([click.pixel], dtype=float)
    far = zone_pixels[np.hypot(*(zone_pixels - at).T) > NEARBY_RATIO * diagonal]
    far_shift = shift(far) if len(far) else np.zeros(0)
    bx, by = before.model(at[:, 0], at[:, 1])
    surprise = math.hypot(float(bx[0]) - lonlat_to_webmercator(*click.geo)[0],
                          float(by[0]) - lonlat_to_webmercator(*click.geo)[1]) / mpp
    return {
        "guard_predIouBefore": signals[0]["predictedIou"],
        "guard_predIouAfter": signals[1]["predictedIou"],
        "guard_coastBeforePx": signals[0]["snapMisfitPx"],
        "guard_coastAfterPx": signals[1]["snapMisfitPx"],
        "guard_clickSurprisePx": round(surprise, 3),
        "guard_clickShiftPx": round(float(shift(at)[0]), 3),
        "guard_farShiftMedianPx": round(float(np.median(far_shift)), 3) if len(far_shift) else None,
        "guard_farShiftP90Px": round(float(np.percentile(far_shift, 90)), 3) if len(far_shift) else None,
        "guard_oldPointShiftPx": round(float(shift(np.array([p.pixel for p in old_points], float)).max()), 3),
        "guard_appliedAfter": signals[1]["appliedModel"],
    }


def _kmpp(run: Dict[str, Any]) -> float:
    return run["run_metersPerPixel"] * math.cos(math.radians(run["run_referenceLatitude"])) / 1000.0


def process_case(case: Any, samples: Any, estimator: Estimator, strategies: Sequence[str] = STRATEGIES,
                 asked_only: bool = False) -> List[Dict[str, Any]]:
    config = DEFAULT_GEOREF_CONFIG.with_overrides(**BY_NAME["PROD"].overrides)
    record = RunRecord(run_id=f"addpoint/{case.case_id}")
    placement, result, seconds = place_case(case, config, record)
    before, _ = measure(case, result, samples)
    record_dict = record.to_dict()
    run = {f"run_{k}": v for k, v in run_columns(record_dict, seconds, 0.0).items()}
    run["kmpp"] = _kmpp(run)
    ids = {
        "id_case": case.case_id,
        "id_mapSeed": case.map.seed,
        "id_deformation": case.map.deformation,
        "id_layout": case.layout_index,
        "gen_layoutFamily": case.layout.params["family"],
        "gen_count": case.layout.params["count"],
        "run_kmPerPx": round(run["kmpp"], 4),
        "run_appliedModel": run.get("run_appliedModel"),
    }
    predicted_iou = record_signals(record_dict)["predictedIou"]
    if asked_only and predicted_iou is not None and predicted_iou >= ASK_BELOW:
        return [{**ids, "status": "not asked"}]
    candidates = _candidates(case)
    if not candidates:
        return [{**ids, "status": "no candidates"}]

    drawn = np.array([c.get("drawnPixel", c["pixel"]) for _, c in candidates], dtype=float)
    true_px = np.array([c["pixel"] for _, c in candidates], dtype=float)
    lon = np.array([c["lon"] for _, c in candidates])
    lat = np.array([c["lat"] for _, c in candidates])
    loo = ((record_dict.get("errors") or {}).get("affineLeaveOneOut") or {}).get("residualsPx")
    features = point_features(
        drawn, placement.control_points, result.model, result.baseline, placement.image_size,
        coast=coast_evidence(result.model, placement.alignment_context), loo_px=loo,
    )
    map_median, map_p90 = estimator.map(run)
    predicted, _ = estimator.points(map_median, map_p90, features)
    x, y = result.model(true_px[:, 0], true_px[:, 1])
    tx, ty = lonlat_arrays_to_webmercator(lon, lat)
    true_km = np.hypot(np.asarray(x) - tx, np.asarray(y) - ty) * np.cos(np.radians(lat)) / 1000.0

    rng = np.random.default_rng(np.random.SeedSequence([case.map.seed, case.layout_index, _STREAM]))
    offset = rng.normal(0.0, case.layout.params["noisePx"], size=2)
    chosen = {
        "estimator": int(np.argmax(predicted)),
        "random": int(rng.integers(len(candidates))),
        "farthest": int(np.argmax(features["nearestPointRatio"])),
        "oracle": int(np.argmax(true_km)),
    }
    chosen = {k: v for k, v in chosen.items() if k in strategies}
    zone_pixels = zone_sample_pixels(zone_sizes(case.pixel_zones()), ZONE_SAMPLES)
    diagonal = math.hypot(*placement.image_size)
    after: Dict[int, Dict[str, Any]] = {}
    guards: Dict[int, Dict[str, Any]] = {}
    for index in sorted(set(chosen.values())):
        source, candidate = candidates[index]
        click = extra_click(source, candidate, offset)
        points = case.layout.control_points() + [click]
        record = RunRecord(run_id=f"addpoint/{case.case_id}/{index}")
        _, placed, _ = place_case(case, config, record, control_points=points)
        after[index], _ = measure(case, placed, samples)
        guards[index] = _guard(record_dict, record.to_dict(), result, placed, click,
                               placement.control_points, zone_pixels, diagonal)
        for key, correct in LOCALS.items():
            corrected, columns = correct(result, placement, click, points, config)
            measured, _ = measure(case, place_fixed(case, placement, corrected, points, config), samples)
            guards[index].update({
                **{f"local_{key}_{k}": v for k, v in columns.items()},
                f"local_{key}_denseMeanKm": measured["denseMeanKm"],
                f"local_{key}_snappedMeanIou": measured["snappedMeanIou"],
            })

    rows = []
    for strategy in chosen:
        index = chosen[strategy]
        new = after[index]
        row = {
            **ids,
            "status": "ok",
            "strategy": strategy,
            "candidates": len(candidates),
            "pickSource": candidates[index][0],
            "pickPredictedKm": round(float(np.exp(predicted[index]) * run["kmpp"]), 3),
            "pickTrueKm": round(float(true_km[index]), 3),
            "pickNearestRatio": round(float(features["nearestPointRatio"][index]), 4),
            "pickRankByTrue": int((true_km > true_km[index]).sum()),
            "mapPredictedMedianKm": round(float(np.exp(map_median) * run["kmpp"]), 3),
            **guards[index],
        }
        for m in METRICS:
            row[f"before_{m}"] = before[m]
            row[f"after_{m}"] = new[m]
        row["gain"] = round(1.0 - new["denseMeanKm"] / before["denseMeanKm"], 5) if before["denseMeanKm"] else None
        if before["snappedMeanIou"] is not None and new["snappedMeanIou"] is not None:
            row["gainIou"] = round(new["snappedMeanIou"] - before["snappedMeanIou"], 5)
        for key in LOCALS:
            iou = row[f"local_{key}_snappedMeanIou"]
            if before["snappedMeanIou"] is not None and iou is not None:
                row[f"local_{key}_gainIou"] = round(iou - before["snappedMeanIou"], 5)
        if "local_warm_applied" in row:
            # The warm bend, and the plain rerun where it refuses.
            warm = row["local_warm_applied"]
            row["local_warmElse_gainIou"] = row.get("local_warm_gainIou") if warm else row.get("gainIou")
            row["local_warmElse_denseMeanKm"] = row["local_warm_denseMeanKm"] if warm else new["denseMeanKm"]
        rows.append(row)
    return rows


def process_map(seed: int, layouts: Sequence[int], deformations: Sequence[str], model: str,
                strategies: Sequence[str] = STRATEGIES, asked_only: bool = False) -> Tuple[List[Dict[str, Any]], str]:
    started = time.perf_counter()
    estimator = Estimator(model)
    rows: List[Dict[str, Any]] = []
    for synthetic in generate_twins(seed, deformations=deformations).values():
        samples = dense_samples(synthetic)
        for layout in layouts:
            try:
                case = generate_case(synthetic, layout)
            except Rejected as e:
                rows.append({"id_mapSeed": seed, "id_deformation": synthetic.deformation, "id_layout": layout,
                             "status": f"rejected: {e}"})
                continue
            try:
                rows.extend(process_case(case, samples, estimator, strategies, asked_only))
            except Exception as e:  # one bad case must not lose the others
                rows.append({"id_case": case.case_id, "status": f"error: {type(e).__name__}: {e}",
                             "traceback": traceback.format_exc()})
    ok = sum(1 for r in rows if r.get("status") == "ok") // len(strategies)
    return rows, f"m{seed:05d}  cases {ok}  {time.perf_counter() - started:6.1f}s"


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------


def _bootstrap_ratio(by_map: Dict[int, Tuple[List[float], List[float]]], draws: int = 2000) -> Tuple[float, float]:
    """95% interval of mean gain(a) / mean gain(b), resampling maps."""
    rng = np.random.default_rng(0)
    seeds = list(by_map)
    ratios = []
    for _ in range(draws):
        pick = rng.choice(len(seeds), len(seeds))
        a = [g for i in pick for g in by_map[seeds[i]][0]]
        b = [g for i in pick for g in by_map[seeds[i]][1]]
        if np.mean(b) > 0:
            ratios.append(np.mean(a) / np.mean(b))
    if len(ratios) < draws // 2:
        return math.nan, math.nan
    return float(np.percentile(ratios, 2.5)), float(np.percentile(ratios, 97.5))


def write_summary(rows: List[Dict[str, Any]], path: str) -> List[str]:
    ok = [r for r in rows if r.get("status") == "ok"]
    by = {(r["id_case"], r["strategy"]): r for r in ok}
    cases = sorted({r["id_case"] for r in ok})
    lines = ["# Q5: one more click (georeferencing-synthetic.md §4.3)", "",
             f"{len(cases)} cases; {sum(1 for r in rows if r.get('status', '').startswith('error'))} errors, "
             f"{sum(1 for r in rows if r.get('status') == 'no candidates')} without a candidate.", "",
             "Gain: 1 − after / before of the dense mean error. IoU: change of snapped IoU.", ""]

    def table(selection: Sequence[str], title: str) -> None:
        lines.extend([f"## {title}", "", "| strategy | cases | mean gain | median gain | worse | mean IoU gain | pick in true top 10% |",
                      "|---|---|---|---|---|---|---|"])
        for s in STRATEGIES:
            rs = [by[(c, s)] for c in selection if (c, s) in by]
            g = [r["gain"] for r in rs if r["gain"] is not None]
            iou = [r["gainIou"] for r in rs if r.get("gainIou") is not None]
            top = [r["pickRankByTrue"] < max(1, 0.1 * r["candidates"]) for r in rs]
            lines.append(f"| {s} | {len(rs)} | {np.mean(g):.3f} | {np.median(g):.3f} | {np.mean(np.array(g) < 0):.2f} | "
                         f"{np.mean(iou):+.4f} | {np.mean(top):.2f} |")
        by_map: Dict[int, Tuple[List[float], List[float]]] = {}
        for c in selection:
            if (c, "estimator") in by and (c, "random") in by:
                seed = by[(c, "estimator")]["id_mapSeed"]
                a, b = by_map.setdefault(seed, ([], []))
                a.append(by[(c, "estimator")]["gain"])
                b.append(by[(c, "random")]["gain"])
        if len(by_map) >= 5:
            ea = np.mean([g for a, _ in by_map.values() for g in a])
            ra = np.mean([g for _, b in by_map.values() for g in b])
            lo, hi = _bootstrap_ratio(by_map)
            lines.extend(["", f"estimator / random: {ea / ra:.2f} (95% over maps {lo:.2f}–{hi:.2f})", ""])

    table(cases, "All cases")
    for twin in ("none", "field", "local", "stress"):
        table([c for c in cases if by[(c, "estimator")]["id_deformation"] == twin], f"twin = {twin}")
    for family in ("open", "protocol"):
        table([c for c in cases if by[(c, "estimator")]["gen_layoutFamily"] == family], f"layout = {family}")

    def guarded(selection: Sequence[str], title: str) -> None:
        lines.extend([f"## Guarded rerun: {title}", "",
                      f"IoU change of the placement kept; hurt / helped: by more than {IOU_MATTERS}.", "",
                      "| strategy | guard | cases | new click kept | mean IoU gain | hurt | helped | worst |",
                      "|---|---|---|---|---|---|---|---|"])
        for s in ("farthest", "estimator"):
            rs = [by[(c, s)] for c in selection if (c, s) in by and by[(c, s)].get("gainIou") is not None]
            if not rs:
                continue
            for name, keep in GUARDS.items():
                kept = [keep(r) for r in rs]
                g = np.array([r["gainIou"] if k else 0.0 for r, k in zip(rs, kept)])
                lines.append(f"| {s} | {name} | {len(rs)} | {np.mean(kept):.2f} | {g.mean():+.4f} | "
                             f"{int((g < -IOU_MATTERS).sum())} | {int((g > IOU_MATTERS).sum())} | {g.min():+.3f} |")
        lines.append("")

    guarded(cases, "every case")
    asked = [c for c in cases if (by[(c, "farthest")]["guard_predIouBefore"] or 1.0) < ASK_BELOW]
    guarded(asked, f"where the predicted IoU is below {ASK_BELOW}")

    def local(selection: Sequence[str], title: str) -> None:
        lines.extend([f"## Local correction: {title}", "",
                      f"Snapped IoU change; hurt / helped: by more than {IOU_MATTERS}. "
                      "Dense: mean log(before / after). Against the rerun: better / worse by more than "
                      f"{IOU_MATTERS}.", "",
                      "| strategy | placement | cases | mean IoU gain | hurt | helped | worst | dense gain | vs rerun |",
                      "|---|---|---|---|---|---|---|---|---|"])
        for s in ("farthest", "estimator"):
            rs = [by[(c, s)] for c in selection if (c, s) in by and by[(c, s)].get("gainIou") is not None]
            if not rs:
                continue
            placements = [("plain rerun", "gainIou", "after_denseMeanKm")] + [
                (k, f"local_{k}_gainIou", f"local_{k}_denseMeanKm") for k in LOCALS] + (
                [("warm, else rerun", "local_warmElse_gainIou", "local_warmElse_denseMeanKm")]
                if "warm" in LOCALS else [])
            for name, iou_key, dense_key in placements:
                g = np.array([r.get(iou_key) or 0.0 for r in rs])
                dense = np.mean([math.log(r["before_denseMeanKm"] / r[dense_key]) for r in rs])
                better = int(sum(x > r["gainIou"] + IOU_MATTERS for x, r in zip(g, rs)))
                worse = int(sum(x < r["gainIou"] - IOU_MATTERS for x, r in zip(g, rs)))
                versus = "" if name == "plain rerun" else f"{better} / {worse}"
                lines.append(f"| {s} | {name} | {len(rs)} | {g.mean():+.4f} | {int((g < -IOU_MATTERS).sum())} | "
                             f"{int((g > IOU_MATTERS).sum())} | {g.min():+.3f} | {dense:+.3f} | {versus} |")
        lines.append("")

    local(cases, "every case")
    local(asked, f"where the predicted IoU is below {ASK_BELOW}")
    for twin in ("none", "field", "local", "stress"):
        local([c for c in asked if by[(c, "farthest")]["id_deformation"] == twin], f"asked, twin = {twin}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=700)
    parser.add_argument("--maps", type=int, default=50)
    parser.add_argument("--layouts", type=int, default=2)
    parser.add_argument("--deformation", default="none,field,local,stress")
    parser.add_argument("--model", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", required=True)
    parser.add_argument("--strategies", default=",".join(STRATEGIES))
    parser.add_argument("--asked-only", action="store_true",
                        help=f"place again only where the predicted IoU is below {ASK_BELOW}")
    args = parser.parse_args()
    strategies = [s for s in STRATEGIES if s in set(args.strategies.split(",")) | {"estimator"}]

    os.makedirs(args.out, exist_ok=True)
    deformations = args.deformation.split(",")
    layouts = list(range(args.layouts))
    rows: List[Dict[str, Any]] = []
    started = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process_map, args.seed + i, layouts, deformations, args.model, strategies, args.asked_only) for i in range(args.maps)]
        for future in as_completed(futures):
            map_rows, line = future.result()
            rows.extend(map_rows)
            print(line, flush=True)

    rows.sort(key=lambda r: (r.get("id_mapSeed", 0), str(r.get("id_deformation")), r.get("id_layout", 0),
                             STRATEGIES.index(r["strategy"]) if "strategy" in r else -1))
    columns = list(dict.fromkeys(k for r in rows for k in r if k != "traceback"))
    with open(os.path.join(args.out, "results.csv"), "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    for r in rows:
        if "traceback" in r:
            print(r["traceback"], file=sys.stderr)
    lines = write_summary(rows, os.path.join(args.out, "summary.md"))
    print("\n".join(lines))
    print(f"{len(rows)} rows in {time.time() - started:.0f} s -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
