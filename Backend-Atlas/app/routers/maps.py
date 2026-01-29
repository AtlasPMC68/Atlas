from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from ..tasks import process_map_extraction
from ..celery_app import celery_app
from fastapi import Depends, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database.session import get_async_session
from app.models.features import Feature
from app.models.map import Map
from app.schemas.map import MapOut
from app.schemas.georeference import GeoreferencePayload
from uuid import UUID
from datetime import date
from sqlalchemy.orm import Session
from ..db import get_db
from app.schemas.mapCreateRequest import MapCreateRequest
from uuid import UUID
from ..utils.auth import get_current_user
from app.services.maps import create_map_in_db
import json

router = APIRouter()

import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/maps", tags=["Maps Processing"])

# Tailles et types de fichiers autorisés
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".gif"}


@router.post("/sift")
async def extract_sift_keypoints(
    file: UploadFile = File(...),
):
    """Return SIFT keypoints (pixel coords) for an uploaded image.

    Request: multipart/form-data with `file`.
    Response: { image: {width,height}, count, keypoints: [{x,y,...}, ...] }
    """

    if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    file_content = await file.read()

    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
        )

    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # try:
    #     return extract_sift_keypoints_from_image_bytes(
    #         file_content,
    #         max_features=max_features,
    #     )
    # except ValueError as e:
    #     raise HTTPException(status_code=400, detail=str(e))
    # except RuntimeError as e:
    #     raise HTTPException(status_code=501, detail=str(e))
    # except Exception:
    #     logger.exception("Unexpected error extracting SIFT keypoints")
    #     raise HTTPException(status_code=500, detail="Failed to extract SIFT keypoints")

@router.post("/upload")
async def upload_and_process_map(
    image_polyline: str | None = Form(None),
    world_polyline: str  | None = Form(None),
    image_point: str | None = Form(None),
    world_point: str  | None = Form(None),
    file: UploadFile = File(...), 
    session: AsyncSession = Depends(get_async_session),
):
    
    logger.debug(f"Logger debug camarche tu")
    logger.info(f"image polyline for the pixels{image_polyline}")
    logger.info(f"world polyline for the coordinates{world_polyline}")
    logger.info(f"image point for the pixels{image_point}")
    logger.info(f"world point for the coordinates{world_point}")
    
    """Upload une carte et lance l'extraction de données"""
    
    # Validation du type de fichier
    if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400, 
            detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    pixel_control_polyline = None
    geo_control_polyline = None
    pixel_control_points = None
    geo_control_points = None
    
    # Parse polyline (list of points)
    if image_polyline and world_polyline:
        img_points = json.loads(image_polyline)      # list of {"x":..,"y":..}
        world_points = json.loads(world_polyline)    # list of {"lat":..,"lng":..}

        pixel_control_polyline = [
            (float(p["x"]), float(p["y"])) for p in img_points
        ]
        geo_control_polyline = [
            (float(p["lng"]), float(p["lat"])) for p in world_points
        ]

    # Parse single point (not in a list)
    if image_point and world_point:
        img_point = json.loads(image_point)          # single {"x":..,"y":..}
        world_pt = json.loads(world_point)           # single {"lat":..,"lng":..}

        # Wrap in list for consistency with function signature
        pixel_control_points = [(float(img_point["x"]), float(img_point["y"]))]
        geo_control_points = [(float(world_pt["lng"]), float(world_pt["lat"]))]
    
    # Lire le contenu du fichier
    file_content = await file.read()
    
    # Validation de la taille
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
            owner_id=UUID("00000000-0000-0000-0000-000000000001"),
            title=file.filename,
            description=None,
            access_level="private",
        )
        # Lancer la tâche Celery (pass map_id as string for JSON serialization)
        task = process_map_extraction.delay(
            file.filename, 
            file_content, 
            str(map_id),
            pixel_control_polyline,
            geo_control_polyline,
            pixel_control_points,
            geo_control_points
        )
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

    result = await session.execute(select(Feature).where(Feature.map_id == map_uuid))
    features_rows = result.scalars().all()

    all_features = []
    for f in features_rows:
        for feature in f.data.get("features", []):
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
    from sqlalchemy import select

    if user_id:
        try:
            owner_uuid = UUID(user_id)
            query = select(Map).where(Map.owner_id == owner_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id format")
    else:
        query = select(Map).where(Map.access_level == "public")

    result = await session.execute(query)
    maps = result.scalars().all()

    return maps

@router.post("/save")
async def create_map(
    request: MapCreateRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
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
        precision=None
    )
    db.add(new_map)
    db.commit()
    db.refresh(new_map)
    return {"id": new_map.id}