import json
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from ..tasks import process_map_extraction
from ..celery_app import celery_app
from fastapi import Depends, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database.session import get_async_session
from app.models.features import Feature
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping

router = APIRouter()

import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/maps", tags=["Maps Processing"])

# Tailles et types de fichiers autorisés
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".gif"}

@router.post("/upload")
async def upload_and_process_map(file: UploadFile = File(...)):
    """Upload une carte et lance l'extraction de données"""
    
    # Validation du type de fichier
    if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400, 
            detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
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
        # Lancer la tâche Celery
        task = process_map_extraction.delay(file.filename, file_content)
        
        logger.info(f"Map processing task started: {task.id} for file {file.filename}")
        
        return {
            "task_id": task.id,
            "filename": file.filename,
            "status": "processing_started",
            "message": f"Map upload successful. Processing started for {file.filename}"
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
async def get_features(map_id: str, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Feature).where(Feature.map_id == map_id))
    features = result.scalars().all()

    def feature_to_dict(f: Feature):
        d = f.__dict__.copy()
        # Convert geometry WKBElement to GeoJSON dict
        if f.geometry:
            shape = to_shape(f.geometry)  # shapely geometry
            d['geometry'] = json.loads(json.dumps(mapping(shape)))
        else:
            d['geometry'] = None
        return d

    return [feature_to_dict(f) for f in features]