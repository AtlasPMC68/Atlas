from sqlalchemy import Column, DateTime, JSON, LargeBinary, func
from sqlalchemy.dialects.postgresql import UUID
from ..database.base import Base
import uuid

class Feature(Base):
    __tablename__ = "features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    map_id = Column(UUID(as_uuid=True), nullable=True)
    data = Column(JSON, nullable=False)
    image = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())