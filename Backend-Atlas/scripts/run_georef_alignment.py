#!/usr/bin/env python
"""Run georeferencing on dev-test cases directly, without Celery or pytest.

The existing loop is ``docker compose run --rm test-backend pytest``, which boots
a container, collects every test, and runs a task containing literal
``time.sleep(2)`` calls. Tuning an annealing schedule means re-running dozens of
times a day, so seconds versus minutes compounds across the whole build.

This script skips all of that: it loads a case config, runs colour extraction
once (cached on disk afterwards), fits and applies the transform, evaluates, and
prints the numbers. Colour extraction is by far the slowest part and does not
change while alignment is being tuned, hence the cache.

Usage, from Backend-Atlas with the dependencies installed:

    python scripts/run_georef_alignment.py                     # every case
    python scripts/run_georef_alignment.py --test-id abc       # one map
    python scripts/run_georef_alignment.py --case-id pip_7sift # one case
    python scripts/run_georef_alignment.py --no-cache          # re-extract colours
    python scripts/run_georef_alignment.py --no-write          # touch nothing on disk
    python scripts/run_georef_alignment.py --reference         # + reference layer PNGs
    python scripts/run_georef_alignment.py --evidence          # + user-side evidence PNGs
    python scripts/run_georef_alignment.py --ocr               # + text mask (slow once, then cached)
    python scripts/run_georef_alignment.py --align             # Step 4 alignment (implies --ocr)
    python scripts/run_georef_alignment.py --debug             # + alignment diagnostics (implies --align)
    python scripts/run_georef_alignment.py --kind probe        # only replay-only cases
    python scripts/run_georef_alignment.py --refresh-derived   # re-run OCR even if cached

Or through the dedicated compose service, which depends on no broker, no
database and no backend:

    docker compose run --rm georef-dev
    docker compose run --rm georef-dev python scripts/run_georef_alignment.py --case-id pip_7sift
"""

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

from app.utils.color_extraction import extract_colors  # noqa: E402
from app.utils.dev_test import (  # noqa: E402
    load_case_config,
    parse_extraction_inputs,
    evaluate_and_persist_case,
    find_test_image_path,
)
from app.utils.dev_test_assets import GEOREF_ASSETS_DIR  # noqa: E402
from app.utils.dev_test_cases import (  # noqa: E402
    KIND_PROBE,
    build_case_state,
    resolve_case_kind,
)
from app.utils.dev_test_derived import ensure_text_regions  # noqa: E402
from app.utils.dev_test_evaluator import build_test_case_paths  # noqa: E402
from app.utils.georeferencing import (  # noqa: E402
    DEFAULT_GEOREF_CONFIG,
    ControlPoint,
    RunRecord,
    build_reference_layers,
    dump_reference_debug_pngs,
    georeference_features,
)

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


def extract_text_regions_cached(
    test_id: str, image_path: str, image_bgr: Any, refresh: bool = False
):
    """OCR regions for the map, from the shared derived store.

    EasyOCR takes ~135 s on CPU for a 1736x1350 scan, which is why the dev-test
    task skips text extraction entirely. But without a text mask roughly half
    the edge pixels on a labelled map are place names, so the edge map the dev
    loop shows is not the one Step 4 should be tuned against.

    These used to live in this script's private pickle cache, which meant the
    Celery path could not see them and a second case on the same map paid the
    135 s again. They are now a *derived artifact* of the map
    (``app/utils/dev_test_derived.py``): produced once, persisted under the test
    assets, shared by every case and by the task.
    """
    regions, state = ensure_text_regions(
        test_id, image_path, image_bgr, refresh=refresh
    )
    if state.detail:
        print(f"  ocr cache: {state.detail}")
    return regions or []


def _extraction_library_versions() -> dict:
    """Versions of the libraries colour extraction actually depends on.

    Part of the cache key. Learned the hard way: a cached result computed under
    OpenCV 5.0.0 was served after the image was rebuilt on 4.13, and the two
    disagree on zone geometry (IoU 0.9406 vs 0.9414). A measurement harness
    handing back a silently stale number is worse than having no cache.
    """
    import cv2
    import skimage

    return {"cv2": cv2.__version__, "skimage": skimage.__version__}


def _cache_key(image_path: str, inputs: Any) -> str:
    """Identify a colour-extraction result by everything that could change it."""
    payload = {
        "image": os.path.basename(image_path),
        "mtime": os.path.getmtime(image_path),
        "size": os.path.getsize(image_path),
        "clicks": inputs.imposed_click_positions,
        "names": inputs.imposed_colors_names,
        "radii": inputs.imposed_sampling_radii,
        "libs": _extraction_library_versions(),
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


def extract_colors_cached(image_path: str, inputs: Any, use_cache: bool) -> dict:
    key = _cache_key(image_path, inputs)
    cache_path = os.path.join(CACHE_DIR, f"{key}.pickle")

    if use_cache and os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass  # A stale or corrupt cache entry is never worth failing over.

    result = extract_colors(
        image_path,
        debug=False,
        legend_shapes=None,
        imposed_click_positions=(
            [tuple(c) for c in inputs.imposed_click_positions]
            if inputs.imposed_click_positions
            else None
        ),
        imposed_colors_names=inputs.imposed_colors_names,
        imposed_sampling_radii=(
            [int(r) for r in inputs.imposed_sampling_radii]
            if inputs.imposed_sampling_radii
            else None
        ),
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
) -> Optional[dict]:
    print(f"\n=== {test_id}/{case_id}")

    image_path = find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        print("  SKIP: map image not found")
        return None

    config = load_case_config(assets_root, test_id, case_id)
    inputs = parse_extraction_inputs(config, image_path)

    # What this case is for, and whether its stored inputs still satisfy the
    # algorithm as it stands today. Printed every run: a case authored before a
    # requirement existed otherwise runs quietly with less evidence than the
    # pipeline expects, and reports a worse number for a reason that has nothing
    # to do with the change being measured.
    run_config = DEFAULT_GEOREF_CONFIG.with_overrides(
        enable_curve_alignment=True if align else None,
        snap_to_coastline=snap,
    )
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

    record = RunRecord(run_id=f"{test_id}/{case_id}")
    record.set_inputs(caseKind=case_state.kind)

    # Always the drawn box: a case without one is blocked above, because a box
    # derived from the control points is systematically too tight (the points
    # sit inside the mapped area) and silently crops the reference layers.
    frame_bounds = inputs.frame_bounds
    record.set_inputs(frameBoundsSource="config")

    text_regions = None

    if reference:
        with record.phase("reference_layers"):
            layers = build_reference_layers(frame_bounds)
        record.set_inputs(
            referenceLayers={
                "grid": {
                    "width": layers.grid.width,
                    "height": layers.grid.height,
                    "kmPerPixel": round(layers.grid.km_per_pixel, 3),
                },
                "versions": layers.layer_versions,
                "coverage": {k: round(v, 5) for k, v in layers.coverage().items()},
            }
        )
        coverage = layers.coverage()
        print(
            "  reference: %.2f km/px  coast %.2f%%  lakes %.2f%%  rivers %.2f%%  land %.1f%%"
            % (
                layers.grid.km_per_pixel,
                coverage["coastline"] * 100,
                coverage["lakes"] * 100,
                coverage["rivers"] * 100,
                coverage["land"] * 100,
            )
        )
        if write:
            debug_dir = os.path.join(
                build_test_case_paths(assets_root, test_id, case_id).case_dir,
                "reference_debug",
            )
            dump_reference_debug_pngs(layers, debug_dir)
            print(f"  reference debug PNGs -> {debug_dir}")

    if evidence:
        # Imported here, not at module scope: evidence.py is the only part of
        # the package that needs cv2.
        import cv2

        from app.utils.georeferencing.evidence import (
            build_user_evidence,
            dump_evidence_debug_pngs,
        )

        image_bgr = cv2.imread(image_path)
        if image_bgr is None:
            print("  evidence: could not read the map image")
        else:
            if ocr:
                with record.phase("ocr"):
                    text_regions = extract_text_regions_cached(
                        test_id, image_path, image_bgr, refresh=refresh_derived
                    )
                print(f"  ocr:       {len(text_regions)} text regions")
            with record.phase("user_evidence"):
                user_evidence = build_user_evidence(
                    image_bgr,
                    text_regions=text_regions,
                    water_click_positions=inputs.water_click_positions,
                    water_sampling_radii=inputs.water_sampling_radii,
                )
            record.set_inputs(userEvidence=user_evidence.stats)
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
                print("             (no water picks in this case's config)")
            if not ocr:
                print(
                    "             (no text mask: pass --ocr, or ~half these edge"
                    " pixels are place names)"
                )
            if write:
                debug_dir = os.path.join(
                    build_test_case_paths(assets_root, test_id, case_id).case_dir,
                    "evidence_debug",
                )
                dump_evidence_debug_pngs(user_evidence, image_bgr, debug_dir)
                print(f"  evidence debug PNGs -> {debug_dir}")

    t0 = time.perf_counter()
    with record.phase("color_extraction"):
        color_result = extract_colors_cached(image_path, inputs, use_cache)
    extract_ms = (time.perf_counter() - t0) * 1000.0

    pixel_features = color_result.get("pixel_features", [])

    control_points = ControlPoint.from_pairs(
        inputs.pixel_points, inputs.geo_points_lonlat, source="sift"
    )

    aligned_model = None
    alignment = None
    if align:
        import cv2

        from app.utils.georeferencing.runner import align_map

        image_bgr = cv2.imread(image_path)
        if image_bgr is None:
            print("  align: could not read the map image")
        else:
            if text_regions is None and ocr:
                text_regions = extract_text_regions_cached(
                    test_id, image_path, image_bgr, refresh=refresh_derived
                )
            # Cleared rather than merged, so a run writing fewer files than
            # the last one cannot leave stale overlays reading as current.
            alignment_debug_dir = None
            if debug and write:
                import shutil

                alignment_debug_dir = os.path.join(
                    build_test_case_paths(assets_root, test_id, case_id).case_dir,
                    "alignment_debug",
                )
                shutil.rmtree(alignment_debug_dir, ignore_errors=True)
                os.makedirs(alignment_debug_dir, exist_ok=True)

            t0 = time.perf_counter()
            alignment = align_map(
                image_bgr,
                control_points,
                frame_bounds=frame_bounds,
                text_regions=text_regions,
                water_click_positions=inputs.water_click_positions,
                water_sampling_radii=inputs.water_sampling_radii,
                config=DEFAULT_GEOREF_CONFIG.with_overrides(
                    enable_curve_alignment=True
                ),
                record=record,
                debug_dir=alignment_debug_dir,
            )
            if alignment_debug_dir:
                print(f"  alignment debug -> {alignment_debug_dir}")
            print(
                "  align:     %s (rung %d) in %.1fs  probe %.1f px  %s"
                % (
                    alignment.method,
                    alignment.rung,
                    time.perf_counter() - t0,
                    alignment.probe_agreement_px or float("nan"),
                    "gates passed"
                    if not alignment.failed_checks
                    else "FAILED: " + ", ".join(alignment.failed_checks),
                )
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
            if alignment.used_curve_evidence:
                aligned_model = alignment.model

    t0 = time.perf_counter()
    georef = georeference_features(
        pixel_features,
        control_points,
        frame_bounds=frame_bounds,
        config=DEFAULT_GEOREF_CONFIG.with_overrides(snap_to_coastline=snap),
        record=record,
        model=aligned_model,
    )
    georef_ms = (time.perf_counter() - t0) * 1000.0
    record.set_model("chosen", georef.transform_payload)

    paths = build_test_case_paths(assets_root, test_id, case_id)
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
    print(
        f"  control points: {len(control_points)}   "
        f"zones out: {sum(len(fc.get('features', [])) for fc in georef.collections)}"
    )
    print(
        "  gcp rmse: "
        + (f"{rmse_km:.2f} km" if rmse_km is not None else "n/a")
        + f"  ({errors.get('gcpRmseStatus')})"
    )
    if report:
        metrics = report.get("metrics") or {}
        score = metrics.get("scoreUsed") or (metrics.get("mean") or {}).get("meanIou")
        print(f"  IoU: {score}")
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
        "--align",
        action="store_true",
        help="Run Step 4 curve alignment and georeference with the gated result",
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
            " correspondences, every gate with its threshold. Implies --align,"
            " since there is nothing to diagnose without it."
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
    args = parser.parse_args()

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
                evidence=args.evidence or args.ocr or args.align or args.debug,
                ocr=args.ocr or args.align or args.debug,
                align=args.align or args.debug,
                snap=not args.no_snap,
                refresh_derived=args.refresh_derived,
                strict=args.no_refresh,
                debug=args.debug,
            )
        except Exception as e:
            failures += 1
            print(f"  FAILED: {e}")
            import traceback

            traceback.print_exc()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
