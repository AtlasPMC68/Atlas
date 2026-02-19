import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import not_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.database.session import get_async_session
from app.models.features import Feature
from app.models.map import Map
from app.schemas.map import MapOut
from app.schemas.georeference import GeoreferencePayload
from app.schemas.mapCreateRequest import MapCreateRequest
from app.services.maps import create_map_in_db
import json
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
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    """Upload a map and start data extraction"""    
    # Validate file extension
    if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    pixel_points_list = None
    geo_points_list = None

    # Parse matched point pairs for SIFT georeferencing (only if enabled)
    if enable_georeferencing and image_points and world_points:
        img_pts = json.loads(image_points)  # list of {"x":..,"y":..}
        world_pts = json.loads(world_points)  # list of {"lat":..,"lng":..}

        pixel_points_list = [(float(p["x"]), float(p["y"])) for p in img_pts]
        geo_points_list = [(float(p["lng"]), float(p["lat"])) for p in world_pts]

    # Lire le contenu du fichier
    file_content = await file.read()
    
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        map_id = await create_map_in_db(
            db=session,
            user_id = UUID(user_id),
            title=file.filename,
            description=None,
            is_private=True,
        )
        # Lancer la tâche Celery (pass map_id as string for JSON serialization)
        task = process_map_extraction.delay(
            file.filename,
            file_content,
            str(map_id),
            pixel_points_list,
            geo_points_list,
            enable_color_extraction,
            enable_shapes_extraction,
            enable_text_extraction,
        )
        # TODO: either delete the created map if task fails or create cleanup mechanism

        logger.info(f"Map processing task started: {task.id} for file {file.filename}")

        return {
            "task_id": task.id,
            "filename": file.filename,
            "status": "processing_started",
            "message": f"Map upload successful. Processing started for {file.filename}",
            "map_id": str(map_id),
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
            start_date = props.get("start_date")
            end_date = props.get("end_date")

            feature["start_date"] = start_date
            feature["end_date"] = end_date

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
    owner_id = UUID(user["sid"])

    new_map = Map(
        owner_id,
        base_layer_id=UUID("00000000-0000-0000-0000-000000000100"),
        title=request.title,
        description=request.description,
        access_level=request.access_level,
        start_date=date(1400, 1, 1),
        end_date=date.today(),
        style_id="light",
        parent_map_id=None,
        precision=None,
    )
    db.add(new_map)
    db.commit()
    db.refresh(new_map)
    return {"id": new_map.id}


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
