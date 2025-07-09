import uuid
from sqlalchemy import Column, Text, Integer, Date, TIMESTAMP, String, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, unique=True, nullable=False)
    username = Column(Text, unique=True, nullable=False)
    password = Column(Text, nullable=False)
    icone = Column(String, nullable=False, default="basic_icone.png")
    post = Column(Text, nullable=True)
    organisation = Column(Text, nullable=True)
    tag_line = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    language = Column(Text, nullable=False, default="fr")
    theme = Column(Text, nullable=False, default="light")
    notification_prefs = Column(JSONB)
    DOB = Column(Date, nullable=False)
    emplacement = Column(Text, nullable=False)
    last_login_at = Column(TIMESTAMP, nullable=True)
    followers_count = Column(Integer, nullable=True)
    maps_created = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())