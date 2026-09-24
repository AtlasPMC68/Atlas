import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.dev"))
load_dotenv()


CELERY_MODE = os.getenv("CELERY_MODE", "redis").strip().lower()

if CELERY_MODE in {"eager", "local", "memory"}:
    BROKER_URL = "memory://"
    RESULT_BACKEND = "cache+memory://"
    TASK_ALWAYS_EAGER = True
    TASK_STORE_EAGER_RESULT = True
elif CELERY_MODE == "redis":
    BROKER_URL = os.getenv("REDIS_URL")
    if not BROKER_URL:
        raise RuntimeError("REDIS_URL is required when CELERY_MODE=redis")
    RESULT_BACKEND = BROKER_URL
    TASK_ALWAYS_EAGER = False
    TASK_STORE_EAGER_RESULT = False
else:
    raise RuntimeError(
        "Unsupported CELERY_MODE. Use 'redis' or 'eager' (local in-process mode)."
    )

celery_app = Celery(
    "atlas",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["app.tasks"],
    broker_connection_retry_on_startup=True,
    task_always_eager=TASK_ALWAYS_EAGER,
    task_store_eager_result=TASK_STORE_EAGER_RESULT,
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
