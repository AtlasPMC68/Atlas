from celery import Celery
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Créer l'instance Celery
celery_app = Celery(
    "atlas",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
    broker_connection_retry_on_startup=True
)

# Configuration Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Toronto", 
    enable_utc=True,
    result_expires=3600,  # Les résultats expirent après 1h
    task_routes={
        "app.tasks.process_map": {"queue": "maps"},  # Queue spéciale pour les cartes
        "app.tasks.*": {"queue": "default"},
    },
)

# Auto-découverte des tâches
celery_app.autodiscover_tasks()
