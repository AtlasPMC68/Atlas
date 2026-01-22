from fastapi import APIRouter, UploadFile, File, HTTPException
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
<<<<<<< HEAD
from app.schemas.feature import FeatureCreateRequest, FeatureUpdateRequest
from geoalchemy2 import WKTElement
from shapely.geometry import shape
from datetime import datetime
=======
from app.schemas.featuresCreate import FeatureCreate
from app.services.maps import create_map_in_db
>>>>>>> main

router = APIRouter()

import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/maps", tags=["Maps Processing"])

# Tailles et types de fichiers autorisés
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".gif"}

@router.post("/upload")
async def upload_and_process_map(file: UploadFile = File(...), session: AsyncSession = Depends(get_async_session)):
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
        map_id = await create_map_in_db(
            db=session,
            #TODO: replace with real owner
            owner_id=UUID("00000000-0000-0000-0000-000000000001"),
            title=file.filename,
            description=None,
            access_level="private",
        )
        # Lancer la tâche Celery (pass map_id as string for JSON serialization)
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
        query = select(Map).where(Map.owner_id == user_id)
    else:
        query = select(Map).where(Map.access_level == "public")

    result = await session.execute(query)
    maps = result.scalars().all()

    return maps

@router.post("/save")
async def create_map(
    request: MapCreateRequest,
    db: Session = Depends(get_db)
):
    new_map = Map(
        owner_id=request.owner_id,
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

@router.post("/features")
async def create_feature(
    request: FeatureCreateRequest,
    session: AsyncSession = Depends(get_async_session)
):
    """Créer une nouvelle feature sur la carte"""
    
    try:
        # Convertir la géométrie GeoJSON en WKT pour PostGIS
        geom_shape = shape(request.geometry.dict())
        wkt_geom = WKTElement(geom_shape.wkt, srid=4326)
        
        # Créer la nouvelle feature
        new_feature = Feature(
            map_id=request.map_id,
            name=request.name,
            type=request.type,
            geometry=wkt_geom,
            color=request.color,
            stroke_width=request.stroke_width,
            opacity=request.opacity,
            z_index=request.z_index,
            tags=request.tags or {},
            start_date=request.start_date,
            end_date=request.end_date,
            precision=request.precision,
            source=request.source,
            created_at=datetime.utcnow()
        )
        
        session.add(new_feature)
        await session.commit()
        await session.refresh(new_feature)
        
        # Convertir pour la réponse
        response = new_feature.__dict__.copy()
        if new_feature.geometry:
            shape_geom = to_shape(new_feature.geometry)
            response['geometry'] = json.loads(json.dumps(mapping(shape_geom)))
        
        return response
        
    except Exception as e:
        logger.error(f"Error creating feature: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create feature: {str(e)}")

@router.put("/features/{feature_id}")
async def update_feature(
    feature_id: str,
    request: FeatureUpdateRequest,
    session: AsyncSession = Depends(get_async_session)
):
    """Mettre à jour une feature existante"""

    try:
        # Récupérer la feature existante
        result = await session.execute(
            select(Feature).where(Feature.id == feature_id)
        )
        feature = result.scalar_one_or_none()

        if not feature:
            raise HTTPException(status_code=404, detail="Feature not found")

        # Mettre à jour seulement les champs fournis
        update_data = request.dict(exclude_unset=True)

        for field, value in update_data.items():
            if field == 'geometry' and value is not None:
                # Convertir la géométrie GeoJSON en WKT pour PostGIS
                geom_shape = shape(value)
                wkt_geom = WKTElement(geom_shape.wkt, srid=4326)
                setattr(feature, field, wkt_geom)
            elif field == 'tags' and value is not None:
                setattr(feature, field, value or {})
            elif value is not None:
                setattr(feature, field, value)

        await session.commit()
        await session.refresh(feature)

        # Convertir pour la réponse
        response = feature.__dict__.copy()
        if feature.geometry:
            shape_geom = to_shape(feature.geometry)
            response['geometry'] = json.loads(json.dumps(mapping(shape_geom)))

        return response

    except Exception as e:
        logger.error(f"Error updating feature: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update feature: {str(e)}")

@router.delete("/features/{feature_id}")
async def delete_feature(
    feature_id: str,
    session: AsyncSession = Depends(get_async_session)
):
    """Supprimer une feature"""
    
    try:
        result = await session.execute(
            select(Feature).where(Feature.id == feature_id)
        )
        feature = result.scalar_one_or_none()
        
        if not feature:
            raise HTTPException(status_code=404, detail="Feature not found")
        
        await session.delete(feature)
        await session.commit()
        
        return {"message": "Feature deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting feature: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete feature: {str(e)}")
        