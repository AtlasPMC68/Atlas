#!/usr/bin/env python
"""Read a synthetic run's results.csv and compare variants, one vote per map
(dev-docs/georeferencing-synthetic.md §7). Nothing is re-run.

    python scripts/analyze_georef_synthetic.py ablations/synthetic-step2-2026-10-27 --findings
    python scripts/analyze_georef_synthetic.py ablations/<run> --compare B10:B5b,A1:A0 \\
        --where gen_deformation=none --by gen_projection,gen_radiusRatio:0.5
    python scripts/analyze_georef_synthetic.py ablations/<run> --compare B5c:B2 --twins none:field
    python scripts/analyze_georef_synthetic.py ablations/<sweep run> --sweep

A **vote** is one map and twin: the median over its layouts of the paired
difference, better / worse / tie. A tie is under ``--tie`` (0.2 px; 0.1 for a
km metric) or ``--tie-ratio`` (2%) of the map's ``A0`` error, whichever is
larger. ``--twins a:b`` reads each comparison on both twins and the change of
its effect from twin a to twin b, paired by map and layout.

Slices (``--by``, ``--where``): a column's values, or numeric bins given as
``column:edge,edge``. ``gen_longSide`` (the image's long side) and the metrics
in px (``denseCoastalMeanPx``, ``denseInlandMeanPx``) are derived here.
"""

import argparse
import csv
import os
import statistics
import sys
from collections import defaultdict
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

BASELINE = "A0"
DEFAULT_METRIC = "denseMeanPx"
#: The twins, in reading order, then the map as drawn.
TWINS = ("none", "field", "local", "stress", "drawn")

Row = Dict[str, Any]
#: (map seed, twin, layout): what makes two runs of different variants paired.
Key = Tuple[int, str, int]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def _typed(value: str) -> Any:
    if value in ("", "None"):
        return None
    if value in ("True", "False"):
        return value == "True"
    try:
        return float(value)
    except ValueError:
        return value


def load(run_dir: str) -> List[Row]:
    """The run's ok rows, typed, with the derived columns."""
    with open(os.path.join(run_dir, "results.csv"), encoding="utf-8") as f:
        rows = [{k: _typed(v) for k, v in r.items()} for r in csv.DictReader(f)]
    ok = []
    for r in rows:
        if r.get("run_status") != "ok":
            continue
        # Runs before the twins have no deformation column: the map as drawn.
        r["id_deformation"] = r.get("id_deformation") or "drawn"
        r["gen_deformation"] = r.get("gen_deformation") or "drawn"
        r["gen_longSide"] = max(r["gen_imageWidth"], r["gen_imageHeight"])
        km_px = r["gen_kmPerPixel"]
        for name in ("denseCoastalMeanKm", "denseInlandMeanKm", "denseMeanKmGcpAffine"):
            value = r.get(f"m_{name}")
            r[f"m_{name[:-2]}Px"] = None if value is None or not km_px else value / km_px
        ok.append(r)
    return ok


def _key(r: Row) -> Key:
    return int(r["id_mapSeed"]), r["id_deformation"], int(r["id_layout"])


def _vote_key(key: Key) -> Tuple[int, str]:
    return key[0], key[1]


def by_variant(rows: Iterable[Row], metric: str) -> Dict[str, Dict[Key, float]]:
    out: Dict[str, Dict[Key, float]] = defaultdict(dict)
    for r in rows:
        value = r.get(f"m_{metric}")
        if isinstance(value, float):
            out[r["id_variant"]][_key(r)] = value
    return out


# --------------------------------------------------------------------------
# Slices
# --------------------------------------------------------------------------


def _slicer(spec: str) -> Tuple[str, Callable[[Row], Optional[str]]]:
    """``column`` (its values) or ``column:e1,e2`` (numeric bins)."""
    column, _, edges = spec.partition(":")
    column = column if column.startswith(("gen_", "run_", "id_", "m_")) else f"gen_{column}"
    if not edges:
        return column, lambda r: None if r.get(column) is None else str(r.get(column))
    bounds = [float(e) for e in edges.split(",")]

    def label(r: Row) -> Optional[str]:
        value = r.get(column)
        if not isinstance(value, float):
            return None
        for i, edge in enumerate(bounds):
            if value < edge:
                return f"< {edge:g}" if i == 0 else f"{bounds[i - 1]:g}–{edge:g}"
        return f">= {bounds[-1]:g}"

    return column, label


def _where(rows: List[Row], specs: Sequence[str]) -> List[Row]:
    """Keep rows matching every ``column=value`` (a slice label, for bins)."""
    for spec in specs:
        target, _, value = spec.partition("=")
        _, label = _slicer(target)
        rows = [r for r in rows if label(r) == value]
    return rows


# --------------------------------------------------------------------------
# Votes
# --------------------------------------------------------------------------


class Comparison:
    """Variant *a* against *b* on *metric*: paired differences a - b, lower
    is better."""

    def __init__(
        self,
        values: Dict[str, Dict[Key, float]],
        a: str,
        b: str,
        tie: float,
        tie_ratio: float,
        keys: Optional[Iterable[Key]] = None,
    ):
        self.a, self.b = a, b
        va, vb = values.get(a, {}), values.get(b, {})
        common = set(va) & set(vb)
        if keys is not None:
            common &= set(keys)
        self.diffs = {k: va[k] - vb[k] for k in common}
        base = values.get(BASELINE, {})
        grouped: Dict[Tuple[int, str], List[float]] = defaultdict(list)
        floors: Dict[Tuple[int, str], List[float]] = defaultdict(list)
        for k, d in self.diffs.items():
            grouped[_vote_key(k)].append(d)
            if k in base:
                floors[_vote_key(k)].append(base[k])
        self.votes = {m: statistics.median(ds) for m, ds in grouped.items()}
        self.ties = {
            m: max(tie, tie_ratio * statistics.median(floors[m]) if floors[m] else 0.0) for m in self.votes
        }
        # Per case, as the runner's summary.md counts them.
        case_ties = {k: max(tie, tie_ratio * base[k] if k in base else 0.0) for k in self.diffs}
        self.case_better = sum(1 for k, d in self.diffs.items() if d < -case_ties[k])
        self.case_worse = sum(1 for k, d in self.diffs.items() if d > case_ties[k])
        self.case_median = statistics.median(self.diffs.values()) if self.diffs else None

    def case_cells(self) -> str:
        tied = len(self.diffs) - self.case_better - self.case_worse
        return f"{self.case_better} / {self.case_worse} / {tied} · {_fmt(self.case_median)}"

    @property
    def better(self) -> int:
        return sum(1 for m, d in self.votes.items() if d < -self.ties[m])

    @property
    def worse(self) -> int:
        return sum(1 for m, d in self.votes.items() if d > self.ties[m])

    @property
    def n(self) -> int:
        return len(self.votes)

    @property
    def tied(self) -> int:
        return self.n - self.better - self.worse

    @property
    def median(self) -> Optional[float]:
        return statistics.median(self.votes.values()) if self.votes else None

    def verdict(self) -> str:
        """`better` / `worse` at 2 to 1 or more, else `even`; `tie` when most
        votes are ties."""
        if not self.n:
            return "–"
        if self.tied * 2 >= self.n:
            return "tie"
        if self.better >= 2 * max(self.worse, 1) and self.better * 2 >= self.n:
            return "better"
        if self.worse >= 2 * max(self.better, 1) and self.worse * 2 >= self.n:
            return "worse"
        return "even"

    def cells(self) -> List[str]:
        return [f"{self.better} / {self.worse} / {self.tied}", _fmt(self.median), self.verdict()]


def _fmt(value: Optional[float], digits: int = 2) -> str:
    return "–" if value is None else f"{value:+.{digits}f}"


def _median_of(values: Dict[Key, float], keys: Iterable[Key]) -> Optional[float]:
    v = [values[k] for k in keys if k in values]
    return statistics.median(v) if v else None


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> List[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines + [""]


def compare_report(
    rows: List[Row],
    pairs: Sequence[Tuple[str, str]],
    metric: str,
    tie: float,
    tie_ratio: float,
    slices: Sequence[str],
) -> List[str]:
    values = by_variant(rows, metric)
    lines = [f"## {metric}: votes per map (better / worse / tie), median of the per-map differences", ""]
    groups: List[Tuple[str, Optional[List[Key]]]] = [("all", None)]
    for spec in slices:
        column, label = _slicer(spec)
        keyed: Dict[str, List[Key]] = defaultdict(list)
        for r in rows:
            g = label(r)
            if g is not None:
                keyed[g].append(_key(r))
        groups += [(f"{column} {g}", keyed[g]) for g in sorted(keyed)]
    body = []
    for name, keys in groups:
        for a, b in pairs:
            c = Comparison(values, a, b, tie, tie_ratio, keys)
            body.append([f"`{a}` vs `{b}`", name, *c.cells(), str(c.n), c.case_cells()])
    return lines + _table(["Comparison", "Slice", "Votes", "Median", "Verdict", "Maps", "Cases (b / w / t · median)"], body)


def twins_report(
    rows: List[Row], pairs: Sequence[Tuple[str, str]], twins: Tuple[str, str], metric: str, tie: float, tie_ratio: float
) -> List[str]:
    """Each comparison on both twins, and how its effect changes from the
    first twin to the second, paired by map and layout."""
    first, second = twins
    values = by_variant(rows, metric)
    lines = [f"## {metric}: from the `{first}` twin to the `{second}` twin", ""]
    body = []
    for a, b in pairs:
        on = {t: Comparison(values, a, b, tie, tie_ratio, [k for k in values.get(a, {}) if k[1] == t]) for t in twins}
        effect = {t: {(k[0], k[2]): d for k, d in on[t].diffs.items()} for t in twins}
        common = set(effect[first]) & set(effect[second])
        change: Dict[int, List[float]] = defaultdict(list)
        for m, layout in common:
            change[m].append(effect[second][(m, layout)] - effect[first][(m, layout)])
        per_map = {m: statistics.median(v) for m, v in change.items()}
        more = sum(1 for d in per_map.values() if d < -tie)
        less = sum(1 for d in per_map.values() if d > tie)
        body.append([
            f"`{a}` vs `{b}`",
            " · ".join(f"{t}: {on[t].cells()[0]}, {on[t].cells()[1]}" for t in twins),
            f"{more} / {less} / {len(per_map) - more - less}",
            _fmt(statistics.median(per_map.values()) if per_map else None),
        ])
    return lines + _table(
        ["Comparison", "Votes and median, per twin",
         f"On `{second}` against `{first}`, the first variant gains more / less / same", "Median change"],
        body,
    )


# --------------------------------------------------------------------------
# Step 2's findings (georeferencing-synthetic.md §7.3)
# --------------------------------------------------------------------------


def _relative_gain(values: Dict[str, Dict[Key, float]], a: str, b: str, keys: Sequence[Key]) -> Optional[float]:
    """Median over maps of (b - a) / b: how much a removes of b's error."""
    per_map: Dict[Tuple[int, str], List[float]] = defaultdict(list)
    for k in keys:
        if k in values.get(a, {}) and k in values.get(b, {}) and values[b][k] > 0:
            per_map[_vote_key(k)].append((values[b][k] - values[a][k]) / values[b][k])
    return statistics.median(statistics.median(v) for v in per_map.values()) if per_map else None


def findings_report(rows: List[Row], tie: float, tie_ratio: float) -> List[str]:
    """F1-F8 per twin, with the rule each must meet on the `none` twin."""
    twins = [t for t in TWINS if any(r["id_deformation"] == t for r in rows)]
    values = by_variant(rows, DEFAULT_METRIC)
    keys_of = {t: [k for k in values.get(BASELINE, {}) if k[1] == t] for t in twins}

    def comp(a: str, b: str, keys: Sequence[Key], metric_values=values) -> Comparison:
        return Comparison(metric_values, a, b, tie, tie_ratio, keys)

    lines = ["## Step 2 findings", "",
             f"{DEFAULT_METRIC}, one vote per map. Votes are better / worse / tie; the verdict is",
             "`better` or `worse` at 2 to 1 and half the votes or more, `tie` when half the votes or",
             "more are ties, else `even`. The rule is the one of georeferencing-synthetic.md §7.3, read on `none`.", ""]

    def row(name: str, finding: str, rule: str, cell: Callable[[str], str], passes: Callable[[], Optional[bool]]) -> List[str]:
        ok = passes()
        return [name, finding, rule, *[cell(t) for t in twins], "–" if ok is None else ("yes" if ok else "**no**")]

    def votes(a: str, b: str, keys_filter: Callable[[Key], bool] = lambda k: True) -> Callable[[str], str]:
        def cell(t: str) -> str:
            c = comp(a, b, [k for k in keys_of[t] if keys_filter(k)])
            return f"{c.better} / {c.worse} / {c.tied} · {_fmt(c.median)} · {c.verdict()}" if c.n else "–"
        return cell

    def verdict_on_none(a: str, b: str, keys_filter: Callable[[Key], bool] = lambda k: True) -> str:
        return comp(a, b, [k for k in keys_of.get("none", []) if keys_filter(k)]).verdict()

    radius = {_key(r): r["gen_radiusRatio"] for r in rows}
    clustered = lambda k: radius.get(k, 1.0) < 0.5  # noqa: E731
    spread = lambda k: radius.get(k, 0.0) >= 0.5  # noqa: E731
    coastal, inland = by_variant(rows, "denseCoastalMeanPx"), by_variant(rows, "denseInlandMeanPx")

    def weights_cell(t: str) -> str:
        meds = [_median_of(values.get(v, {}), keys_of[t]) for v in ("B2", "B5b", "B5c", "B5d")]
        return " → ".join("–" if m is None else f"{m:.2f}" for m in meds)

    def f3_cell(t: str) -> str:
        cg, ig = _relative_gain(coastal, "B5c", BASELINE, keys_of[t]), _relative_gain(inland, "B5c", BASELINE, keys_of[t])
        return f"coastal {_pct(cg)}, inland {_pct(ig)}"

    def f3_pass() -> Optional[bool]:
        if "none" not in keys_of:
            return None
        cg = _relative_gain(coastal, "B5c", BASELINE, keys_of["none"])
        ig = _relative_gain(inland, "B5c", BASELINE, keys_of["none"])
        return None if cg is None or ig is None else cg > ig + 0.05

    def f2_pass() -> Optional[bool]:
        if "none" not in keys_of:
            return None
        return verdict_on_none("B5c", "B2") == "better" and verdict_on_none("B5d", "B5c") in ("tie", "even")

    def f7_pass() -> Optional[bool]:
        if "none" not in keys_of:
            return None
        return verdict_on_none("B10", "B5b", clustered) == "worse" and verdict_on_none("B10", "B5b", spread) != "worse"

    body = [
        row("F1", "Alignment helps", "`B2` vs `A0` better", votes("B2", "A0"),
            lambda: None if "none" not in keys_of else verdict_on_none("B2", "A0") == "better"),
        row("F2", "Weight helps to ×30, then flat", "`B5c` vs `B2` better, `B5d` vs `B5c` not", weights_cell, f2_pass),
        row("F2", "", "×30 against ×1", votes("B5c", "B2"), lambda: None),
        row("F2", "", "×100 against ×30", votes("B5d", "B5c"), lambda: None),
        row("F2", "", "×10 against ×30", votes("B5b", "B5c"), lambda: None),
        row("F3", "The gain is at the coast", "coastal gain of `B5c` over `A0` larger", f3_cell, f3_pass),
        row("F4", "Piecewise ≈ affine", "`A1` vs `A0` no clear winner", votes("A1", "A0"),
            lambda: None if "none" not in keys_of else verdict_on_none("A1", "A0") in ("tie", "even")),
        row("F5", "Piecewise after alignment undoes it", "`B3` vs `B2` worse on a majority", votes("B3", "B2"),
            lambda: None if "none" not in keys_of else comp("B3", "B2", keys_of["none"]).worse * 2 > comp("B3", "B2", keys_of["none"]).n),
        row("F6", "Align, local piecewise, align wins", "`B7b` vs `B2` better on a majority", votes("B7b", "B2"),
            lambda: None if "none" not in keys_of else comp("B7b", "B2", keys_of["none"]).better * 2 > comp("B7b", "B2", keys_of["none"]).n),
        row("F7", "Chamfer needed when clustered", "`B10` vs `B5b` worse when radius < 0.5", votes("B10", "B5b", clustered), f7_pass),
        row("F7", "", "… and not worse when radius ≥ 0.5", votes("B10", "B5b", spread), lambda: None),
        row("F8", "ICP at 60° changes nothing", "`B4` vs `B2` ties", votes("B4", "B2"),
            lambda: None if "none" not in keys_of else verdict_on_none("B4", "B2") in ("tie", "even")),
    ]
    lines += _table(["#", "Real finding", "Rule", *[f"`{t}`" for t in twins], "Holds on `none`"], body)

    lines += ["F2's first row: the median over cases of the dense error at ×1, ×10, ×30, ×100 (px).",
              "F3: the median over maps of the share of `A0`'s error `B5c` removes, coastal and inland.", ""]
    if "none" in twins:
        pairs = [("B2", "A0"), ("B5c", "B2"), ("B5d", "B5c"), ("A1", "A0"), ("B3", "B2"), ("B7b", "B2"), ("B10", "B5b"), ("B4", "B2")]
        for other in ("field", "local", "stress"):
            if other in twins:
                lines += twins_report(rows, pairs, ("none", other), DEFAULT_METRIC, tie, tie_ratio)
    return lines


def _pct(value: Optional[float]) -> str:
    return "–" if value is None else f"{value * 100:+.0f}%"


# --------------------------------------------------------------------------
# Against the real corpus (georeferencing-synthetic.md §7.3): the tables of
# scripts/read_georef_records.py, real and synthetic read the same way
# --------------------------------------------------------------------------

SIGNALS_FILE = "signals.csv"
CHECKPOINTS_FILE = "checkpoints.csv"

#: The signals of §7.3, as run_ columns; ``clicksMovedPx`` is derived (the
#: ``control_points_held`` gate logs the same value).
SIGNALS = (
    ("baselineGcpRmsPx", "In-fit residual of the control-point affine, px"),
    ("clicksMovedPx", "How far alignment moves the clicks, px"),
    ("baselineChamferPx", "Chamfer before alignment, px"),
    ("alignedChamferPx", "Chamfer after alignment, px"),
    ("coastDisplacementPx", "How far alignment moves the coast, px"),
    ("gate.water_agreement", "Water agreement"),
    ("gate.curve_fit_engaged", "Chamfer's relative improvement (curve_fit_engaged)"),
    ("controlPointCount", "Control points"),
    ("cityCount", "of them cities"),
    ("edgeFraction", "Edge fraction"),
    ("waterEdgeFilterKept", "Edges kept by the water filter"),
    ("coastLinePairedFraction", "Coast line: paired share"),
    ("coastLineFlankGapPx", "Coast line: flank gap, px"),
)

#: Reported, not gated (georeferencing-synthetic.md §7.3): the level of water agreement is set by
#: what a real sea holds (labels, legends, hatching); the pipeline only reads
#: its drop under alignment.
UNGATED = {"gate.water_agreement"}

#: A check point this close to the coast (ground km) is coastal, as in
#: georeferencing-testing.md §8.2.
COAST_KM = 50.0
#: A check point's change under this many px counts as neither better nor worse.
CHECK_TIE_PX = 0.2


def _read_table(run_dir: str, name: str) -> List[Row]:
    path = os.path.join(run_dir, name)
    if not os.path.exists(path):
        raise SystemExit(f"{path} is missing: run scripts/read_georef_records.py {run_dir} first")
    with open(path, encoding="utf-8") as f:
        return [{k: _typed(v) for k, v in r.items()} for r in csv.DictReader(f)]


def _signal(r: Row, name: str) -> Optional[float]:
    if name == "clicksMovedPx":
        a, b = r.get("run_alignedGcpRmsPx"), r.get("run_baselineGcpRmsPx")
        return a - b if isinstance(a, float) and isinstance(b, float) else None
    value = r.get(f"run_{name}")
    return float(value) if isinstance(value, (float, bool)) else None


def _quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))]


def signals_report(rows: List[Row], run_dir: str, real_dir: str, variant: str) -> List[str]:
    """Each signal's range on the synthetic runs kept (by --where), and where
    each real case falls in it. Passes if no real case is outside the range
    and they are not all in one quartile's tail."""
    cases = {r["id_case"] for r in rows}
    synthetic = [r for r in _read_table(run_dir, SIGNALS_FILE) if r["id_variant"] == variant and r["id_case"] in cases]
    real = [r for r in _read_table(real_dir, SIGNALS_FILE) if r["id_variant"] == variant]
    lines = [f"## Signals of `{variant}`: {len(synthetic)} synthetic runs against {len(real)} real cases", "",
             "Synthetic: min, p10, median, p90, max. Real: median [min–max]. Outside: real cases outside",
             "the synthetic range. Passes unless a real case is outside, or every real case is below the",
             "synthetic p25 or every one above its p75.", ""]
    body = []
    for name, label in SIGNALS:
        s = [v for v in (_signal(r, name) for r in synthetic) if v is not None]
        named = [(r["id_case"], v) for r, v in ((r, _signal(r, name)) for r in real) if v is not None]
        if not s or not named:
            body.append([label, "–", "–", "–", "–"])
            continue
        values = [v for _, v in named]
        lo, hi = min(s), max(s)
        outside = [f"`{c}` {v:.3g}" for c, v in named if v < lo or v > hi]
        one_tail = all(v < _quantile(s, 0.25) for v in values) or all(v > _quantile(s, 0.75) for v in values)
        body.append([
            label,
            " · ".join(f"{v:.3g}" for v in (lo, _quantile(s, 0.1), statistics.median(s), _quantile(s, 0.9), hi)),
            f"{statistics.median(values):.3g} [{min(values):.3g}–{max(values):.3g}]",
            ", ".join(outside) or "none",
            "not gated" if name in UNGATED else ("**no**" if outside or one_tail else "yes"),
        ])
    return lines + _table(["Signal", "Synthetic", "Real", "Outside", "Passes"], body)


def _check_groups(points: List[Row]) -> Dict[str, Callable[[Row], bool]]:
    return {
        f"coastal (≤ {COAST_KM:g} km)": lambda p: p["coastDistanceKm"] <= COAST_KM,
        "inland": lambda p: p["coastDistanceKm"] > COAST_KM,
        "SIFT": lambda p: p["source"] == "sift",
        "city": lambda p: p["source"] == "city",
    }


def _check_cells(points: List[Row], variant: str, map_of: Callable[[str], str]) -> Dict[str, List[str]]:
    """Per group: points, the median point error in px under A0 and the
    variant, the share of A0's median removed, points better / worse, and the
    median over maps of the share each map's RMS loses. Medians, not a pooled
    RMS: one degenerate layout (control points nearly in a line, extrapolated
    1,000 px) would set a pooled RMS on its own."""
    px = {}
    for p in points:
        if isinstance(p.get("errorKm"), float) and isinstance(p.get("kmPerPixel"), float) and p["coastDistanceKm"] is not None:
            px[(p["id_case"], int(p["id_point"]), p["id_variant"])] = (p, p["errorKm"] / p["kmPerPixel"])
    out = {}
    for group, keep in _check_groups(points).items():
        pairs = [
            (p, e0, px[(c, i, variant)][1])
            for (c, i, v), (p, e0) in px.items()
            if v == BASELINE and (c, i, variant) in px and keep(p)
        ]
        if not pairs:
            out[group] = ["0", "–", "–", "–", "–"]
            continue
        rms = lambda xs: (sum(x * x for x in xs) / len(xs)) ** 0.5  # noqa: E731
        r0, r1 = statistics.median(e0 for _, e0, _ in pairs), statistics.median(e1 for _, _, e1 in pairs)
        better = sum(1 for _, e0, e1 in pairs if e1 < e0 - CHECK_TIE_PX)
        worse = sum(1 for _, e0, e1 in pairs if e1 > e0 + CHECK_TIE_PX)
        per_map: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
        for p, e0, e1 in pairs:
            per_map[map_of(p["id_case"])].append((e0, e1))
        shares = [1 - rms([b for _, b in v]) / rms([a for a, _ in v]) for v in per_map.values() if rms([a for a, _ in v]) > 0]
        out[group] = [
            str(len(pairs)),
            f"{r0:.2f} → {r1:.2f}",
            _pct(1 - r1 / r0 if r0 > 0 else None),
            f"{better} / {worse}",
            f"{_pct(statistics.median(shares) if shares else None)} ({len(shares)})",
        ]
    return out


def checkpoints_report(rows: List[Row], run_dir: str, real_dir: str, variants: Sequence[str]) -> List[str]:
    """What alignment buys at the check points, real and synthetic, scored the
    same way: coastal or inland, SIFT or city. Errors in px of each map
    (ground km over the control-point affine's km per px), so maps of every
    scale pool."""
    cases = {r["id_case"] for r in rows}
    synthetic = [p for p in _read_table(run_dir, CHECKPOINTS_FILE) if p["id_case"] in cases]
    real = _read_table(real_dir, CHECKPOINTS_FILE)
    corpora = (
        (f"real ({os.path.basename(os.path.normpath(real_dir))})", real, lambda c: c.split("/")[0]),
        ("synthetic", synthetic, lambda c: c.rsplit("-l", 1)[0]),
    )
    lines = ["## Check points: the share of `A0`'s error removed", "",
             f"Coastal: within {COAST_KM:g} km of the coast. Median point error in px, pooled; better / worse",
             f"per point at {CHECK_TIE_PX:g} px; per map: the median over maps of the share each map's RMS",
             "loses (maps counted).", ""]
    body = []
    for variant in variants:
        for name, points, map_of in corpora:
            cells = _check_cells(points, variant, map_of)
            for group, c in cells.items():
                body.append([f"`{variant}`", name, group, *c])
    return lines + _table(["Variant", "Corpus", "Points", "Count", "Median px, A0 → variant", "Removed", "Better / worse", "Per map"], body)


# --------------------------------------------------------------------------
# Step 3, phase A: one constant at a time (georeferencing-synthetic.md §7.4)
# --------------------------------------------------------------------------

SWEEP_BASE = "PROD"
#: A value matters if it moves the median of the per-map differences by more
#: than this (px) or this share of the base's error, whichever is larger, with
#: a ``better`` or ``worse`` verdict (2 to 1 votes).
MATTERS_PX = 0.3
MATTERS_RATIO = 0.03
#: A slice with fewer votes is shown but never decides.
MIN_VOTES = 10
SWEEP_METRICS = (("denseMeanPx", "all"), ("denseCoastalMeanPx", "coastal"), ("denseInlandMeanPx", "inland"))
#: §7.4's slices, pooled over the twins; bins put roughly a third of the
#: step-2 cases in each.
SWEEP_SLICES = (
    "gen_longSide:900,1400",
    "gen_kmPerPixel:1,4",
    "gen_radiusRatio:0.45,0.65",
    "gen_count:6,9",
    "gen_projection",
    "gen_coastWidthPx:1,3",
)


def _sweep_groups(rows: List[Row]) -> List[Tuple[str, List[Key]]]:
    """Every case, each twin, then each slice."""
    groups: List[Tuple[str, List[Key]]] = [("all", sorted({_key(r) for r in rows}))]
    twins = [t for t in TWINS if any(r["id_deformation"] == t for r in rows)]
    groups += [(f"`{t}`", sorted({_key(r) for r in rows if r["id_deformation"] == t})) for t in twins]
    for spec in SWEEP_SLICES:
        column, label = _slicer(spec)
        keyed: Dict[str, set] = defaultdict(set)
        for r in rows:
            g = label(r)
            if g is not None:
                keyed[g].add(_key(r))
        groups += [(f"{column[4:]} {g}", sorted(keyed[g])) for g in sorted(keyed)]
    return groups


def _level(values: Dict[Key, float], keys: Sequence[Key]) -> Optional[float]:
    """The median over maps of a variant's per-map median error."""
    per_map: Dict[Tuple[int, str], List[float]] = defaultdict(list)
    for k in keys:
        if k in values:
            per_map[_vote_key(k)].append(values[k])
    return statistics.median(statistics.median(v) for v in per_map.values()) if per_map else None


def _knob_values(variants: Iterable[str]) -> Dict[str, List[Tuple[str, str]]]:
    """``S-<knob>-<value>`` -> knob: [(value, variant)], values in order."""
    knobs: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for v in variants:
        if v.startswith("S-"):
            _, knob, value = v.split("-", 2)
            knobs[knob].append((value, v))
    return {k: sorted(vs, key=lambda p: float(p[0].lstrip("x"))) for k, vs in sorted(knobs.items())}


def sweep_knobs(rows: List[Row], tie: float, tie_ratio: float) -> Dict[str, Dict[str, Any]]:
    """Per knob: its values' comparisons with the base, where each matters,
    the best value per twin, and what phase A makes of it: ``frozen`` (matters
    nowhere), ``selector`` (its best value differs between twins: step 5's
    choice), else ``phase B``."""
    metric_values = {m: by_variant(rows, m) for m, _ in SWEEP_METRICS}
    groups = _sweep_groups(rows)
    out: Dict[str, Dict[str, Any]] = {}
    for knob, values in _knob_values({r["id_variant"] for r in rows}).items():
        per_value = []
        for value, variant in values:
            cells: Dict[Tuple[str, str], Comparison] = {}
            matters: List[Tuple[str, str, str, float]] = []
            for metric, metric_name in SWEEP_METRICS:
                mv = metric_values[metric]
                for group, keys in groups:
                    c = Comparison(mv, variant, SWEEP_BASE, tie, tie_ratio, keys)
                    cells[(group, metric_name)] = c
                    level = _level(mv.get(SWEEP_BASE, {}), keys)
                    if c.n < MIN_VOTES or c.verdict() not in ("better", "worse") or level is None:
                        continue
                    if abs(c.median) > max(MATTERS_PX, MATTERS_RATIO * level):
                        matters.append((group, metric_name, c.verdict(), c.median))
            per_value.append({"value": value, "variant": variant, "cells": cells, "matters": matters})
        twins = [g for g, _ in groups if g.startswith("`")]
        best = {}
        for twin in twins:
            better = [(p["cells"][(twin, "all")].median, p["value"]) for p in per_value
                      if any(m[0] == twin and m[1] == "all" and m[2] == "better" for m in p["matters"])]
            best[twin] = min(better)[1] if better else "default"
        if not any(p["matters"] for p in per_value):
            verdict = "frozen"
        elif len(set(best.values())) > 1:
            verdict = "selector"
        else:
            verdict = "phase B"
        out[knob] = {"values": per_value, "best": best, "verdict": verdict}
    return out


def sweep_report(rows: List[Row], tie: float, tie_ratio: float) -> List[str]:
    knobs = sweep_knobs(rows, tie, tie_ratio)
    seconds: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        if isinstance(r.get("run_pipelineSeconds"), float):
            seconds[r["id_variant"]].append(r["run_pipelineSeconds"])
    median_s = lambda v: f"{statistics.median(seconds[v]):.1f}" if seconds.get(v) else "–"  # noqa: E731
    twins = [t for t in TWINS if any(r["id_deformation"] == t for r in rows)]
    lines = [f"## Step 3, phase A: each constant against `{SWEEP_BASE}`", "",
             f"{DEFAULT_METRIC} unless named; votes better / worse / tie · median of the per-map differences",
             f"(px, lower is better) · verdict. A value **matters** where it moves that median by more than",
             f"{MATTERS_PX:g} px or {MATTERS_RATIO:.0%} of `{SWEEP_BASE}`'s error, with a `better` or `worse` verdict,",
             f"on a twin or a slice of {MIN_VOTES} votes or more; coastal and inland are the dense metric on",
             f"each side of the coast. `{SWEEP_BASE}`'s median pipeline time is {median_s(SWEEP_BASE)} s.", ""]

    summary = []
    for knob, k in knobs.items():
        n_cells = sum(len(p["matters"]) for p in k["values"])
        summary.append([f"`{knob}`", k["verdict"], str(n_cells),
                        " · ".join(f"{t}: {b}" for t, b in k["best"].items())])
    lines += _table(["Knob", "Phase A", "Cells where a value matters", "Best value per twin (all)"], summary)

    def cell(c: Comparison) -> str:
        return f"{c.better} / {c.worse} / {c.tied} · {_fmt(c.median)} · {c.verdict()}" if c.n else "–"

    for knob, k in knobs.items():
        lines += [f"### `{knob}`: {k['verdict']}", ""]
        body = []
        for p in k["values"]:
            where = [f"{g} {m}: {_fmt(d)}" for g, m, _, d in p["matters"]]
            shown = ", ".join(where[:8]) + (f", … {len(where) - 8} more" if len(where) > 8 else "")
            body.append([
                p["value"], cell(p["cells"][("all", "all")]),
                *[cell(p["cells"][(f"`{t}`", "all")]) for t in twins],
                cell(p["cells"][("all", "coastal")]), cell(p["cells"][("all", "inland")]),
                median_s(p["variant"]), shown or "nowhere",
            ])
        lines += _table(["Value", "All", *[f"`{t}`" for t in twins], "Coastal", "Inland", "s", "Matters in"], body)
    return lines


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _split_slices(spec: str) -> List[str]:
    """``gen_projection,gen_radiusRatio:0.5,0.8`` -> two slices: a number
    continues the previous slice's bins."""
    slices: List[str] = []
    for token in (t.strip() for t in spec.split(",") if t.strip()):
        if slices and ":" in slices[-1] and isinstance(_typed(token), float):
            slices[-1] += f",{token}"
        else:
            slices.append(token)
    return slices


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", help="a run folder under ablations/, holding results.csv")
    parser.add_argument("--compare", default="", help="pairs a:b, comma-separated (a - b; lower is better)")
    parser.add_argument("--metric", default=DEFAULT_METRIC, help=f"a metric without its m_ prefix (default {DEFAULT_METRIC})")
    parser.add_argument("--by", default="", help="slices, comma-separated; column or column:edge,edge")
    parser.add_argument("--where", default="", help="keep rows matching column=value, comma-separated")
    parser.add_argument("--twins", default="", help="a:b, e.g. none:field: each comparison on both twins")
    parser.add_argument("--findings", action="store_true", help="step 2's F1-F8, per twin")
    parser.add_argument("--tie", type=float, help="tie floor (default 0.2 for px metrics, 0.1 otherwise)")
    parser.add_argument("--tie-ratio", type=float, default=0.02, help="tie as a share of the map's A0 error (default 0.02)")
    parser.add_argument("--real", help="a real run folder, read by scripts/read_georef_records.py, for --signals and --checkpoints")
    parser.add_argument("--signals", action="store_true", help="§7.3: the real cases' signals against the synthetic range")
    parser.add_argument("--signal-variant", default="PROD", help="the variant whose signals --signals compares (default PROD)")
    parser.add_argument("--checkpoints", default="", help="variants, comma-separated: their check-point gains over A0, real and synthetic")
    parser.add_argument("--sweep", action="store_true", help="step 3's phase A: every S- variant against PROD")
    parser.add_argument("--out", help="also write the report to this file")
    args = parser.parse_args(argv)
    if (args.signals or args.checkpoints) and not args.real:
        raise SystemExit("--signals and --checkpoints need --real")

    tie = args.tie if args.tie is not None else (0.2 if args.metric.endswith("Px") else 0.1)
    rows = load(args.run)
    if args.where:
        rows = _where(rows, [w for w in args.where.split(",") if w])
    pairs = [tuple(p.split(":")) for p in args.compare.split(",") if p]
    if any(len(p) != 2 for p in pairs):
        raise SystemExit("--compare expects pairs like B10:B5b")
    slices = _split_slices(args.by)

    maps = {(r["id_mapSeed"], r["id_deformation"]) for r in rows}
    lines = [f"# {os.path.basename(os.path.normpath(args.run))}", "",
             f"{len(rows)} ok runs, {len({_key(r) for r in rows})} cases, {len(maps)} votes (map × twin). "
             f"Ties under {tie:g} or {args.tie_ratio:.0%} of the map's {BASELINE} error.", ""]
    if pairs:
        lines += compare_report(rows, pairs, args.metric, tie, args.tie_ratio, slices)
        if args.twins:
            first, _, second = args.twins.partition(":")
            lines += twins_report(rows, pairs, (first, second), args.metric, tie, args.tie_ratio)
    if args.findings:
        lines += findings_report(rows, tie, args.tie_ratio)
    if args.signals:
        lines += signals_report(rows, args.run, args.real, args.signal_variant)
    if args.checkpoints:
        lines += checkpoints_report(rows, args.run, args.real, [v for v in args.checkpoints.split(",") if v])
    if args.sweep:
        lines += sweep_report(rows, tie, args.tie_ratio)

    text = "\n".join(lines)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
