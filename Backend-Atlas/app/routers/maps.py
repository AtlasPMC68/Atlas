import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import not_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.database.session import get_async_session
from app.models.features import Feature
from app.models.map import Map
from app.schemas.map import MapOut
from app.schemas.mapCreateRequest import MapCreateRequest
from app.services.maps import create_map_in_db


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
    file: UploadFile = File(...), 
    session: AsyncSession = Depends(get_async_session),
    user_id: str = Depends(get_current_user_id)
):
    """Upload a map and start data extraction"""    
    # Validate file extension
    if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
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
        print(user_id)
        map_id = await create_map_in_db(
            db=session,
            user_id = UUID(user_id),
            title=file.filename,
            description=None,
            is_private=True,
        )
        # Launch the Celery task (pass map_id as string for JSON serialization)
        task = process_map_extraction.delay(file.filename, file_content, str(map_id))
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
            print( f"Fetching maps for user_id: {user_id}" )
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