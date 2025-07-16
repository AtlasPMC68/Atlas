from sqlalchemy import Column, String, DateTime, Integer, Text, Float, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from ..database.base import Base

import uuid

class Feature(Base):
    __tablename__ = "features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    map_id = Column(UUID(as_uuid=True), ForeignKey("maps.id", ondelete="CASCADE"))
    name = Column(String)
    type = Column(String)
    geometry = Column(Geometry("GEOMETRY", srid=4326))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    precision = Column(String)
    color = Column(String)
    stroke_width = Column(Integer)
    icon = Column(String)
    tags = Column(JSON)
    source = Column(String)
    opacity = Column(Float, default=1.0)
    z_index = Column(Integer, default=1)
    created_at = Column(DateTime)

