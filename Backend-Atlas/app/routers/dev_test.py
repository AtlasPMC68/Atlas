import json
import logging
import os

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)

from app.utils.auth import get_current_user_id
from ..tasks import process_dev_test_extraction
from app.utils.dev_test import (
    delete_dev_test,
    list_dev_test_cases,
    list_dev_tests,
    run_evaluate_case_blocking,
    slugify_test_case,
    upload_dev_test,
    write_test_config,
)
from app.utils.dev_test_assets import GEOREF_ASSETS_DIR, ZONES_DIR
from app.utils.dev_test_evaluator import build_test_case_paths

router = APIRouter(prefix="/dev-test-api", tags=["Dev Test"])

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _safe_id(value: str, label: str = "id") -> str:
    """Slugify *value* and reject it if the result is empty."""
    slug = slugify_test_case(value)
    if not slug:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label}: must contain at least one alphanumeric character",
        )
    return slug


@router.post("/upload")
async def upload_dev_test_map(
    test_id: str = Form(...),
    test_case: str = Form(...),
    image_points: str | None = Form(None),
    world_points: str | None = Form(None),
    file: UploadFile = File(...),
    _user_id: str = Depends(get_current_user_id),
):
    """Upload a map image and start a dev-test extraction (file-only, no DB persistence)."""
    safe_test_id = _safe_id(test_id, "test_id")
    safe_test_case = _safe_id(test_case, "test_case")

    filename = (file.filename or "").lower()
    if not any(filename.endswith(ext) for ext in _ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
        )

    pixel_points_list = None
    geo_points_list = None

    if image_points and world_points:
        try:
            img_pts = json.loads(image_points)
            world_pts = json.loads(world_points)
            if not isinstance(img_pts, list) or not isinstance(world_pts, list):
                raise ValueError("image_points and world_points must be JSON arrays")
            if len(img_pts) != len(world_pts):
                raise ValueError(
                    "image_points and world_points must have the same length"
                )
            pixel_points_list = [(float(p["x"]), float(p["y"])) for p in img_pts]
            geo_points_list = [(float(p["lng"]), float(p["lat"])) for p in world_pts]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid georeferencing payload: {e}"
            )

    file_content = await file.read()
    if len(file_content) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {_MAX_FILE_SIZE // (1024 * 1024)}MB",
        )
    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Persist anchor points immediately so the test case can be rerun from config
    # even if the async task fails. We do this synchronously before dispatching.
    write_test_config(
        parent_test_id=safe_test_id,
        test_case_id=safe_test_case,
        test_case_name=test_case,
        original_filename=file.filename,
        img_pts=[{"x": float(p[0]), "y": float(p[1])} for p in pixel_points_list]
        if pixel_points_list
        else None,
        world_pts=[{"lng": float(p[0]), "lat": float(p[1])} for p in geo_points_list]
        if geo_points_list
        else None,
    )

    try:
        task = process_dev_test_extraction.delay(
            filename=file.filename,
            file_content=file_content,
            test_id=safe_test_id,
            test_case=safe_test_case,
            pixel_points=pixel_points_list,
            geo_points_lonlat=geo_points_list,
        )
        logger.info(
            f"[DEV-TEST] Started extraction task {task.id} for test_id={safe_test_id} case={safe_test_case}"
        )
        return {
            "task_id": task.id,
            "map_id": safe_test_id,
            "status": "processing_started",
        }
    except Exception as e:
        logger.error(f"[DEV-TEST] Error starting extraction: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to start dev-test processing"
        )


@router.put("/georef_zones/{map_id}")
async def save_dev_test_zones(
    map_id: str,
    payload: dict = Body(...),
    _user_id: str = Depends(get_current_user_id),
):
    """Save or overwrite the dev-test zones GeoJSON file for a given map.

    This is used only by the internal test editor UI.
    """
    safe_map_id = _safe_id(map_id, "map_id")

    os.makedirs(ZONES_DIR, exist_ok=True)
    zones_output_path = os.path.join(ZONES_DIR, f"{safe_map_id}_zones.geojson")

    with open(zones_output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return {"status": "ok", "map_id": safe_map_id}


@router.get("/georef_zones/{map_id}")
async def get_dev_test_zones(
    map_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Return the current dev-test zones GeoJSON for a given map.

    This mirrors the static file under /dev-test/georef_zones but avoids any
    browser caching issues by serving it via the API layer.
    """
    safe_map_id = _safe_id(map_id, "map_id")

    zones_path = os.path.join(ZONES_DIR, f"{safe_map_id}_zones.geojson")
    if not os.path.exists(zones_path):
        raise HTTPException(status_code=404, detail="Zones file not found")

    with open(zones_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


@router.get("/tests")
async def list_tests(_user_id: str = Depends(get_current_user_id)):
    """List available dev tests based on files in tests/assets/georef/maps."""

    return list_dev_tests()


@router.post("/tests/upload")
async def upload_test(
    file: UploadFile = File(...),
    name: str = Form(...),
    _user_id: str = Depends(get_current_user_id),
):
    """Create a dev test by saving the map image and metadata."""

    contents = await file.read()
    return upload_dev_test(
        file_bytes=contents, original_filename=file.filename, name=name
    )


@router.delete("/tests/{map_id}")
async def delete_test(
    map_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Delete a dev test: image file, zones GeoJSON, and metadata entry."""
    safe_map_id = _safe_id(map_id, "map_id")

    return delete_dev_test(safe_map_id)


@router.get("/test-cases/{test_id}")
async def list_test_cases(
    test_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """List available test cases for a given test (map) id."""
    safe_test_id = _safe_id(test_id, "test_id")

    return list_dev_test_cases(safe_test_id)


# Not really used for now but would be if we wanted to trigger evaluation through frontend
@router.post("/test-cases/{test_id}/{test_case_id}/run-evaluate")
async def run_evaluate_dev_test_case(
    test_id: str,
    test_case_id: str,
    min_iou: float | None = Query(
        None, description="Optional minimum IoU to mark pass/fail"
    ),
    _user_id: str = Depends(get_current_user_id),
):
    """Run extraction from saved anchors *and then* evaluate.

    This endpoint blocks until the Celery task finishes.
    """
    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    try:
        return await run_evaluate_case_blocking(
            test_id=safe_test_id,
            test_case_id=safe_case_id,
            min_iou=min_iou,
            assets_root=GEOREF_ASSETS_DIR,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-cases/{test_id}/{test_case_id}/report")
async def get_dev_test_case_report(
    test_id: str,
    test_case_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Get the latest persisted evaluation report for a test case."""
    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    paths = build_test_case_paths(GEOREF_ASSETS_DIR, safe_test_id, safe_case_id)
    report_path = paths.report_path
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-cases/{test_id}/{test_case_id}/best-report")
async def get_dev_test_case_best_report(
    test_id: str,
    test_case_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Get the best persisted evaluation report for a test case."""
    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    paths = build_test_case_paths(GEOREF_ASSETS_DIR, safe_test_id, safe_case_id)
    report_path = paths.best_report_path
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Best report not found")

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
