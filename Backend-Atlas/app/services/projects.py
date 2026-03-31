# app/services/projects.py
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.project import Project

async def create_project_in_db(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    description: str | None,
    is_private: bool = True,
) -> UUID:
    new_project = Project(
        user_id=user_id,
        title=title,
        description=description,
        is_private=is_private,
    )
    db.add(new_project)
    await db.commit()
    await db.refresh(new_project)
    return new_project.id

async def delete_project_in_db(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
) -> bool:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project_obj = result.scalar_one_or_none()
    if not project_obj:
        return False
    await db.delete(project_obj)
    await db.commit()
    return True

async def update_project_in_db(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    title: str,
    description: str | None,
    is_private: bool,
) -> Project | None:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project_obj = result.scalar_one_or_none()
    if not project_obj:
        return None
    try:
        project_obj.title = title
        project_obj.description = description
        project_obj.is_private = is_private
        project_obj.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(project_obj)
        return project_obj
    except Exception:
        await db.rollback()
        raise