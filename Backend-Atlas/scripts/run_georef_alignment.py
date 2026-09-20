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
from app.utils.dev_test_evaluator import build_test_case_paths  # noqa: E402
from app.utils.georeferencing import (  # noqa: E402
    DEFAULT_GEOREF_CONFIG,
    ControlPoint,
    RunRecord,
    build_reference_layers,
    dump_reference_debug_pngs,
    frame_bounds_from_geo_points,
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


def _cache_key(image_path: str, inputs: Any) -> str:
    """Identify a colour-extraction result by everything that could change it."""
    payload = {
        "image": os.path.basename(image_path),
        "mtime": os.path.getmtime(image_path),
        "size": os.path.getsize(image_path),
        "clicks": inputs.imposed_click_positions,
        "names": inputs.imposed_colors_names,
        "radii": inputs.imposed_sampling_radii,
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
) -> Optional[dict]:
    print(f"\n=== {test_id}/{case_id}")

    image_path = find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        print("  SKIP: map image not found")
        return None

    config = load_case_config(assets_root, test_id, case_id)
    inputs = parse_extraction_inputs(config, image_path)

    if not (inputs.pixel_points and inputs.geo_points_lonlat):
        print("  SKIP: no control points in config")
        return None

    record = RunRecord(run_id=f"{test_id}/{case_id}")

    # Cases predating the framing box fall back to a padded control-point box,
    # which is the best available guess at the map's working extent.
    frame_bounds = inputs.frame_bounds
    frame_source = "config"
    if not frame_bounds:
        frame_bounds = frame_bounds_from_geo_points(inputs.geo_points_lonlat)
        frame_source = "derived_from_control_points" if frame_bounds else "none"
    record.set_inputs(frameBoundsSource=frame_source)

    if reference and frame_bounds:
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

    t0 = time.perf_counter()
    with record.phase("color_extraction"):
        color_result = extract_colors_cached(image_path, inputs, use_cache)
    extract_ms = (time.perf_counter() - t0) * 1000.0

    pixel_features = color_result.get("pixel_features", [])

    control_points = ControlPoint.from_pairs(
        inputs.pixel_points, inputs.geo_points_lonlat, source="sift"
    )

    t0 = time.perf_counter()
    georef = georeference_features(
        pixel_features,
        control_points,
        frame_bounds=frame_bounds,
        config=DEFAULT_GEOREF_CONFIG,
        record=record,
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

        if os.path.exists(paths.expected_zones_path):
            report = evaluate_and_persist_case(
                assets_root=assets_root,
                test_id=test_id,
                test_case_id=case_id,
                min_iou=None,
            )
        else:
            print("  (no expected zones: evaluation skipped)")

        record.write(paths.case_dir)

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
    args = parser.parse_args()

    cases = discover_cases(args.assets_root)
    if args.test_id:
        cases = [c for c in cases if c[0] == args.test_id]
    if args.case_id:
        cases = [c for c in cases if c[1] == args.case_id]

    if not cases:
        print("No matching cases found.")
        return 1

    for test_id, case_id in cases:
        try:
            run_case(
                args.assets_root,
                test_id,
                case_id,
                use_cache=not args.no_cache,
                write=not args.no_write,
                reference=args.reference,
            )
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback

            traceback.print_exc()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
