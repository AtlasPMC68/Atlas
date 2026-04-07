from datetime import date

from pydantic import BaseModel


class MapImportRequest(BaseModel):
    title: str
    start_date: date
    end_date: date
    exact_date: bool = False
