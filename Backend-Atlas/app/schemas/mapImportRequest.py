from datetime import date

from pydantic import BaseModel
from uuid import UUID


class MapImportRequest(BaseModel):
    project_id: UUID
    title: str
    start_date: date
    end_date: date
    exact_date: bool = False
