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
    year: int,
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
        date=date(year, 1, 1),
    )
    db.add(new_map)
    await db.commit()
    await db.refresh(new_map)
    return new_map.id
