import os

import pytest

from app.utils.dev_test import build_extraction_task_args_for_case
from app.utils.dev_test_evaluator import (
    build_test_case_paths,
    evaluate_georef_test_case,
    write_geojson,
    write_report,
)

from app.tasks import process_map_extraction

MIN_IOU = 0.7


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

        for name in os.listdir(test_dir):
            case_path = os.path.join(test_dir, name)
            if not os.path.isdir(case_path):
                continue
            if os.path.exists(os.path.join(case_path, "config.json")):
                discovered.append((test_id, name))

    # Stable ordering
    discovered.sort(key=lambda x: (x[0], x[1]))
    return discovered


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

    try:
        args = build_extraction_task_args_for_case(
            assets_root=assets_root,
            test_id=test_id,
            test_case_id=test_case_id,
        )
    except FileNotFoundError as e:
        pytest.skip(str(e))
    except ValueError as e:
        pytest.skip(str(e))
    except Exception as e:
        pytest.skip(str(e))

    # Run the Celery task synchronously (no broker) via Task.apply.
    # Args are the same as the /maps/upload path.
    res = process_map_extraction.apply(args=args)

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

    report, errors_geojson = evaluate_georef_test_case(
        assets_root,
        test_id,
        test_case_id,
        min_iou=MIN_IOU,
    )

    # Persist error overlay (false positive/negative areas) for later frontend display.
    write_geojson(errors_geojson, paths.errors_geojson_path)

    # Persist latest report (overwrite)
    write_report(report, paths.report_path)

    # Basic sanity invariants
    assert report["testId"] == test_id
    assert report["testCaseId"] == test_case_id

    metrics = report["metrics"]
    first = (metrics.get("expected") or [None])[0]
    best = (first or {}).get("bestMatch") if isinstance(first, dict) else None
    first_iou = float(best.get("iou", 0.0)) if isinstance(best, dict) else 0.0
    assert 0.0 <= first_iou <= 1.0
    score_used = float(
        metrics.get("scoreUsed")
        or (metrics.get("mean") or {}).get("meanIou")
        or first_iou
    )
    assert 0.0 <= score_used <= 1.0

    if MIN_IOU is not None:
        assert score_used >= MIN_IOU
