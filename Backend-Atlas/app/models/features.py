from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, JSON, func, Boolean
from sqlalchemy.dialects.postgresql import UUID
from ..database.base import Base
import uuid

class Feature(Base):
    __tablename__ = "features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    map_id = Column(UUID(as_uuid=True), nullable=False)
    geometry = Column(Geometry(geometry_type='GEOMETRY', srid=4326), nullable=False)
    properties = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())