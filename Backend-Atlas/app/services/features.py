from typing import Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.features import Feature
from typing import Any

async def insert_feature_in_db(
    db: AsyncSession,
    map_id: UUID,
    is_feature_collection: bool,
    data: dict[str, Any],
) -> str:
    feature = Feature(
        map_id=map_id,
        is_feature_collection=is_feature_collection,
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