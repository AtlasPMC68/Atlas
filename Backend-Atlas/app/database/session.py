# app/database/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database.base import Base
import os 
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.dev")

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = sessionmaker( 
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
