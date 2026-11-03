"""Read the run records of run folders into flat tables, the same columns for
real and synthetic runs (dev-docs/georeferencing-synthetic.md §7.5):

    docker compose run --rm georef-dev python scripts/read_georef_records.py \\
        ablations/coast-line-centre-2026-10-27 ablations/synthetic-step2-v9-2026-10-27

Writes into each folder:

    signals.csv      one row per run: id_case, id_variant, then the record's
                     signals as run_ columns (``record_signals``)
    checkpoints.csv  one row per check point of each run, as scored in
                     errors.checkPoints

The in-fit residual of the control-point affine (``run_baselineGcpRmsPx``) is
refitted from ``inputs.controlPoints`` when the record does not log it (runs
without alignment, records written before it was logged);
``run_baselineRefitted`` says which. ``run_kmPerPixel`` is the control-point
affine's scale in ground km at the reference latitude.
"""

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, Iterator, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.utils.georeferencing import ControlPoint, fit_affine_from_control_points, record_signals  # noqa: E402
from app.utils.georeferencing.gates import gcp_rms_px  # noqa: E402
from app.utils.georeferencing.projection import webmercator_meters_to_km  # noqa: E402
from app.utils.georeferencing.records import RUN_RECORD_FILENAME  # noqa: E402

SIGNALS_FILE = "signals.csv"
CHECKPOINTS_FILE = "checkpoints.csv"

#: Where the synthetic runner keeps its cases inside a run folder.
_SYNTHETIC_CASES = "cases"

_CHECK_FIELDS = ("source", "name", "errorKm", "gcpAffineErrorKm", "coastDistanceKm", "nearestControlPx", "insideControlHull")


def records(run_dir: str) -> Iterator[Tuple[str, str, Dict[str, Any]]]:
    """(case, variant, record) for every run under *run_dir*, sorted. A real
    case is ``<test>/<case>``, a synthetic one its case id."""
    found = []
    for root, _dirs, files in os.walk(run_dir):
        if RUN_RECORD_FILENAME in files:
            case = os.path.relpath(os.path.dirname(root), run_dir).replace(os.sep, "/")
            if case.startswith(_SYNTHETIC_CASES + "/"):
                case = case[len(_SYNTHETIC_CASES) + 1:]
            found.append((case, os.path.basename(root), os.path.join(root, RUN_RECORD_FILENAME)))
    for case, variant, path in sorted(found):
        with open(path, encoding="utf-8") as f:
            yield case, variant, json.load(f)


def refit_baseline_px(record: Dict[str, Any]) -> Optional[float]:
    """The control-point affine's in-fit RMS in pixels, refitted from the
    record's control points, as ``gates.gcp_rms_px`` logs it (unweighted)."""
    points = (record.get("inputs") or {}).get("controlPoints") or []
    if len(points) < 3:
        return None
    # The source only sets weights, which the baseline does not use.
    cps = [ControlPoint.sift((p["pixel"]["x"], p["pixel"]["y"]), (p["geo"]["lon"], p["geo"]["lat"])) for p in points]
    return gcp_rms_px(fit_affine_from_control_points(cps), cps)


def signal_row(case: str, variant: str, record: Dict[str, Any]) -> Dict[str, Any]:
    signals = record_signals(record)
    refitted = signals["baselineGcpRmsPx"] is None
    if refitted:
        signals["baselineGcpRmsPx"] = refit_baseline_px(record)
    signals["baselineRefitted"] = refitted
    mpp, lat = signals["metersPerPixel"], signals["referenceLatitude"]
    signals["kmPerPixel"] = None if mpp is None or lat is None else webmercator_meters_to_km(mpp, lat)
    return {"id_case": case, "id_variant": variant, **{f"run_{k}": v for k, v in signals.items()}}


def check_rows(case: str, variant: str, record: Dict[str, Any], km_per_pixel: Optional[float]) -> List[Dict[str, Any]]:
    points = ((record.get("errors") or {}).get("checkPoints") or {}).get("points") or []
    return [
        {"id_case": case, "id_variant": variant, "id_point": i, "kmPerPixel": km_per_pixel, **{k: p.get(k) for k in _CHECK_FIELDS}}
        for i, p in enumerate(points)
    ]


def _write(rows: List[Dict[str, Any]], path: str) -> None:
    columns: List[str] = []
    for row in rows:
        columns.extend(k for k in row if k not in columns)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_run(run_dir: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    signals, checks = [], []
    for case, variant, record in records(run_dir):
        row = signal_row(case, variant, record)
        signals.append(row)
        checks.extend(check_rows(case, variant, record, row["run_kmPerPixel"]))
    return signals, checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", help="run folders holding <case>/<variant>/run_record.json")
    args = parser.parse_args()
    for run_dir in args.runs:
        signals, checks = read_run(run_dir)
        _write(signals, os.path.join(run_dir, SIGNALS_FILE))
        _write(checks, os.path.join(run_dir, CHECKPOINTS_FILE))
        refitted = sum(bool(r["run_baselineRefitted"]) for r in signals)
        print(f"{run_dir}: {len(signals)} runs ({refitted} baselines refitted), {len(checks)} check points")
    return 0


if __name__ == "__main__":
    sys.exit(main())
