import base64
import logging
from uuid import UUID
import json
import logging
import math
from json import JSONDecodeError
from copy import deepcopy
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Body
from sqlalchemy import not_, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.database.session import get_async_session
from app.models.features import Feature
from app.models.map import Map
from app.models.user import User
from app.schemas.map import MapOut
from app.schemas.mapCreateRequest import MapCreateRequest
from app.services.maps import create_map_in_db, delete_map_in_db, update_map_in_db
from app.utils.update_feature import (
    to_feature_collection,
    normalize_feature_collection,
    serialize_db_feature,
)
from app.utils.sift_key_points_finder import find_coastline_keypoints

from ..celery_app import celery_app
from ..db import get_db
from ..tasks import process_map_extraction
from ..utils.maps import default_bounds_from_image
from ..utils.auth import get_current_user_id, get_user_from_token

router = APIRouter()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/maps", tags=["Maps Processing"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
IMAGE_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}

@router.post("/create")
async def create_map(
    request: MapCreateRequest,
    user_id: dict = Depends(get_current_user_id),
    db: Session = Depends(get_async_session),
):
    try:
        map_id = await create_map_in_db(
            db=db,
            user_id=UUID(user_id),
            title=request.title,
            description=request.description,
            is_private=request.is_private,
        )
        return {"map_id": str(map_id)}
    except Exception as e:
        logger.error(f"Error creating map: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create map")

@router.delete("/{map_id}")
async def delete_map(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session),
):
    try:
        deleted = await delete_map_in_db(
            db=db,
            map_id=map_id,
            user_id=UUID(user_id),
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Map not found or access denied")
        return {"detail": "Map deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting map: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete map")
    
@router.put("/{map_id}")
async def update_map(
    map_id: UUID,
    request: MapCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session),
):
    try:
        updated_map = await update_map_in_db(
            db=db,
            map_id=map_id,
            user_id=UUID(user_id),
            title=request.title,
            description=request.description,
            is_private=request.is_private,
        )
        if not updated_map:
            raise HTTPException(status_code=404, detail="Map not found or access denied")
        return {"map_id": str(updated_map)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating map: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update map")

@router.post("/upload")
async def upload_and_process_map(
    image_points: str | None = Form(None),
    world_points: str | None = Form(None),
    legend_bounds: str | None = Form(None),
    enable_georeferencing: bool = Form(True),
    enable_color_extraction: bool = Form(True),
    enable_shapes_extraction: bool = Form(False),
    enable_text_extraction: bool = Form(False),
    map_id: str = Form(None),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        map_id = UUID(map_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid map_id")
    
    result = await session.execute(
        select(Map).where(Map.id == map_id, Map.user_id == UUID(user_id))
    )
    map_obj = result.scalar_one_or_none()
    if not map_obj:
        raise HTTPException(status_code=404, detail="Map not found or access denied")

    # Validate file extension
    if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    pixel_points_list = None
    geo_points_list = None
    legend_bounds_dict = None

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

    # Parse optional legend rectangle (pixel-space bounds)
    if legend_bounds:
        try:
            parsed = json.loads(legend_bounds)
            required_keys = {"x", "y", "width", "height"}
            if not isinstance(parsed, dict) or not required_keys.issubset(parsed.keys()):
                raise ValueError(
                    "legend_bounds must be a JSON object with x, y, width, height"
                )

            legend_bounds_dict = {
                "x": float(parsed["x"]),
                "y": float(parsed["y"]),
                "width": float(parsed["width"]),
                "height": float(parsed["height"]),
            }

            if not all(math.isfinite(value) for value in legend_bounds_dict.values()):
                raise ValueError("legend_bounds values must be finite numbers")

            if legend_bounds_dict["width"] <= 0 or legend_bounds_dict["height"] <= 0:
                raise ValueError("legend_bounds width and height must be > 0")
        except (JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid legend bounds payload: {e}",
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
        task = process_map_extraction.delay(
            filename=file.filename,
            file_content=file_content,
            map_id=map_id,
            pixel_points=pixel_points_list,
            geo_points_lonlat=geo_points_list,
            enable_color_extraction=enable_color_extraction,
            enable_shapes_extraction=enable_shapes_extraction,
            enable_text_extraction=enable_text_extraction,
            legend_bounds=legend_bounds_dict,
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
async def get_features(
    map_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        map_id = UUID(map_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid map_id")

    result = await session.execute(
        select(Feature).where(Feature.map_id == map_id)
    )
    feature_rows = result.scalars().all()

    serialized_features = []
    for row in feature_rows:
        serialized = serialize_db_feature(row)
        if serialized is not None:
            serialized_features.append(serialized)

    return serialized_features

@router.put("/features/{map_id}")
async def update_features(
    map_id: str,
    features: list[dict] = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        map_id = UUID(map_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid map_id")

    result = await session.execute(
        select(Feature).where(Feature.map_id == map_id)
    )
    existing_rows = result.scalars().all()
    existing_by_id = {str(row.id): row for row in existing_rows}

    for feature in features:
        feature_id = feature.get("id")
        db_feature = None

        if feature_id:
            feature_id_str = str(feature_id)
            try:
                UUID(feature_id_str)
                db_feature = existing_by_id.get(feature_id_str)
            except ValueError:
                logger.warning(
                    f"Feature id is not a valid UUID, creating a new row: {feature_id}"
                )

        if db_feature:
            new_data = to_feature_collection(feature)
            old_data = normalize_feature_collection(db_feature.data)

            if old_data != new_data:
                db_feature.data = new_data
                db_feature.updated_at = func.now()
                session.add(db_feature)
        else:
            new_feature = Feature(
                map_id=map_id,
                is_feature_collection=False,
                data=to_feature_collection(feature),
            )
            session.add(new_feature)

    await session.commit()

    refreshed_result = await session.execute(
        select(Feature).where(Feature.map_id == map_id)
    )
    persisted_rows = refreshed_result.scalars().all()

    persisted_features = []
    for row in persisted_rows:
        serialized = serialize_db_feature(row)
        if serialized is not None:
            persisted_features.append(serialized)

    return persisted_features


@router.delete("/features/{map_id}/{feature_id}")
async def delete_feature(
    map_id: str,
    feature_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        map_id = UUID(map_id)
        feature_id = UUID(feature_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid map_id or feature_id")
    
    feature_id_str = str(feature_id)
    db_feature = None

    try:
        result = await session.execute(
            select(Feature).where(
                Feature.id == feature_id,
                Feature.map_id == map_id,
            )
        )
        db_feature = result.scalar_one_or_none()
    except ValueError:
        pass

    if not db_feature:
        result = await session.execute(
            select(Feature).where(Feature.map_id == map_id)
        )
        candidate_rows = result.scalars().all()

        for row in candidate_rows:
            features = row.data.get("features", [])
            for stored_feature in features:
                if str(stored_feature.get("id")) == feature_id_str:
                    db_feature = row
                    break
            if db_feature:
                break

    if not db_feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    await session.delete(db_feature)
    await session.commit()

    return {
        "feature_id": str(feature_id),
    }


@router.get("/map", response_model=list[MapOut])
async def get_maps(
    user_id: str | None = None,
    session: AsyncSession = Depends(get_async_session),
):
    if user_id:
        try:
            user_id = UUID(user_id)
            query = (
                select(Map, User.username)
                .join(User, Map.user_id == User.id, isouter=True)
                .where(Map.user_id == user_id)
                .order_by(Map.updated_at.desc())
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id format")
    else:
        query = (
            select(Map, User.username)
            .join(User, Map.user_id == User.id, isouter=True)
            .where(not_(Map.is_private))
            .order_by(Map.updated_at.desc())
        )

    result = await session.execute(query)
    rows = result.all()

    maps = []
    for map_obj, username in rows:
        encoded_image = (
            base64.b64encode(map_obj.image).decode("ascii")
            if map_obj.image
            else None
        )

        out = MapOut(
            id=map_obj.id,
            user_id=map_obj.user_id,
            username=username,
            title=map_obj.title,
            description=map_obj.description,
            is_private=map_obj.is_private,
            image=encoded_image,
            start_date=map_obj.start_date,
            end_date=map_obj.end_date,
            created_at=map_obj.created_at,
            updated_at=map_obj.updated_at,
        )
        maps.append(out)

    return maps


# TODO real save on that endpoint
@router.post("/save")
async def save_map(
    request: MapCreateRequest,
    user: dict = Depends(get_user_from_token),
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
        used_lakes = bool(result.get("used_lakes", False))

        return {
            "status": "success",
            "keypoints": result["keypoints"],
            "total": result["total"],
            "bounds": bounds,
            "used_lakes": used_lakes,
        }
    except Exception as e:
        logger.error(f"Error finding coastline keypoints: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{map_id}/thumbnail")
async def upload_map_thumbnail(
    map_id: UUID,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    if image.content_type not in IMAGE_ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type. Allowed: {', '.join(sorted(IMAGE_ALLOWED_CONTENT_TYPES))}",
        )
    try:
        user_uuid = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid user")

    result = await session.execute(
        select(Map).where(Map.id == map_id, Map.user_id == user_uuid)
    )
    map_obj = result.scalar_one_or_none()
    if not map_obj:
        raise HTTPException(status_code=404, detail="Map not found or access denied")

    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty image")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    try:
        map_obj.image = content
        await session.commit()
        return {"status": "ok", "map_id": str(map_id)}
    except Exception as e:
        await session.rollback()
        logger.error(f"Error saving map thumbnail: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save thumbnail")


@router.post("/{map_id}/features/image")
async def upload_image(
    map_id: UUID,
    image: UploadFile = File(...),
    bounds: str | None = Form(None),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    filename = (image.filename or "").lower()

    if not filename or not any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    try:
        user_id = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid user")

    map_result = await session.execute(
        select(Map).where(Map.id == map_id, Map.user_id == user_id)
    )
    map_obj = map_result.scalar_one_or_none()
    if not map_obj:
        raise HTTPException(status_code=404, detail="Map not found or access denied")

    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty image")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    parsed_bounds = default_bounds_from_image(content)
    if bounds:
        try:
            raw = json.loads(bounds)

            if (
                isinstance(raw, list)
                and len(raw) == 2
                and isinstance(raw[0], list)
                and isinstance(raw[1], list)
                and len(raw[0]) == 2
                and len(raw[1]) == 2
            ):
                south, west = float(raw[0][0]), float(raw[0][1])
                north, east = float(raw[1][0]), float(raw[1][1])
                parsed_bounds = [[south, west], [north, east]]

            elif isinstance(raw, list) and len(raw) == 4:
                west, south, east, north = map(float, raw)
                parsed_bounds = [[south, west], [north, east]]
            else:
                raise ValueError("Invalid bounds format")
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid bounds. Expected [[south,west],[north,east]] or [west,south,east,north]",
            )

    center_lat = (parsed_bounds[0][0] + parsed_bounds[1][0]) / 2
    center_lng = (parsed_bounds[0][1] + parsed_bounds[1][1]) / 2

    feature_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "mapElementType": "image",
                    "name": image.filename or "Image",
                    "mimeType": image.content_type,
                    "start_date": "1700-01-01",
                    "end_date": "2026-01-01",
                    "bounds": parsed_bounds,
                    "isPlaced": bool(bounds),
                },
                "geometry": {"type": "Point", "coordinates": [center_lng, center_lat]},
            }
        ],
    }

    try:
        feature = Feature(
            map_id=map_id,
            is_feature_collection=False,
            data=feature_data,
            image=content,
        )
        session.add(feature)
        await session.commit()
        await session.refresh(feature)

        return {"map_id": str(map_id), "feature_id": str(feature.id)}
    except Exception as e:
        await session.rollback()
        logger.error(f"Error saving feature image: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save feature image")


@router.get("/is-owner/{map_id}")
async def is_map_owner(
    map_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    
    try:
        map_id = UUID(map_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid map_id")
    
    result = await session.execute(select(Map.user_id).where(Map.id == map_id))
    owner_id = result.scalar_one_or_none()
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Map not found")

    return {"is_owner": user_id == str(owner_id)}

@router.get("/{map_id}", response_model=MapOut)
async def get_map_by_id(
    map_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        map_uuid = UUID(map_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid map_id format")

    query = (
        select(Map, User.username)
        .join(User, Map.user_id == User.id, isouter=True)
        .where(Map.id == map_uuid)
    )

    result = await session.execute(query)
    row = result.first()

    if row is None:
        raise HTTPException(status_code=404, detail="Map not found")

    map_obj, username = row

    if map_obj.is_private and str(map_obj.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    encoded_image = (
        base64.b64encode(map_obj.image).decode("ascii")
        if map_obj.image
        else None
    )

    return MapOut(
        id=map_obj.id,
        user_id=map_obj.user_id,
        username=username,
        title=map_obj.title,
        description=map_obj.description,
        is_private=map_obj.is_private,
        image=encoded_image,
        start_date=map_obj.start_date,
        end_date=map_obj.end_date,
        created_at=map_obj.created_at,
        updated_at=map_obj.updated_at,
    )