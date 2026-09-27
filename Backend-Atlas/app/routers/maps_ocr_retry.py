import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_session
from app.models.features import Feature
from app.models.map import Map
from app.models.project import Project
from app.tasks import process_map_extraction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["Maps OCR"])


@router.post("/{project_id}/maps/{map_id}/retry-ocr")
async def retry_ocr_for_map(
    project_id: UUID, map_id: UUID, session: AsyncSession = Depends(get_async_session)
):
    # Verify map and project exist
    result = await session.execute(
        select(Map).where(Map.id == map_id, Map.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Map not found")

    # Find original image feature
    features_result = await session.execute(select(Feature).where(Feature.map_id == map_id))
    all_features = features_result.scalars().all()

    original_feature = None
    for f in all_features:
        props = f.data.get("properties", {})
        if props.get("isOriginalMapImage") is True:
            original_feature = f
            break

    if not original_feature or not original_feature.image:
        raise HTTPException(
            status_code=400,
            detail="L'image originale et la configuration sont introuvables. Cette carte a probablement été importée avant l'ajout de cette fonctionnalité.",
        )

    import_config = original_feature.data.get("properties", {}).get("importConfig", {})

    # Launch Celery task
    task_kwargs = {
        "filename": "retry_map.png",
        "file_content": original_feature.image,
        "project_id": project_id,
        "map_id": map_id,
        "pixel_points": import_config.get("pixel_points"),
        "geo_points_lonlat": import_config.get("geo_points_lonlat"),
        "enable_color_extraction": False,
        "enable_shapes_extraction": False,
        "enable_text_extraction": True,
        "legend_bounds": import_config.get("legend_bounds"),
        "title_bounds": import_config.get("title_bounds"),
        "scale_bounds": import_config.get("scale_bounds"),
        "compass_bounds": import_config.get("compass_bounds"),
        "imposed_click_positions": None,
        "imposed_colors_names": None,
        "imposed_sampling_radii": None,
    }

    task = process_map_extraction.apply_async(kwargs=task_kwargs, queue="maps_ocr")
    return {"status": "ok", "task_id": task.id}
