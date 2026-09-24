from sqlalchemy import Column, LargeBinary, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ..database.base import Base

OCR_PENDING = "pending"
OCR_RUNNING = "running"
OCR_DONE = "done"
OCR_FAILED = "failed"

EXTRACTION_IDLE = "idle"
EXTRACTION_WAITING_FOR_TEXT = "waiting_for_text"
EXTRACTION_QUEUED = "queued"
EXTRACTION_RUNNING = "running"
EXTRACTION_CANCELLING = "cancelling"
EXTRACTION_CANCELLED = "cancelled"
EXTRACTION_FAILED = "failed"

#: States in which an extraction is on its way and the inputs are frozen.
EXTRACTION_ACTIVE = (
    EXTRACTION_WAITING_FOR_TEXT,
    EXTRACTION_QUEUED,
    EXTRACTION_RUNNING,
    EXTRACTION_CANCELLING,
)


class MapImport(Base):
    """An import in progress. Deleted once its features are saved."""

    __tablename__ = "map_imports"

    map_id = Column(UUID(as_uuid=True), primary_key=True)
    image = Column(LargeBinary, nullable=False)
    filename = Column(Text, nullable=False)
    inputs = Column(JSONB, nullable=False, default=dict)
    ocr_state = Column(Text, nullable=False, default=OCR_PENDING)
    ocr_task_id = Column(Text)
    ocr_result = Column(JSONB)
    extraction_state = Column(Text, nullable=False, default=EXTRACTION_IDLE)
    extraction_task_id = Column(Text)
    extraction_error = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
