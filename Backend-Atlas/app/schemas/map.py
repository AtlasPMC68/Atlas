from pydantic import BaseModel, ConfigDict
from datetime import datetime, date
from typing import Optional
from uuid import UUID

class MapOut(BaseModel):
    id: UUID
    user_id: UUID
    base_layer_id: Optional[UUID]
    title: str
    description: Optional[str]
    is_private: bool
    start_date: Optional[date]
    end_date: Optional[date]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)