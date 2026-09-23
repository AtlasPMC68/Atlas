import os
import socket
from urllib.parse import urlparse

from celery import Celery
from dotenv import load_dotenv

load_dotenv()


def _resolve_celery_backend() -> str:
    """Prefer Redis when available, otherwise fall back to an in-memory backend.

    This keeps local task tests runnable on developer machines without a Docker
    Redis container, while still using Redis in containerized deployments.
    """
    configured = os.getenv("REDIS_URL")
    if not configured:
        return "cache+memory://"

    try:
        parsed = urlparse(configured)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        socket.create_connection((host, port), timeout=0.3).close()
        return configured
    except Exception:
        return "cache+memory://"


REDIS_URL = _resolve_celery_backend()

celery_app = Celery(
    "atlas",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
    broker_connection_retry_on_startup=True,
)

# Configuration Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Toronto", 
    enable_utc=True,
    result_expires=3600,
    task_routes={
        "app.tasks.process_map": {"queue": "maps"},
        "app.tasks.*": {"queue": "default"},
    },
)

celery_app.autodiscover_tasks()
