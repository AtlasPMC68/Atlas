import logging
from pathlib import Path
from uuid import UUID
import json
import math
from json import JSONDecodeError
from uuid import UUID
import base64
import cv2
import numpy as np

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Body
from sqlalchemy import delete, not_, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.database.session import get_async_session
from app.models.features import Feature
from app.models.map import Map
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectOut
from app.schemas.projectCreateRequest import ProjectCreateRequest
from app.schemas.mapImportRequest import MapImportRequest
from app.services.maps import create_map_in_db
from app.services.projects import (
    create_project_in_db,
    delete_project_in_db,
    update_project_in_db,
)
from app.utils.update_feature import (
    to_feature_collection,
    normalize_feature_collection,
    serialize_feature_rows,
)
from app.utils.sift_key_points_finder import find_coastline_keypoints

from ..celery_app import celery_app
from ..tasks import process_map_extraction
from ..utils.maps import default_bounds_from_image
from ..utils.auth import get_current_user_id
from ..utils.color_in_legends_extraction import sample_color_at
from ..utils.color_extraction import get_nearest_css4_color_name

router = APIRouter()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["Projects operations"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
IMAGE_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}


@router.post("/{project_id}/maps")
async def create_map_for_project(
    project_id: UUID,
    request: MapImportRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session),
):
    try:
        if request.start_date > request.end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date must be before or equal to end_date",
            )

        created_map_id = await create_map_in_db(
            db=db,
            project_id=project_id,
            user_id=UUID(user_id),
            title=request.title,
            start_date=request.start_date,
            end_date=request.end_date,
            exact_date=request.exact_date,
        )
        if not created_map_id:
            raise HTTPException(
                status_code=404, detail="Project not found or access denied"
            )
        return {"map_id": str(created_map_id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating map for project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create map")


@router.post("/create")
async def create_project(
    request: ProjectCreateRequest,
    user_id: dict = Depends(get_current_user_id),
    db: Session = Depends(get_async_session),
):
    try:
        project_id = await create_project_in_db(
            db=db,
            user_id=UUID(user_id),
            title=request.title,
            description=request.description,
            is_private=request.is_private,
        )
        return {"project_id": str(project_id)}
    except Exception as e:
        logger.error(f"Error creating project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create project")


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session),
):
    try:
        deleted = await delete_project_in_db(
            db=db,
            project_id=project_id,
            user_id=UUID(user_id),
        )
        if not deleted:
            raise HTTPException(
                status_code=404, detail="Project not found or access denied"
            )
        return {"detail": "Project deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete project")


@router.put("/{project_id}")
async def update_project(
    project_id: UUID,
    request: ProjectCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session),
):
    try:
        updated_project = await update_project_in_db(
            db=db,
            project_id=project_id,
            user_id=UUID(user_id),
            title=request.title,
            description=request.description,
            is_private=request.is_private,
        )
        if not updated_project:
            raise HTTPException(
                status_code=404, detail="Project not found or access denied"
            )
        return {"project_id": str(updated_project.id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update project")


@router.get("/is-owner/{project_id}")
async def is_project_owner(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        user_id = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid user")

    result = await session.execute(
        select(Project.id).where(
            Project.id == project_id,
            Project.user_id == user_id,
        )
    )

    return result.scalar_one_or_none() is not None


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        user_id = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid user")

    result = await session.execute(
        select(Project, User.username)
        .join(User, Project.user_id == User.id, isouter=True)
        .where(Project.id == project_id)
        .where((Project.user_id == user_id) | (Project.is_private.is_(False)))
    )

    row = result.first()
    if not row:
        raise HTTPException(
            status_code=404, detail="Project not found or access denied"
        )

    project_obj, username = row
    encoded_image = (
        base64.b64encode(project_obj.image).decode("ascii")
        if project_obj.image
        else None
    )

    return ProjectOut(
        id=project_obj.id,
        user_id=project_obj.user_id,
        username=username,
        title=project_obj.title,
        description=project_obj.description,
        is_private=project_obj.is_private,
        image=encoded_image,
        created_at=project_obj.created_at,
        updated_at=project_obj.updated_at,
    )


@router.post("/upload")
async def upload_and_process_map(
    image_points: str | None = Form(None),
    world_points: str | None = Form(None),
    legend_bounds: str | None = Form(None),
    imposed_colors: str | None = Form(None),
    enable_georeferencing: bool = Form(True),
    enable_color_extraction: bool = Form(True),
    enable_shapes_extraction: bool = Form(False),
    enable_text_extraction: bool = Form(False),
    project_id: str = Form(...),
    map_id: str = Form(...),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        project_id = UUID(project_id)
        map_id = UUID(map_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or map_id")

    result = await session.execute(
        select(Map)
        .join(Project, Map.project_id == Project.id)
        .where(
            Map.id == map_id,
            Map.project_id == project_id,
            Project.user_id == UUID(user_id),
        )
    )
    map_obj = result.scalar_one_or_none()
    if not map_obj:
        raise HTTPException(
            status_code=404,
            detail="Map not found for this project or access denied",
        )

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
            if not isinstance(parsed, dict) or not required_keys.issubset(
                parsed.keys()
            ):
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

    # Parse optional user-picked click positions as [{"x": 0.5, "y": 0.3, "name": "..."}, ...]
    imposed_click_positions = None
    imposed_colors_names = None
    imposed_sampling_radii = None
    if imposed_colors:
        try:
            parsed_colors = json.loads(imposed_colors)
            if not isinstance(parsed_colors, list):
                raise ValueError("imposed_colors must be a JSON array")
            imposed_click_positions = []
            imposed_colors_names = []
            imposed_sampling_radii = []
            for entry in parsed_colors:
                if not isinstance(entry, dict) or "x" not in entry or "y" not in entry:
                    raise ValueError(
                        'Each entry must be {"x": float, "y": float, "name": "..."}'
                    )
                x, y = float(entry["x"]), float(entry["y"])
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    raise ValueError("x and y must be normalised floats in [0, 1]")

                radius_raw = entry.get("radius", 20)
                radius = int(float(radius_raw))
                if radius < 1 or radius > 200:
                    raise ValueError("radius must be an int in [1, 200]")

                imposed_click_positions.append((x, y))
                imposed_colors_names.append(str(entry.get("name", "")).strip() or None)
                imposed_sampling_radii.append(radius)
        except (JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid imposed_colors payload: {e}",
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
            project_id=map_obj.project_id,
            map_id=map_id,
            pixel_points=pixel_points_list,
            geo_points_lonlat=geo_points_list,
            enable_color_extraction=enable_color_extraction,
            enable_shapes_extraction=enable_shapes_extraction,
            enable_text_extraction=enable_text_extraction,
            legend_bounds=legend_bounds_dict,
            imposed_click_positions=imposed_click_positions,
            imposed_colors_names=imposed_colors_names,
            imposed_sampling_radii=imposed_sampling_radii,
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


@router.put("/{project_id}/features")
async def update_features(
    project_id: str,
    features: list[dict] = Body(...),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        project_uuid = UUID(project_id)
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or user")

    project_result = await session.execute(
        select(Project.id).where(
            Project.id == project_uuid, Project.user_id == user_uuid
        )
    )
    allowed_project = project_result.scalar_one_or_none()
    if not allowed_project:
        raise HTTPException(
            status_code=404, detail="Project not found or access denied"
        )

    result = await session.execute(
        select(Feature).where(Feature.project_id == project_uuid)
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
            changed = False

            if db_feature.project_id != project_uuid:
                db_feature.project_id = project_uuid
                changed = True

            if old_data != new_data:
                db_feature.data = new_data
                db_feature.updated_at = func.now()
                changed = True

            if changed:
                session.add(db_feature)
        else:
            new_feature = Feature(
                project_id=project_uuid,
                map_id=None,
                data=to_feature_collection(feature),
            )
            session.add(new_feature)

    await session.commit()

    refreshed_result = await session.execute(
        select(Feature).where(Feature.project_id == project_uuid)
    )
    persisted_rows = refreshed_result.scalars().all()

    return serialize_feature_rows(persisted_rows)


@router.delete("/{project_id}/features")
async def delete_features_bulk(
    project_id: str,
    feature_ids: list[str] = Body(...),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        project_uuid = UUID(project_id)
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or user")

    project_result = await session.execute(
        select(Project.id).where(
            Project.id == project_uuid, Project.user_id == user_uuid
        )
    )
    allowed_project = project_result.scalar_one_or_none()
    if not allowed_project:
        raise HTTPException(
            status_code=404, detail="Project not found or access denied"
        )

    if not feature_ids:
        return {"deleted_feature_ids": []}

    try:
        feature_uuid_ids = [UUID(feature_id) for feature_id in feature_ids]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid feature_id in payload")

    existing_result = await session.execute(
        select(Feature.id).where(
            Feature.project_id == project_uuid,
            Feature.id.in_(feature_uuid_ids),
        )
    )
    deleted_feature_ids = [
        str(feature_id) for feature_id in existing_result.scalars().all()
    ]

    await session.execute(
        delete(Feature).where(
            Feature.project_id == project_uuid,
            Feature.id.in_(feature_uuid_ids),
        )
    )

    await session.commit()

    return {"deleted_feature_ids": deleted_feature_ids}


@router.get("/{project_id}/features")
async def get_project_features(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        project_id = UUID(project_id)
        user_id = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or user")

    project_result = await session.execute(
        select(Project.id)
        .where(Project.id == project_id)
        .where((Project.user_id == user_id) | (Project.is_private.is_(False)))
    )
    allowed_project = project_result.scalar_one_or_none()
    if not allowed_project:
        raise HTTPException(
            status_code=404, detail="Project not found or access denied"
        )

    features_result = await session.execute(
        select(Feature).where(Feature.project_id == project_id)
    )
    features_rows = features_result.scalars().all()

    return serialize_feature_rows(features_rows)


# Used to have lightweight data on maps for the timeline
@router.get("/{project_id}/maps")
async def get_project_maps(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        project_uuid = UUID(project_id)
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or user")

    project_result = await session.execute(
        select(Project.id)
        .where(Project.id == project_uuid)
        .where((Project.user_id == user_uuid) | (Project.is_private.is_(False)))
    )
    allowed_project = project_result.scalar_one_or_none()
    if not allowed_project:
        raise HTTPException(
            status_code=404, detail="Project not found or access denied"
        )

    maps_result = await session.execute(
        select(Map)
        .where(Map.project_id == project_uuid)
        .order_by(Map.start_date.asc(), Map.created_at.asc())
    )
    maps = maps_result.scalars().all()

    return [
        {
            "id": str(map_obj.id),
            "title": map_obj.title,
            "start_date": map_obj.start_date.isoformat()
            if map_obj.start_date
            else None,
            "end_date": map_obj.end_date.isoformat() if map_obj.end_date else None,
            "exact_date": bool(map_obj.exact_date),
        }
        for map_obj in maps
    ]


@router.get("/map-project/{map_id}")
async def get_project_id_for_map(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        user_uuid = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid user")

    result = await session.execute(
        select(Map.project_id)
        .join(Project, Map.project_id == Project.id)
        .where(Map.id == map_id, Project.user_id == user_uuid)
    )
    project_id = result.scalar_one_or_none()
    if not project_id:
        raise HTTPException(status_code=404, detail="Map not found or access denied")

    return {"map_id": str(map_id), "project_id": str(project_id)}


@router.get("", response_model=list[ProjectOut])
async def get_projects(
    user_id: str | None = None,
    session: AsyncSession = Depends(get_async_session),
):
    if user_id:
        try:
            user_id = UUID(user_id)
            query = (
                select(Project, User.username)
                .join(User, Project.user_id == User.id, isouter=True)
                .where(Project.user_id == user_id)
                .order_by(Project.updated_at.desc())
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id format")
    else:
        query = (
            select(Project, User.username)
            .join(User, Project.user_id == User.id, isouter=True)
            .where(not_(Project.is_private))
            .order_by(Project.updated_at.desc())
        )

    result = await session.execute(query)
    rows = result.all()

    projects = []
    for project_obj, username in rows:
        encoded_image = (
            base64.b64encode(project_obj.image).decode("ascii")
            if project_obj.image
            else None
        )

        out = ProjectOut(
            id=project_obj.id,
            user_id=project_obj.user_id,
            username=username,
            title=project_obj.title,
            description=project_obj.description,
            is_private=project_obj.is_private,
            image=encoded_image,
            created_at=project_obj.created_at,
            updated_at=project_obj.updated_at,
        )
        projects.append(out)

    return projects


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


@router.post("/{project_id}/thumbnail")
async def upload_map_thumbnail(
    project_id: UUID,
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
        select(Project).where(Project.id == project_id, Project.user_id == user_uuid)
    )
    project_obj = result.scalar_one_or_none()
    if not project_obj:
        raise HTTPException(
            status_code=404, detail="Project not found or access denied"
        )

    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty image")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    try:
        project_obj.image = content
        await session.commit()
        return {"status": "ok", "project_id": str(project_id)}
    except Exception as e:
        await session.rollback()
        logger.error(f"Error saving project thumbnail: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save thumbnail")


@router.post("/{project_id}/features/image")
async def upload_image(
    project_id: UUID,
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
        user_uuid = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid user")

    project_result = await session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_uuid)
    )
    project_obj = project_result.scalar_one_or_none()
    if not project_obj:
        raise HTTPException(
            status_code=404, detail="Project not found or access denied"
        )

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
    image_display_name = Path(image.filename).stem if image.filename else "Image"

    feature_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "map_element_type": "image",
                    "name": image.filename or "Image",
                    "mimeType": image.content_type,
                    "bounds": parsed_bounds,
                },
                "geometry": {"type": "Point", "coordinates": [center_lng, center_lat]},
            }
        ],
    }

    try:
        feature = Feature(
            project_id=project_id,
            map_id=None,
            data=feature_data,
            image=content,
        )
        session.add(feature)
        await session.commit()
        await session.refresh(feature)

        return {
            "project_id": str(project_id),
            "map_id": None,
            "feature_id": str(feature.id),
        }
    except Exception as e:
        await session.rollback()
        logger.error(f"Error saving feature image: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save feature image")


@router.post("/sample-color")
async def sample_color(
    x: float = Form(
        ..., ge=0.0, le=1.0, description="Normalised X position [0,1] from left"
    ),
    y: float = Form(
        ..., ge=0.0, le=1.0, description="Normalised Y position [0,1] from top"
    ),
    radius: int = Form(20, ge=1, le=200, description="Sampling radius in pixels"),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """
    Stateless endpoint — no map or DB needed.

    The frontend sends the image file it already has from the file picker,
    along with normalised click coordinates [0,1].  The backend samples the
    dominant colour in a neighbourhood around the click and returns the result
    so the frontend can show a colour swatch.

    The returned LAB values are consistent with what extract_colors() will
    compute on the same file during /upload.

    Returns: { rgb: [r,g,b], lab: [L,a,b], hex: "#rrggbb" }
    """
    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )
    nparr = np.frombuffer(raw, dtype=np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise HTTPException(status_code=422, detail="Could not decode image file")

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    color = sample_color_at(img_rgb, x, y, radius_px=radius)
    if color is None:
        raise HTTPException(
            status_code=422,
            detail="Click coordinates are outside the image bounds",
        )

    name = get_nearest_css4_color_name(tuple(color["rgb"]))
    return {**color, "name": name}
