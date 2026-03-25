import asyncio
import json
import os
import time

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from app.celery_app import celery_app
from app.services.dev_test import (
    delete_dev_test,
    evaluate_and_persist_case,
    find_test_image_path,
    list_dev_test_cases,
    list_dev_tests,
    register_dev_test,
    upload_dev_test,
)
from app.utils.dev_test_assets import GEOREF_ASSETS_DIR, ZONES_DIR

router = APIRouter(prefix="/dev-test-api", tags=["Dev Test"])


@router.put("/georef_zones/{map_id}")
async def save_dev_test_zones(map_id: str, payload: dict = Body(...)):
    """Save or overwrite the dev-test zones GeoJSON file for a given map.

    This is used only by the internal test editor UI.
    """

    os.makedirs(ZONES_DIR, exist_ok=True)
    zones_output_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")

    with open(zones_output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return {"status": "ok", "map_id": map_id}


@router.get("/georef_zones/{map_id}")
async def get_dev_test_zones(map_id: str):
    """Return the current dev-test zones GeoJSON for a given map.

    This mirrors the static file under /dev-test/georef_zones but avoids any
    browser caching issues by serving it via the API layer.
    """

    zones_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")
    if not os.path.exists(zones_path):
        raise HTTPException(status_code=404, detail="Zones file not found")

    with open(zones_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


@router.get("/tests")
async def list_tests():
    """List available dev tests based on files in tests/assets/georef/maps."""

    return list_dev_tests()


@router.post("/tests")
async def register_test(payload: dict = Body(...)):
    """Register or update metadata for a dev test."""

    map_id = payload.get("mapId")
    name = payload.get("name")
    if not map_id or not isinstance(map_id, str):
        raise HTTPException(status_code=400, detail="mapId is required")
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail="name is required")

    return register_dev_test(map_id=map_id, name=name)


@router.post("/tests/upload")
async def upload_test(file: UploadFile = File(...), name: str = Form(...)):
    """Create a dev test by saving the map image and metadata."""

    contents = await file.read()
    return upload_dev_test(
        file_bytes=contents, original_filename=file.filename, name=name
    )


@router.delete("/tests/{map_id}")
async def delete_test(map_id: str):
    """Delete a dev test: image file, zones GeoJSON, and metadata entry."""

    return delete_dev_test(map_id)


@router.get("/test-cases/{test_id}")
async def list_test_cases(test_id: str):
    """List available test cases for a given test (map) id."""

    return list_dev_test_cases(test_id)


@router.post("/test-cases/{test_id}/{test_case_id}/run")
async def run_dev_test_case(test_id: str, test_case_id: str):
    """Rerun extraction for a saved dev-test case using its anchor config."""

    if not os.path.isdir(GEOREF_ASSETS_DIR):
        raise HTTPException(
            status_code=500, detail="Georef test assets directory missing"
        )

    from app.utils.dev_test_evaluator import build_test_case_paths

    paths = build_test_case_paths(GEOREF_ASSETS_DIR, test_id, test_case_id)
    config_path = paths.config_path
    if not os.path.exists(config_path):
        raise HTTPException(status_code=404, detail=f"Config not found: {config_path}")

    image_path = find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        raise HTTPException(
            status_code=404,
            detail=f"Test image not found for test_id={test_id} under {os.path.join(GEOREF_ASSETS_DIR, 'maps')}",
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config JSON: {e}")

    georef = config.get("georef") if isinstance(config.get("georef"), dict) else {}
    options = config.get("options") if isinstance(config.get("options"), dict) else {}

    enable_georeferencing = bool(options.get("enableGeoreferencing", True))
    enable_color_extraction = bool(options.get("enableColorExtraction", True))
    enable_shapes_extraction = bool(options.get("enableShapesExtraction", False))
    enable_text_extraction = bool(options.get("enableTextExtraction", False))

    pixel_points_list = None
    geo_points_list = None

    if enable_georeferencing:
        img_pts = georef.get("imagePoints")
        world_pts = georef.get("worldPoints")
        if (
            isinstance(img_pts, list)
            and isinstance(world_pts, list)
            and len(img_pts) == len(world_pts)
        ):
            try:
                pixel_points_list = [(float(p["x"]), float(p["y"])) for p in img_pts]
                geo_points_list = [
                    (float(p["lng"]), float(p["lat"])) for p in world_pts
                ]
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid georef points in config: {e}"
                )

    try:
        with open(image_path, "rb") as f:
            file_content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read test image: {e}")

    filename = config.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        filename = os.path.basename(image_path)

    try:
        from app.tasks import process_map_extraction

        task = process_map_extraction.delay(
            filename,
            file_content,
            test_id,
            pixel_points_list,
            geo_points_list,
            enable_color_extraction,
            enable_shapes_extraction,
            enable_text_extraction,
            True,
            test_case_id,
        )
        return {
            "status": "processing_started",
            "task_id": task.id,
            "map_id": test_id,
            "test_id": test_id,
            "test_case_id": test_case_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start extraction: {e}")


@router.post("/test-cases/{test_id}/{test_case_id}/evaluate")
async def evaluate_dev_test_case(
    test_id: str,
    test_case_id: str,
    min_iou: float | None = Query(
        None, description="Optional minimum IoU to mark pass/fail"
    ),
):
    """Evaluate one dev test case and persist a report JSON."""

    if not os.path.isdir(GEOREF_ASSETS_DIR):
        raise HTTPException(
            status_code=500, detail="Georef test assets directory missing"
        )

    try:
        return evaluate_and_persist_case(
            assets_root=GEOREF_ASSETS_DIR,
            test_id=test_id,
            test_case_id=test_case_id,
            min_iou=min_iou,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-cases/{test_id}/{test_case_id}/run-evaluate")
async def run_evaluate_dev_test_case(
    test_id: str,
    test_case_id: str,
    min_iou: float | None = Query(
        None, description="Optional minimum IoU to mark pass/fail"
    ),
    timeout_s: float = Query(
        300.0,
        ge=1.0,
        le=3600.0,
        description="Max seconds to wait for the extraction task before returning 202",
    ),
    poll_interval_s: float = Query(
        1.0,
        ge=0.1,
        le=10.0,
        description="Polling interval while waiting for the extraction task",
    ),
):
    """Run extraction from saved anchors *and then* evaluate."""

    if not os.path.isdir(GEOREF_ASSETS_DIR):
        raise HTTPException(
            status_code=500, detail="Georef test assets directory missing"
        )

    from app.utils.dev_test_evaluator import build_test_case_paths

    paths = build_test_case_paths(GEOREF_ASSETS_DIR, test_id, test_case_id)
    config_path = paths.config_path
    if not os.path.exists(config_path):
        raise HTTPException(status_code=404, detail=f"Config not found: {config_path}")

    image_path = find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        raise HTTPException(
            status_code=404,
            detail=f"Test image not found for test_id={test_id} under {os.path.join(GEOREF_ASSETS_DIR, 'maps')}",
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config JSON: {e}")

    georef = config.get("georef") if isinstance(config.get("georef"), dict) else {}
    options = config.get("options") if isinstance(config.get("options"), dict) else {}

    enable_georeferencing = bool(options.get("enableGeoreferencing", True))
    enable_color_extraction = bool(options.get("enableColorExtraction", True))
    enable_shapes_extraction = bool(options.get("enableShapesExtraction", False))
    enable_text_extraction = bool(options.get("enableTextExtraction", False))

    pixel_points_list = None
    geo_points_list = None

    if enable_georeferencing:
        img_pts = georef.get("imagePoints")
        world_pts = georef.get("worldPoints")
        if (
            isinstance(img_pts, list)
            and isinstance(world_pts, list)
            and len(img_pts) == len(world_pts)
        ):
            try:
                pixel_points_list = [(float(p["x"]), float(p["y"])) for p in img_pts]
                geo_points_list = [
                    (float(p["lng"]), float(p["lat"])) for p in world_pts
                ]
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid georef points in config: {e}"
                )

    try:
        with open(image_path, "rb") as f:
            file_content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read test image: {e}")

    filename = config.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        filename = os.path.basename(image_path)

    try:
        from app.tasks import process_map_extraction

        task = process_map_extraction.delay(
            filename,
            file_content,
            test_id,
            pixel_points_list,
            geo_points_list,
            enable_color_extraction,
            enable_shapes_extraction,
            enable_text_extraction,
            True,
            test_case_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start extraction: {e}")

    async_result = celery_app.AsyncResult(task.id)
    deadline = time.monotonic() + float(timeout_s)
    while not async_result.ready():
        if time.monotonic() >= deadline:
            return JSONResponse(
                status_code=202,
                content={
                    "status": "processing_started",
                    "task_id": task.id,
                    "test_id": test_id,
                    "test_case_id": test_case_id,
                    "message": "Extraction still running; poll /maps/status/{task_id} then call /evaluate",
                },
            )
        await asyncio.sleep(float(poll_interval_s))

    if async_result.state != "SUCCESS":
        raise HTTPException(
            status_code=500,
            detail=f"Extraction task ended in state {async_result.state}: {async_result.info}",
        )

    try:
        report = evaluate_and_persist_case(
            assets_root=GEOREF_ASSETS_DIR,
            test_id=test_id,
            test_case_id=test_case_id,
            min_iou=min_iou,
        )
        return {
            "status": "ok",
            "task_id": task.id,
            "task_state": async_result.state,
            "report": report,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-cases/{test_id}/{test_case_id}/report")
async def get_dev_test_case_report(test_id: str, test_case_id: str):
    """Get the latest persisted evaluation report for a test case."""

    from app.utils.dev_test_evaluator import build_test_case_paths

    paths = build_test_case_paths(GEOREF_ASSETS_DIR, test_id, test_case_id)
    report_path = paths.report_path
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
