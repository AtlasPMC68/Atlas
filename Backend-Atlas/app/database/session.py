# app/database/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database.base import Base
import os 
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(".env")

DATABASE_URL = os.getenv("DATABASE_URL")

# Convert DATABASE_URL to use asyncpg
# e.g. postgresql:// → postgresql+asyncpg://
if DATABASE_URL.startswith("postgresql://"): #pipi
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = sessionmaker( 
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
