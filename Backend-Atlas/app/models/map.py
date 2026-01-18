import uuid
from sqlalchemy import Column, Text, TIMESTAMP, func, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Map(Base):
    __tablename__ = "maps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True))
    #base_layer_id?
    base_layer_id = Column(UUID(as_uuid=True))
    style_id = Column(Text, default='light')
    parent_map_id = Column(UUID(as_uuid=True))
    title = Column(Text, nullable=False)
    description = Column(Text)
    access_level = Column(Text, default='private')
    start_date = Column(Date)
    end_date = Column(Date)
    #Precision?
    precision = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())
