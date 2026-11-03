#!/usr/bin/env python
"""Fit the success predictor: will a map's snapped IoU be good enough without
one more click? (dev-docs/georeferencing-synthetic.md §4.3, Q8)

    python scripts/fit_georef_success.py \\
        --fit ablations/synthetic-quality-fit-a-v11-2026-10-31,ablations/synthetic-quality-fit-b-v11-2026-10-31 \\
        --test ablations/synthetic-quality-test-v11-2026-10-31 \\
        --quality ablations/georef-quality-q4-2026-11-01 \\
        --out ablations/georef-success-q8-2026-11-01

Q5 measured what one more click is worth: below a snapped IoU of ~0.75 it
nearly always helps, above ~0.85 it does nothing on average and hurts as
often as it helps. So the question asked of a map is whether its IoU is below
``BAD_IOU``, not how many km it is off.

The target is log(1 − snapped IoU) (``FLOOR_LOSS`` below), least squares on
blind inputs under the same leave-map-out folds and forward selection as Q4,
the stress twin held out. The inputs are Q4's (the run's signals, and Q4's
predicted map median and p90 in blind pixels, out of fold on the fit runs)
and the zones' sizes in pixels, known before placement (``quality.zone_sizes``):
a shift costs a small zone more IoU than a large one. Per zone, Q4's point
model at the run's scored points inside it gives its predicted error; over a
disc of the zone's size, that is a predicted IoU (``quality.disc_iou``).

Scored as a decision: asking for a click where the predicted IoU is below a
threshold, how many bad maps (IoU < ``BAD_IOU``) are asked about, and how
many asks go to maps already good (IoU ≥ ``GOOD_IOU``). Against the ``rmse_km``
the pipeline reports and Q4's predicted median, by ranking at the same share
of maps asked.

Writes ``report.md``, ``model.json`` and ``predictions.csv``.

With ``--ship``, fits nothing: writes the Q4 and Q8 ``model.json`` of
``--quality`` and ``--out`` into the one file production reads
(``quality.QUALITY_MODEL_PATH``)::

    python scripts/fit_georef_success.py --ship app/utils/georeferencing/quality_model.json \\
        --quality ablations/georef-quality-q4-2026-11-01 --out ablations/georef-success-q8-2026-11-01
"""

import argparse
import csv
import json
import math
import os
import sys
import time
from typing import Dict, List, Tuple

import numpy as np
from scipy.stats import spearmanr

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
for _path in (_BACKEND_ROOT, _SCRIPT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.utils.georeferencing.quality import (  # noqa: E402
    MAP_PREDICTIONS,
    QualityModel,
    ZONE_FEATURES,
    ZoneSizes,
    zone_features,
    zone_sizes,
)
from fit_georef_quality import (  # noqa: E402
    HELD_OUT_TWIN,
    POINT_COLUMNS,
    TWINS,
    Design,
    Estimator,
    Runs,
    _num,
    _table,
    cv_predict,
    folds_of,
    forward_select,
    least_squares,
)

BAD_IOU = 0.75
GOOD_IOU = 0.85
#: 1 − IoU below this counts as this: an IoU of 0.995 and of 1 are the same map.
FLOOR_LOSS = 0.005
#: Thresholds on the predicted IoU the decision table tries.
THRESHOLDS = (0.70, 0.75, 0.80, 0.85)
#: Shares of maps asked about, for comparing rankings.
ASK_SHARES = (0.2, 0.3, 0.4)


class SuccessModel:
    """A fitted ``model.json``: a run's predicted snapped IoU."""

    def __init__(self, path: str):
        with open(path, encoding="utf-8") as f:
            model = json.load(f)
        self.design = Design(model["inputs"], model["fill"], model["missingFlag"])
        self.beta = np.array(model["coefficients"])
        self.names = model["names"]

    def iou(self, row: Dict[str, float]) -> float:
        F = np.array([[row.get(n, math.nan) for n in self.names]], dtype=float)
        return float(1.0 - np.exp(self.design(F, self.names) @ self.beta)[0])


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def _q4_predictions(folder: str, runs: Runs) -> Tuple[np.ndarray, np.ndarray]:
    """Q4's map median and p90 per run, log blind pixels."""
    by_case = {}
    with open(os.path.join(folder, "predictions.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            by_case[r["id_case"]] = (_num(r["predMedianKm"]), _num(r["predP90Km"]))
    med = np.array([math.log(by_case[c][0] / k) for c, k in zip(runs.case, runs.kmpp)])
    p90 = np.array([math.log(by_case[c][1] / k) for c, k in zip(runs.case, runs.kmpp)])
    return med, p90


def _scored_points(runs: Runs) -> Dict[str, Tuple[np.ndarray, Dict[str, np.ndarray]]]:
    """Per run, its scored points' pixels and ``point_features``."""
    wanted = set(runs.case)
    rows: Dict[str, List[List[float]]] = {}
    for d in runs.dirs:
        with open(os.path.join(d, "points.csv"), encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            cols = ["pt_x", "pt_y", *POINT_COLUMNS]
            at = [header.index(c) for c in cols]
            case_at = header.index("id_case")
            for line in reader:
                if line[case_at] in wanted:
                    rows.setdefault(line[case_at], []).append([_num(line[i]) for i in at])
    out = {}
    for case, values in rows.items():
        a = np.array(values, dtype=float)
        out[case] = (a[:, :2], {c[3:]: a[:, 2 + k] for k, c in enumerate(POINT_COLUMNS)})
    return out


def _zone_sizes(runs: Runs) -> Dict[str, ZoneSizes]:
    """Per map (a seed's twin), its zones as the map draws them."""
    out: Dict[str, ZoneSizes] = {}
    for d in runs.dirs:
        for case in runs.case:
            map_id = case.rsplit("-l", 1)[0]
            path = os.path.join(d, "maps", map_id, "zones_pixel.geojson")
            if map_id not in out and os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    out[map_id] = zone_sizes([json.load(f)])
    return out


# --------------------------------------------------------------------------
# Scores
# --------------------------------------------------------------------------


def _auc(badness: np.ndarray, bad: np.ndarray) -> float:
    """The chance a bad map ranks worse than a good one (ties count half)."""
    ok = np.isfinite(badness)
    x, b = badness[ok], bad[ok]
    if b.all() or not b.any():
        return math.nan
    ranks = np.argsort(np.argsort(x, kind="stable"), kind="stable").astype(float) + 1.0
    for v in np.unique(x):  # average ranks over ties
        tie = x == v
        ranks[tie] = ranks[tie].mean()
    n_bad, n_good = b.sum(), (~b).sum()
    return float((ranks[b].sum() - n_bad * (n_bad + 1) / 2) / (n_bad * n_good))


def _decision(iou: np.ndarray, ask: np.ndarray) -> Dict[str, float]:
    bad, good = iou < BAD_IOU, iou >= GOOD_IOU
    return {
        "asked": float(ask.mean()),
        "badCaught": float((ask & bad).sum() / max(bad.sum(), 1)),
        "askedGood": float((ask & good).sum() / max(ask.sum(), 1)),
        "shippedBad": float((~ask & bad).sum() / max((~ask).sum(), 1)),
    }


def _at_share(badness: np.ndarray, iou: np.ndarray, share: float) -> Dict[str, float]:
    """Ask on the *share* of maps ranked worst."""
    ok = np.isfinite(badness)
    cut = np.quantile(badness[ok], 1.0 - share)
    return _decision(iou[ok], badness[ok] >= cut)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def ship(quality_dir: str, success_dir: str, path: str) -> None:
    """The models production applies, in one file (module docstring)."""
    with open(os.path.join(quality_dir, "model.json"), encoding="utf-8") as f:
        quality = json.load(f)
    with open(os.path.join(success_dir, "model.json"), encoding="utf-8") as f:
        success = json.load(f)
    parts = {k: {key: quality[k][key] for key in ("inputs", "fill", "missingFlag", "coefficients")}
             for k in ("mapMedian", "mapP90", "pointMedian")}
    parts["success"] = {key: success[key] for key in ("inputs", "fill", "missingFlag", "coefficients", "floorLoss")}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({
            "version": f"{os.path.basename(os.path.normpath(quality_dir))}+{os.path.basename(os.path.normpath(success_dir))}",
            "units": quality["units"],
            "successTarget": success["target"],
            **parts,
        }, f, indent=2)
        f.write("\n")
    QualityModel(path)  # reads back
    print(f"wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fit", help="comma-separated dataset folders to fit on")
    parser.add_argument("--test", help="comma-separated dataset folders to score once")
    parser.add_argument("--quality", required=True, help="the Q4 output folder (model.json, predictions.csv)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--ship", default="", help="write the production model file here instead of fitting")
    args = parser.parse_args()
    if args.ship:
        ship(args.quality, args.out, args.ship)
        return
    if not args.fit or not args.test:
        parser.error("--fit and --test are required unless --ship")
    started = time.time()

    def log(msg: str) -> None:
        print(f"[{time.time() - started:6.0f}s] {msg}", flush=True)

    fit_dirs, test_dirs = args.fit.split(","), args.test.split(",")
    runs = Runs([(d, "fit") for d in fit_dirs] + [(d, "test") for d in test_dirs])
    has_iou = np.isfinite(runs.iou)
    log(f"{len(runs)} runs, {int(has_iou.sum())} with a snapped IoU")
    map_median, map_p90 = _q4_predictions(args.quality, runs)
    estimator = Estimator(os.path.join(args.quality, "model.json"))
    points = _scored_points(runs)
    sizes = _zone_sizes(runs)
    log(f"{len(points)} runs with points, {len(sizes)} maps with zones")

    Z = np.full((len(runs), len(ZONE_FEATURES)), np.nan)
    for i, case in enumerate(runs.case):
        zones = sizes.get(case.rsplit("-l", 1)[0])
        if zones is None:
            continue
        pixels, features = points.get(case, (np.zeros((0, 2)), None))
        point_log = estimator.points(map_median[i], map_p90[i], features)[0] if features is not None else np.zeros(0)
        z = zone_features(zones, pixels, point_log, map_median[i])
        Z[i] = [z[k] for k in ZONE_FEATURES]
    log("zone features")

    names = [*runs.names, *MAP_PREDICTIONS, *ZONE_FEATURES]
    F = np.column_stack([runs.F, map_median, map_p90, Z])
    y = np.log(np.maximum(1.0 - runs.iou, FLOOR_LOSS))
    stress = runs.twin == HELD_OUT_TWIN
    fit = (runs.chunk == "fit") & ~stress & has_iou
    test = (runs.chunk == "test") & ~stress & has_iou
    stress = stress & has_iou
    fold = folds_of(runs.seed)

    chosen, history = forward_select(F, names, y, fold, fit)
    log("inputs: " + ", ".join(names[j] for j in chosen))
    pred = cv_predict(F, names, y, fold, fit, chosen)
    design = Design.fit(F, names, chosen, fit)
    beta = least_squares(design(F[fit], names), y[fit])
    pred[~fit] = design(F[~fit], names) @ beta
    iou_pred = 1.0 - np.exp(pred)

    # Badness, higher is worse, for ranking.
    rankers = {
        "success model": -iou_pred,
        "Q4 map median (px)": map_median,
        "Q4 map median over zone width": F[:, names.index("logErrorOverWidth")],
        "rmse_km as reported": runs.rmse_km,
    }
    sets = {"fit (CV)": fit, "test": test, "stress": stress}

    lines = ["# Success predictor, Q8 (georeferencing-synthetic.md §4.3)", "",
             f"Fit: {', '.join(fit_dirs)}  ", f"Test: {', '.join(test_dirs)}  ", f"Q4: {args.quality}  ",
             f"{int(fit.sum())} fit runs, {int(test.sum())} test, {int(stress.sum())} stress (held out). "
             f"Bad: snapped IoU < {BAD_IOU}; good: ≥ {GOOD_IOU}.", "",
             "Q4's point model was fitted on every fit run, so its zone inputs are in-sample there; its map median is out of fold.", "",
             "## The model", "", "Forward selection (cross-validated mean |log(1 − IoU) error|):", ""]
    lines += _table(["step", "input", "CV mean |log|"], [(i, n, s) for i, (n, s) in enumerate(history)])
    expanded = ["intercept"]
    for n, flag in zip(design.names, design.flag):
        expanded += [n] + ([n + "?missing"] if flag else [])
    lines += ["", "Final: " + ", ".join(f"{n} {b:+.3f}" for n, b in zip(expanded, beta)), ""]

    acc = []
    for s, m in sets.items():
        err = np.abs(iou_pred - runs.iou)[m]
        acc.append((s, int(m.sum()), float(np.mean(runs.iou[m] < BAD_IOU)), float(np.median(err)),
                    float(np.mean(err <= 0.05)), float(np.median(runs.iou[m] - iou_pred[m])),
                    float(spearmanr(iou_pred[m], runs.iou[m]).statistic)))
    lines += _table(["set", "runs", "share bad", "median |IoU error|", "within 0.05", "median true − predicted", "rank"], acc)

    lines += ["", "## Ranking: which maps to ask about", "",
              f"AUC: the chance a bad map ranks worse than a good one. Then, asking on the share of maps ranked worst: "
              f"the bad maps caught, and the asks that went to maps already ≥ {GOOD_IOU}.", ""]
    header = ["set", "ranked by", "AUC"] + [f"{int(q * 100)}% asked: bad caught / asks wasted" for q in ASK_SHARES]
    rank_rows = []
    for s, m in sets.items():
        bad = runs.iou[m] < BAD_IOU
        for label, badness in rankers.items():
            cells = []
            for q in ASK_SHARES:
                d = _at_share(badness[m], runs.iou[m], q)
                cells.append(f"{d['badCaught']:.2f} / {d['askedGood']:.2f}")
            rank_rows.append((s, label, _auc(badness[m], bad), *cells))
    lines += _table(header, rank_rows)

    lines += ["", "## Deciding on the predicted IoU", "",
              "Ask when the predicted snapped IoU is below the threshold.", ""]
    dec_rows = []
    for s, m in sets.items():
        for t in THRESHOLDS:
            d = _decision(runs.iou[m], iou_pred[m] < t)
            dec_rows.append((s, t, d["asked"], d["badCaught"], d["askedGood"], d["shippedBad"]))
    lines += _table(["set", "ask below", "maps asked", "bad caught", "asks to good maps", "bad among not asked"], dec_rows)

    lines += ["", "By twin, threshold 0.75:", ""]
    twin_rows = []
    for t in TWINS:
        m = (runs.twin == t) & (fit | test | stress)
        if m.sum():
            d = _decision(runs.iou[m], iou_pred[m] < 0.75)
            twin_rows.append((t, int(m.sum()), float(np.mean(runs.iou[m] < BAD_IOU)), d["asked"], d["badCaught"],
                              d["askedGood"], float(np.median(runs.iou[m] - iou_pred[m]))))
    lines += _table(["twin", "runs", "share bad", "asked", "bad caught", "asks to good", "median true − predicted"], twin_rows)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(args.out, "model.json"), "w", encoding="utf-8") as f:
        json.dump({"target": "log(max(1 - snapped IoU, floorLoss))", "floorLoss": FLOOR_LOSS, "quality": args.quality,
                   "names": names, **design.to_json(), "coefficients": beta.tolist()}, f, indent=2)
    with open(os.path.join(args.out, "predictions.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id_case", "chunk", "twin", "snappedIou", "predictedIou", *ZONE_FEATURES])
        for i, case in enumerate(runs.case):
            w.writerow([case, runs.chunk[i], runs.twin[i], runs.iou[i], round(float(iou_pred[i]), 4),
                        *[round(float(v), 4) for v in Z[i]]])
    log(f"wrote {args.out}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
