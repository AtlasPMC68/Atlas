from pydantic import BaseModel
from typing import Optional

class ProjectCreateRequest(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    is_private: bool