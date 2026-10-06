from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.map import Map
from app.models.project import Project


async def create_map_in_db(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    title: str,
    start_date: date,
    end_date: date,
    exact_date: bool,
) -> UUID | None:
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project_obj = project_result.scalar_one_or_none()
    if not project_obj:
        return None

    new_map = Map(
        project_id=project_id,
        title=title,
        start_date=start_date,
        end_date=end_date,
        exact_date=exact_date,
    )
    db.add(new_map)
    await db.commit()
    await db.refresh(new_map)
    return new_map.id

async def delete_map_in_db(
    db: AsyncSession,
    project_id: UUID,
    map_id: UUID,
    user_id: UUID,
) -> bool:
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project_obj = project_result.scalar_one_or_none()
    if not project_obj:
        return False

    map_result = await db.execute(
        select(Map).where(Map.id == map_id, Map.project_id == project_id)
    )
    map_obj = map_result.scalar_one_or_none()
    if not map_obj:
        return False

    from sqlalchemy import delete
    from app.models.features import Feature

    await db.execute(delete(Feature).where(Feature.map_id == map_id))
    await db.execute(delete(Map).where(Map.id == map_id))
    await db.commit()
    return True
