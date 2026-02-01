import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from ..tasks import process_map_extraction
from ..celery_app import celery_app
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.database.session import get_async_session
from app.models.features import Feature
from app.models.map import Map
from app.schemas.map import MapOut
from app.schemas.mapCreateRequest import MapCreateRequest
from app.schemas.feature import FeatureCreateRequest, FeatureUpdateRequest
from uuid import UUID
from ..utils.auth import get_current_user
from app.services.maps import create_map_in_db

from ..celery_app import celery_app
from ..db import get_db
from ..tasks import process_map_extraction
from ..utils.auth import get_current_user

router = APIRouter()


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/maps", tags=["Maps Processing"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".gif"}


@router.post("/upload")
async def upload_and_process_map(
    file: UploadFile = File(...), session: AsyncSession = Depends(get_async_session)
):
    """Upload a map and start data extraction"""

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
        map_id = await create_map_in_db(
            db=session,
            # TODO: replace with real owner
            owner_id=UUID("00000000-0000-0000-0000-000000000001"),
            title=file.filename,
            description=None,
            access_level="private",
        )
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

"""TODO"""
@router.post("/features")
async def create_feature(
    request: FeatureCreateRequest,
    session: AsyncSession = Depends(get_async_session)
):
    
    try:
        geometry = request.geometry.dict() if hasattr(request.geometry, "dict") else request.geometry
        feature_payload = {
            "type": request.type,
            "geometry": geometry,
            "color": request.color or "#000000",
            "stroke_width": request.stroke_width if request.stroke_width is not None else 2,
            "opacity": request.opacity if request.opacity is not None else 1.0,
            "z_index": request.z_index if request.z_index is not None else 1,
            "properties": {
                "name": request.name,
                "tags": request.tags or {},
                "start_date": request.start_date.isoformat() if request.start_date else None,
                "end_date": request.end_date.isoformat() if request.end_date else None,
                "precision": request.precision,
                "source": request.source,
            },
        }

        new_feature = Feature(
            map_id=UUID(request.map_id),
            is_feature_collection=False,
            data={
                "type": "FeatureCollection",
                "features": [feature_payload],
            },
        )
        
        session.add(new_feature)
        await session.commit()
        await session.refresh(new_feature)
        
        response = feature_payload.copy()
        response["id"] = str(new_feature.id)
        return response
        
    except Exception as e:
        logger.error(f"Error creating feature: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create feature: {str(e)}")

"""TODO"""
@router.put("/features/{feature_id}")
async def update_feature(
    feature_id: str,
    request: FeatureUpdateRequest,
    session: AsyncSession = Depends(get_async_session)
):

    try:
        # Récupérer la feature existante
        result = await session.execute(
            select(Feature).where(Feature.id == feature_id)
        )
        feature = result.scalar_one_or_none()

        if not feature:
            raise HTTPException(status_code=404, detail="Feature not found")

        update_data = request.dict(exclude_unset=True)
        data = feature.data or {}
        features = data.get("features") or []
        feature_payload = features[0] if features else {}
        feature_payload.setdefault("properties", {})

        for field, value in update_data.items():
            if value is None:
                continue
            if field == "geometry":
                feature_payload["geometry"] = value
            elif field in {"type", "color", "stroke_width", "opacity", "z_index"}:
                feature_payload[field] = value
            else:
                if field in {"start_date", "end_date"}:
                    feature_payload["properties"][field] = value.isoformat() if value else None
                elif field == "tags":
                    feature_payload["properties"][field] = value or {}
                else:
                    feature_payload["properties"][field] = value

        if not features:
            features = [feature_payload]
        else:
            features[0] = feature_payload

        data["features"] = features
        data.setdefault("type", "FeatureCollection")
        feature.data = data

        await session.commit()
        await session.refresh(feature)

        response = feature_payload.copy()
        response["id"] = str(feature.id)
        return response

    except Exception as e:
        logger.error(f"Error updating feature: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update feature: {str(e)}")

"""TODO"""
@router.delete("/features/{feature_id}")
async def delete_feature(
    feature_id: str,
    session: AsyncSession = Depends(get_async_session)
):
    
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
        