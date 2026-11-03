#!/usr/bin/env python
"""Q6 of the quality estimator (dev-docs/georeferencing-synthetic.md §4.3):
the Q4 model on the real corpus, and flagging a control point that disagrees.

    python scripts/run_georef_quality_corpus.py \\
        --model ablations/georef-quality-q4-2026-11-01/model.json \\
        --out ablations/georef-quality-q6-2026-11-01

Every dev-test case, probes included, is placed by production (``PROD``).
Its predicted error is compared with the error measured at its check points
(held out of the fit, clicked by hand, so their own click error is in the
truth), per map and per check point; maps are ranked against check-point
error and snapped IoU, as is the ``rmse_km`` the pipeline reports.

Flagging: each control point's leave-one-out residual under the control-point
affine (``quality.affine_leave_one_out``), over the median of the map's. On the
real corpus, which points a ratio would flag (c0d9544d/protocol-iquique holds
the SIFT pair 349 km off that was removed from the regression case); on the
synthetic layouts of Q3 (seeds 600-749, four twins, 5 layouts), whether the
largest ratio is the layout's bad point (a SIFT mismatch, 5% of layouts), and
how often a clean layout passes a ratio. No pipeline run is needed there:
the leave-one-out reads the control points alone.

Each case's predicted snapped IoU (Q8) is the one production records,
``errors.predictedQuality`` (``quality.predict_quality``, the shipped model).

Writes ``maps.csv``, ``points.csv``, ``flags.csv``, ``synthetic_flags.csv``
and ``report.md``.
"""

import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import csv
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
from scipy.stats import spearmanr

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
for _path in (_BACKEND_ROOT, _SCRIPT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import cv2  # noqa: E402

from app.utils.dev_test import find_test_image_path, load_case_config, parse_extraction_inputs  # noqa: E402
from app.utils.dev_test_assets import GEOREF_ASSETS_DIR  # noqa: E402
from app.utils.dev_test_cases import resolve_case_kind  # noqa: E402
from app.utils.dev_test_derived import text_regions_for_run  # noqa: E402
from app.utils.dev_test_evaluator import evaluate_case_zones  # noqa: E402
from app.utils.dev_test_expected import load_cleaned_zones, load_drawn_zones  # noqa: E402
from app.utils.extraction_steps import place_map  # noqa: E402
from app.utils.georef_synthetic import Rejected, generate_case, generate_twins  # noqa: E402
from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG, RunRecord, record_signals  # noqa: E402
from app.utils.georeferencing.affine import fit_affine_from_control_points  # noqa: E402
from app.utils.georeferencing.quality import (  # noqa: E402
    affine_leave_one_out,
    coast_evidence,
    point_features,
)
from fit_georef_quality import Estimator  # noqa: E402
from georef_variants import BY_NAME  # noqa: E402
from run_georef_alignment import discover_cases, extract_colors_cached  # noqa: E402

#: The ratios a flag could use: a point's leave-one-out residual over the
#: median of its map's.
FLAG_RATIOS = (2.0, 3.0, 4.0, 6.0)
SYNTHETIC_SEEDS = range(600, 750)
SYNTHETIC_LAYOUTS = range(5)
SYNTHETIC_TWINS = ("none", "field", "local", "stress")


def _kmpp(run: Dict[str, Any]) -> float:
    return run["run_metersPerPixel"] * math.cos(math.radians(run["run_referenceLatitude"])) / 1000.0


def _flat(collections: List[dict]) -> dict:
    return {"type": "FeatureCollection", "features": [f for fc in collections for f in fc.get("features", [])]}


def _ratios(residuals: Sequence[Any]) -> np.ndarray:
    """Each residual over the median of the finite ones; NaN where unknown."""
    r = np.array([math.nan if v is None else v for v in residuals], dtype=float)
    finite = r[np.isfinite(r)]
    if finite.size < 2 or np.median(finite) <= 0:
        return np.full(r.shape, math.nan)
    return r / np.median(finite)


# --------------------------------------------------------------------------
# The real corpus
# --------------------------------------------------------------------------


def process_case(
    test_id: str, case_id: str, estimator: Estimator
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """One case: its map row, its check-point rows, its control-point rows."""
    config = DEFAULT_GEOREF_CONFIG.with_overrides(**BY_NAME["PROD"].overrides)
    image_path = find_test_image_path(test_id)
    image_bgr = cv2.imread(image_path) if image_path else None
    if image_bgr is None:
        return {"case": f"{test_id}/{case_id}", "status": "no image"}, [], []
    inputs = parse_extraction_inputs(load_case_config(GEOREF_ASSETS_DIR, test_id, case_id))
    text_regions = text_regions_for_run(test_id, image_path, image_bgr, DEFAULT_GEOREF_CONFIG, allow_compute=True)
    colors = extract_colors_cached(image_path, inputs, text_regions, config, True)

    record = RunRecord(run_id=f"q6/{test_id}/{case_id}")
    placement = place_map(
        image_bgr,
        inputs.control_points,
        frame_bounds=inputs.frame_bounds,
        legend_bounds=inputs.legend_bounds,
        water_picks=inputs.water_picks,
        text_regions=text_regions,
        config=config,
        record=record,
    )
    pixel_zones = colors.get("pixel_features", [])
    georef = placement.georeference(pixel_zones, check_points=inputs.check_points, score_snapping=True)
    record_dict = record.to_dict()
    run = {f"run_{k}": v for k, v in record_signals(record_dict).items()}
    run["kmpp"] = kmpp = _kmpp(run)
    map_median, map_p90 = estimator.map(run)
    errors = record_dict.get("errors") or {}

    snapped_iou = None
    zones_dir = os.path.join(GEOREF_ASSETS_DIR, "georef_zones")
    drawn = load_drawn_zones(test_id, zones_dir)
    if drawn:
        report, _, _ = evaluate_case_zones(
            test_id=test_id,
            test_case_id=case_id,
            drawn_expected=drawn,
            cleaned_expected=load_cleaned_zones(test_id, zones_dir),
            zones=_flat(georef.collections),
            raw_zones=_flat(georef.raw_collections),
            unsnapped_zones=_flat(georef.unsnapped_collections),
            snapped_zones=_flat(georef.snapped_collections),
        )
        snapped_iou = (((report.get("snapped") or {}).get("metrics") or {}).get("mean") or {}).get("meanIou")

    checks = (errors.get("checkPoints") or {}).get("points") or []
    point_rows: List[Dict[str, Any]] = []
    if checks:
        pixels = np.array([[c["pixel"]["x"], c["pixel"]["y"]] for c in checks], dtype=float)
        loo = (errors.get("affineLeaveOneOut") or {}).get("residualsPx")
        features = point_features(
            pixels, placement.control_points, georef.model, georef.baseline, placement.image_size,
            coast=coast_evidence(georef.model, placement.alignment_context), loo_px=loo,
        )
        median, p90 = estimator.points(map_median, map_p90, features)
        for i, c in enumerate(checks):
            point_rows.append({
                "case": f"{test_id}/{case_id}",
                "name": c.get("name"),
                "source": c.get("source"),
                "errorKm": c["errorKm"],
                "predictedKm": round(float(np.exp(median[i]) * kmpp), 3),
                "predictedP90Km": round(float(np.exp(p90[i]) * kmpp), 3),
                "insideHull": bool(features["insideHull"][i]),
                "nearestPointRatio": round(float(features["nearestPointRatio"][i]), 4),
            })

    residuals = (errors.get("affineLeaveOneOut") or {}).get("residualsPx") or []
    ratios = _ratios(residuals)
    flag_rows = [
        {
            "case": f"{test_id}/{case_id}",
            "index": i,
            "source": cp.source,
            "lon": round(cp.geo[0], 4),
            "lat": round(cp.geo[1], 4),
            "looPx": residuals[i] if i < len(residuals) else None,
            "looKm": round(residuals[i] * kmpp, 2) if i < len(residuals) and residuals[i] is not None else None,
            "ratio": round(float(ratios[i]), 3) if i < len(ratios) and math.isfinite(ratios[i]) else None,
        }
        for i, cp in enumerate(placement.control_points)
    ]

    check_km = np.array([c["errorKm"] for c in checks], dtype=float)
    map_row = {
        "case": f"{test_id}/{case_id}",
        "kind": resolve_case_kind(test_id, case_id),
        "status": "ok",
        "points": len(placement.control_points),
        "checks": len(checks),
        "appliedModel": run.get("run_appliedModel"),
        "kmPerPx": round(kmpp, 4),
        "predictedMedianKm": round(float(np.exp(map_median) * kmpp), 3),
        "predictedP90Km": round(float(np.exp(map_p90) * kmpp), 3),
        "rmseKmReported": errors.get("gcpRmseKm"),
        "checkMedianKm": round(float(np.median(check_km)), 3) if checks else None,
        "checkRmseKm": (errors.get("checkPoints") or {}).get("rmseKm"),
        "snappedMeanIou": snapped_iou,
        "coastlineCoverage": run.get("run_coastlineCoverage"),
        "maxLooRatio": round(float(np.nanmax(ratios)), 3) if np.isfinite(ratios).any() else None,
    }
    predicted = errors.get("predictedQuality") or {}
    map_row["zones"] = predicted.get("zones")
    map_row["predictedIou"] = predicted.get("iou")
    return map_row, point_rows, flag_rows


# --------------------------------------------------------------------------
# Synthetic flagging
# --------------------------------------------------------------------------


def synthetic_flags(seed: int) -> List[Dict[str, Any]]:
    """Every Q3 layout of one map seed: its bad point, if any, and the ratios."""
    rows = []
    for synthetic in generate_twins(seed, deformations=SYNTHETIC_TWINS).values():
        for layout in SYNTHETIC_LAYOUTS:
            try:
                case = generate_case(synthetic, layout)
            except Rejected:
                continue
            cps = case.layout.control_points()
            affine = fit_affine_from_control_points(cps)
            residuals = affine_leave_one_out(cps, affine.meters_per_pixel)["residualsPx"]
            ratios = _ratios(residuals)
            if not np.isfinite(ratios).any():
                continue
            bad = [i for i, p in enumerate(case.layout.points) if p.get("bad")]
            top = int(np.nanargmax(ratios))
            rows.append({
                "case": case.case_id,
                "deformation": synthetic.deformation,
                "points": len(cps),
                "bad": bad[0] if bad else None,
                "top": top,
                "topRatio": round(float(ratios[top]), 3),
                "badRatio": round(float(ratios[bad[0]]), 3) if bad and math.isfinite(ratios[bad[0]]) else None,
                "kmPerPx": synthetic.km_per_pixel,
            })
    return rows


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def _spearman(a: Sequence[Any], b: Sequence[Any]) -> Tuple[float, int]:
    x, y = np.array(a, dtype=float), np.array(b, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    return (float(spearmanr(x[ok], y[ok]).statistic) if ok.sum() > 2 else math.nan), int(ok.sum())


def write_report(maps: List[Dict[str, Any]], points: List[Dict[str, Any]], flags: List[Dict[str, Any]],
                 synthetic: List[Dict[str, Any]], path: str) -> List[str]:
    ok = [m for m in maps if m.get("status") == "ok"]
    regression = [m for m in ok if m["kind"] == "regression"]
    lines = ["# Quality estimator, Q6 (georeferencing-synthetic.md §4.3)", "",
             f"{len(ok)} cases placed ({len(regression)} regression, {len(ok) - len(regression)} probe), "
             f"{sum(m['checks'] for m in ok)} check points.", "",
             "Measured error at the check points includes their own click error.", "",
             "## Per map", "",
             "| case | model | points | checks | predicted median km | predicted p90 km | rmse_km reported | check median km | check RMS km | snapped IoU |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for m in ok:
        lines.append(f"| {m['case'][:8]}/{m['case'].split('/')[1]}{' (probe)' if m['kind'] == 'probe' else ''} | {m['appliedModel']} | "
                     f"{m['points']} | {m['checks']} | {m['predictedMedianKm']:.1f} | {m['predictedP90Km']:.1f} | "
                     f"{_f(m['rmseKmReported'])} | {_f(m['checkMedianKm'])} | {_f(m['checkRmseKm'])} | {_f(m['snappedMeanIou'], 3)} |")

    lines += ["", "Rank correlation over the regression cases (Spearman; IoU is negated, so higher is better everywhere):", "",
              "| predictor | vs check median km | vs check RMS km | vs −snapped IoU |", "|---|---|---|---|"]
    for name, key in (("estimator median", "predictedMedianKm"), ("rmse_km as reported", "rmseKmReported")):
        cells = []
        for target in ("checkMedianKm", "checkRmseKm", "snappedMeanIou"):
            sign = -1.0 if target == "snappedMeanIou" else 1.0
            rho, n = _spearman([m[key] for m in regression], [None if m[target] is None else sign * m[target] for m in regression])
            cells.append(f"{rho:+.2f} (n={n})")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    with_iou = [m for m in regression if m.get("predictedIou") is not None and m["snappedMeanIou"] is not None]
    if with_iou:
        lines += ["", f"Predicted snapped IoU (Q8) against the real one, {len(with_iou)} regression cases; "
                  "real zones carry their own extraction error, which the predictor does not see:", "",
                  "| case | zones | predicted IoU | snapped IoU |", "|---|---|---|---|"]
        for m in with_iou:
            lines.append(f"| {m['case'][:8]}/{m['case'].split('/')[1]} | {m['zones']} | {m['predictedIou']:.3f} | {m['snappedMeanIou']:.3f} |")
        rho, n = _spearman([m["predictedIou"] for m in with_iou], [m["snappedMeanIou"] for m in with_iou])
        diff = [m["snappedMeanIou"] - m["predictedIou"] for m in with_iou]
        lines += ["", f"Rank {rho:+.2f} (n={n}); real − predicted, median {float(np.median(diff)):+.3f}, "
                  f"range {min(diff):+.3f} to {max(diff):+.3f}."]

    reg_points = [p for p in points if any(m["case"] == p["case"] and m["kind"] == "regression" for m in ok)]
    if reg_points:
        e = np.array([p["errorKm"] for p in reg_points])
        med = np.array([p["predictedKm"] for p in reg_points])
        p90 = np.array([p["predictedP90Km"] for p in reg_points])
        log_off = np.abs(np.log(np.maximum(e, 1e-3) / med))
        by_case: Dict[str, List[float]] = {}
        for p in reg_points:
            by_case.setdefault(p["case"], []).append(float(p["errorKm"] <= p["predictedP90Km"]))
        lines += ["", "## Per check point (regression cases)", "",
                  f"- {len(reg_points)} check points on {len(by_case)} cases.",
                  f"- Factor exp(median |log(measured / predicted)|): {math.exp(float(np.median(log_off))):.2f}; "
                  f"within 2×: {np.mean(log_off <= math.log(2)):.2f}.",
                  f"- Optimism, median measured / predicted: {float(np.median(e / med)):.2f}.",
                  f"- p90 coverage: {np.mean(e <= p90):.2f} (target 0.80–0.95); per case, lowest "
                  f"{min(np.mean(v) for v in by_case.values()):.2f}.",
                  f"- Rank within all points (Spearman): {_spearman(med, e)[0]:+.2f}."]
        within = []
        for case in by_case:
            sel = [p for p in reg_points if p["case"] == case]
            if len(sel) >= 4:
                within.append(_spearman([p["predictedKm"] for p in sel], [p["errorKm"] for p in sel])[0])
        if within:
            lines.append(f"- Rank within a case, mean over the {len(within)} cases with 4+ check points: {np.nanmean(within):+.2f}.")
        lines += ["", "| case | check point | measured km | predicted km | p90 km | inside hull |", "|---|---|---|---|---|---|"]
        for p in reg_points:
            lines.append(f"| {p['case'][:8]}/{p['case'].split('/')[1]} | {p['name'] or p['source']} | {p['errorKm']:.1f} | "
                         f"{p['predictedKm']:.1f} | {p['predictedP90Km']:.1f} | {'yes' if p['insideHull'] else 'no'} |")

    lines += ["", "## Flagging a control point", "",
              "Ratio: a point's leave-one-out residual over the median of its map's.", "",
              "Real corpus, the largest ratio per case and the points each ratio would flag:", "",
              "| case | points | largest ratio (point, km off) | " + " | ".join(f"≥{r:g}" for r in FLAG_RATIOS) + " |",
              "|---|---|---|" + "---|" * len(FLAG_RATIOS)]
    for m in ok:
        rows = [f for f in flags if f["case"] == m["case"] and f["ratio"] is not None]
        if not rows:
            lines.append(f"| {m['case'][:8]}/{m['case'].split('/')[1]} | {m['points']} | — |" + " |" * len(FLAG_RATIOS))
            continue
        top = max(rows, key=lambda f: f["ratio"])
        cells = [str(sum(f["ratio"] >= r for f in rows)) for r in FLAG_RATIOS]
        lines.append(f"| {m['case'][:8]}/{m['case'].split('/')[1]}{' (probe)' if m['kind'] == 'probe' else ''} | {m['points']} | "
                     f"{top['ratio']:.1f} (#{top['index']} {top['lat']:.2f}°, {_f(top['looKm'])} km) | " + " | ".join(cells) + " |")

    if synthetic:
        with_bad = [s for s in synthetic if s["bad"] is not None]
        clean = [s for s in synthetic if s["bad"] is None]
        lines += ["", f"Synthetic layouts (Q3 seeds, 4+ points): {len(synthetic)}, {len(with_bad)} with a bad point.", "",
                  "| ratio | bad point flagged and the largest | clean layouts with any flag | " + " | ".join(f"clean, {t}" for t in SYNTHETIC_TWINS) + " |",
                  "|---|---|---|" + "---|" * len(SYNTHETIC_TWINS)]
        for r in FLAG_RATIOS:
            hit = np.mean([s["top"] == s["bad"] and s["topRatio"] >= r for s in with_bad]) if with_bad else math.nan
            false = np.mean([s["topRatio"] >= r for s in clean]) if clean else math.nan
            per = [np.mean([s["topRatio"] >= r for s in clean if s["deformation"] == t] or [math.nan]) for t in SYNTHETIC_TWINS]
            lines.append(f"| ≥{r:g} | {hit:.2f} | {false:.2f} | " + " | ".join(f"{v:.2f}" for v in per) + " |")
        if with_bad:
            lines.append("")
            lines.append(f"The bad point has the largest ratio in {np.mean([s['top'] == s['bad'] for s in with_bad]):.2f} of its layouts; "
                         f"its ratio, median {np.nanmedian([s['badRatio'] or math.nan for s in with_bad]):.1f}.")
    else:
        lines += ["", "Synthetic flagging not run (`--corpus-only`)."]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return lines


def _f(value: Any, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    return f"{value:.{digits}f}"


def _write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    columns = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--corpus-only", action="store_true", help="skip the synthetic flagging")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    started = time.time()

    estimator = Estimator(args.model)
    maps: List[Dict[str, Any]] = []
    points: List[Dict[str, Any]] = []
    flags: List[Dict[str, Any]] = []
    for test_id, case_id in discover_cases(GEOREF_ASSETS_DIR):
        try:
            map_row, point_rows, flag_rows = process_case(test_id, case_id, estimator)
        except Exception as e:  # one bad case must not lose the others
            map_row, point_rows, flag_rows = {"case": f"{test_id}/{case_id}", "status": f"error: {type(e).__name__}: {e}"}, [], []
        maps.append(map_row)
        points += point_rows
        flags += flag_rows
        print(f"{map_row['case']}  {map_row['status']}  {time.time() - started:6.0f}s", flush=True)

    synthetic: List[Dict[str, Any]] = []
    if not args.corpus_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for rows in pool.map(synthetic_flags, SYNTHETIC_SEEDS):
                synthetic += rows
        print(f"{len(synthetic)} synthetic layouts  {time.time() - started:6.0f}s", flush=True)

    for name, rows in (("maps", maps), ("points", points), ("flags", flags), ("synthetic_flags", synthetic)):
        _write_csv(rows, os.path.join(args.out, f"{name}.csv"))
    print("\n".join(write_report(maps, points, flags, synthetic, os.path.join(args.out, "report.md"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
