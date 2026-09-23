from __future__ import annotations

from copy import deepcopy
from typing import Any


HIGHER_IS_BETTER = ("meanIou", "meanPrecision", "meanRecall")
LOWER_IS_BETTER = (
    "totalFalseNegativeArea",
    "totalFalsePositiveArea",
    "rmseMeters",
    "medianMeters",
    "p95Meters",
    "maxMeters",
)


def baseline_from_report(report: dict[str, Any]) -> dict[str, Any]:
    mean = report.get("metrics", {}).get("mean") or {}
    georef = report.get("georefAccuracy")
    if not isinstance(georef, dict):
        raise ValueError("The report has no georefAccuracy metrics")

    baseline = {
        name: float(mean[name]) for name in HIGHER_IS_BETTER + LOWER_IS_BETTER[:2]
    }
    baseline["georefAccuracy"] = deepcopy(georef)
    return baseline


def compare_report_to_baseline(
    report: dict[str, Any], baseline: dict[str, Any], tolerance: float = 1e-6
) -> tuple[bool, bool, list[str]]:
    """Return (not_worse, strictly_better, problems) for a complete baseline."""
    current = baseline_from_report(report)
    problems: list[str] = []
    strictly_better = False

    for name in HIGHER_IS_BETTER:
        old = float(baseline[name])
        new = float(current[name])
        if new + tolerance < old:
            problems.append(f"{name} decreased from {old} to {new}")
        elif new > old + tolerance:
            strictly_better = True

    for name in LOWER_IS_BETTER[:2]:
        old = float(baseline[name])
        new = float(current[name])
        if new > old + tolerance:
            problems.append(f"{name} increased from {old} to {new}")
        elif new + tolerance < old:
            strictly_better = True

    old_georef = baseline.get("georefAccuracy")
    if not isinstance(old_georef, dict):
        raise ValueError("The baseline has no georefAccuracy metrics")
    new_georef = current["georefAccuracy"]
    for name in LOWER_IS_BETTER[2:]:
        old = float(old_georef[name])
        new = float(new_georef[name])
        if new > old + tolerance:
            problems.append(f"georefAccuracy.{name} increased from {old} to {new}")
        elif new + tolerance < old:
            strictly_better = True

    old_points = old_georef.get("checkPoints") or []
    new_points = new_georef.get("checkPoints") or []
    if len(old_points) != len(new_points):
        problems.append("georefAccuracy.checkPoints count changed")
    for index, (old_point, new_point) in enumerate(zip(old_points, new_points)):
        old_error = float(old_point["errorMeters"])
        new_error = float(new_point["errorMeters"])
        if new_error > old_error + tolerance:
            problems.append(
                f"georefAccuracy.checkPoints[{index}].errorMeters increased"
            )
        elif new_error + tolerance < old_error:
            strictly_better = True

    return not problems, strictly_better, problems