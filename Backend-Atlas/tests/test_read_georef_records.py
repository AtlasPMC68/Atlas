"""The run-record reader (scripts/read_georef_records.py): one row of signals
per run and one per check point, the same for real and synthetic folders; the
control-point affine's residual refitted where the record does not log it."""

import json
import os
import sys

import numpy as np
import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if not os.path.isdir(_SCRIPTS):
    pytest.skip("scripts/ is not mounted in this container", allow_module_level=True)
sys.path.insert(0, _SCRIPTS)

from read_georef_records import read_run  # noqa: E402


def _record(pixels, logged=None):
    # A known affine, so the in-fit residual is exactly the offset added below.
    points = [{"source": "sift", "pixel": {"x": x, "y": y}, "geo": {"lon": 0.01 * x, "lat": -0.01 * y}} for x, y in pixels]
    alignment = {} if logged is None else {"baselineGcpRmsPx": logged}
    return {
        "inputs": {"controlPoints": points, "controlPointCount": len(points), "alignment": alignment,
                   "referenceLatitude": 60.0, "controlPointsBySource": {"sift": len(points), "city": 0}},
        "models": {"gcp_affine": {"metersPerPixel": 2000.0}},
        "errors": {"checkPoints": {"count": 1, "points": [{"source": "city", "errorKm": 3.0, "coastDistanceKm": 120.0}]}},
        "gates": [{"name": "water_agreement", "value": 0.8}],
    }


def _put(root, case, variant, record):
    path = os.path.join(root, *case.split("/"), variant)
    os.makedirs(path)
    with open(os.path.join(path, "run_record.json"), "w", encoding="utf-8") as f:
        json.dump(record, f)


def test_real_and_synthetic_folders_read_the_same_way(tmp_path):
    square = [(0, 0), (100, 0), (0, 100), (100, 100)]
    _put(tmp_path, "test-1/protocol", "A0", _record(square))
    _put(tmp_path, "test-1/protocol", "B5b", _record(square, logged=4.2))
    _put(tmp_path, "cases/m00100-none-l00", "A0", _record(square))
    signals, checks = read_run(str(tmp_path))
    by = {(r["id_case"], r["id_variant"]): r for r in signals}
    assert set(by) == {("test-1/protocol", "A0"), ("test-1/protocol", "B5b"), ("m00100-none-l00", "A0")}

    a0, b5b = by[("test-1/protocol", "A0")], by[("test-1/protocol", "B5b")]
    assert a0["run_baselineRefitted"] and a0["run_baselineGcpRmsPx"] < 1e-6
    assert not b5b["run_baselineRefitted"] and b5b["run_baselineGcpRmsPx"] == 4.2
    # 2 km per px in EPSG:3857 is 1 ground km at 60°.
    assert np.isclose(a0["run_kmPerPixel"], 1.0)
    assert a0["run_gate.water_agreement"] == 0.8 and a0["run_siftCount"] == 4

    assert len(checks) == 3
    assert {c["id_case"] for c in checks} == {"test-1/protocol", "m00100-none-l00"}
    assert all(c["source"] == "city" and c["errorKm"] == 3.0 and np.isclose(c["kmPerPixel"], 1.0) for c in checks)
