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
from ..tasks import (
    GEOREF_CONFIG,
    process_dev_test_extraction,
    warm_dev_test_text_regions,
)
from app.utils.dev_test import (
    delete_dev_test,
    delete_dev_test_case,
    list_dev_test_cases,
    list_dev_tests,
    run_evaluate_case_blocking,
    slugify_test_case,
    upload_dev_test,
    write_test_config,
)
from app.utils.dev_test_assets import GEOREF_ASSETS_DIR, ZONES_DIR
from app.utils.dev_test_cases import (
    VALID_KINDS,
    load_case_state,
    normalize_kind,
    resolve_case_kind,
)
from app.utils.georeferencing import (
    frame_bounds_to_config_entry,
    parse_control_points_field,
    parse_frame_bounds,
)
from app.utils.georeferencing.config import describe_config, parse_config_overrides
from app.utils.imposed_colors import (
    KIND_WATER,
    KIND_ZONE,
    imposed_colors_to_config_entries,
    parse_imposed_colors,
    split_imposed_colors_by_kind,
)
from app.utils.dev_test_evaluator import build_test_case_paths
from app.utils.legend import legend_to_entry, parse_legend_entry

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
    control_points: str | None = Form(None),
    frame_bounds: str | None = Form(None),
    imposed_colors: str | None = Form(None),
    legend: str | None = Form(None),
    kind: str | None = Form(None),
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

    try:
        points = parse_control_points_field(control_points)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid control_points payload: {e}"
        )

    try:
        frame_bounds_dict = parse_frame_bounds(frame_bounds)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid frame_bounds payload: {e}")

    # {"present": bool, "bounds": {...}}. Absent means the step was not answered,
    # which the case state reports; the route does not refuse it.
    try:
        legend_answered, legend_bounds = parse_legend_entry(
            json.loads(legend) if legend else None
        )
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid legend payload: {e}")

    # Pipette colors picked by the user; without them nothing is extracted at all,
    # so the georeferencing step would have no zones to transform.
    try:
        (
            all_click_positions,
            all_colors_names,
            all_sampling_radii,
            all_color_kinds,
        ) = parse_imposed_colors(imposed_colors)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid imposed_colors payload: {e}"
        )

    (
        imposed_click_positions,
        imposed_colors_names,
        imposed_sampling_radii,
    ) = split_imposed_colors_by_kind(
        all_click_positions, all_colors_names, all_sampling_radii, all_color_kinds, KIND_ZONE
    )
    (
        water_click_positions,
        water_colors_names,
        water_sampling_radii,
    ) = split_imposed_colors_by_kind(
        all_click_positions, all_colors_names, all_sampling_radii, all_color_kinds, KIND_WATER
    )

    if not imposed_click_positions:
        logger.warning(
            f"[DEV-TEST] No imposed colors provided for test_id={safe_test_id} "
            f"case={safe_test_case}; extraction will produce no zones"
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
        control_points=points,
        imposed_colors=imposed_colors_to_config_entries(
            all_click_positions,
            all_colors_names,
            all_sampling_radii,
            all_color_kinds,
        ),
        frame_bounds=frame_bounds_to_config_entry(frame_bounds_dict),
        # Only stored when this case overrides its map's kind, so the common
        # case carries no redundant flag.
        kind=normalize_kind(kind, default="") or None,
        legend=legend_to_entry(legend_bounds) if legend_answered else None,
    )

    try:
        task = process_dev_test_extraction.delay(
            filename=file.filename,
            file_content=file_content,
            test_id=safe_test_id,
            test_case=safe_test_case,
            control_points=[cp.to_dict() for cp in points],
            imposed_click_positions=imposed_click_positions,
            imposed_colors_names=imposed_colors_names,
            imposed_sampling_radii=imposed_sampling_radii,
            frame_bounds=frame_bounds_dict,
            water_click_positions=water_click_positions,
            water_colors_names=water_colors_names,
            water_sampling_radii=water_sampling_radii,
            legend_bounds=legend_bounds,
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
    kind: str = Form("regression"),
    _user_id: str = Depends(get_current_user_id),
):
    """Create a dev test by saving the map image and metadata.

    ``kind`` decides what every case on this map is for. A ``regression`` test
    is scored against expected zones you draw and gates the backend suite; a
    ``probe`` test carries no ground truth and exists to replay a map's stored
    clicks quickly while georeferencing is being changed.
    """
    if kind not in VALID_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid kind: {kind}. Allowed: {', '.join(VALID_KINDS)}",
        )

    contents = await file.read()
    return upload_dev_test(
        file_bytes=contents,
        original_filename=file.filename,
        name=name,
        kind=kind,
    )


@router.post("/tests/{test_id}/warm-text-regions")
async def warm_text_regions(
    test_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Start OCR for a test map in the background if it is not cached yet.

    Called when the import view opens, so the first case's run finds the text
    regions ready instead of paying ~135 s for them.
    """
    safe_test_id = _safe_id(test_id, "test_id")
    if not GEOREF_CONFIG.enable_curve_alignment:
        return {"state": "disabled"}

    from app.utils.dev_test import find_test_image_path
    from app.utils.dev_test_derived import inspect_text_regions

    image_path = find_test_image_path(safe_test_id)
    if not image_path:
        raise HTTPException(status_code=404, detail="Test image not found")
    if inspect_text_regions(safe_test_id, image_path).usable:
        return {"state": "cached"}

    task = warm_dev_test_text_regions.delay(safe_test_id)
    return {"state": "started", "task_id": task.id}


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


@router.delete("/test-cases/{test_id}/{test_case_id}")
async def delete_test_case(
    test_id: str,
    test_case_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Delete a single test case of a given test (map) id."""
    safe_test_id = _safe_id(test_id, "test_id")
    safe_test_case_id = _safe_id(test_case_id, "test_case_id")

    result = delete_dev_test_case(safe_test_id, safe_test_case_id)
    if result.get("status") == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Test case not found: {safe_test_id}/{safe_test_case_id}",
        )

    logger.info(
        f"[DEV-TEST] Deleted test case {safe_test_id}/{safe_test_case_id}"
    )
    return result


@router.get("/georef-config")
async def get_georef_config(_user_id: str = Depends(get_current_user_id)):
    """The georeferencing config a re-run uses when nothing is overridden.

    Feeds the tuning panel. Values are the worker's ambient config -- the file
    defaults with the environment applied -- since that is the baseline an
    override is measured against. Read-only: overrides go with the run.
    """
    return describe_config(GEOREF_CONFIG)


@router.post("/test-cases/{test_id}/{test_case_id}/run-evaluate")
async def run_evaluate_dev_test_case(
    test_id: str,
    test_case_id: str,
    min_iou: float | None = Query(
        None, description="Optional minimum IoU to mark pass/fail"
    ),
    snap_to_coastline: bool | None = Query(
        None,
        description=(
            "Blind coastline snapping. Turn it OFF when judging alignment: it"
            " corrects transform error after the fact, so it both flatters the"
            " baseline and hides the improvement you are trying to see."
        ),
    ),
    enable_curve_alignment: bool | None = Query(
        None, description="Step 4 chamfer + ICP alignment"
    ),
    clip_to_land_mask: bool | None = Query(
        None, description="Drop zone area falling in the ocean"
    ),
    config_overrides: dict | None = Body(
        None,
        description=(
            "Any GeorefConfig field, for this run only -- the tuning panel."
            " See GET /georef-config for the fields and their current values."
            " The query switches above win over the same key here."
        ),
    ),
    _user_id: str = Depends(get_current_user_id),
):
    """Re-run a test case from its saved inputs, and evaluate it if it is scored.

    Blocks until the Celery task finishes. The switches apply to this run only;
    omitting one leaves it at the worker's ambient setting. A run using any
    non-ambient switch is written as the latest result but never promoted to
    `zones_best`, because a snapped and an unsnapped run are not the same
    measurement.
    """
    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    # Validated here as well as in the task so a mistyped value is a 400 on
    # the request, not a failure buried in the worker's log.
    try:
        overrides = parse_config_overrides(config_overrides)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    overrides.update(
        {
            key: value
            for key, value in (
                ("snap_to_coastline", snap_to_coastline),
                ("enable_curve_alignment", enable_curve_alignment),
                ("clip_to_land_mask", clip_to_land_mask),
            )
            if value is not None
        }
    )

    try:
        return await run_evaluate_case_blocking(
            test_id=safe_test_id,
            test_case_id=safe_case_id,
            min_iou=min_iou,
            assets_root=GEOREF_ASSETS_DIR,
            config_overrides=overrides or None,
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


@router.get("/test-cases/{test_id}/{test_case_id}/state")
async def get_dev_test_case_state(
    test_id: str,
    test_case_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """What this case is for, and whether its stored inputs still suffice.

    Read from ``case_state.json``, written by the last run. When no run has
    happened yet the kind is still resolvable from config and metadata, so a
    minimal answer is returned rather than a 404 -- the UI needs to know whether
    to expect a score before anything has been run.
    """
    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    state = load_case_state(safe_test_id, safe_case_id)
    if state is not None:
        return state

    return {
        "testId": safe_test_id,
        "testCaseId": safe_case_id,
        "kind": resolve_case_kind(safe_test_id, safe_case_id),
        "scored": None,
        "requirements": None,
        "derived": [],
    }


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
