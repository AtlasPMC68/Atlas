from sqlalchemy import Column, DateTime, JSON, func, Boolean
from sqlalchemy.dialects.postgresql import UUID
from ..database.base import Base
import uuid

class Feature(Base):
    __tablename__ = "features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    map_id = Column(UUID(as_uuid=True), nullable=False)
    is_feature_collection = Column(Boolean, nullable=False, default=False)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now())