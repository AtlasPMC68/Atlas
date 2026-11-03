#!/usr/bin/env python
"""Synthetic maps under a known deformation, run through the pipeline and measured
against the truth (dev-docs/georeferencing-synthetic.md).

    docker compose run --rm georef-dev python scripts/run_georef_synthetic.py \\
        --maps 20 --layouts 5 --seed 0 --variants A0,PROD --workers 4
    docker compose run --rm georef-dev python scripts/run_georef_synthetic.py \\
        --case m00042-l03 --variants PROD --debug
    docker compose run --rm georef-dev python scripts/run_georef_synthetic.py \\
        --maps 40 --seed 100 --layouts 2 --deformation none,field,local --variants A0,PROD
    docker compose run --rm georef-dev python scripts/run_georef_synthetic.py \\
        --maps 50 --seed 200 --layouts 1 --deformation none,field,local --stage S

Output, under ablations/synthetic-<date>-s<seed>/ (or --out):

    maps/<map id>/      (m00042, or m00042-field for a twin) image.png, overview.png, map.json,
                        zones_true.geojson, zones_pixel.geojson
    cases/<case id>/    case.json, control_points.png
        <variant>/      run_record.json, zones_raw.geojson, metrics.json
                        (alignment_debug/ with --debug)
    results.csv         one row per case x variant; columns id_, gen_ (what the
                        generator drew: never a selector feature), run_ (what the
                        run did and saw), m_ (the metrics)
    points.csv          with --points N: N dense samples per case x variant, each
                        with what the run knew there (pt_) and its error (m_),
                        for the quality estimator (georeferencing-synthetic.md
                        §4.3); also per run as cases/<case id>/<variant>/points.csv
    summary.md          per variant, by projection, family, level and bad point
    run.json            generator version, code fingerprint, arguments
"""

import os

# One BLAS thread per worker, set before numpy loads: with several workers,
# OpenBLAS's own threads fight over the cores, and a 118 x 118 solve took
# 0.3 s instead of well under a millisecond (2026-10-30).
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import csv
import glob
import hashlib
import json
import shutil
import statistics
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
for _path in (_BACKEND_ROOT, _SCRIPT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.utils.georef_synthetic import (  # noqa: E402
    DEFORMATIONS,
    GENERATOR_VERSION,
    Rejected,
    SyntheticCase,
    SyntheticMap,
    case_id,
    generate_case,
    generate_map,
    generate_twins,
)
from app.utils.georef_synthetic.metrics import dense_samples  # noqa: E402
from app.utils.georef_synthetic.run import run_case  # noqa: E402
from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG, RunRecord  # noqa: E402
from georef_variants import BASELINE, BY_NAME, VARIANTS, Variant  # noqa: E402

OUT_ROOT = os.path.join(_BACKEND_ROOT, "ablations")

#: The smallest difference in dense mean error counted as better or worse.
TIE_KM = 0.1

_FINGERPRINT_PATTERNS = (
    "app/utils/georeferencing/*.py",
    "app/utils/georef_synthetic/*.py",
    "app/utils/extraction_steps.py",
    "app/utils/sift_key_points_finder.py",
    "app/utils/city_gazetteer.py",
    "app/utils/borders.py",
    "app/utils/dev_test_evaluator.py",
    "app/utils/coastline_land_mask.py",
    "scripts/georef_variants.py",
)


def _code_fingerprint() -> str:
    """A hash of the code the numbers depend on (the image has no git)."""
    digest = hashlib.sha256()
    for pattern in _FINGERPRINT_PATTERNS:
        for path in sorted(glob.glob(os.path.join(_BACKEND_ROOT, pattern))):
            with open(path, "rb") as f:
                digest.update(f.read())
    return digest.hexdigest()[:16]


def _write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False, default=str)


# --------------------------------------------------------------------------
# Columns
# --------------------------------------------------------------------------


def _map_columns(synthetic: SyntheticMap) -> Dict[str, Any]:
    warp = synthetic.warp
    w, h = synthetic.image_size
    diagonal = (w * w + h * h) ** 0.5
    families = warp.families
    row: Dict[str, Any] = {
        "gen_generatorVersion": synthetic.generator_version,
        # The twin, or "drawn": the displacements as the generator's coins drew them.
        "gen_deformation": synthetic.deformation or "drawn",
        "gen_projection": warp.projection.name,
        "gen_families": "+".join(families),
        "gen_easy": families == ["mercator", "affine"],
        "gen_rotationDeg": round(warp.affine_params["rotationDeg"], 3),
        "gen_scaleRatio": round(warp.affine_params["scaleRatio"], 4),
        "gen_shear": round(warp.affine_params["shear"], 4),
        "gen_fieldRmsRatio": None,
        "gen_bump": None,
        "gen_bumpRadiusRatio": None,
        "gen_bumpShiftRatio": None,
        "gen_bumpScale": None,
        "gen_bumps": 0,
        "gen_patches": None,
        "gen_seamPx": None,
        # What no affine can take out, the twins' common measure of strength.
        "gen_nonAffineRmsPx": round(warp.non_affine_rms_px(), 3),
        "gen_nonAffineRmsRatio": round(warp.non_affine_rms_px() / diagonal, 5),
        "gen_stressStrength": synthetic.stress["strength"] if synthetic.stress else None,
        "gen_lonSpanDeg": round(synthetic.region.lon_span, 3),
        "gen_aspect": round(synthetic.region.aspect, 3),
        "gen_imageWidth": w,
        "gen_imageHeight": h,
        "gen_kmPerPixel": round(synthetic.km_per_pixel, 4),
        "gen_zoneLevel": synthetic.zone_level,
        "gen_zones": len(synthetic.zones),
        "gen_coastLengthRatio": synthetic.coast["coastLengthRatio"],
        "gen_zoneCoastShare": synthetic.coast["zoneCoastShare"],
        "gen_landFraction": round(synthetic.land_fraction, 4),
        "gen_oceanFraction": round(synthetic.ocean_fraction, 4),
        "gen_coastWidthPx": synthetic.style.coast_width,
        "gen_coastContrast": synthetic.style.coast_contrast,
        "gen_coastOutline": synthetic.style.coast_outline,
        "gen_coastAmplitudePx": synthetic.generalisation.amplitude_px if synthetic.generalisation else None,
        "gen_coastSpacingPx": synthetic.generalisation.spacing_px if synthetic.generalisation else None,
        "gen_coastTolerancePx": synthetic.generalisation.tolerance_px if synthetic.generalisation else None,
        "gen_graticuleStepDeg": synthetic.style.graticule_step,
        "gen_frame": synthetic.style.frame,
        "gen_waterPick": synthetic.water_pick is not None,
        "gen_siftCandidates": len(synthetic.sift_candidates),
        "gen_cityCandidates": len(synthetic.city_candidates),
    }
    for d in warp.displacements:
        params = d.to_dict()
        if params["kind"] == "gaussian_grid":
            row["gen_fieldRmsRatio"] = params["rmsRatio"]
        elif params["kind"] == "patchwork":
            row["gen_patches"] = len(params["centres"])
            row["gen_seamPx"] = params["seamPx"]
        else:
            # Several on the stress twin: the last one's parameters, and the count.
            row["gen_bumps"] += 1
            row["gen_bump"] = params["kind"]
            row["gen_bumpRadiusRatio"] = round(params["radiusPx"] / diagonal, 4)
            if "shiftPx" in params:
                row["gen_bumpShiftRatio"] = round((params["shiftPx"][0] ** 2 + params["shiftPx"][1] ** 2) ** 0.5 / diagonal, 4)
            else:
                row["gen_bumpScale"] = params["scale"]
    return row


def _case_columns(case: SyntheticCase) -> Dict[str, Any]:
    p = case.layout.params
    bad = p["bad"] or {}
    return {
        "gen_layoutFamily": p["family"],
        "gen_siftRequested": p["siftRequested"],
        "gen_cityRequested": p["cityRequested"],
        "gen_count": p["count"],
        "gen_siftCount": p["siftCount"],
        "gen_cityCount": p["cityCount"],
        "gen_radiusRatio": round(p["radiusRatio"], 4),
        "gen_radiusRatioUsed": round(p["radiusRatioUsed"], 4),
        "gen_noisePx": round(p["noisePx"], 3),
        "gen_bad": bad.get("kind", "none"),
        "gen_badAlongPx": bad.get("alongPx"),
        "gen_badDisplacementPx": bad.get("displacementPx"),
    }


def _id_columns(seed: int, deformation: Optional[str], layout: int, variant: str) -> Dict[str, Any]:
    return {
        "id_case": case_id(seed, layout, deformation),
        "id_mapSeed": seed,
        "id_deformation": deformation or "drawn",
        "id_layout": layout,
        "id_variant": variant,
    }


# --------------------------------------------------------------------------
# One map
# --------------------------------------------------------------------------


def process_map(
    seed: int,
    layouts: Sequence[int],
    variant_names: Sequence[str],
    out_dir: str,
    debug: bool,
    deformations: Sequence[str] = (),
    points: int = 0,
) -> Tuple[List[Dict[str, Any]], str]:
    """Generate the map (or the twins in *deformations*), their layouts, and
    run every variant. Returns the rows and one console line per map."""
    if deformations:
        maps = list(generate_twins(seed, deformations=deformations).values())
    else:
        maps = [generate_map(seed)]
    rows: List[Dict[str, Any]] = []
    lines: List[str] = []
    for synthetic in maps:
        map_rows, line = _process_one(synthetic, layouts, variant_names, out_dir, debug, points)
        rows.extend(map_rows)
        lines.append(line)
    return rows, "\n".join(lines)


def _process_one(
    synthetic: SyntheticMap,
    layouts: Sequence[int],
    variant_names: Sequence[str],
    out_dir: str,
    debug: bool,
    points: int = 0,
) -> Tuple[List[Dict[str, Any]], str]:
    started = time.perf_counter()
    seed, deformation = synthetic.seed, synthetic.deformation
    synthetic.write(os.path.join(out_dir, "maps", synthetic.map_id))
    samples = dense_samples(synthetic)
    map_cols = _map_columns(synthetic)

    rows: List[Dict[str, Any]] = []
    for layout in layouts:
        try:
            case = generate_case(synthetic, layout)
        except Rejected as e:
            rows.append({**_id_columns(seed, deformation, layout, "-"), **map_cols, "run_status": "rejected", "run_reason": str(e)})
            continue
        case_dir = os.path.join(out_dir, "cases", case.case_id)
        case.write(case_dir)
        case_cols = _case_columns(case)

        for name in variant_names:
            variant: Variant = BY_NAME[name]
            config = DEFAULT_GEOREF_CONFIG.with_overrides(**variant.overrides)
            record = RunRecord(run_id=f"synthetic/{case.case_id}/{name}")
            record.set_inputs(variant=name, variantOverrides=variant.overrides, generatorVersion=GENERATOR_VERSION)
            variant_dir = os.path.join(case_dir, name)
            debug_dir = None
            if debug:
                # Cleared first, as run_georef_alignment.py does: a folder
                # mixing two runs is worse than none.
                debug_dir = os.path.join(variant_dir, "alignment_debug")
                shutil.rmtree(debug_dir, ignore_errors=True)
                os.makedirs(debug_dir)
            row = {**_id_columns(seed, deformation, layout, name), **map_cols, **case_cols}
            try:
                measured, record_dict, raw = run_case(
                    case, config, samples, record=record, debug_dir=debug_dir, points=points
                )
            except Exception as e:  # one bad run must not lose the others
                rows.append({**row, "run_status": "error", "run_reason": f"{type(e).__name__}: {e}"})
                _write_json(os.path.join(variant_dir, "error.json"), {"error": traceback.format_exc()})
                continue
            point_rows = measured.pop("points", None)
            if point_rows:
                ids = _id_columns(seed, deformation, layout, name)
                os.makedirs(variant_dir, exist_ok=True)
                write_results([{**ids, **r} for r in point_rows], os.path.join(variant_dir, "points.csv"))
            metrics = dict(measured["metrics"])
            metrics["denseMeanPx"] = round(metrics["denseMeanKm"] / synthetic.km_per_pixel, 3)
            row.update({"run_status": "ok"})
            row.update({f"run_{k}": v for k, v in measured["run"].items()})
            row.update({f"m_{k}": v for k, v in metrics.items()})
            rows.append(row)
            _write_json(os.path.join(variant_dir, "run_record.json"), record_dict)
            _write_json(os.path.join(variant_dir, "zones_raw.geojson"), raw)
            _write_json(os.path.join(variant_dir, "metrics.json"), measured)

    ok = [r for r in rows if r.get("run_status") == "ok"]
    line = (
        f"{synthetic.map_id}  {synthetic.image_size[0]}x{synthetic.image_size[1]}  "
        f"{synthetic.km_per_pixel:5.2f} km/px  {'+'.join(synthetic.warp.families):42s} "
        f"runs {len(ok)}/{len(layouts) * len(variant_names)}  {time.perf_counter() - started:6.1f}s"
    )
    return rows, line


# --------------------------------------------------------------------------
# Results and summary
# --------------------------------------------------------------------------

_PREFIX_ORDER = ("id_", "gen_", "run_", "pt_", "m_")


def write_results(rows: List[Dict[str, Any]], path: str) -> None:
    keys: List[str] = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    keys.sort(key=lambda k: next((i for i, p in enumerate(_PREFIX_ORDER) if k.startswith(p)), len(_PREFIX_ORDER)))
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["id_case"], r["id_variant"], r.get("pt_index", 0))):
            writer.writerow(row)


def _join_points(rows: List[Dict[str, Any]], out_dir: str) -> None:
    """The runs' points.csv files, this run's only, as one table."""
    paths = [
        os.path.join(out_dir, "cases", r["id_case"], r["id_variant"], "points.csv")
        for r in rows
        if r.get("run_status") == "ok"
    ]
    with open(os.path.join(out_dir, "points.csv"), "w", encoding="utf-8", newline="") as out:
        header_written = False
        for path in sorted(p for p in paths if os.path.exists(p)):
            with open(path, encoding="utf-8", newline="") as f:
                header = f.readline()
                if not header_written:
                    out.write(header)
                    header_written = True
                out.write(f.read())


def _fmt(value: Optional[float], digits: int = 2) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    v = [x for x in values if x is not None]
    return statistics.fmean(v) if v else None


def _median(values: Iterable[Optional[float]]) -> Optional[float]:
    v = [x for x in values if x is not None]
    return statistics.median(v) if v else None


def _grouped_table(ok: List[Dict[str, Any]], variants: Sequence[str], column: str, title: str) -> List[str]:
    groups = sorted({str(r.get(column)) for r in ok})
    lines = [f"### {title}", "", "Median dense error per case, px (km) · cases", "",
             "| " + " | ".join([column] + list(variants)) + " |",
             "|" + "---|" * (len(variants) + 1)]
    for g in groups:
        cells = [g]
        for v in variants:
            rs = [r for r in ok if r["id_variant"] == v and str(r.get(column)) == g]
            cells.append(
                f"{_fmt(_median(r['m_denseMeanPx'] for r in rs))} ({_fmt(_median(r['m_denseMeanKm'] for r in rs), 1)}) · {len(rs)}"
                if rs else "–"
            )
        lines.append("| " + " | ".join(cells) + " |")
    return lines + [""]


def write_summary(rows: List[Dict[str, Any]], variants: Sequence[str], path: str, header: Dict[str, Any]) -> None:
    ok = [r for r in rows if r.get("run_status") == "ok"]
    rejected = [r for r in rows if r.get("run_status") == "rejected"]
    errors = [r for r in rows if r.get("run_status") == "error"]
    cases = sorted({r["id_case"] for r in ok})
    lines = [
        f"# Synthetic run {header['name']}",
        "",
        f"Generator v{header['generatorVersion']}, code `{header['codeFingerprint']}`, "
        f"{header['maps']} maps × {header['layouts']} layouts ({', '.join(header['deformations'])}), "
        f"variants {', '.join(variants)}. "
        f"{len(cases)} cases ran, {len(rejected)} layouts rejected, {len(errors)} runs failed.",
        "",
        "Dense error: how far the run places the zones' points from where they are, in ground km, on",
        "20,000 points uniform on the ground inside the true zones (the same points for every layout",
        "and variant of a map). In px it is that error over the map's km per pixel, comparable",
        "across map scales; means in km are dominated by the largest maps.",
        "",
        "## Per variant",
        "",
        "| Variant | Runs | Dense mean px (median over cases) | Dense mean km (median) | (mean) | Coastal km | Inland km | Under the GCP affine km | Raw IoU | Pipeline s (median) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for v in variants:
        rs = [r for r in ok if r["id_variant"] == v]
        lines.append(
            f"| {v} | {len(rs)} | {_fmt(_median(r['m_denseMeanPx'] for r in rs))} | "
            f"{_fmt(_median(r['m_denseMeanKm'] for r in rs))} | {_fmt(_mean(r['m_denseMeanKm'] for r in rs))} | "
            f"{_fmt(_median(r['m_denseCoastalMeanKm'] for r in rs))} | {_fmt(_median(r['m_denseInlandMeanKm'] for r in rs))} | "
            f"{_fmt(_median(r['m_denseMeanKmGcpAffine'] for r in rs))} | {_fmt(_mean(r['m_rawMeanIou'] for r in rs), 4)} | "
            f"{_fmt(_median(r['run_pipelineSeconds'] for r in rs))} |"
        )
    lines.append("")

    if BASELINE in variants:
        lines += [f"## Against {BASELINE}", "",
                  f"Per case, dense mean error; differences under {TIE_KM} km are ties.", "",
                  "| Variant | Better | Worse | Tie | Median difference km | Median difference px |", "|---|---|---|---|---|---|"]
        base = {r["id_case"]: r for r in ok if r["id_variant"] == BASELINE}
        for v in variants:
            if v == BASELINE:
                continue
            diffs, diffs_px = [], []
            for r in ok:
                if r["id_variant"] == v and r["id_case"] in base:
                    diffs.append(r["m_denseMeanKm"] - base[r["id_case"]]["m_denseMeanKm"])
                    diffs_px.append(r["m_denseMeanPx"] - base[r["id_case"]]["m_denseMeanPx"])
            better = sum(d < -TIE_KM for d in diffs)
            worse = sum(d > TIE_KM for d in diffs)
            lines.append(
                f"| {v} | {better} | {worse} | {len(diffs) - better - worse} | "
                f"{_fmt(_median(diffs))} | {_fmt(_median(diffs_px))} |"
            )
        lines.append("")

    lines += ["## By what the generator drew", ""]
    for column, title in (
        ("gen_deformation", "Twin (or the map as drawn)"),
        ("gen_projection", "Projection"),
        ("gen_families", "Families"),
        ("gen_easy", "Easy case (Mercator, no field, no local error)"),
        ("gen_bad", "Bad point"),
        ("gen_cityCount", "Cities in the layout"),
        ("gen_zoneLevel", "Zone level"),
        ("gen_waterPick", "Has a water pick"),
    ):
        lines += _grouped_table(ok, variants, column, title)

    if rejected or errors:
        lines += ["## Not run", ""]
        for r in rejected + errors:
            lines.append(f"- `{r['id_case']}` {r['id_variant']}: {r['run_status']}, {r.get('run_reason')}")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _parse_case(value: str) -> Tuple[int, Optional[str], int]:
    """``m00042-l03`` -> (42, None, 3); ``m00042-field-l03`` -> (42, "field", 3)."""
    try:
        map_part, layout_part = value.rsplit("-l", 1)
        seed_part, _, deformation = map_part.partition("-")
        if deformation and deformation not in DEFORMATIONS:
            raise ValueError
        return int(seed_part.lstrip("m")), deformation or None, int(layout_part)
    except ValueError:
        raise SystemExit(f"--case expects an id like m00042-l03 or m00042-field-l03, got {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--maps", type=int, default=20, help="how many maps (default 20)")
    parser.add_argument("--layouts", type=int, default=5, help="layouts per map (default 5)")
    parser.add_argument("--seed", type=int, default=0, help="first map seed (default 0)")
    parser.add_argument("--variants", default="A0,PROD", help="variants from georef_variants.py (default A0,PROD)")
    parser.add_argument("--stage", default="", help="also every variant of these stages, comma-separated (S: the sweep)")
    parser.add_argument("--case", help="run one case only, e.g. m00042-l03 or m00042-field-l03")
    parser.add_argument(
        "--deformation",
        default="",
        help=f"run these twins of each map instead of the map as drawn: some of {','.join(DEFORMATIONS)}",
    )
    parser.add_argument("--debug", action="store_true", help="write alignment_debug/ per run")
    parser.add_argument("--workers", type=int, default=1, help="processes; a map's layouts stay in one")
    parser.add_argument("--out", help="output folder name under ablations/")
    parser.add_argument(
        "--points", type=int, default=0,
        help="also write N dense samples per run with what the run knew there (points.csv)",
    )
    args = parser.parse_args()

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    unknown = [v for v in variants if v not in BY_NAME]
    if unknown:
        raise SystemExit(f"Unknown variant(s): {', '.join(unknown)}")
    stages = {s.strip() for s in args.stage.split(",") if s.strip()}
    staged = [v.name for v in VARIANTS if v.stage in stages and v.name not in variants]
    if stages and not staged:
        raise SystemExit(f"No variants in stage(s) {', '.join(sorted(stages))}")
    variants += staged

    deformations = [d.strip() for d in args.deformation.split(",") if d.strip()]
    unknown = [d for d in deformations if d not in DEFORMATIONS]
    if unknown:
        raise SystemExit(f"Unknown deformation(s): {', '.join(unknown)}; expected some of {', '.join(DEFORMATIONS)}")

    if args.case:
        seed, deformation, layout = _parse_case(args.case)
        deformations = [deformation] if deformation else []
        tasks = [(seed, [layout])]
    else:
        tasks = [(s, list(range(args.layouts))) for s in range(args.seed, args.seed + args.maps)]

    name = args.out or (f"synthetic-{args.case}" if args.case else f"synthetic-{datetime.now():%Y-%m-%d}-s{args.seed}")
    out_dir = os.path.join(OUT_ROOT, name)
    os.makedirs(out_dir, exist_ok=True)
    header = {
        "name": name,
        "generatorVersion": GENERATOR_VERSION,
        "codeFingerprint": _code_fingerprint(),
        "maps": len(tasks),
        "layouts": args.layouts if not args.case else 1,
        "deformations": deformations or ["drawn"],
        "variants": variants,
        "arguments": vars(args),
        "startedAt": datetime.now().isoformat(timespec="seconds"),
    }
    print(f"generator v{GENERATOR_VERSION}, code {header['codeFingerprint']} -> {out_dir}")

    started = time.perf_counter()
    rows: List[Dict[str, Any]] = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(process_map, s, ls, variants, out_dir, args.debug, deformations, args.points)
                for s, ls in tasks
            ]
            for future in as_completed(futures):
                map_rows, line = future.result()
                rows.extend(map_rows)
                print(line, flush=True)
    else:
        for s, ls in tasks:
            map_rows, line = process_map(s, ls, variants, out_dir, args.debug, deformations, args.points)
            rows.extend(map_rows)
            print(line, flush=True)

    header["seconds"] = round(time.perf_counter() - started, 1)
    write_results(rows, os.path.join(out_dir, "results.csv"))
    write_summary(rows, variants, os.path.join(out_dir, "summary.md"), header)
    if args.points:
        _join_points(rows, out_dir)
    _write_json(os.path.join(out_dir, "run.json"), header)
    print(f"{len(rows)} rows in {header['seconds']} s -> {os.path.join(out_dir, 'summary.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
