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
    # What the map was georeferenced from: control points, framing box, legend,
    # pipette picks (format in app/utils/georeferencing/inputs.py). Kept so a
    # map can be re-georeferenced as the algorithm improves without the user
    # clicking again; the fitted transform itself is cheap to recompute.
    # Written by the import; nothing reads it yet.
    georef_inputs = Column(JSONB)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    