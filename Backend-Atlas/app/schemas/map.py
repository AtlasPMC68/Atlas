from pydantic import BaseModel, ConfigDict
from datetime import datetime, date
from typing import Optional
from uuid import UUID

class MapOut(BaseModel):
    id: UUID
    owner_id: UUID
    base_layer_id: Optional[UUID]
    style_id: str
    parent_map_id: Optional[UUID]
    title: str
    description: Optional[str]
    access_level: str
    start_date: Optional[date]
    end_date: Optional[date]
    precision: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)