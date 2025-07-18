from pydantic import BaseModel
from typing import Optional

class MapCreateRequest(BaseModel):
    owner_id: str
    title: str
    description: Optional[str] = None
    access_level: str