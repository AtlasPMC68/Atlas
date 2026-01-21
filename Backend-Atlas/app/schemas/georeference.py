from typing import List

from pydantic import BaseModel


class ImagePoint(BaseModel):
    x: float
    y: float


class WorldPoint(BaseModel):
    lat: float
    lng: float


class GeoreferencePayload(BaseModel):
    image_polyline: List[ImagePoint]
    world_polyline: List[WorldPoint]
