"""The dev tool's control-point diagnostics and hand-driven exclusion.

Both broke silently when control points became one list of source-tagged
records: the diagnostics endpoints still read the old pixel/geo pair lists and
answered 500, and an exclusion was applied to task arguments that no longer
existed, so a "leave point 3 out" re-run used every point and could even be
promoted to the case's best.
"""

import inspect
import json
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG, ControlPoint

FRAME = {"west": -80.0, "south": 40.0, "east": -60.0, "north": 60.0}


def _points():
    """Five SIFT points and two cities, spread enough for leave-one-out."""
    sift = [
        ControlPoint.sift((40.0 * i + 10, 25.0 * (i % 3) + 10), (-78.0 + 3 * i, 42.0 + 2 * (i % 3)))
        for i in range(5)
    ]
    cities = [
        ControlPoint.from_city((70.0, 90.0), (-74.0, 48.0), 6325494, "Québec"),
        ControlPoint.from_city((150.0, 40.0), (-66.0, 44.0), 6077243, "Montréal"),
    ]
    return sift + cities


def _write_case(tmp_path, monkeypatch, test_id="cp", case_id="case", points=None):
    """A case on disk with a readable map, wired into every module that looks."""
    import app.routers.dev_test as router
    import app.utils.dev_test as dev_test

    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    ok, png = cv2.imencode(".png", np.full((120, 200, 3), 200, dtype=np.uint8))
    assert ok
    (maps_dir / f"{test_id}.png").write_bytes(png.tobytes())
    monkeypatch.setattr(dev_test, "MAPS_DIR", str(maps_dir))

    assets_root = tmp_path / "assets"
    case_dir = assets_root / "test_cases" / test_id / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "config.json").write_text(
        json.dumps(
            {
                "filename": f"{test_id}.png",
                "georef": {
                    "controlPoints": [cp.to_dict() for cp in (points or _points())],
                    "frameBounds": FRAME,
                    "legend": {"present": False},
                },
                "colors": {
                    "imposed": [
                        {"x": 0.5, "y": 0.5, "name": "Zone", "radius": 20, "kind": "zone"}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(router, "GEOREF_ASSETS_DIR", str(assets_root))
    return assets_root, case_dir


# --- excluding points by index ------------------------------------------------


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


def test_the_task_accepts_the_exclusion():
    from app.tasks import process_dev_test_extraction

    assert "excluded_control_points" in inspect.signature(
        process_dev_test_extraction.run
    ).parameters


def test_a_rerun_dispatches_the_exclusion(tmp_path, monkeypatch):
    import app.utils.dev_test as dev_test
    from app.tasks import process_dev_test_extraction

    assets_root, _ = _write_case(tmp_path, monkeypatch)
    sent = {}

    def _capture(**kwargs):
        sent.update(kwargs)
        return MagicMock(id="task")

    monkeypatch.setattr(process_dev_test_extraction, "delay", _capture)
    dev_test._start_extraction_for_case(
        assets_root=str(assets_root),
        test_id="cp",
        test_case_id="case",
        excluded_control_points=[2, 0],
    )

    assert sent["excluded_control_points"] == [0, 2]
    # Every stored point still travels: the task drops by stored index.
    assert len(sent["control_points"]) == 7


def test_an_exclusion_leaving_too_few_selected_points_is_refused(tmp_path, monkeypatch):
    import app.utils.dev_test as dev_test
    from app.tasks import process_dev_test_extraction

    assets_root, _ = _write_case(tmp_path, monkeypatch)
    monkeypatch.setattr(
        process_dev_test_extraction,
        "delay",
        MagicMock(side_effect=AssertionError("must not be dispatched")),
    )

    # Five SIFT points pass the requirements; dropping three leaves two.
    with pytest.raises(ValueError, match="at least 3"):
        dev_test._start_extraction_for_case(
            assets_root=str(assets_root),
            test_id="cp",
            test_case_id="case",
            config_overrides={"gcp_sources": ("sift",)},
            excluded_control_points=[0, 1, 2],
        )


def test_the_task_fits_without_the_excluded_points_and_never_promotes(
    tmp_path, monkeypatch
):
    import app.tasks as tasks
    import app.utils.dev_test as dev_test

    _assets_root, case_dir = _write_case(tmp_path, monkeypatch)
    image_path = tmp_path / "maps" / "cp.png"
    monkeypatch.setattr(tasks, "TEST_CASES_DIR", str(case_dir.parent.parent))
    monkeypatch.setattr(tasks, "MAPS_DIR", str(tmp_path / "maps"))
    monkeypatch.setattr(tasks, "resolve_case_kind", lambda *_: "regression")
    monkeypatch.setattr(tasks, "_write_dev_test_case_state", lambda *a, **k: None)
    monkeypatch.setattr(tasks, "text_regions_for_run", lambda *a, **k: None)
    monkeypatch.setattr(
        tasks,
        "extract_zone_colors",
        MagicMock(return_value={"pixel_features": [], "normalized_features": []}),
    )
    monkeypatch.setattr(tasks, "align_if_enabled", MagicMock(return_value=None))
    georef = MagicMock(return_value=MagicMock(collections=[], transform_payload=None))
    monkeypatch.setattr(tasks, "georeference_zones", georef)
    evaluate = MagicMock(return_value={"metrics": {}})
    monkeypatch.setattr(dev_test, "evaluate_and_persist_case", evaluate)
    monkeypatch.setattr(tasks.process_dev_test_extraction, "update_state", MagicMock())

    points = _points()
    result = tasks.process_dev_test_extraction.apply(
        kwargs={
            "filename": "cp.png",
            "file_content": image_path.read_bytes(),
            "test_id": "cp",
            "test_case": "case",
            "control_points": [cp.to_dict() for cp in points],
            "imposed_click_positions": [(0.5, 0.5)],
            "excluded_control_points": [3],
        }
    )
    assert result.successful(), result.result

    fitted = georef.call_args.args[1]
    assert fitted == [cp for i, cp in enumerate(points) if i != 3]
    assert evaluate.call_args.kwargs["allow_best_promotion"] is False

    record = json.loads((case_dir / "run_record.json").read_text(encoding="utf-8"))
    assert record["inputs"]["excludedControlPoints"] == [3]


# --- diagnostics --------------------------------------------------------------


def test_diagnostics_cover_every_source_with_the_configured_sigma():
    from app.utils.georeferencing.diagnostics import control_point_diagnostics

    config = DEFAULT_GEOREF_CONFIG.with_overrides(
        gcp_sigma_px_sift=4.0, gcp_sigma_px_city=9.0
    )
    out = control_point_diagnostics(_points(), FRAME, config=config)

    assert [p["source"] for p in out["points"]] == ["sift"] * 5 + ["city"] * 2
    assert [p["sigmaPx"] for p in out["points"]] == [4.0] * 5 + [9.0] * 2
    assert out["summary"]["looAvailable"] is True


@pytest.fixture
def client():
    from app.routers.dev_test import router
    from app.utils.auth import get_current_user_id

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: "dev"
    return TestClient(app)


def test_the_control_points_endpoint_answers(tmp_path, monkeypatch, client):
    _write_case(tmp_path, monkeypatch)

    res = client.get("/dev-test-api/test-cases/cp/case/control-points")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["summary"]["count"] == 7
    assert {p["source"] for p in body["points"]} == {"sift", "city"}


def test_the_control_points_image_answers(tmp_path, monkeypatch, client):
    _write_case(tmp_path, monkeypatch)

    res = client.get("/dev-test-api/test-cases/cp/case/control-points.png?view=map")

    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "image/png"


# --- reopening a case's inputs ---------------------------------------------------


def test_a_case_reopens_with_its_stored_inputs(tmp_path, monkeypatch, client):
    _write_case(tmp_path, monkeypatch)

    res = client.get("/dev-test-api/test-cases/cp/case/inputs")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["testCaseId"] == "case"
    assert body["imageUrl"] == "/dev-test/maps/cp.png"
    inputs = body["inputs"]
    assert inputs["frameBounds"] == FRAME
    assert inputs["legend"] == {"present": False, "bounds": None}
    assert len(inputs["controlPoints"]) == 7
    assert inputs["colors"] == [
        {"x": 0.5, "y": 0.5, "name": "Zone", "radius": 20, "kind": "zone", "hex": "#c8c8c8"}
    ]


def test_missing_inputs_are_absent_rather_than_null(tmp_path, monkeypatch, client):
    """The import flow reads an absent key as a step still to do."""
    _assets_root, case_dir = _write_case(tmp_path, monkeypatch)
    config = json.loads((case_dir / "config.json").read_text(encoding="utf-8"))
    del config["georef"]["frameBounds"]
    del config["georef"]["legend"]
    (case_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")

    inputs = client.get("/dev-test-api/test-cases/cp/case/inputs").json()["inputs"]

    assert "frameBounds" not in inputs
    assert "legend" not in inputs
    assert len(inputs["controlPoints"]) == 7


# --- editing a case's inputs -----------------------------------------------------


def _write_through_upload_helper(tmp_path, monkeypatch, imposed):
    import app.utils.dev_test as dev_test

    monkeypatch.setattr(dev_test, "TEST_CASES_DIR", str(tmp_path / "cases"))
    dev_test.write_test_config(
        parent_test_id="t",
        test_case_id="c",
        test_case_name="c",
        original_filename="map.png",
        control_points=_points(),
        imposed_colors=imposed,
        frame_bounds=FRAME,
        legend={"present": False, "bounds": None},
    )
    return tmp_path / "cases" / "t" / "c"


ZONE_PICK = [{"x": 0.5, "y": 0.5, "name": "Zone", "radius": 20, "kind": "zone"}]
WATER_PICK = [{"x": 0.1, "y": 0.1, "name": "Mer", "radius": 20, "kind": "water"}]


def test_editing_a_case_forgets_its_best_run(tmp_path, monkeypatch):
    """The old best was scored on other clicks: kept, it would outrank every
    run on the new ones."""
    case_dir = _write_through_upload_helper(tmp_path, monkeypatch, ZONE_PICK)
    for name in ("best_report.json", "zones_best.geojson", "errors_best.geojson"):
        (case_dir / name).write_text("{}", encoding="utf-8")

    _write_through_upload_helper(tmp_path, monkeypatch, ZONE_PICK + WATER_PICK)

    assert not any((case_dir / n).exists() for n in ("best_report.json", "zones_best.geojson", "errors_best.geojson"))


def test_resaving_identical_inputs_keeps_the_best_run(tmp_path, monkeypatch):
    case_dir = _write_through_upload_helper(tmp_path, monkeypatch, ZONE_PICK)
    (case_dir / "best_report.json").write_text("{}", encoding="utf-8")

    _write_through_upload_helper(tmp_path, monkeypatch, ZONE_PICK)

    assert (case_dir / "best_report.json").exists()
