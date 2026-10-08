#!/usr/bin/env python
"""Run named georeferencing variants over the dev-test cases and compare them.
    docker compose run --rm georef-dev python scripts/run_georef_variants.py --stage 1
    docker compose run --rm georef-dev python scripts/run_georef_variants.py --variants A1,B2 --case-id pip_7sift
    docker compose run --rm georef-dev python scripts/run_georef_variants.py --list

Output, under ablations/<run name>/:

    <test id>/<case id>/<variant>/zones.geojson, run_record.json, metrics.json
    results.csv     one row per case x variant x metric
    summary.md      per metric, cases x variants, the difference from A0, wins/losses
    variants.json   what each variant ran with, and a fingerprint of the code
"""

import argparse
import copy
import csv
import glob
import hashlib
import json
import os
import statistics
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
for _path in (_BACKEND_ROOT, _SCRIPT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import cv2  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402

from app.utils.dev_test import (  # noqa: E402
    find_test_image_path,
    load_case_config,
    parse_extraction_inputs,
)
from app.utils.dev_test_assets import GEOREF_ASSETS_DIR  # noqa: E402
from app.utils.dev_test_cases import build_case_state, resolve_case_kind  # noqa: E402
from app.utils.dev_test_derived import text_regions_for_run  # noqa: E402
from app.utils.dev_test_evaluator import evaluate_case_zones  # noqa: E402
from app.utils.dev_test_expected import (  # noqa: E402
    load_cleaned_zones,
    load_drawn_zones,
)
from app.utils.extraction_steps import place_map  # noqa: E402
from app.utils.georeferencing import (  # noqa: E402
    CONFIG_VERSION,
    DEFAULT_GEOREF_CONFIG,
    RunRecord,
)
from georef_variants import BASELINE, BY_NAME, VARIANTS, Variant  # noqa: E402
from run_georef_alignment import discover_cases, extract_colors_cached  # noqa: E402

OUT_ROOT = os.path.join(_BACKEND_ROOT, "ablations")

#: The metrics the summary tables show, with which direction is better.
#: Check-point error first: it is the one placement metric not measured on the
#: points the model was fitted to.
#: Placement first (check points, then the zones before cleaning, against the
#: zones as drawn), then the shipped output (after cleaning, against the
#: expected zones cut the same way). Cleaning corrects transform error after the
#: fact, so placement variants are judged on the raw rows.
SUMMARY_METRICS: Tuple[Tuple[str, str, str], ...] = (
    ("checkRmseKm", "lower", "Check-point RMS error (km) -- held out of the fit"),
    ("rawMeanBoundaryKm", "lower", "Before cleaning: zone outline distance, mean (km)"),
    ("rawMeanBoundaryP90Km", "lower", "Before cleaning: zone outline distance, p90 (km)"),
    ("rawMeanIou", "higher", "Before cleaning: mean IoU"),
    ("meanBoundaryKm", "lower", "Shipped output: zone outline distance, mean (km)"),
    ("meanIou", "higher", "Shipped output: mean IoU (the regression score)"),
)

#: The smallest difference counted as better or worse, per metric. On a case
#: where N1 ran, its own one-pixel wobble is the floor when that is larger.
MIN_TIE: Dict[str, float] = {
    "checkRmseKm": 0.1,
    "rawMeanBoundaryKm": 0.1,
    "rawMeanBoundaryP90Km": 0.1,
    "rawMeanIou": 0.001,
    "meanBoundaryKm": 0.1,
    "meanIou": 0.001,
}
NOISE_VARIANT = "N1"


# --------------------------------------------------------------------------
# One case, one variant
# --------------------------------------------------------------------------


def _shift_features(collections: List[dict], dx: float, dy: float) -> List[dict]:
    """The pixel-space zones translated by (dx, dy) px: moving the transform."""
    shifted = copy.deepcopy(collections)
    for fc in shifted:
        for feature in fc.get("features", []):
            geom = shapely.transform(
                shape(feature["geometry"]), lambda xy: xy + (dx, dy)
            )
            feature["geometry"] = mapping(geom)
    return shifted


def _metrics(record: dict, report: Optional[dict], zones_out: int) -> Dict[str, Any]:
    errors = record.get("errors") or {}
    checks = errors.get("checkPoints") or {}
    alignment = (record.get("inputs") or {}).get("alignment") or {}
    row: Dict[str, Any] = {
        "checkCount": checks.get("count"),
        "checkRmseKm": checks.get("rmseKm"),
        "checkMedianKm": checks.get("medianKm"),
        "checkMaxKm": checks.get("maxKm"),
        "checkRmseKmGcpAffine": (checks.get("byModel") or {}).get("gcp_affine"),
        "gcpRmseKm": errors.get("gcpRmseKm"),
        "gcpRmseKind": errors.get("gcpRmseKind"),
        "zonesOut": zones_out,
        "alignmentMethod": alignment.get("method"),
        "alignmentSkipped": alignment.get("skipped"),
        "failedChecks": ",".join(alignment.get("failedChecks") or []) or None,
        # In-sample, in image pixels: how far each fit sits from the clicks.
        # Diagnostics for the gate analysis, never a verdict.
        "baselineGcpRmsPx": alignment.get("baselineGcpRmsPx"),
        "alignedGcpRmsPx": alignment.get("alignedGcpRmsPx"),
        "coastDisplacementPx": alignment.get("coastDisplacementPx"),
    }
    for gate in record.get("gates") or []:
        row[f"gate.{gate.get('name')}"] = gate.get("value")
    if report:
        keys = ("meanIou", "meanBoundaryKm", "meanBoundaryP90Km", "maxBoundaryKm")
        mean = (report.get("metrics") or {}).get("mean") or {}
        raw_mean = ((report.get("raw") or {}).get("metrics") or {}).get("mean") or {}
        for key in keys:
            row[key] = mean.get(key)
            row["raw" + key[0].upper() + key[1:]] = raw_mean.get(key)
    return row


def run_variant(
    *,
    test_id: str,
    case_id: str,
    variant: Variant,
    inputs: Any,
    case_config: dict,
    image_path: str,
    image_bgr: Any,
    text_regions: Optional[list],
    expected: Optional[Tuple[dict, dict]],
    use_cache: bool,
    out_dir: str,
) -> Dict[str, Any]:
    """Georeference one case under one variant. Returns its metrics row."""
    config = DEFAULT_GEOREF_CONFIG.with_overrides(**variant.overrides)

    state = build_case_state(
        test_id=test_id,
        test_case_id=case_id,
        inputs=inputs,
        image_path=image_path,
        config=config,
        case_config=case_config,
    )
    blockers = [s for s in state.requirements.blocked if s.key != "textRegions"]
    if blockers:
        return {
            "status": "skipped",
            "reason": "; ".join(
                f"{s.key}: {s.detail or s.requirement.summary}" for s in blockers
            ),
        }

    started = time.perf_counter()
    record = RunRecord(run_id=f"{test_id}/{case_id}/{variant.name}")
    record.set_inputs(variant=variant.name, variantOverrides=variant.overrides)

    colors = extract_colors_cached(image_path, inputs, text_regions, config, use_cache)
    pixel_features = colors.get("pixel_features", [])
    if variant.pixel_shift_px != (0.0, 0.0):
        pixel_features = _shift_features(pixel_features, *variant.pixel_shift_px)

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
    georef = placement.georeference(pixel_features, check_points=inputs.check_points)
    def _flat(collections: List[dict]) -> dict:
        features = [f for fc in collections for f in fc.get("features", [])]
        return {"type": "FeatureCollection", "features": features}

    zones = _flat(georef.collections)
    raw_zones = _flat(georef.raw_collections)

    report = None
    if expected is not None:
        drawn, cleaned = expected
        report, _errors, _raw_errors = evaluate_case_zones(
            test_id=test_id,
            test_case_id=case_id,
            drawn_expected=drawn,
            cleaned_expected=cleaned,
            zones=zones,
            raw_zones=raw_zones,
        )

    record_dict = record.to_dict()
    row = _metrics(record_dict, report, len(zones["features"]))
    row["status"] = "ok"
    row["seconds"] = round(time.perf_counter() - started, 2)

    os.makedirs(out_dir, exist_ok=True)
    for name, payload in (
        ("zones.geojson", zones),
        ("zones_raw.geojson", raw_zones),
        ("run_record.json", record_dict),
        ("metrics.json", {"metrics": row, "report": report}),
    ):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1, ensure_ascii=False, default=str)
    return row


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}" if abs(value) < 10 else f"{value:.1f}"
    return str(value)


def write_summary(
    out_dir: str,
    rows: Dict[Tuple[str, str], Dict[str, Any]],
    cases: List[Tuple[str, str, str]],
    variants: List[Variant],
) -> str:
    """Per metric: cases x variants, each cell with its difference from A0."""
    names = [v.name for v in variants]
    lines = [
        f"# Variant run `{os.path.basename(out_dir)}`",
        "",
        "Differences are against `A0` on the same case. *Better / worse* counts the "
        "cases where the variant moved the metric in the good / bad direction by more "
        "than the noise floor: the case's own `N1` difference (the transform moved by "
        "one pixel) when `N1` ran, and never less than "
        + ", ".join(f"{v} for `{k}`" for k, v in MIN_TIE.items())
        + ". Smaller differences and missing values count as neither.",
        "",
        "| Variant | Stage | Question |",
        "|---|---|---|",
    ]
    lines += [f"| `{v.name}` | {v.stage} | {v.question} |" for v in variants]

    for metric, direction, title in SUMMARY_METRICS:
        present = [
            key for key, row in rows.items() if row.get(metric) is not None
        ]
        if not present:
            continue
        lines += ["", f"## {title}", "", "| Case | Kind | " + " | ".join(names) + " |"]
        lines.append("|---|---|" + "---|" * len(names))
        deltas: Dict[str, List[Tuple[float, float]]] = {n: [] for n in names}
        for test_id, case_id, kind in cases:
            base = rows.get((f"{test_id}/{case_id}", BASELINE), {}).get(metric)
            noise = rows.get((f"{test_id}/{case_id}", NOISE_VARIANT), {}).get(metric)
            tie = MIN_TIE.get(metric, 0.0)
            if noise is not None and base is not None:
                tie = max(tie, abs(float(noise) - float(base)))
            cells = []
            for name in names:
                row = rows.get((f"{test_id}/{case_id}", name), {})
                value = row.get(metric)
                if row.get("status") == "skipped":
                    cells.append("skip")
                    continue
                cell = _fmt(value)
                if value is not None and base is not None and name != BASELINE:
                    delta = float(value) - float(base)
                    deltas[name].append((delta, tie))
                    cell += f" ({delta:+.3f})" if abs(delta) < 10 else f" ({delta:+.1f})"
                cells.append(cell)
            lines.append(f"| {case_id} | {kind} | " + " | ".join(cells) + " |")

        def _verdict(name: str) -> str:
            ds = deltas[name]
            if name in (BASELINE, NOISE_VARIANT) or not ds:
                return "—"
            sign = -1.0 if direction == "lower" else 1.0
            better = sum(1 for d, tie in ds if sign * d > tie)
            worse = sum(1 for d, tie in ds if -sign * d > tie)
            median = statistics.median(d for d, _ in ds)
            return f"{median:+.3f} · {better}↑ {worse}↓"

        lines.append(
            "| **median Δ · better↑ worse↓** | | "
            + " | ".join(_verdict(n) for n in names)
            + " |"
        )

    skipped = [
        (case, name, row.get("reason"))
        for (case, name), row in sorted(rows.items())
        if row.get("status") == "skipped"
    ]
    if skipped:
        lines += ["", "## Skipped", ""]
        lines += [f"- `{case}` / `{name}`: {reason}" for case, name, reason in skipped]

    path = os.path.join(out_dir, "summary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _code_fingerprint() -> str:
    """A hash of the code the numbers depend on. The image has no git, so the
    commit cannot be read here; this changes whenever that code does."""
    digest = hashlib.sha256()
    patterns = [
        "app/utils/georeferencing/*.py",
        "app/utils/extraction_steps.py",
        "app/utils/color_extraction.py",
        "app/utils/dev_test_evaluator.py",
        "app/utils/coastline_land_mask.py",
        "scripts/georef_variants.py",
    ]
    for pattern in patterns:
        for path in sorted(glob.glob(os.path.join(_BACKEND_ROOT, pattern))):
            with open(path, "rb") as f:
                digest.update(f.read())
    return digest.hexdigest()[:16]


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _select_variants(args: argparse.Namespace) -> List[Variant]:
    if args.variants:
        names = [n.strip() for n in args.variants.split(",") if n.strip()]
        unknown = [n for n in names if n not in BY_NAME]
        if unknown:
            raise SystemExit(f"Unknown variant(s): {', '.join(unknown)}. See --list.")
        chosen = [BY_NAME[n] for n in names]
    elif args.stage:
        stages = {s.strip() for s in args.stage.split(",")}
        chosen = [v for v in VARIANTS if v.stage in stages]
    else:
        chosen = list(VARIANTS)
    if BY_NAME[BASELINE] not in chosen:
        chosen.insert(0, BY_NAME[BASELINE])
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", default="", help="Comma-separated stages: 1, 2, 3, E, N")
    parser.add_argument("--variants", default="", help="Comma-separated variant names")
    parser.add_argument("--test-id", default="", help="Only cases of these maps (comma-separated)")
    parser.add_argument("--case-id", default="", help="Only cases with these ids (comma-separated)")
    parser.add_argument("--kind", default="all", choices=("all", "regression", "probe"))
    parser.add_argument("--run-name", default="", help="Output folder name (default: timestamp)")
    parser.add_argument("--out-root", default=OUT_ROOT, help="Where run folders go")
    parser.add_argument("--assets-root", default=GEOREF_ASSETS_DIR)
    parser.add_argument("--no-cache", action="store_true", help="Re-run colour extraction")
    parser.add_argument("--list", action="store_true", help="List the variants and exit")
    args = parser.parse_args()

    if args.list:
        for v in VARIANTS:
            print(f"{v.name:5s} stage {v.stage}  {v.question}")
            print(f"      {v.overrides}" + (f"  shift {v.pixel_shift_px} px" if v.pixel_shift_px != (0.0, 0.0) else ""))
        return 0

    variants = _select_variants(args)
    cases = discover_cases(args.assets_root)
    if args.test_id:
        test_ids = {t.strip() for t in args.test_id.split(",")}
        cases = [c for c in cases if c[0] in test_ids]
    if args.case_id:
        case_ids = {c.strip() for c in args.case_id.split(",")}
        cases = [c for c in cases if c[1] in case_ids]
    kinds = {c: resolve_case_kind(*c) for c in cases}
    if args.kind != "all":
        cases = [c for c in cases if kinds[c] == args.kind]
    if not cases:
        print("No matching cases found.")
        return 1

    run_name = args.run_name or datetime.now().strftime("%Y%m%d-%H%M%S")
    out_root = os.path.join(args.out_root, run_name)
    os.makedirs(out_root, exist_ok=True)
    print(f"{len(cases)} case(s) x {len(variants)} variant(s) -> {out_root}")

    rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    case_rows: List[Tuple[str, str, str]] = []

    for test_id, case_id in cases:
        label = f"{test_id}/{case_id}"
        print(f"\n=== {label}")
        image_path = find_test_image_path(test_id)
        image_bgr = cv2.imread(image_path) if image_path else None
        if image_bgr is None:
            print("  SKIP: map image missing or unreadable")
            continue
        try:
            case_config = load_case_config(args.assets_root, test_id, case_id)
            inputs = parse_extraction_inputs(case_config)
        except (FileNotFoundError, ValueError) as e:
            print(f"  SKIP: {e}")
            continue

        # One set of OCR boxes for every variant of the case, computed if it is
        # missing: the text fill uses them, so variants that disagreed on OCR
        # would extract different zones and the comparison would mix the two.
        text_regions = text_regions_for_run(
            test_id, image_path, image_bgr, DEFAULT_GEOREF_CONFIG, allow_compute=True
        )
        # Drawn (for the raw comparison) and cleaned (for the shipped one).
        zones_dir = os.path.join(args.assets_root, "georef_zones")
        drawn = load_drawn_zones(test_id, zones_dir)
        expected = (drawn, load_cleaned_zones(test_id, zones_dir)) if drawn else None
        case_rows.append((test_id, case_id, kinds[(test_id, case_id)]))
        print(
            f"  {len(inputs.control_points)} control point(s), {len(inputs.check_points)}"
            f" check point(s), expected zones: {'yes' if expected else 'no'}"
        )

        for variant in variants:
            try:
                row = run_variant(
                    test_id=test_id,
                    case_id=case_id,
                    variant=variant,
                    inputs=inputs,
                    case_config=case_config,
                    image_path=image_path,
                    image_bgr=image_bgr,
                    text_regions=text_regions,
                    expected=expected,
                    use_cache=not args.no_cache,
                    out_dir=os.path.join(out_root, test_id, case_id, variant.name),
                )
            except Exception as e:  # one variant failing must not stop the run
                row = {"status": "failed", "reason": f"{type(e).__name__}: {e}"}
            rows[(label, variant.name)] = row
            if row["status"] == "ok":
                print(
                    f"  {variant.name:5s} check {_fmt(row.get('checkRmseKm'))} km"
                    f"  raw outline {_fmt(row.get('rawMeanBoundaryKm'))} km"
                    f" IoU {_fmt(row.get('rawMeanIou'))}"
                    f"  | shipped outline {_fmt(row.get('meanBoundaryKm'))} km"
                    f" IoU {_fmt(row.get('meanIou'))}"
                    + (f"  [{row['alignmentMethod']}]" if row.get("alignmentMethod") else "")
                    + f"  {row['seconds']}s"
                )
            else:
                print(f"  {variant.name:5s} {row['status'].upper()}: {row['reason']}")

    with open(os.path.join(out_root, "results.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "kind", "variant", "metric", "value"])
        for test_id, case_id, kind in case_rows:
            for variant in variants:
                row = rows.get((f"{test_id}/{case_id}", variant.name)) or {}
                for metric, value in row.items():
                    writer.writerow([f"{test_id}/{case_id}", kind, variant.name, metric, value])

    with open(os.path.join(out_root, "variants.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "runName": run_name,
                "startedAt": datetime.now().isoformat(),
                "configVersion": CONFIG_VERSION,
                "codeFingerprint": _code_fingerprint(),
                "variants": [
                    {
                        "name": v.name,
                        "stage": v.stage,
                        "question": v.question,
                        "overrides": v.overrides,
                        "pixelShiftPx": list(v.pixel_shift_px),
                    }
                    for v in variants
                ],
            },
            f,
            indent=2,
            default=list,
        )

    summary = write_summary(out_root, rows, case_rows, variants)
    print(f"\nsummary -> {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
