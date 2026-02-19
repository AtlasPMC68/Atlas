from pydantic import BaseModel
from typing import Optional

class MapCreateRequest(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    is_private: bool