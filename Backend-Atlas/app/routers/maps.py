import logging
import os
import re
from datetime import datetime
from uuid import UUID
import json
from json import JSONDecodeError

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import not_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.database.session import get_async_session
from app.models.features import Feature
from app.models.map import Map
from app.schemas.map import MapOut
from app.schemas.mapCreateRequest import MapCreateRequest
from app.services.maps import create_map_in_db
from app.utils.sift_key_points_finder import find_coastline_keypoints

from ..celery_app import celery_app
from ..db import get_db
from ..tasks import process_map_extraction
from ..utils.auth import get_current_user, get_current_user_id

router = APIRouter()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/maps", tags=["Maps Processing"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".gif"}


@router.post("/upload")
async def upload_and_process_map(
    image_points: str | None = Form(None),
    world_points: str | None = Form(None),
    enable_georeferencing: bool = Form(True),
    enable_color_extraction: bool = Form(True),
    enable_shapes_extraction: bool = Form(False),
    enable_text_extraction: bool = Form(False),
    test_id: str | None = Form(None),
    test_case: str | None = Form(None),
    is_test: bool = Form(False),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    def _slugify_test_case(value: str) -> str:
        # Keep this conservative: only allow simple filename-safe tokens.
        slug = value.strip().lower()
        slug = re.sub(r"\s+", "-", slug)
        slug = re.sub(r"[^a-z0-9_-]", "", slug)
        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-_")
        return slug[:80]

    def _write_test_config(
        parent_test_id: str,
        test_case_id: str,
        test_case_name: str | None,
        original_filename: str | None,
        img_pts: list | None,
        world_pts: list | None,
    ) -> None:
        # Store under Backend-Atlas/tests/assets/test_cases/<testId>
        base_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(os.path.dirname(base_dir))
        assets_dir = os.path.join(root_dir, "tests", "assets")
        cases_root = os.path.join(assets_dir, "test_cases")
        case_dir = os.path.join(cases_root, parent_test_id)
        os.makedirs(case_dir, exist_ok=True)

        config_path = os.path.join(case_dir, f"{test_case_id}_config.json")
        config_payload = {
            "testId": parent_test_id,
            "testCase": test_case_name or test_case_id,
            "testCaseId": test_case_id,
            "updatedAt": datetime.utcnow().isoformat() + "Z",
            "filename": original_filename,
            "georef": {
                "imagePoints": img_pts,
                "worldPoints": world_pts,
            },
            "options": {
                "enableGeoreferencing": enable_georeferencing,
                "enableColorExtraction": enable_color_extraction,
                "enableShapesExtraction": enable_shapes_extraction,
                "enableTextExtraction": enable_text_extraction,
            },
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_payload, f, indent=2, ensure_ascii=False)

    # Validate file extension
    if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    incoming_test_id = test_id.strip() if isinstance(test_id, str) else ""
    parent_test_id = _slugify_test_case(incoming_test_id) if incoming_test_id else ""

    test_case_name = test_case.strip() if isinstance(test_case, str) else ""
    test_case_id = _slugify_test_case(test_case_name) if test_case_name else ""

    # TODO: Handle that better, not good
    # Backward-compat: if only test_case is provided (older clients), treat it as the parent test id.
    if not parent_test_id and test_case_id and not incoming_test_id:
        parent_test_id = test_case_id
        test_case_id = "default"
        test_case_name = "default"

    is_test_mode = bool(parent_test_id) or bool(is_test)

    pixel_points_list = None
    geo_points_list = None
    img_pts: list | None = None
    world_pts: list | None = None

    # Parse matched point pairs for SIFT georeferencing
    if enable_georeferencing and image_points and world_points:
        try:
            img_pts = json.loads(image_points)  # list of {"x":..,"y":..}
            world_pts = json.loads(world_points)  # list of {"lat":..,"lng":..}

            # Basic structural validation
            if not isinstance(img_pts, list) or not isinstance(world_pts, list):
                raise ValueError("image_points and world_points must be JSON arrays")

            if len(img_pts) != len(world_pts):
                raise ValueError(
                    "image_points and world_points must have the same length"
                )

            pixel_points_list = [(float(p["x"]), float(p["y"])) for p in img_pts]
            geo_points_list = [(float(p["lng"]), float(p["lat"])) for p in world_pts]
        except (JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid georeferencing payload: {e}",
            )

    file_content = await file.read()

    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        # In test mode, do not create a map in the database.
        # Prefer the stable parent test id so reruns overwrite the same test map assets.
        from uuid import uuid4

        if is_test_mode:
            map_id_str = parent_test_id or str(uuid4())

            # Persist the latest anchor point config for this (testId,testCase).
            # Only write when a test_case is provided, otherwise we can't associate a scenario.
            if test_case_id:
                try:
                    _write_test_config(
                        parent_test_id=map_id_str,
                        test_case_id=test_case_id,
                        test_case_name=(test_case_name or None),
                        original_filename=file.filename,
                        img_pts=img_pts,
                        world_pts=world_pts,
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to write test config for {map_id_str}/{test_case_id}: {e}"
                    )

        else:
            map_id = await create_map_in_db(
                db=session,
                user_id=UUID(user_id),
                title=file.filename,
                description=None,
                is_private=True,
            )
            map_id_str = str(map_id)

        task = process_map_extraction.delay(
            file.filename,
            file_content,
            map_id_str,
            pixel_points_list,
            geo_points_list,
            enable_color_extraction,
            enable_shapes_extraction,
            enable_text_extraction,
            is_test_mode,
            test_case_id or None,
        )
        # TODO: either delete the created map if task fails or create cleanup mechanism

        logger.info(f"Map processing task started: {task.id} for file {file.filename}")

        return {
            "task_id": task.id,
            "filename": file.filename,
            "status": "processing_started",
            "message": f"Map upload successful. Processing started for {file.filename}",
            # For tests, map_id is a synthetic identifier, not a DB id.
            "map_id": map_id_str,
        }

    except Exception as e:
        logger.error(f"Error starting map processing: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to start processing")


@router.get("/status/{task_id}")
async def get_processing_status(task_id: str):
    """Get the status of a map processing task"""
    task = celery_app.AsyncResult(task_id)

    if task.state == "PENDING":
        response = {
            "task_id": task_id,
            "state": task.state,
            "status": "Task is waiting to be processed",
        }
    elif task.state == "PROGRESS":
        response = {
            "task_id": task_id,
            "state": task.state,
            "current": task.info.get("current", 0),
            "total": task.info.get("total", 1),
            "status": task.info.get("status", ""),
            "progress_percentage": round(
                (task.info.get("current", 0) / task.info.get("total", 1)) * 100, 2
            ),
        }
    elif task.state == "SUCCESS":
        response = {
            "task_id": task_id,
            "state": task.state,
            "result": task.result,
            "progress_percentage": 100,
        }
    else:  # FAILURE
        response = {
            "task_id": task_id,
            "state": task.state,
            "error": str(task.info),
            "progress_percentage": 0,
        }

    return response


@router.get("/results/{task_id}")
async def get_extraction_results(task_id: str):
    """Get extraction results only if completed"""
    task = celery_app.AsyncResult(task_id)

    if task.state == "SUCCESS":
        return {"task_id": task_id, "extracted_data": task.result}
    elif task.state == "FAILURE":
        raise HTTPException(status_code=500, detail=f"Task failed: {task.info}")
    else:
        raise HTTPException(
            status_code=202,
            detail=f"Task not completed yet. Current state: {task.state}",
        )


@router.get("/features/{map_id}")
async def get_features(map_id: str, session: AsyncSession = Depends(get_async_session)):
    try:
        map_uuid = UUID(map_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid map_id")

    result = await session.execute(select(Feature).where(Feature.map_id == map_uuid))
    features_rows = result.scalars().all()

    all_features = []
    for f in features_rows:
        feature_data = f.data.get("features", [])
        if feature_data:
            feature = feature_data[0]
            feature["id"] = str(f.id)

            props = feature.get("properties", {})
            feature["start_date"] = props.get("start_date")
            feature["end_date"] = props.get("end_date")
            all_features.append(feature)

    return all_features


@router.get("/map", response_model=list[MapOut])
async def get_maps(
    user_id: str | None = None,
    session: AsyncSession = Depends(get_async_session),
):
    if user_id:
        try:
            user_id = UUID(user_id)
            query = select(Map).where(Map.user_id == user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id format")
    else:
        query = select(Map).where(not_(Map.is_private))

    result = await session.execute(query)
    maps = result.scalars().all()

    return maps


# TODO real save on that endpoint
@router.post("/save")
async def save_map(
    request: MapCreateRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return 1


@router.post("/coastline-keypoints")
async def get_coastline_keypoints(
    west: float = Form(...),
    south: float = Form(...),
    east: float = Form(...),
    north: float = Form(...),
    width: int = Form(1024),
    height: int = Form(768),
):
    """Find SIFT keypoints on coastlines within geographic bounds."""
    try:
        bounds = {"west": west, "south": south, "east": east, "north": north}
        result = find_coastline_keypoints(bounds, width, height)

        return {
            "status": "success",
            "keypoints": result["keypoints"],
            "total": result["total"],
            "bounds": bounds,
        }
    except Exception as e:
        logger.error(f"Error finding coastline keypoints: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
