# app/services/maps.py
from uuid import UUID
from uuid import uuid4
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.map import Map

async def create_map_in_db(
    db: AsyncSession,
    owner_id: UUID,
    title: str,
    description: str | None,
    access_level: str = "private",
) -> UUID:
    new_map = Map(
        owner_id=owner_id,
        #random uuid
        base_layer_id=uuid4(),
        title=title,
        description=description,
        access_level=access_level,
        #bs values for now
        start_date=date(1400, 1, 1),
        end_date=date.today(),
        style_id="light",
        parent_map_id=None,
        precision=None,
    )
    db.add(new_map)
    await db.commit()
    await db.refresh(new_map)
    return new_map.id