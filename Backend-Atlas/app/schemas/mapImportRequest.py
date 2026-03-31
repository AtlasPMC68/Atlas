from pydantic import BaseModel, Field
from uuid import UUID


class MapImportRequest(BaseModel):
    project_id: UUID
    title: str
    year: int = Field(ge=1, le=9999)
