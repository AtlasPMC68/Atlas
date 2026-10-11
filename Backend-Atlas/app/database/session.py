# app/database/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from app.database.base import Base
import os 
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.dev")

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = sessionmaker( 
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

# Celery tasks reach the database through ``asyncio.run``, a new event loop per
# call, and a pooled asyncpg connection is bound to the loop that opened it. The
# worker therefore opens a fresh connection per session instead of pooling.
worker_engine = create_async_engine(DATABASE_URL, poolclass=NullPool)

WorkerSessionLocal = sessionmaker(
    bind=worker_engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
