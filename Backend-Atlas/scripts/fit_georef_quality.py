#!/usr/bin/env python
"""Fit the quality estimator on a synthetic quality dataset and score it
against the baselines (dev-docs/georeferencing-synthetic.md §4.3, Q4).

    python scripts/fit_georef_quality.py \\
        --fit ablations/synthetic-quality-fit-a-v11-2026-10-31,ablations/synthetic-quality-fit-b-v11-2026-10-31 \\
        --test ablations/synthetic-quality-test-v11-2026-10-31 \\
        --out ablations/georef-quality-q4-2026-11-01

Everything is in **blind pixels**: an error in km is divided by the km per
pixel the run itself measured (the control-point affine's, at the reference
latitude), so a model reads the same on a map of any scale, and its
prediction goes back to km the same way.

- **Per map**, the log of the median and of the p90 dense error, least
  squares on the run's blind signals.
- **Per point**, the log error at a pixel (least squares) and its p90
  (quantile regression), from the map's prediction and the pixel's
  ``quality.point_features``.

Inputs are chosen by forward selection under leave-map-out cross-validation
(every twin and layout of a map in the same fold) on the fit runs, the stress
twin held out entirely. The stress runs and the test runs are scored once, by
the models refitted on every fit run outside the stress twin.

Baselines: a constant (the corpus median in pixels, so scaled by km per
pixel), the ``rmse_km`` the pipeline reports as is, and the same calibrated
(a line on its log).

Writes ``report.md``, ``model.json`` (the final models' inputs and
coefficients) and ``predictions.csv`` (each run's predictions, out-of-fold on
the fit runs).
"""

import argparse
import csv
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse
from scipy.optimize import linprog
from scipy.stats import spearmanr

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

# The inputs are production's, so a fitted model reads the same ones there.
from app.utils.georeferencing.quality import (  # noqa: E402
    MAP_FEATURES,
    MAP_PREDICTIONS,
    POINT_COLUMNS,
    POINT_FEATURES,
    Design,
    _g,
    _num,
)

FOLDS = 10
#: Inputs a model may take, besides the ones it always has.
MAX_INPUTS = 6
#: Smallest gain in cross-validated mean |log error| that adds an input (~0.5%).
MIN_GAIN = 0.005
#: Errors below this many pixels count as this: the log of a near-zero error
#: is noise, not information.
FLOOR_PX = 0.5
#: Points per run the point models are fitted on (the first ones, a uniform
#: subsample); every point is scored.
FIT_POINTS = 60
QUANTILE_POINTS = 30
QUANTILE = 0.9
HELD_OUT_TWIN = "stress"
TWINS = ("none", "field", "local", "stress")
#: Optimism (true over predicted) beyond which a family fails §4.3's bar.
OPTIMISM_LIMIT = 2.0

Row = Dict[str, Any]


def least_squares(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def quantile(X: np.ndarray, y: np.ndarray, tau: float = QUANTILE) -> np.ndarray:
    """Quantile regression as a linear programme: X b + u - v = y, minimising
    tau·u + (1 - tau)·v."""
    n, p = X.shape
    cost = np.concatenate([np.zeros(p), np.full(n, tau), np.full(n, 1.0 - tau)])
    A = sparse.hstack([sparse.csr_matrix(X), sparse.eye(n), -sparse.eye(n)], format="csr")
    bounds = [(None, None)] * p + [(0, None)] * (2 * n)
    res = linprog(cost, A_eq=A, b_eq=y, bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"quantile regression failed: {res.message}")
    return res.x[:p]


class Estimator:
    """A fitted ``model.json``, applied to one run: what Q5 and Q6 read."""

    def __init__(self, path: str):
        with open(path, encoding="utf-8") as f:
            model = json.load(f)
        self.models = {
            k: (Design(model[k]["inputs"], model[k]["fill"], model[k]["missingFlag"]), np.array(model[k]["coefficients"]))
            for k in ("mapMedian", "mapP90", "pointMedian", "pointP90")
        }

    def _apply(self, key: str, F: np.ndarray, names: Sequence[str]) -> np.ndarray:
        design, beta = self.models[key]
        return design(F, names) @ beta

    def map(self, run: Row) -> Tuple[float, float]:
        """Log blind px, median and p90, from a run's ``run_`` columns (and
        ``kmpp``, the run's km per pixel)."""
        names = list(MAP_FEATURES)
        F = np.array([[MAP_FEATURES[n](run) for n in names]], dtype=float)
        return float(self._apply("mapMedian", F, names)[0]), float(self._apply("mapP90", F, names)[0])

    def points(self, map_median: float, map_p90: float, features: Dict[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
        """Log blind px at each pixel, median and p90, from ``point_features``."""
        raw = {f"pt_{k}": np.asarray(v, dtype=float) for k, v in features.items()}
        with np.errstate(divide="ignore", invalid="ignore"):
            columns = [f(raw) for f in POINT_FEATURES.values()]
        n = len(columns[0])
        F = np.column_stack([np.full(n, map_median), np.full(n, map_p90), *columns])
        names = [*MAP_PREDICTIONS, *POINT_FEATURES]
        return self._apply("pointMedian", F, names), self._apply("pointP90", F, names)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


class Runs:
    """The ok runs of some datasets, each (folder, chunk), with their per-map
    inputs and labels."""

    def __init__(self, datasets: Sequence[Tuple[str, str]]):
        rows: List[Row] = []
        for d, chunk in datasets:
            with open(os.path.join(d, "results.csv"), encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["run_status"] != "ok" or not r.get("m_denseMedianKm"):
                        continue
                    r["kmpp"] = _g(r, "run_metersPerPixel") * math.cos(math.radians(_g(r, "run_referenceLatitude"))) / 1000.0
                    r["chunk"] = chunk
                    rows.append(r)
        self.rows = rows
        self.case = [r["id_case"] for r in rows]
        self.chunk = np.array([r["chunk"] for r in rows])
        self.seed = np.array([int(_g(r, "id_mapSeed")) for r in rows])
        self.twin = np.array([r["id_deformation"] for r in rows])
        self.layout = np.array([r["gen_layoutFamily"] for r in rows])
        self.points = np.array([_g(r, "run_controlPointCount") for r in rows])
        self.kmpp = np.array([r["kmpp"] for r in rows])
        self.median_km = np.array([_g(r, "m_denseMedianKm") for r in rows])
        self.p90_km = np.array([_g(r, "m_denseP90Km") for r in rows])
        self.iou = np.array([_g(r, "m_snappedMeanIou") for r in rows])
        self.rmse_km = np.array([_g(r, "run_gcpRmseKm") for r in rows])
        self.y_median = np.log(np.maximum(self.median_km / self.kmpp, FLOOR_PX))
        self.y_p90 = np.log(np.maximum(self.p90_km / self.kmpp, FLOOR_PX))
        self.names = list(MAP_FEATURES)
        self.F = np.array([[MAP_FEATURES[n](r) for n in self.names] for r in rows], dtype=float)
        self.dirs = [d for d, _ in datasets]

    def __len__(self) -> int:
        return len(self.rows)


class Points:
    """The scored points of the same datasets, keyed to their runs."""

    def __init__(self, runs: Runs):
        index = {c: i for i, c in enumerate(runs.case)}
        run, pt, error_km, raw = [], [], [], []
        for d in runs.dirs:
            with open(os.path.join(d, "points.csv"), encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                at = {c: header.index(c) for c in ["id_case", "pt_index", "m_errorKm", *POINT_COLUMNS]}
                for line in reader:
                    i = index.get(line[at["id_case"]])
                    if i is None:
                        continue
                    run.append(i)
                    pt.append(int(line[at["pt_index"]]))
                    error_km.append(_num(line[at["m_errorKm"]]))
                    raw.append([_num(line[at[c]]) for c in POINT_COLUMNS])
        self.run = np.array(run)
        self.index = np.array(pt)
        self.error_km = np.array(error_km)
        self.y = np.log(np.maximum(self.error_km / runs.kmpp[self.run], FLOOR_PX))
        raw_array = np.array(raw, dtype=float)
        raw_cols = {c: raw_array[:, k] for k, c in enumerate(POINT_COLUMNS)}
        with np.errstate(divide="ignore", invalid="ignore"):
            feats = [f(raw_cols) for f in POINT_FEATURES.values()]
        self.names = [*MAP_PREDICTIONS, *POINT_FEATURES]
        self.F = np.column_stack([np.full(len(self.run), np.nan), np.full(len(self.run), np.nan), *feats])

    def set_map_predictions(self, median: np.ndarray, p90: np.ndarray) -> None:
        self.F[:, 0] = median[self.run]
        self.F[:, 1] = p90[self.run]

    def __len__(self) -> int:
        return len(self.run)


# --------------------------------------------------------------------------
# Cross-validation and selection
# --------------------------------------------------------------------------


def folds_of(seeds: np.ndarray) -> np.ndarray:
    unique = np.unique(seeds)
    order = np.random.default_rng(0).permutation(len(unique))
    fold_of_seed = {s: k % FOLDS for s, k in zip(unique[order], range(len(unique)))}
    return np.array([fold_of_seed[s] for s in seeds])


def cv_predict(F, names, y, fold, mask, cols, fit=least_squares) -> np.ndarray:
    """Out-of-fold predictions on *mask*'s rows."""
    pred = np.full(len(y), np.nan)
    for k in range(FOLDS):
        train, test = mask & (fold != k), mask & (fold == k)
        if not test.any():
            continue
        design = Design.fit(F, names, cols, train)
        beta = fit(design(F[train], names), y[train])
        pred[test] = design(F[test], names) @ beta
    return pred


def forward_select(F, names, y, fold, mask, base: Sequence[int] = ()) -> Tuple[List[int], List[Tuple[str, float]]]:
    """Add the input that most lowers the cross-validated mean |log error|,
    while it lowers it by MIN_GAIN, up to MAX_INPUTS."""

    def score(cols: Sequence[int]) -> float:
        return float(np.mean(np.abs(cv_predict(F, names, y, fold, mask, cols) - y)[mask]))

    chosen = list(base)
    best = score(chosen)
    history = [("(base)" if base else "(constant)", best)]
    while len(chosen) < len(base) + MAX_INPUTS:
        trials = {j: score(chosen + [j]) for j in range(len(names)) if j not in chosen}
        j = min(trials, key=trials.get)
        if best - trials[j] < MIN_GAIN:
            break
        chosen.append(j)
        best = trials[j]
        history.append((names[j], best))
    return chosen, history


# --------------------------------------------------------------------------
# Scores
# --------------------------------------------------------------------------


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    return float(spearmanr(a[ok], b[ok]).statistic) if ok.sum() > 2 else math.nan


def map_scores(runs: Runs, points: Points, rows: np.ndarray, median: np.ndarray, p90: Optional[np.ndarray]) -> Dict[str, float]:
    """*median* and *p90* are log blind pixels; scores on *rows*."""
    off = np.abs(median - runs.y_median)[rows]
    off = off[np.isfinite(off)]  # rmse_km is missing on a few runs
    median_km = np.exp(median) * runs.kmpp
    out = {
        "factor": math.exp(float(np.median(off))),
        "within2x": float(np.mean(off < math.log(2.0))),
        "rankKm": _spearman(median_km[rows], runs.median_km[rows]),
        "rankPx": _spearman(median[rows], runs.y_median[rows]),
        "rankIou": _spearman(median_km[rows], -runs.iou[rows]),
        "rankIouPx": _spearman(median[rows], -runs.iou[rows]),
    }
    if p90 is not None:
        p90_km = np.exp(p90) * runs.kmpp
        in_rows = np.isin(points.run, np.flatnonzero(rows))
        out["p90Factor"] = math.exp(float(np.median(np.abs(p90 - runs.y_p90)[rows])))
        out["coverage"] = float(np.mean(points.error_km[in_rows] <= p90_km[points.run[in_rows]]))
    return out


def optimism(runs: Runs, rows: np.ndarray, median: np.ndarray, p90: np.ndarray) -> List[Tuple[str, int, float, float]]:
    """Per twin, layout family and control-point count: the median of true
    over predicted, median and p90 (above 1, the estimator is optimistic)."""
    groups = [(f"twin={t}", runs.twin == t) for t in TWINS]
    groups += [(f"layout={l}", runs.layout == l) for l in np.unique(runs.layout)]
    groups += [("points 3-5", runs.points <= 5), ("points 6-10", (runs.points > 5) & (runs.points <= 10)),
               ("points 11+", runs.points > 10)]
    out = []
    for name, m in groups:
        m = m & rows
        if m.sum() < 10:
            continue
        out.append((name, int(m.sum()), math.exp(float(np.median(runs.y_median[m] - median[m]))),
                    math.exp(float(np.median(runs.y_p90[m] - p90[m])))))
    return out


def point_scores(runs: Runs, points: Points, rows: np.ndarray, median: np.ndarray, p90: np.ndarray) -> Dict[str, float]:
    """Per-point predictions (log blind pixels) on the points of *rows*' runs."""
    m = np.isin(points.run, np.flatnonzero(rows))
    order = np.flatnonzero(m)[np.argsort(points.run[m], kind="stable")]
    by_run = np.split(order, np.flatnonzero(np.diff(points.run[order])) + 1)
    within = []
    for idx in by_run:
        if len(idx) > 10 and np.ptp(median[idx]) > 0:
            within.append(_spearman(median[idx], points.y[idx]))
    p90_km = np.exp(p90) * runs.kmpp[points.run]
    return {
        "factor": math.exp(float(np.median(np.abs(median - points.y)[m]))),
        "rankWithinMap": float(np.nanmedian(within)) if within else math.nan,
        "coverage": float(np.mean(points.error_km[m] <= p90_km[m])),
    }


def point_coverage_by(runs: Runs, points: Points, rows: np.ndarray, p90: np.ndarray) -> List[Tuple[str, float]]:
    out = []
    p90_km = np.exp(p90) * runs.kmpp[points.run]
    covered = points.error_km <= p90_km
    for name, m in [(f"twin={t}", runs.twin == t) for t in TWINS] + [(f"layout={l}", runs.layout == l) for l in np.unique(runs.layout)]:
        sel = np.isin(points.run, np.flatnonzero(m & rows))
        if sel.any():
            out.append((name, float(covered[sel].mean())))
    return out


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    def cell(v: Any) -> str:
        if isinstance(v, float):
            return "—" if not math.isfinite(v) else f"{v:.3f}"
        return str(v)

    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + [
        "| " + " | ".join(cell(v) for v in r) + " |" for r in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fit", required=True, help="comma-separated dataset folders to fit on")
    parser.add_argument("--test", required=True, help="comma-separated dataset folders to score once")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    started = time.time()

    def log(msg: str) -> None:
        print(f"[{time.time() - started:6.0f}s] {msg}", flush=True)

    fit_dirs, test_dirs = args.fit.split(","), args.test.split(",")
    runs = Runs([(d, "fit") for d in fit_dirs] + [(d, "test") for d in test_dirs])
    log(f"{len(runs)} runs")
    points = Points(runs)
    log(f"{len(points)} points")

    stress = runs.twin == HELD_OUT_TWIN
    fit = (runs.chunk == "fit") & ~stress
    test = (runs.chunk == "test") & ~stress
    fold = folds_of(runs.seed)
    names = runs.names
    sets = {"fit (CV)": fit, "test": test, "stress": stress}

    # -- per map: selection on the median, the same inputs for the p90 ------
    chosen, history = forward_select(runs.F, names, runs.y_median, fold, fit)
    log("map inputs: " + ", ".join(names[j] for j in chosen))

    def predictions(cols: Sequence[int], y: np.ndarray) -> Tuple[np.ndarray, Design, np.ndarray]:
        """Out-of-fold on the fit runs, the final model elsewhere."""
        pred = cv_predict(runs.F, names, y, fold, fit, cols)
        design = Design.fit(runs.F, names, cols, fit)
        beta = least_squares(design(runs.F[fit], names), y[fit])
        rest = ~fit
        pred[rest] = design(runs.F[rest], names) @ beta
        return pred, design, beta

    est_med, med_design, med_beta = predictions(chosen, runs.y_median)
    est_p90, p90_design, p90_beta = predictions(chosen, runs.y_p90)
    models: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for label, cols in [("constant", []), ("rmse_km calibrated", [names.index("logGcpRmsePx")])]:
        models[label] = (predictions(cols, runs.y_median)[0], predictions(cols, runs.y_p90)[0])
    models["estimator"] = (est_med, est_p90)
    as_reported = np.log(np.maximum(runs.rmse_km / runs.kmpp, FLOOR_PX))

    lines = ["# Quality estimator, Q4 (georeferencing-synthetic.md §4.3)", "",
             f"Fit: {', '.join(fit_dirs)}  ", f"Test: {', '.join(test_dirs)}  ",
             f"{int(fit.sum())} fit runs ({len(np.unique(runs.seed[fit]))} maps), {int(test.sum())} test runs, "
             f"{int(stress.sum())} stress runs (held out); {len(points)} scored points.", "",
             "Errors in blind pixels (km over the run's own km per pixel); a factor is exp(median |log error|).", "",
             "## Per map", "", "Forward selection (cross-validated mean |log median error|):", ""]
    lines += _table(["step", "input", "CV mean |log|"], [(i, n, s) for i, (n, s) in enumerate(history)])
    lines += ["", "Final median model: " + ", ".join(f"{n} {b:+.3f}" for n, b in zip(["intercept", *_expand(med_design)], med_beta)), ""]

    header = ["set", "model", "factor", "within 2×", "rank km", "rank px", "rank IoU", "rank IoU px", "p90 factor", "p90 coverage"]
    table = []
    for set_name, rows in sets.items():
        s = map_scores(runs, points, rows, as_reported, as_reported)
        table.append((set_name, "rmse_km as reported", s["factor"], s["within2x"], s["rankKm"], s["rankPx"], s["rankIou"],
                      s["rankIouPx"], math.nan, s["coverage"]))
        for label, (med, p90) in models.items():
            s = map_scores(runs, points, rows, med, p90)
            table.append((set_name, label, s["factor"], s["within2x"], s["rankKm"], s["rankPx"], s["rankIou"],
                          s["rankIouPx"], s["p90Factor"], s["coverage"]))
    lines += _table(header, table)
    lines += ["", "For `rmse_km as reported`, coverage is the share of points within the reported number.", "",
              "Optimism of the estimator (median true / predicted; above 1 it is optimistic):", ""]
    opt_rows = []
    for set_name, rows in sets.items():
        for name, n, om, op in optimism(runs, rows, est_med, est_p90):
            flag = " ⚠" if max(om, op) > OPTIMISM_LIMIT else ""
            opt_rows.append((set_name, name + flag, n, om, op))
    lines += _table(["set", "family", "runs", "median", "p90"], opt_rows)
    log("map models scored")

    # -- per point ----------------------------------------------------------
    points.set_map_predictions(est_med, est_p90)
    pnames = points.names
    fit_pts = np.isin(points.run, np.flatnonzero(fit))
    pt_fold = fold[points.run]
    sub = fit_pts & (points.index < FIT_POINTS)
    base = [pnames.index("mapMedian")]
    pchosen, phistory = forward_select(points.F, pnames, points.y, pt_fold, sub, base=base)
    log("point inputs: " + ", ".join(pnames[j] for j in pchosen))

    def point_predictions(cols, fit_fn, mask) -> Tuple[np.ndarray, Design, np.ndarray]:
        pred = np.full(len(points), np.nan)
        for k in range(FOLDS):
            train = mask & (pt_fold != k)
            test_k = fit_pts & (pt_fold == k)
            design = Design.fit(points.F, pnames, cols, train)
            beta = fit_fn(design(points.F[train], pnames), points.y[train])
            pred[test_k] = design(points.F[test_k], pnames) @ beta
        design = Design.fit(points.F, pnames, cols, mask)
        beta = fit_fn(design(points.F[mask], pnames), points.y[mask])
        pred[~fit_pts] = design(points.F[~fit_pts], pnames) @ beta
        return pred, design, beta

    qsub = fit_pts & (points.index < QUANTILE_POINTS)
    map_only = [pnames.index("mapMedian")]
    map_only_q = [pnames.index("mapMedian"), pnames.index("mapP90")]
    q_cols = pchosen + ([pnames.index("mapP90")] if pnames.index("mapP90") not in pchosen else [])
    pt_med, pt_med_design, pt_med_beta = point_predictions(pchosen, least_squares, sub)
    log("point median fitted")
    pt_q, pt_q_design, pt_q_beta = point_predictions(q_cols, quantile, qsub)
    log("point p90 fitted")
    mo_med, _, _ = point_predictions(map_only, least_squares, sub)
    mo_q, _, _ = point_predictions(map_only_q, quantile, qsub)
    log("map-only point models fitted")

    lines += ["", "## Per point", "", "Forward selection (from the map's predicted median):", ""]
    lines += _table(["step", "input", "CV mean |log|"], [(i, n, s) for i, (n, s) in enumerate(phistory)])
    lines += ["", "Final point model: " + ", ".join(f"{n} {b:+.3f}" for n, b in zip(["intercept", *_expand(pt_med_design)], pt_med_beta)),
              "", "Final point p90 model: " + ", ".join(f"{n} {b:+.3f}" for n, b in zip(["intercept", *_expand(pt_q_design)], pt_q_beta)), ""]
    ptable = []
    for set_name, rows in sets.items():
        for label, med, q in [("map only", mo_med, mo_q), ("map + point", pt_med, pt_q)]:
            s = point_scores(runs, points, rows, med, q)
            ptable.append((set_name, label, s["factor"], s["rankWithinMap"], s["coverage"]))
    lines += _table(["set", "model", "factor", "rank within map", "p90 coverage"], ptable)
    lines += ["", "p90 coverage of the point model by family:", ""]
    cov_rows = [(set_name, name, c) for set_name, rows in sets.items() for name, c in point_coverage_by(runs, points, rows, pt_q)]
    lines += _table(["set", "family", "coverage"], cov_rows)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(args.out, "model.json"), "w", encoding="utf-8") as f:
        json.dump({
            "units": "log blind pixels; km = exp(prediction) * the run's km per pixel",
            "floorPx": FLOOR_PX,
            "mapMedian": {**med_design.to_json(), "coefficients": med_beta.tolist()},
            "mapP90": {**p90_design.to_json(), "coefficients": p90_beta.tolist()},
            "pointMedian": {**pt_med_design.to_json(), "coefficients": pt_med_beta.tolist()},
            "pointP90": {**pt_q_design.to_json(), "coefficients": pt_q_beta.tolist(), "quantile": QUANTILE},
        }, f, indent=2)
    with open(os.path.join(args.out, "predictions.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id_case", "chunk", "twin", "layout", "kmPerPx", "trueMedianKm", "trueP90Km", "snappedIou",
                    "rmseKm", "predMedianKm", "predP90Km"])
        for i, r in enumerate(runs.rows):
            w.writerow([r["id_case"], r["chunk"], runs.twin[i], runs.layout[i], round(runs.kmpp[i], 4),
                        runs.median_km[i], runs.p90_km[i], runs.iou[i], runs.rmse_km[i],
                        round(float(np.exp(est_med[i]) * runs.kmpp[i]), 3), round(float(np.exp(est_p90[i]) * runs.kmpp[i]), 3)])
    log(f"wrote {args.out}")
    print("\n".join(lines))


def _expand(design: Design) -> List[str]:
    """Column names after the intercept, missing flags included."""
    out = []
    for name, flag in zip(design.names, design.flag):
        out.append(name)
        if flag:
            out.append(name + "?missing")
    return out


if __name__ == "__main__":
    main()
