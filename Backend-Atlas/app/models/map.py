import uuid
from sqlalchemy import Boolean, Column, LargeBinary, Text, TIMESTAMP, func, Date
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Map(Base):
    __tablename__ = "maps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True))
    title = Column(Text, nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    exact_date = Column(Boolean, nullable=False, default=False)
    # Control points, framing box and pipette picks this map was georeferenced
    # from (see app/utils/georeferencing/inputs.py). Georeferencing runs once at
    # import; keeping the inputs is what makes a later re-run possible at all.
    georef_inputs = Column(JSONB)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    