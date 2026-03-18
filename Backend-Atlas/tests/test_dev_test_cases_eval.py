import os

import pytest

from app.utils.dev_test_evaluator import (
    build_test_case_paths,
    evaluate_georef_test_case,
    write_report,
)


def _assets_root() -> str:
    # Backend-Atlas root is one level up from tests/
    here = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(here)
    return os.path.join(root_dir, "tests", "assets")


def _discover_cases(assets_root: str) -> list[tuple[str, str]]:
    cases_root = os.path.join(assets_root, "test_cases")
    if not os.path.isdir(cases_root):
        return []

    discovered: list[tuple[str, str]] = []
    for test_id in os.listdir(cases_root):
        case_dir = os.path.join(cases_root, test_id)
        if not os.path.isdir(case_dir):
            continue

        # Prefer config files as the canonical list of cases
        for fn in os.listdir(case_dir):
            if fn.endswith("_config.json"):
                case_id = fn[: -len("_config.json")]
                discovered.append((test_id, case_id))

    # Fallback: if no configs exist, use zones
    if not discovered:
        for test_id in os.listdir(cases_root):
            case_dir = os.path.join(cases_root, test_id)
            if not os.path.isdir(case_dir):
                continue
            for fn in os.listdir(case_dir):
                if fn.endswith("_zones.geojson"):
                    case_id = fn[: -len("_zones.geojson")]
                    discovered.append((test_id, case_id))

    # Stable ordering
    discovered.sort(key=lambda x: (x[0], x[1]))
    return discovered


@pytest.mark.parametrize("test_id,test_case_id", _discover_cases(_assets_root()))
def test_dev_test_case_evaluation(test_id: str, test_case_id: str):
    assets_root = _assets_root()

    # Skip cases that don't have both expected+extracted zones present.
    paths = build_test_case_paths(assets_root, test_id, test_case_id)
    if not os.path.exists(paths.expected_zones_path):
        pytest.skip(
            f"Missing expected zones for {test_id}: {paths.expected_zones_path}"
        )
    if not os.path.exists(paths.extracted_zones_path):
        pytest.skip(
            f"Missing extracted zones for {test_id}/{test_case_id}: {paths.extracted_zones_path}"
        )

    min_iou_raw = os.getenv("DEV_TEST_MIN_IOU")
    min_iou = float(min_iou_raw) if min_iou_raw else None

    report = evaluate_georef_test_case(
        assets_root,
        test_id,
        test_case_id,
        min_iou=min_iou,
    )

    # Persist latest report (overwrite)
    write_report(report, paths.report_path)

    # Basic sanity invariants
    assert report["testId"] == test_id
    assert report["testCaseId"] == test_case_id

    metrics = report["metrics"]
    assert 0.0 <= metrics["primaryExpectedBestIou"] <= 1.0

    # Optional gating: set DEV_TEST_MIN_IOU=0.7 (for example) to enforce pass/fail
    if min_iou is not None:
        assert metrics["primaryExpectedBestIou"] >= min_iou
