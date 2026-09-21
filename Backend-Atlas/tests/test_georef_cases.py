import json
import os

import pytest

from app.utils.dev_test import build_extraction_task_kwargs_for_case, inspect_case
from app.utils.dev_test_cases import KIND_PROBE
from app.utils.dev_test_evaluator import build_test_case_paths
from app.utils.georeferencing.requirements import MissingUserInputError

from app.tasks import GEOREF_CONFIG, process_dev_test_extraction

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

    kwargs = build_extraction_task_kwargs_for_case(
        assets_root=assets_root,
        test_id=test_id,
        test_case_id=test_case_id,
    )

    # Run the Celery task synchronously (no broker) via Task.apply.
    # The task writes zones.geojson and the evaluation report itself.
    res = process_dev_test_extraction.apply(kwargs=kwargs)

    if res.failed():
        raise AssertionError(
            f"Extraction failed for {test_id}/{test_case_id}: {res.result}"
        )


@pytest.mark.parametrize("test_id,test_case_id", _discover_cases(_assets_root()))
def test_dev_test_case_evaluation(test_id: str, test_case_id: str):
    assets_root = _assets_root()
    label = f"{test_id}/{test_case_id}"

    # Resolve the case against what the current algorithm needs *before*
    # spending a pipeline run on it. Two outcomes are not failures and two are.
    try:
        state, _inputs = inspect_case(
            assets_root=assets_root,
            test_id=test_id,
            test_case_id=test_case_id,
            config=GEOREF_CONFIG,
        )
    except FileNotFoundError as e:
        pytest.skip(str(e))
    except ValueError as e:
        pytest.fail(f"Unreadable case config for {label}: {e}")

    state.write()

    # A probe case is a persisted set of clicks for replaying a map quickly. It
    # has no ground truth on purpose, so there is nothing here to assert.
    if state.kind == KIND_PROBE:
        pytest.skip(f"{label} is a probe case: replay-only, never scored")

    # A regression case with no expected zones is a broken regression case, not
    # a probe. Skipping it would silently drop coverage, which is exactly the
    # thing declaring the kind exists to prevent -- so fail and say which it is.
    paths = build_test_case_paths(assets_root, test_id, test_case_id)
    if not os.path.exists(paths.expected_zones_path):
        pytest.fail(
            f"{label} is a regression case but has no expected zones at"
            f" {paths.expected_zones_path}. Draw them, or mark the test as a"
            f" probe (kind='probe') if it is only meant for replaying."
        )

    # Missing *user* input cannot be repaired by re-running anything, so this is
    # a hard failure carrying the remedy rather than a silent degraded run.
    try:
        state.requirements.raise_if_blocked(label)
    except MissingUserInputError as e:
        pytest.fail(str(e))

    # Rerun extraction from saved anchors/options so we test the current algorithm.
    # The task writes zones.geojson, evaluates, and persists the report itself.
    _rerun_extraction_from_config(assets_root, test_id, test_case_id)

    # Report is written by the task; just read it back.
    if not os.path.exists(paths.report_path):
        pytest.fail(
            f"No report written after rerun for {label}: {paths.report_path}"
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
