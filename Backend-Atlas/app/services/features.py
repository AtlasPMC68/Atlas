from typing import Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.features import Feature


async def create_feature_in_db(
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
    await db.commit()
    await db.refresh(feature)
    return str(feature.id)