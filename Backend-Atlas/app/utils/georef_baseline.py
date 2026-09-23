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


def _checkpoint_map(
    points: list[Any], source: str
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    checkpoint_by_name: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for index, point in enumerate(points):
        name = point.get("name") if isinstance(point, dict) else None
        if not isinstance(name, str) or not name.strip():
            problems.append(f"georefAccuracy.checkPoints[{source}][{index}] missing name")
            continue
        name = name.strip()
        if name in checkpoint_by_name:
            problems.append(
                f"georefAccuracy.checkPoints[{source}] duplicate name: {name}"
            )
            continue
        checkpoint_by_name[name] = point
    return checkpoint_by_name, problems


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

    old_georef = baseline.get("georefAccuracy")
    if not isinstance(old_georef, dict):
        raise ValueError("The baseline has no georefAccuracy metrics")
    new_georef = current["georefAccuracy"]

    for name in ("controlPointCount", "checkpointCount"):
        if int(old_georef[name]) != int(new_georef[name]):
            problems.append(f"georefAccuracy.{name} changed")

    for name in LOWER_IS_BETTER[2:]:
        old = float(old_georef[name])
        new = float(new_georef[name])
        delta = allowed_delta(old, new)
        if new > old + delta:
            problems.append(f"georefAccuracy.{name} increased from {old} to {new}")
        elif new + delta < old:
            strictly_better = True

    old_points = old_georef.get("checkPoints") or []
    new_points = new_georef.get("checkPoints") or []
    if len(old_points) != len(new_points):
        problems.append("georefAccuracy.checkPoints count changed")
    old_by_name, old_name_problems = _checkpoint_map(old_points, "baseline")
    new_by_name, new_name_problems = _checkpoint_map(new_points, "report")
    problems.extend(old_name_problems)
    problems.extend(new_name_problems)

    missing_names = sorted(set(old_by_name) - set(new_by_name))
    unexpected_names = sorted(set(new_by_name) - set(old_by_name))
    if missing_names:
        problems.append(
            "georefAccuracy.checkPoints missing names: " + ", ".join(missing_names)
        )
    if unexpected_names:
        problems.append(
            "georefAccuracy.checkPoints unexpected names: "
            + ", ".join(unexpected_names)
        )

    for name in sorted(set(old_by_name) & set(new_by_name)):
        old_point = old_by_name[name]
        new_point = new_by_name[name]
        old_error = float(old_point["errorMeters"])
        new_error = float(new_point["errorMeters"])
        delta = allowed_delta(old_error, new_error)
        if new_error > old_error + delta:
            problems.append(
                f"georefAccuracy.checkPoints[{name}].errorMeters increased"
            )
        elif new_error + delta < old_error:
            strictly_better = True

    return not problems, strictly_better, problems