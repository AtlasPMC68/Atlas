import uuid
from sqlalchemy import Boolean, Column, Text, TIMESTAMP, func, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Map(Base):
    __tablename__ = "maps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True))
    title = Column(Text, nullable=False)
    description = Column(Text)
    is_private = Column(Boolean, default=True)
    start_date = Column(Date)
    end_date = Column(Date)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
