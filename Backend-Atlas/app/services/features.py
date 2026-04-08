from typing import Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.features import Feature
from app.models.map import Map

async def insert_feature_in_db(
    db: AsyncSession,
    map_id: UUID | None,
    data: dict[str, Any],
    project_id: UUID | None = None,
) -> str:
    resolved_project_id = project_id

    if map_id is not None:
        result = await db.execute(select(Map.project_id).where(Map.id == map_id))
        resolved_project_id = result.scalar_one_or_none()

    if not resolved_project_id:
        raise ValueError("Project not found while inserting feature")

    feature = Feature(
        project_id=resolved_project_id,
        map_id=map_id,
        data=data,
    )
    db.add(feature)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(feature)
    return str(feature.id)