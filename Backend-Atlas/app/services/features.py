from typing import Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.features import Feature
from geoalchemy2.functions import ST_GeomFromGeoJSON
from typing import Dict, Any
import json

async def insert_feature_in_db(
    db: AsyncSession,
    map_id: UUID,
    is_feature_collection: bool,
    data: Dict[str, Any],
) -> UUID:
    """Insert a GeoJSON feature into the database"""
    if is_feature_collection and data.get("type") == "FeatureCollection":
        feature_ids = []
        for feature_data in data.get("features", []):
            feature_id = await insert_feature_in_db(db, map_id, feature_data)
            feature_ids.append(feature_id)
        return feature_ids
    else:
        return await insert_single_feature(db, map_id, data)

async def insert_single_feature(
    db: AsyncSession,
    map_id: UUID,
    feature_data: Dict[str, Any]
) -> UUID:
    """Insert a single GeoJSON feature"""
    geometry = feature_data.get("geometry")
    properties = feature_data.get("properties", {})
    
    geometry_wkt = ST_GeomFromGeoJSON(json.dumps(geometry))
    
    new_feature = Feature(
        map_id=map_id,
        geometry=geometry_wkt,
        properties=properties
    )
    
    db.add(new_feature)
    await db.commit()
    await db.refresh(new_feature)
    
    return new_feature.id