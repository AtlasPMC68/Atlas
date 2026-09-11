from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()


def resolve_redis_url() -> str:
    """Resolve the broker/backend URL from the environment used by the project and OCR workers."""
    return os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL") or "redis://redis:6379/0"


REDIS_URL = resolve_redis_url()

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
        "florence.run_pipeline": {"queue": "florence"},
        "qwen.run_pipeline": {"queue": "qwen"},
        "app.tasks.*": {"queue": "default"},
    },
)

celery_app.autodiscover_tasks()
