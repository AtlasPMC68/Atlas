from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.georef_baseline import (
    baseline_from_report,
    compare_report_to_baseline,
)


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


def promote(config_path: str, report_path: str) -> bool:
    with open(config_path, "r", encoding="utf-8") as input_file:
        config = json.load(input_file)
    with open(report_path, "r", encoding="utf-8") as input_file:
        report = json.load(input_file)

    if (
        config.get("testId") != report.get("testId")
        or config.get("testCaseId") != report.get("testCaseId")
    ):
        raise ValueError(
            "config.json and report.json refer to different test cases"
        )

    baseline = config.get("nonRegressionBaseline")
    if not isinstance(baseline, dict):
        raise ValueError("config.json has no nonRegressionBaseline")

    not_worse, strictly_better, problems = compare_report_to_baseline(
        report, baseline
    )
    if not not_worse:
        raise ValueError("Cannot promote a regression: " + "; ".join(problems))
    if not strictly_better:
        raise ValueError("Cannot promote: the new report is not strictly better")

    config["nonRegressionBaseline"] = baseline_from_report(report)
    _write_json_atomically(config_path, config)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a better georef baseline")
    parser.add_argument("config")
    parser.add_argument("report")
    args = parser.parse_args()
    try:
        promote(args.config, args.report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"Baseline promoted in {args.config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())