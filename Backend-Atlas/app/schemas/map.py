from pydantic import BaseModel, ConfigDict
from datetime import datetime, date
from typing import Optional
from uuid import UUID

class MapOut(BaseModel):
    id: UUID
    user_id: UUID
    username: Optional[str] = None
    title: str
    description: Optional[str] = None
    is_private: bool
    image: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)