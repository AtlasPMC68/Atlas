import json
from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy import text
from ..tasks import process_map_extraction
from ..celery_app import celery_app
from fastapi import Depends, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database.session import get_async_session
from app.models.features import Feature
from app.models.map import Map
from app.schemas.map import MapOut
from uuid import UUID
from datetime import date
from sqlalchemy.orm import Session
from ..db import get_db
from app.schemas.mapCreateRequest import MapCreateRequest
from uuid import UUID
from ..utils.auth import get_current_user
from app.services.maps import create_map_in_db
from geoalchemy2.functions import ST_AsGeoJSON


router = APIRouter()

import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/maps", tags=["Maps Processing"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".gif"}

@router.post("/upload")
async def upload_and_process_map(file: UploadFile = File(...), session: AsyncSession = Depends(get_async_session)):
    """Upload une carte et lance l'extraction de données"""
    
    # Validate file extension
    if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400, 
            detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    file_content = await file.read()
    
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    
    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    
    try:
        map_id = await create_map_in_db(
            db=session,
            #TODO: replace with real owner
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            title=file.filename,
            description=None,
            is_private=True,
        )
        # Launch the Celery task (pass map_id as string for JSON serialization)
        task = process_map_extraction.delay(file.filename, file_content, str(map_id))
        #TODO: either delete the created map if task fails or create cleanup mechanism
        
        logger.info(f"Map processing task started: {task.id} for file {file.filename}")
        
        return {
            "task_id": task.id,
            "filename": file.filename,
            "status": "processing_started",
            "message": f"Map upload successful. Processing started for {file.filename}",
            "map_id": str(map_id)
        }
        
    except Exception as e:
        logger.error(f"Error starting map processing: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to start processing")


@router.get("/status/{task_id}")
async def get_processing_status(task_id: str):
    """Récupère l'état d'une tâche de traitement de carte"""
    task = celery_app.AsyncResult(task_id)
    
    if task.state == "PENDING":
        response = {
            "task_id": task_id,
            "state": task.state,
            "status": "Task is waiting to be processed"
        }
    elif task.state == "PROGRESS":
        response = {
            "task_id": task_id,
            "state": task.state,
            "current": task.info.get("current", 0),
            "total": task.info.get("total", 1),
            "status": task.info.get("status", ""),
            "progress_percentage": round((task.info.get("current", 0) / task.info.get("total", 1)) * 100, 2)
        }
    elif task.state == "SUCCESS":
        response = {
            "task_id": task_id,
            "state": task.state,
            "result": task.result,
            "progress_percentage": 100
        }
    else:  # FAILURE
        response = {
            "task_id": task_id,
            "state": task.state,
            "error": str(task.info),
            "progress_percentage": 0
        }
    
    return response

@router.get("/results/{task_id}")
async def get_extraction_results(task_id: str):
    """Récupère uniquement les résultats d'extraction (si terminé)"""
    task = celery_app.AsyncResult(task_id)
    
    if task.state == "SUCCESS":
        return {
            "task_id": task_id,
            "extracted_data": task.result
        }
    elif task.state == "FAILURE":
        raise HTTPException(status_code=500, detail=f"Task failed: {task.info}")
    else:
        raise HTTPException(status_code=202, detail=f"Task not completed yet. Current state: {task.state}")
    
@router.get("/features/{map_id}")
async def get_features(
    map_id: str,
    session: AsyncSession = Depends(get_async_session)
):
    try:
        map_uuid = UUID(map_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid map_id")

    # Retrieve features with their geometry and properties
    result = await session.execute(
        select(Feature.id, Feature.properties, Feature.created_at, ST_AsGeoJSON(Feature.geometry).label('geometry_json'))
        .where(Feature.map_id == map_uuid)
    )
    features_rows = result.all()

    geojson_features = []
    for row in features_rows:
        geometry_json = json.loads(row.geometry_json)
        
        geojson_feature = {
            "type": "Feature",
            "id": str(row.id),
            "geometry": geometry_json,
            "properties": {
                **(row.properties or {}),
                "start_date": row.properties.get("start_date") if row.properties else None,
                "end_date": row.properties.get("end_date") if row.properties else None,
            }
        }
        
        geojson_features.append(geojson_feature)

    return geojson_features

@router.get("/map", response_model=list[MapOut])
async def get_maps(
    user_id: str | None = None,
    session: AsyncSession = Depends(get_async_session),
):
    from sqlalchemy import select

    if user_id:
        try:
            user_uuid = UUID(user_id)
            query = select(Map).where(Map.user_id == user_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id format")
    else:
        query = select(Map).where(Map.is_private == False)

    result = await session.execute(query)
    maps = result.scalars().all()

    return maps

# TODO refactor this endpoint
@router.post("/save")
async def create_map(
    request: MapCreateRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = UUID(user["sid"])

    new_map = Map(
        user_id=user_id,
        base_layer_id=UUID("00000000-0000-0000-0000-000000000100"),
        title=request.title,
        description=request.description,
        is_private=request.is_private,
        start_date=date(1400, 1, 1),
        end_date=date.today(),
    )
    db.add(new_map)
    db.commit()
    db.refresh(new_map)
    return {"id": new_map.id}