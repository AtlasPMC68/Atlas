from celery import current_task
from .celery_app import celery_app
import time
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def test_task(self, name: str = "World"):
    """Tâche de test simple"""
    logger.info(f"Starting test task for {name}")
    
    # Simuler du travail
    for i in range(5):
        time.sleep(1)
        # Mettre à jour le statut
        self.update_state(
            state="PROGRESS",
            meta={"current": i + 1, "total": 5, "status": f"Processing step {i + 1}"}
        )
    
    result = f"Hello {name}! Task completed successfully."
    logger.info(f"Test task completed: {result}")
    return result