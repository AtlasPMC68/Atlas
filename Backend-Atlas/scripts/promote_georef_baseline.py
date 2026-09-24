from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.georef_baseline import promote_best_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a better georef baseline")
    parser.add_argument("config")
    parser.add_argument("report")
    args = parser.parse_args()
    try:
        promote_best_report(args.config, args.report)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Best report promoted for {args.config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())