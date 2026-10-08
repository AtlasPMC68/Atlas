"""A dev-test case's stored inputs: excluding control points from a re-run,
editing a case, and check points that are also fitted."""

import json

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.utils.georeferencing import ControlPoint

FRAME = {"west": -80.0, "south": 40.0, "east": -60.0, "north": 60.0}
ZONE_PICK = [{"x": 0.5, "y": 0.5, "name": "Zone", "radius": 20, "kind": "zone"}]
WATER_PICK = [{"x": 0.1, "y": 0.1, "name": "Mer", "radius": 20, "kind": "water"}]
BEST_FILES = ("best_report.json", "zones_best.geojson", "zones_raw_best.geojson")


def _points():
    """Five SIFT points and two cities."""
    sift = [
        ControlPoint.sift((40.0 * i + 10, 25.0 * (i % 3) + 10), (-78.0 + 3 * i, 42.0 + 2 * (i % 3)))
        for i in range(5)
    ]
    cities = [
        ControlPoint.from_city((70.0, 90.0), (-74.0, 48.0), 6325494, "Québec"),
        ControlPoint.from_city((150.0, 40.0), (-66.0, 44.0), 6077243, "Montréal"),
    ]
    return sift + cities


def test_exclusion_drops_by_stored_index_whatever_the_source():
    from app.utils.dev_test import drop_control_points

    points = _points()
    kept, dropped = drop_control_points(points, [6, 1, 1])

    assert dropped == [1, 6]
    assert kept == [points[i] for i in (0, 2, 3, 4, 5)]
    assert [cp.source for cp in kept].count("city") == 1


def test_an_out_of_range_index_is_refused_rather_than_ignored():
    from app.utils.dev_test import drop_control_points

    with pytest.raises(ValueError, match="out of range"):
        drop_control_points(_points(), [7])


def _save_case(tmp_path, monkeypatch, imposed):
    import app.utils.dev_test as dev_test

    monkeypatch.setattr(dev_test, "TEST_CASES_DIR", str(tmp_path / "cases"))
    dev_test.write_test_config(
        parent_test_id="t",
        test_case_id="c",
        test_case_name="c",
        control_points=_points(),
        check_points=[],
        imposed_colors=imposed,
        frame_bounds=FRAME,
        legend={"present": False, "bounds": None},
    )
    return tmp_path / "cases" / "t" / "c"


def test_editing_a_case_forgets_its_best_run(tmp_path, monkeypatch):
    """The old best was scored on other clicks: kept, it would outrank every
    run on the new ones."""
    case_dir = _save_case(tmp_path, monkeypatch, ZONE_PICK)
    for name in BEST_FILES:
        (case_dir / name).write_text("{}", encoding="utf-8")

    _save_case(tmp_path, monkeypatch, ZONE_PICK + WATER_PICK)

    assert not any((case_dir / name).exists() for name in BEST_FILES)


def test_resaving_identical_inputs_keeps_the_best_run(tmp_path, monkeypatch):
    case_dir = _save_case(tmp_path, monkeypatch, ZONE_PICK)
    (case_dir / "best_report.json").write_text("{}", encoding="utf-8")

    _save_case(tmp_path, monkeypatch, ZONE_PICK)

    assert (case_dir / "best_report.json").exists()


def test_a_stored_check_point_that_is_also_fitted_is_refused(tmp_path, monkeypatch):
    import app.routers.dev_test as router
    import app.utils.dev_test as dev_test
    from app.utils.auth import get_current_user_id

    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    ok, png = cv2.imencode(".png", np.full((120, 200, 3), 200, dtype=np.uint8))
    assert ok
    (maps_dir / "cp.png").write_bytes(png.tobytes())
    monkeypatch.setattr(dev_test, "MAPS_DIR", str(maps_dir))

    quebec_again = ControlPoint.from_city((10.0, 10.0), (-71.2, 46.8), 6325494, "Québec")
    assets_root = tmp_path / "assets"
    case_dir = assets_root / "test_cases" / "cp" / "case"
    case_dir.mkdir(parents=True)
    (case_dir / "config.json").write_text(
        json.dumps(
            {
                "georef": {
                    "controlPoints": [cp.to_dict() for cp in _points()],
                    "checkPoints": [quebec_again.to_dict()],
                    "frameBounds": FRAME,
                    "legend": {"present": False},
                },
                "colors": {"imposed": ZONE_PICK},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(router, "GEOREF_ASSETS_DIR", str(assets_root))

    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[get_current_user_id] = lambda: "dev"
    res = TestClient(app).get("/dev-test-api/test-cases/cp/case/inputs")

    assert res.status_code == 400
    assert "also a control point" in res.json()["detail"]
