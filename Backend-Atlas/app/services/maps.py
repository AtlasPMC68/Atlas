from datetime import date
from uuid import UUID

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.features import Feature
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

    # features.map_id is ON DELETE CASCADE: detach first any feature of
    # another project still pointing at this map (copies made before the
    # PUT /features check existed), so deleting it doesn't wipe their data.
    await db.execute(
        update(Feature)
        .where(Feature.map_id == map_id, Feature.project_id != project_id)
        .values(map_id=None)
    )
    await db.execute(
        delete(Feature).where(
            Feature.map_id == map_id, Feature.project_id == project_id
        )
    )
    await db.execute(delete(Map).where(Map.id == map_id))
    await db.commit()
    return True


async def copy_maps_between_projects(
    db: AsyncSession,
    source_project_id: UUID,
    target_project_id: UUID,
    user_id: UUID,
) -> dict[str, str] | None:
    """Copy the maps (periods) and label styles of a project the user can read
    into a project the user owns. Returns {source_map_id: new_map_id}, or None
    when either project is missing or not accessible.

    The reference image is not copied: its file is replaced (and the old one
    deleted) on re-upload, so sharing the path would let the copy delete the
    source's image.
    """
    target_result = await db.execute(
        select(Project).where(
            Project.id == target_project_id, Project.user_id == user_id
        )
    )
    target_project = target_result.scalar_one_or_none()
    source_result = await db.execute(
        select(Project).where(
            Project.id == source_project_id,
            (Project.user_id == user_id) | (Project.is_private.is_(False)),
        )
    )
    source_project = source_result.scalar_one_or_none()
    if not target_project or not source_project:
        return None

    maps_result = await db.execute(
        select(Map)
        .where(Map.project_id == source_project_id)
        .order_by(Map.start_date.asc(), Map.created_at.asc())
    )

    mapping: dict[str, Map] = {}
    for source_map in maps_result.scalars().all():
        new_map = Map(
            project_id=target_project_id,
            title=source_map.title,
            start_date=source_map.start_date,
            end_date=source_map.end_date,
            exact_date=bool(source_map.exact_date),
            georef_inputs=source_map.georef_inputs,
        )
        db.add(new_map)
        mapping[str(source_map.id)] = new_map

    if not target_project.label_styles and source_project.label_styles:
        target_project.label_styles = source_project.label_styles

    await db.commit()
    return {old_id: str(new_map.id) for old_id, new_map in mapping.items()}
