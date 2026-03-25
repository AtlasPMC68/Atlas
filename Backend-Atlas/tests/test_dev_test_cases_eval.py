import os
import json

import pytest

from app.utils.dev_test_evaluator import (
    build_test_case_paths,
    evaluate_georef_test_case,
    write_geojson,
    write_report,
)

from app.tasks import process_map_extraction


def _assets_root() -> str:
    # Backend-Atlas root is one level up from tests/
    here = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(here)
    return os.path.join(root_dir, "tests", "assets", "georef")


def _discover_cases(assets_root: str) -> list[tuple[str, str]]:
    cases_root = os.path.join(assets_root, "test_cases")
    if not os.path.isdir(cases_root):
        return []

    discovered: list[tuple[str, str]] = []
    for test_id in os.listdir(cases_root):
        test_dir = os.path.join(cases_root, test_id)
        if not os.path.isdir(test_dir):
            continue

        # New layout: directories under test_id
        for name in os.listdir(test_dir):
            case_path = os.path.join(test_dir, name)
            if not os.path.isdir(case_path):
                continue
            if os.path.exists(os.path.join(case_path, "config.json")):
                discovered.append((test_id, name))

    # Fallback: if no configs exist, use zones
    if not discovered:
        for test_id in os.listdir(cases_root):
            test_dir = os.path.join(cases_root, test_id)
            if not os.path.isdir(test_dir):
                continue

            # New layout fallback: zones.geojson
            for name in os.listdir(test_dir):
                case_path = os.path.join(test_dir, name)
                if os.path.isdir(case_path) and os.path.exists(
                    os.path.join(case_path, "zones.geojson")
                ):
                    discovered.append((test_id, name))

    # Stable ordering
    discovered.sort(key=lambda x: (x[0], x[1]))
    return discovered


def _find_test_image_path(assets_root: str, test_id: str) -> str | None:
    maps_dir = os.path.join(assets_root, "maps")
    if not os.path.isdir(maps_dir):
        return None
    for fn in os.listdir(maps_dir):
        stem, _ext = os.path.splitext(fn)
        if stem == test_id:
            return os.path.join(maps_dir, fn)
    return None


def _rerun_extraction_from_config(
    assets_root: str, test_id: str, test_case_id: str
) -> None:
    """Rerun the current extraction pipeline using saved anchors/options.

    This ensures CI/dev batch evaluation tests the *current* algorithm, not a stale
    extracted GeoJSON left on disk.
    """

    paths = build_test_case_paths(assets_root, test_id, test_case_id)
    if not os.path.exists(paths.config_path):
        pytest.skip(f"Missing config for {test_id}/{test_case_id}: {paths.config_path}")

    image_path = _find_test_image_path(assets_root, test_id)
    if not image_path or not os.path.exists(image_path):
        pytest.skip(
            f"Missing test image for {test_id} under {os.path.join(assets_root, 'maps')}"
        )

    try:
        with open(paths.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        pytest.skip(f"Invalid config JSON for {test_id}/{test_case_id}: {e}")

    georef = config.get("georef") if isinstance(config.get("georef"), dict) else {}
    options = config.get("options") if isinstance(config.get("options"), dict) else {}

    enable_georeferencing = bool(options.get("enableGeoreferencing", True))
    enable_color_extraction = bool(options.get("enableColorExtraction", True))
    enable_shapes_extraction = bool(options.get("enableShapesExtraction", False))
    enable_text_extraction = bool(options.get("enableTextExtraction", False))

    pixel_points_list = None
    geo_points_list = None
    if enable_georeferencing:
        img_pts = georef.get("imagePoints")
        world_pts = georef.get("worldPoints")
        if (
            isinstance(img_pts, list)
            and isinstance(world_pts, list)
            and len(img_pts) == len(world_pts)
        ):
            try:
                pixel_points_list = [(float(p["x"]), float(p["y"])) for p in img_pts]
                geo_points_list = [
                    (float(p["lng"]), float(p["lat"])) for p in world_pts
                ]
            except Exception as e:
                pytest.skip(f"Invalid anchor points for {test_id}/{test_case_id}: {e}")

    try:
        with open(image_path, "rb") as f:
            file_content = f.read()
    except Exception as e:
        pytest.skip(f"Failed to read test image for {test_id}: {e}")

    filename = config.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        filename = os.path.basename(image_path)

    # Run the Celery task synchronously (no broker) via Task.apply.
    # Args are the same as the /maps/upload path.
    res = process_map_extraction.apply(
        args=[
            filename,
            file_content,
            test_id,
            pixel_points_list,
            geo_points_list,
            enable_color_extraction,
            enable_shapes_extraction,
            enable_text_extraction,
            True,
            test_case_id,
        ]
    )

    if res.failed():
        raise AssertionError(
            f"Extraction failed for {test_id}/{test_case_id}: {res.result}"
        )


@pytest.mark.parametrize("test_id,test_case_id", _discover_cases(_assets_root()))
def test_dev_test_case_evaluation(test_id: str, test_case_id: str):
    assets_root = _assets_root()

    # Skip cases that don't have expected zones present.
    paths = build_test_case_paths(assets_root, test_id, test_case_id)
    if not os.path.exists(paths.expected_zones_path):
        pytest.skip(
            f"Missing expected zones for {test_id}: {paths.expected_zones_path}"
        )

    # Rerun extraction from saved anchors/options so we test the current algorithm.
    _rerun_extraction_from_config(assets_root, test_id, test_case_id)

    if not os.path.exists(paths.extracted_zones_path):
        pytest.skip(
            f"Missing extracted zones after rerun for {test_id}/{test_case_id}: {paths.extracted_zones_path}"
        )

    min_iou_raw = os.getenv("DEV_TEST_MIN_IOU")
    min_iou = float(min_iou_raw) if min_iou_raw else None

    report, errors_geojson = evaluate_georef_test_case(
        assets_root,
        test_id,
        test_case_id,
        min_iou=min_iou,
    )

    # Persist error overlay (false positive/negative areas) for later frontend display.
    write_geojson(errors_geojson, paths.errors_geojson_path)

    # Persist latest report (overwrite)
    write_report(report, paths.report_path)

    # Basic sanity invariants
    assert report["testId"] == test_id
    assert report["testCaseId"] == test_case_id

    metrics = report["metrics"]
    assert 0.0 <= metrics["primaryExpectedBestIou"] <= 1.0
    score_used = float(
        metrics.get("scoreUsed")
        or (metrics.get("expectedBest") or {}).get("meanIou")
        or metrics.get("primaryExpectedBestIou")
    )
    assert 0.0 <= score_used <= 1.0

    # Optional gating: set DEV_TEST_MIN_IOU=0.7 (for example) to enforce pass/fail
    if min_iou is not None:
        assert score_used >= min_iou
