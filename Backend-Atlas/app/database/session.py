# app/database/session.py
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database.base import Base
import os 
from dotenv import load_dotenv

_backend_root = Path(__file__).resolve().parents[1]
_env_candidates = [
    Path.cwd() / ".env.dev",
    _backend_root / ".env.dev",
    _backend_root.parent / "Backend-Atlas" / ".env.dev",
]

for candidate in _env_candidates:
    if candidate.exists():
        load_dotenv(dotenv_path=str(candidate), override=False)
        break

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Ensure a .env.dev file exists in the Backend-Atlas folder or export DATABASE_URL before starting the app."
    )

engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = sessionmaker( 
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
