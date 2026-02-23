# app/services/maps.py
from uuid import UUID
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.map import Map

async def create_map_in_db(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    description: str | None,
    is_private: bool = True,
) -> UUID:
    new_map = Map(
        user_id=user_id,
        title=title,
        description=description,
        is_private=is_private,
        #TODO : remove bs values for now
        start_date=date(1400, 1, 1),
        end_date=date.today(),
    )
    db.add(new_map)
    await db.commit()
    await db.refresh(new_map)
    return new_map.id

async def delete_map_in_db(
    db: AsyncSession,
    map_id: UUID,
    user_id: UUID,
) -> bool:
    result = await db.execute(
        select(Map).where(Map.id == map_id, Map.user_id == user_id)
    )
    map_obj = result.scalar_one_or_none()
    if not map_obj:
        return False
    await db.delete(map_obj)
    await db.commit()
    return True