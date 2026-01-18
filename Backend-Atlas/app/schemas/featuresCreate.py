from pydantic import BaseModel
from uuid import UUID
from typing import Dict, Any

class FeatureCreate(BaseModel):
    map_id: UUID
    is_feature_collection: bool = False
    data: Dict[str, Any] 