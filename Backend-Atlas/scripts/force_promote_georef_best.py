#!/usr/bin/env python
"""Make a dev-test case's last run its best, whatever the two scores.
Usage, from Backend-Atlas:

    python scripts/force_promote_georef_best.py --case-id pip_7sift
    python scripts/force_promote_georef_best.py --case-id protocol --test-id 52a1aedc-...

Or through the dev-loop service:

    docker compose run --rm georef-dev python scripts/force_promote_georef_best.py --case-id pip_7sift
"""

import argparse
import os
import sys
from typing import Any, Optional

# Allow running as `python scripts/force_promote_georef_best.py` from Backend-Atlas.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.utils.dev_test import force_promote_latest_to_best  # noqa: E402
from app.utils.dev_test_assets import GEOREF_ASSETS_DIR  # noqa: E402


def _find_cases(assets_root: str, case_id: str, test_id: Optional[str]) -> list[str]:
    """The test ids that have a case named *case_id*."""
    cases_root = os.path.join(assets_root, "test_cases")
    if not os.path.isdir(cases_root):
        return []
    test_ids = [test_id] if test_id else sorted(os.listdir(cases_root))
    return [
        t
        for t in test_ids
        if os.path.exists(os.path.join(cases_root, t, case_id, "config.json"))
    ]


def _scores(report: Optional[dict[str, Any]]) -> str:
    if report is None:
        return "none"
    main = (report.get("metrics") or {}).get("scoreUsed")
    raw = ((report.get("raw") or {}).get("metrics") or {}).get("scoreUsed")
    return f"main {main}, raw {raw}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--test-id", help="the map, when several share the case id")
    parser.add_argument("--assets-root", default=GEOREF_ASSETS_DIR)
    args = parser.parse_args()

    test_ids = _find_cases(args.assets_root, args.case_id, args.test_id)
    if not test_ids:
        print(f"No case {args.case_id!r} found.")
        return 1
    if len(test_ids) > 1:
        print(f"{args.case_id!r} exists on several maps; pass --test-id, one of:")
        for t in test_ids:
            print(f"  {t}")
        return 1

    test_id = test_ids[0]
    try:
        previous, promoted = force_promote_latest_to_best(
            args.assets_root, test_id, args.case_id
        )
    except ValueError as e:
        print(f"Not promoted: {e}")
        return 1

    print(f"{test_id}/{args.case_id}: best replaced by the last run")
    print(f"  before: {_scores(previous)}")
    print(f"  now:    {_scores(promoted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
