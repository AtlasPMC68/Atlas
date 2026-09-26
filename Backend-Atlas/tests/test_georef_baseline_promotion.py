import json

import pytest

from app.utils.georef_baseline import promote_best_report


def test_promote_rejects_report_from_another_case(tmp_path):
    config = {
        "testId": "test-a",
        "testCaseId": "case-a",
    }
    report = {
        "testId": "test-b",
        "testCaseId": "case-b",
    }
    config_path = tmp_path / "config.json"
    report_path = tmp_path / "report.json"
    (tmp_path / "best_report.json").write_text(
        json.dumps({"testId": "test-a", "testCaseId": "case-a"}), encoding="utf-8"
    )
    config_path.write_text(json.dumps(config), encoding="utf-8")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="different test cases"):
        promote_best_report(str(config_path), str(report_path))

    assert json.loads(config_path.read_text(encoding="utf-8")) == config