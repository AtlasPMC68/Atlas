from __future__ import annotations

import json
import os
import tempfile
from typing import Any


HIGHER_IS_BETTER = ("meanIou", "meanPrecision", "meanRecall")
LOWER_IS_BETTER = (
    "totalFalseNegativeArea",
    "totalFalsePositiveArea",
)


def baseline_from_report(report: dict[str, Any]) -> dict[str, Any]:
    mean = report.get("metrics", {}).get("mean") or {}
    baseline = {
        name: float(mean[name]) for name in HIGHER_IS_BETTER + LOWER_IS_BETTER[:2]
    }
    return baseline


def compare_report_to_baseline(
    report: dict[str, Any],
    baseline: dict[str, Any],
    tolerance: float = 1e-6,
    relative_tolerance: float = 1e-9,
) -> tuple[bool, bool, list[str]]:
    """Return (not_worse, strictly_better, problems) for a complete baseline."""
    current = baseline_from_report(report)
    problems: list[str] = []
    strictly_better = False

    def allowed_delta(old: float, new: float) -> float:
        return tolerance + relative_tolerance * max(abs(old), abs(new), 1.0)

    for name in HIGHER_IS_BETTER:
        old = float(baseline[name])
        new = float(current[name])
        delta = allowed_delta(old, new)
        if new + delta < old:
            problems.append(f"{name} decreased from {old} to {new}")
        elif new > old + delta:
            strictly_better = True

    for name in LOWER_IS_BETTER[:2]:
        old = float(baseline[name])
        new = float(current[name])
        delta = allowed_delta(old, new)
        if new > old + delta:
            problems.append(f"{name} increased from {old} to {new}")
        elif new + delta < old:
            strictly_better = True

    return not problems, strictly_better, problems


def _write_json_atomically(path: str, data: dict[str, Any]) -> None:
    directory = os.path.dirname(path)
    fd, temporary_path = tempfile.mkstemp(dir=directory, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=2, ensure_ascii=False)
            output.write("\n")
        os.replace(temporary_path, path)
    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


def promote_best_report(config_path: str, report_path: str) -> bool:
    with open(config_path, "r", encoding="utf-8") as input_file:
        config = json.load(input_file)
    with open(report_path, "r", encoding="utf-8") as input_file:
        report = json.load(input_file)

    if (
        config.get("testId") != report.get("testId")
        or config.get("testCaseId") != report.get("testCaseId")
    ):
        raise ValueError("config.json and report.json refer to different test cases")

    best_report_path = os.path.join(os.path.dirname(config_path), "best_report.json")
    if not os.path.exists(best_report_path):
        raise ValueError(f"Missing best report baseline: {best_report_path}")
    with open(best_report_path, "r", encoding="utf-8") as input_file:
        best_report = json.load(input_file)

    if (
        best_report.get("testId") != config.get("testId")
        or best_report.get("testCaseId") != config.get("testCaseId")
    ):
        raise ValueError("best_report.json and config.json refer to different test cases")

    baseline = baseline_from_report(best_report)

    not_worse, strictly_better, problems = compare_report_to_baseline(
        report, baseline
    )
    if not not_worse:
        raise ValueError("Cannot promote a regression: " + "; ".join(problems))
    if not strictly_better:
        raise ValueError("Cannot promote: the new report is not strictly better")

    _write_json_atomically(best_report_path, report)

    case_dir = os.path.dirname(report_path)
    for source_name, target_name in (
        ("zones.geojson", "zones_best.geojson"),
        ("errors.geojson", "errors_best.geojson"),
    ):
        source_path = os.path.join(case_dir, source_name)
        target_path = os.path.join(case_dir, target_name)
        if os.path.exists(source_path):
            temporary_path = target_path + ".tmp"
            with open(source_path, "rb") as source, open(temporary_path, "wb") as target:
                target.write(source.read())
            os.replace(temporary_path, target_path)
    return True


promote_baseline = promote_best_report