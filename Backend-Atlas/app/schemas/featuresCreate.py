from pydantic import BaseModel
from uuid import UUID
from typing import Dict, Any

class FeatureCreate(BaseModel):
    project_id: UUID
    map_id: UUID | None = None
    is_feature_collection: bool = False
    data: Dict[str, Any]
    image: bytes | None = None