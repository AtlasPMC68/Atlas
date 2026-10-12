#!/usr/bin/env python
"""Run georeferencing on dev-test cases directly, without Celery or pytest."""

import argparse
import hashlib
import json
import os
import pickle
import sys
import time
from typing import Any, Optional

# Allow running as `python scripts/run_georef_alignment.py` from Backend-Atlas.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import cv2  # noqa: E402

from app.utils.dev_test import (  # noqa: E402
    load_case_config,
    parse_extraction_inputs,
    evaluate_and_persist_case,
    find_test_image_path,
    write_raw_zones,
)
from app.utils.dev_test_assets import GEOREF_ASSETS_DIR  # noqa: E402
from app.utils.dev_test_cases import (  # noqa: E402
    KIND_PROBE,
    build_case_state,
    resolve_case_kind,
)
from app.utils.dev_test_derived import text_regions_for_run  # noqa: E402
from app.utils.dev_test_evaluator import build_test_case_paths  # noqa: E402
from app.utils.dev_test_pixel_zones import (  # noqa: E402
    write_classified_image,
    write_pixel_zones,
)
from app.utils.extraction_steps import (  # noqa: E402
    extract_zone_colors,
    place_map,
    zone_extraction_settings,
)
from app.utils.georeferencing import (  # noqa: E402
    GCP_SOURCES,
    RunRecord,
    count_by_source,
    build_reference_layers,
    dump_reference_debug_pngs,
)
from app.utils.georeferencing.config import ambient_georef_config  # noqa: E402

CACHE_DIR = os.path.join(_BACKEND_ROOT, ".georef_cache")


def discover_cases(assets_root: str) -> list[tuple[str, str]]:
    cases_root = os.path.join(assets_root, "test_cases")
    if not os.path.isdir(cases_root):
        return []

    found: list[tuple[str, str]] = []
    for test_id in sorted(os.listdir(cases_root)):
        test_dir = os.path.join(cases_root, test_id)
        if not os.path.isdir(test_dir):
            continue
        for case_id in sorted(os.listdir(test_dir)):
            case_dir = os.path.join(test_dir, case_id)
            if os.path.exists(os.path.join(case_dir, "config.json")):
                found.append((test_id, case_id))
    return found


def _extraction_library_versions() -> dict:
    """Versions of the libraries colour extraction actually depends on."""
    import skimage

    return {"cv2": cv2.__version__, "skimage": skimage.__version__}


def _cache_key(image_path: str, inputs: Any, text_regions: Any, config: Any) -> str:
    """Identify a colour-extraction result by everything that could change it:
    the clicks, the OCR boxes the text fill uses, and every config setting
    colour extraction reads."""
    payload = {
        "image": os.path.basename(image_path),
        "mtime": os.path.getmtime(image_path),
        "size": os.path.getsize(image_path),
        "zonePicks": inputs.zone_picks,
        "legend": inputs.legend_bounds,
        "textRegions": text_regions if config.text_aware_zone_fill else None,
        "settings": zone_extraction_settings(config),
        "libs": _extraction_library_versions(),
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


def extract_colors_cached(
    image_path: str, inputs: Any, text_regions: Any, config: Any, use_cache: bool
) -> dict:
    """The task's colour extraction, cached on disk between runs."""
    key = _cache_key(image_path, inputs, text_regions, config)
    cache_path = os.path.join(CACHE_DIR, f"{key}.pickle")

    if use_cache and os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass  # A stale or corrupt cache entry is never worth failing over.

    result = extract_zone_colors(
        image_path,
        zone_picks=inputs.zone_picks,
        legend_bounds=inputs.legend_bounds,
        text_regions=text_regions,
        config=config,
    )

    if use_cache:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cache_path, "wb") as f:
                pickle.dump(result, f)
        except Exception as e:
            print(f"  (could not cache colour extraction: {e})")

    return result


def run_case(
    assets_root: str,
    test_id: str,
    case_id: str,
    use_cache: bool,
    write: bool,
    reference: bool,
    evidence: bool,
    ocr: bool,
    align: bool,
    snap: bool = True,
    refresh_derived: bool = False,
    strict: bool = False,
    debug: bool = False,
    sources: tuple = GCP_SOURCES,
) -> Optional[dict]:
    """Run one case the way the dev-test task does, step for step."""
    
    print(f"\n=== {test_id}/{case_id}")

    image_path = find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        print("  SKIP: map image not found")
        return None
    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        print("  SKIP: map image could not be read")
        return None

    config = load_case_config(assets_root, test_id, case_id)
    inputs = parse_extraction_inputs(config)

    # The deployment's ambient config with this run's flags on top, exactly
    # as the task layers a re-run's switches on its own. A run that differs
    # from ambient is written as latest, never promoted to best.
    ambient = ambient_georef_config()
    run_config = ambient.with_overrides(
        enable_curve_alignment=align,
        snap_to_coastline=snap,
        gcp_sources=tuple(sources),
    )
    ambient_values = ambient.to_dict()
    switches = {
        key: value
        for key, value in run_config.to_dict().items()
        if ambient_values[key] != value
    }

    # What this case is for, and whether its stored inputs still satisfy the
    # algorithm as it stands today. Printed every run: a case authored before a
    # requirement existed otherwise runs quietly with less evidence than the
    # pipeline expects, and reports a worse number for a reason that has nothing
    # to do with the change being measured.
    case_state = build_case_state(
        test_id=test_id,
        test_case_id=case_id,
        inputs=inputs,
        image_path=image_path,
        config=run_config,
        case_config=config,
    )
    for line in case_state.summary_lines():
        print(f"  {line}")

    if not case_state.runnable:
        # Only a human can repair this, so say so once and move on rather than
        # producing a number nobody should read.
        print("  SKIP: missing user input that cannot be re-derived")
        for blocked in case_state.requirements.blocked:
            print(f"    {blocked.requirement.remedy}")
        if write:
            case_state.write()
        if strict:
            raise RuntimeError(f"{test_id}/{case_id} is missing required user input")
        return None

    if strict and case_state.requirements.refreshable:
        raise RuntimeError(
            f"{test_id}/{case_id} needs "
            + ", ".join(s.key for s in case_state.requirements.refreshable)
            + " recomputed, and --no-refresh was given"
        )

    # The same inputs the task records, so two run records can be diffed.
    record = RunRecord(run_id=f"{test_id}/{case_id}")
    record.set_inputs(
        waterPickCount=len(inputs.water_picks[0] or []),
        legendBounds=inputs.legend_bounds,
        caseKind=case_state.kind,
        runSwitches=switches or None,
        controlPointSources=list(run_config.gcp_sources),
    )

    # A case without a framing box is blocked above.
    frame_bounds = inputs.frame_bounds
    paths = build_test_case_paths(assets_root, test_id, case_id)

    if reference:
        with record.phase("reference_layers"):
            layers = build_reference_layers(frame_bounds)
        coverage = layers.coverage()
        print(
            "  reference: %.2f km/px  coast %.2f%%  lakes %.2f%%  land %.1f%%"
            % (
                layers.grid.km_per_pixel,
                coverage["coastline"] * 100,
                coverage["lakes"] * 100,
                coverage["land"] * 100,
            )
        )
        if write:
            debug_dir = os.path.join(paths.case_dir, "reference_debug")
            dump_reference_debug_pngs(layers, debug_dir)
            print(f"  reference debug PNGs -> {debug_dir}")

    # OCR boxes, decided the way the task decides: computed when alignment
    # (or --ocr) wants them, otherwise reused from the cache for the text fill.
    with record.phase("ocr"):
        text_regions = text_regions_for_run(
            test_id,
            image_path,
            image_bgr,
            run_config,
            allow_compute=ocr or run_config.enable_curve_alignment,
            refresh=refresh_derived,
        )
    print(
        "  ocr:       "
        + (f"{len(text_regions)} text regions" if text_regions is not None else "none")
    )

    if evidence:
        from app.utils.georeferencing.evidence import (
            build_user_evidence,
            dump_evidence_debug_pngs,
        )

        with record.phase("user_evidence"):
            user_evidence = build_user_evidence(
                image_bgr,
                text_regions=text_regions,
                water_click_positions=inputs.water_picks[0],
                water_sampling_radii=inputs.water_picks[2],
                config=run_config,
                legend_bounds=inputs.legend_bounds,
            )
        st = user_evidence.stats
        print(
            "  evidence:  edges %.2f%%  straight lines %d (%.1f%% of edge px"
            " down-weighted)  water %.2f%%"
            % (
                st["edgeFraction"] * 100,
                st["straightLineCount"],
                st["suppressedEdgeFraction"] * 100,
                st["waterFraction"] * 100,
            )
        )
        if not st["hasWater"]:
            print("             (no water picks: alignment will be skipped)")
        if text_regions is None:
            print(
                "             (no text mask: pass --ocr, or ~half these edge"
                " pixels are place names)"
            )
        if write:
            debug_dir = os.path.join(paths.case_dir, "evidence_debug")
            dump_evidence_debug_pngs(user_evidence, image_bgr, debug_dir)
            print(f"  evidence debug PNGs -> {debug_dir}")

    t0 = time.perf_counter()
    with record.phase("color_extraction"):
        color_result = dict(
            extract_colors_cached(image_path, inputs, text_regions, run_config, use_cache)
        )
    extract_ms = (time.perf_counter() - t0) * 1000.0

    classified_rgb = color_result.pop("classified_rgb", None)
    pixel_features = color_result.get("pixel_features", [])
    record.set_errors(
        textFill=color_result.get("text_fill"),
        zoneGaps=color_result.get("zone_gaps"),
    )
    pixel_zones_snapshot = json.loads(json.dumps(pixel_features))

    alignment_debug_dir = None
    if debug and write and run_config.enable_curve_alignment:
        import shutil

        # Cleared rather than merged, so a run writing fewer files than the
        # last one cannot leave stale overlays reading as current.
        alignment_debug_dir = os.path.join(paths.case_dir, "alignment_debug")
        shutil.rmtree(alignment_debug_dir, ignore_errors=True)
        os.makedirs(alignment_debug_dir, exist_ok=True)

    # The task's own step: only the selected sources, for every stage below,
    # so --sources city means the cities alone throughout.
    t0 = time.perf_counter()
    placement = place_map(
        image_bgr,
        inputs.control_points,
        frame_bounds=frame_bounds,
        legend_bounds=inputs.legend_bounds,
        water_picks=inputs.water_picks,
        text_regions=text_regions,
        config=run_config,
        record=record,
        debug_dir=alignment_debug_dir,
    )
    alignment = placement.alignment
    if alignment is not None:
        if alignment_debug_dir:
            print(f"  alignment debug -> {alignment_debug_dir}")
        if alignment.skipped:
            outcome = "skipped: " + alignment.skipped
        elif alignment.failed_checks:
            outcome = "refused: " + ", ".join(alignment.failed_checks)
        else:
            outcome = "checks passed"
        print(
            "  align:     %s in %.1fs  %s"
            % (alignment.method, time.perf_counter() - t0, outcome)
        )
        for gate in alignment.gates:
            print(
                "               %-26s %s  value=%s"
                % (
                    gate.name,
                    "n/a   " if not gate.applicable else ("pass  " if gate.passed else "FAIL  "),
                    None if gate.value is None else round(gate.value, 3),
                )
            )

    t0 = time.perf_counter()
    georef = placement.georeference(pixel_features, check_points=inputs.check_points)
    georef_ms = (time.perf_counter() - t0) * 1000.0

    report = None

    if write:
        flat = [f for fc in georef.collections for f in fc.get("features", [])]
        os.makedirs(paths.case_dir, exist_ok=True)
        with open(paths.extracted_zones_path, "w", encoding="utf-8") as f:
            json.dump(
                {"type": "FeatureCollection", "features": flat},
                f,
                indent=2,
                ensure_ascii=False,
            )
        write_raw_zones(paths.case_dir, georef.raw_collections)
        write_pixel_zones(paths.case_dir, pixel_zones_snapshot)
        write_classified_image(paths.case_dir, classified_rgb)

        if case_state.kind == KIND_PROBE:
            # A probe has no ground truth by design. Scoring it would mean
            # inventing something to compare against, which is worse than
            # reporting no number at all -- the zones and the overlays are the
            # deliverable, and you read them with your eyes.
            print("  (probe case: zones written, not scored)")
        elif os.path.exists(paths.expected_zones_path):
            report = evaluate_and_persist_case(
                assets_root=assets_root,
                test_id=test_id,
                test_case_id=case_id,
                min_iou=None,
                allow_best_promotion=not switches,
            )
        else:
            print(
                "  (regression case with no expected zones: nothing to score."
                " Draw them, or mark the test kind='probe')"
            )

        record.write(paths.case_dir)
        case_state.write(paths.case_dir)

    errors = record.errors
    rmse_km = errors.get("gcpRmseKm")
    by_source = count_by_source(placement.control_points)
    print(
        f"  control points: {len(placement.control_points)} "
        f"({', '.join(f'{k}={v}' for k, v in by_source.items())})   "
        f"zones out: {sum(len(fc.get('features', [])) for fc in georef.collections)}"
    )
    print(
        "  gcp rmse: "
        + (f"{rmse_km:.2f} km" if rmse_km is not None else "n/a")
        + f"  ({errors.get('gcpRmseStatus')})"
        + "".join(
            f"  {source} {value:.2f} km"
            for source, value in (errors.get("gcpRmseKmBySource") or {}).items()
            if value is not None
        )
    )
    checks = errors.get("checkPoints")
    if checks:
        by_model = checks.get("byModel") or {}
        print(
            f"  check points: {checks['count']}  RMS {checks['rmseKm']} km"
            f"  median {checks['medianKm']} km  max {checks['maxKm']} km"
            f"  (GCP-only affine: {by_model.get('gcp_affine')} km)"
        )
    if report:
        metrics = report.get("metrics") or {}
        score = metrics.get("scoreUsed") or (metrics.get("mean") or {}).get("meanIou")
        print(f"  IoU: {score}")
    if switches:
        print(f"  (non-ambient run, not promoted to best: {sorted(switches)})")
    print(f"  timing: colours {extract_ms:.0f} ms, georef {georef_ms:.0f} ms")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-root", default=GEOREF_ASSETS_DIR)
    parser.add_argument("--test-id", default="", help="Only cases of this map")
    parser.add_argument("--case-id", default="", help="Only cases with this id")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Re-run colour extraction instead of reusing the cached result",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write zones, report or run record",
    )
    parser.add_argument(
        "--reference",
        action="store_true",
        help="Build the reference layers and dump a debug PNG per layer",
    )
    parser.add_argument(
        "--evidence",
        action="store_true",
        help="Build the user-side evidence and dump debug overlays",
    )
    parser.add_argument(
        "--no-snap",
        action="store_true",
        help=(
            "Disable blind coastline snapping. Recommended when judging"
            " alignment: snapping corrects transform error after the fact, so it"
            " hides the thing you are trying to measure."
        ),
    )
    parser.add_argument(
        "--no-align",
        action="store_true",
        help=(
            "Skip Step 4 curve alignment and place the map with the control-point"
            " model alone: the floor alignment is measured against. Alignment"
            " is on by default, as in production."
        ),
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help=(
            "Run text extraction so the edge map has a text mask. Slow on the"
            " first run (~135 s/map on CPU), cached afterwards. Implies --evidence."
        ),
    )
    parser.add_argument(
        "--kind",
        default="all",
        choices=("all", "regression", "probe"),
        help=(
            "Which cases to run. 'regression' cases are scored against drawn"
            " expected zones; 'probe' cases only persist the clicks so a map can"
            " be replayed quickly. Default: all."
        ),
    )
    parser.add_argument(
        "--refresh-derived",
        action="store_true",
        help=(
            "Recompute derived artifacts (OCR text regions) even when a usable"
            " one is cached. Use when text extraction itself changed."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Write the per-run alignment diagnostics into the case's"
            " alignment_debug/ folder: the reference coastline drawn through"
            " the transform onto the map, per-control-point residuals, ICP"
            " correspondences, every gate with its threshold. Needs alignment,"
            " so it cannot be combined with --no-align."
        ),
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help=(
            "Fail instead of recomputing a missing derived artifact, and fail on"
            " a case missing user input. For checking which cases are behind the"
            " current algorithm without paying to bring them up to date."
        ),
    )
    parser.add_argument(
        "--sources",
        default=",".join(GCP_SOURCES),
        help=(
            "Comma-separated control point sources to fit from, among"
            f" {', '.join(GCP_SOURCES)}. Default: all. Run the same case with"
            " 'sift', 'city' and both to see what each carries on its own."
        ),
    )
    args = parser.parse_args()

    if args.debug and args.no_align:
        print("--debug diagnoses the alignment, so it cannot be combined with --no-align")
        return 1

    sources = tuple(s.strip() for s in args.sources.split(",") if s.strip())
    unknown = [s for s in sources if s not in GCP_SOURCES]
    if not sources or unknown:
        print(f"--sources must list some of {', '.join(GCP_SOURCES)}; got {args.sources!r}")
        return 1
    sources = tuple(s for s in GCP_SOURCES if s in sources)

    cases = discover_cases(args.assets_root)
    if args.test_id:
        cases = [c for c in cases if c[0] == args.test_id]
    if args.case_id:
        cases = [c for c in cases if c[1] == args.case_id]
    if args.kind != "all":
        cases = [c for c in cases if resolve_case_kind(c[0], c[1]) == args.kind]

    if not cases:
        print("No matching cases found.")
        return 1

    failures = 0
    for test_id, case_id in cases:
        try:
            run_case(
                args.assets_root,
                test_id,
                case_id,
                use_cache=not args.no_cache,
                write=not args.no_write,
                reference=args.reference,
                evidence=args.evidence or args.ocr or args.debug,
                ocr=args.ocr,
                align=not args.no_align,
                snap=not args.no_snap,
                refresh_derived=args.refresh_derived,
                strict=args.no_refresh,
                debug=args.debug,
                sources=sources,
            )
        except Exception as e:
            failures += 1
            print(f"  FAILED: {e}")
            import traceback

            traceback.print_exc()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
