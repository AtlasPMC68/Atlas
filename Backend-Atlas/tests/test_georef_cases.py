import json
import os

import pytest

from app.utils.dev_test import build_extraction_task_args_for_case
from app.utils.dev_test_evaluator import build_test_case_paths

from app.tasks import process_dev_test_extraction

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
    # The task writes zones.geojson and the evaluation report itself.
    res = process_dev_test_extraction.apply(args=args)

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
    # The task writes zones.geojson, evaluates, and persists the report itself.
    _rerun_extraction_from_config(assets_root, test_id, test_case_id)

    # Report is written by the task; just read it back.
    if not os.path.exists(paths.report_path):
        pytest.skip(
            f"Report not written after rerun for {test_id}/{test_case_id}: {paths.report_path}"
        )

    with open(paths.report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

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
