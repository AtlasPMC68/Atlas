"""Forcing a dev-test case's last run to become its best, whatever the scores."""

import json
import os

import pytest

from app.utils.dev_test import force_promote_latest_to_best
from app.utils.dev_test_evaluator import build_test_case_paths

TEST_ID = "t"
CASE_ID = "c"
#: (last run file, best file) for every artifact a best run keeps.
RUN_TO_BEST = (
    ("zones.geojson", "zones_best.geojson"),
    ("zones_raw.geojson", "zones_raw_best.geojson"),
)


def _report(score: float, test_id: str = TEST_ID) -> dict:
    return {
        "testId": test_id,
        "testCaseId": CASE_ID,
        "metrics": {"scoreUsed": score},
        "raw": {"metrics": {"scoreUsed": score - 0.1}},
    }


def _write(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _case(tmp_path, *, last: dict, best: dict | None, inputs: dict | None = None):
    """A case dir holding a last run (and its record), and optionally a best."""
    case_dir = tmp_path / "test_cases" / TEST_ID / CASE_ID
    case_dir.mkdir(parents=True)
    _write(case_dir / "report.json", last)
    _write(case_dir / "run_record.json", {"inputs": inputs or {}})
    for run_file, best_file in RUN_TO_BEST:
        _write(case_dir / run_file, {"run": run_file})
        if best is not None:
            _write(case_dir / best_file, {"old": best_file})
    if best is not None:
        _write(case_dir / "best_report.json", best)
    return case_dir


def _read(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_a_worse_run_replaces_best_with_every_artifact(tmp_path):
    case_dir = _case(tmp_path, last=_report(0.5), best=_report(0.9))

    previous, promoted = force_promote_latest_to_best(str(tmp_path), TEST_ID, CASE_ID)

    assert previous["metrics"]["scoreUsed"] == 0.9
    assert promoted["metrics"]["scoreUsed"] == 0.5
    assert _read(case_dir / "best_report.json") == _report(0.5)
    for run_file, best_file in RUN_TO_BEST:
        assert _read(case_dir / best_file) == {"run": run_file}


def test_a_case_without_a_best_gets_one(tmp_path):
    case_dir = _case(tmp_path, last=_report(0.5), best=None)

    previous, _ = force_promote_latest_to_best(str(tmp_path), TEST_ID, CASE_ID)

    assert previous is None
    assert _read(case_dir / "best_report.json") == _report(0.5)


@pytest.mark.parametrize(
    "inputs",
    [{"runSwitches": {"snap_to_coastline": False}}, {"excludedControlPoints": [2]}],
)
def test_a_run_on_non_default_settings_is_refused(tmp_path, inputs):
    case_dir = _case(tmp_path, last=_report(0.5), best=_report(0.9), inputs=inputs)

    with pytest.raises(ValueError, match="non-default settings"):
        force_promote_latest_to_best(str(tmp_path), TEST_ID, CASE_ID)

    assert _read(case_dir / "best_report.json") == _report(0.9)
    assert _read(case_dir / "zones_best.geojson") == {"old": "zones_best.geojson"}


def test_a_case_never_run_is_refused(tmp_path):
    (tmp_path / "test_cases" / TEST_ID / CASE_ID).mkdir(parents=True)

    with pytest.raises(ValueError, match="no scored last run"):
        force_promote_latest_to_best(str(tmp_path), TEST_ID, CASE_ID)


def test_a_report_from_another_case_is_refused(tmp_path):
    case_dir = _case(tmp_path, last=_report(0.5, test_id="other"), best=_report(0.9))

    with pytest.raises(ValueError, match="belongs to other/c"):
        force_promote_latest_to_best(str(tmp_path), TEST_ID, CASE_ID)

    assert _read(case_dir / "best_report.json") == _report(0.9)


def test_paths_match_the_evaluator(tmp_path):
    """The run/best file names above are the evaluator's, not a copy that drifts."""
    paths = build_test_case_paths(str(tmp_path), TEST_ID, CASE_ID)
    names = {
        (paths.extracted_zones_path, paths.best_zones_path),
        (paths.raw_zones_path, paths.best_raw_zones_path),
    }
    assert {(os.path.basename(a), os.path.basename(b)) for a, b in names} == set(RUN_TO_BEST)
