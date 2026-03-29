import json
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
from app.utils.dev_test import (
    delete_dev_test,
    list_dev_test_cases,
    list_dev_tests,
    run_evaluate_case_blocking,
    slugify_test_case,
    upload_dev_test,
)
from app.utils.dev_test_assets import GEOREF_ASSETS_DIR, ZONES_DIR
from app.utils.dev_test_evaluator import build_test_case_paths

router = APIRouter(prefix="/dev-test-api", tags=["Dev Test"])


def _safe_id(value: str, label: str = "id") -> str:
    """Slugify *value* and reject it if the result is empty."""
    slug = slugify_test_case(value)
    if not slug:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label}: must contain at least one alphanumeric character",
        )
    return slug


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
