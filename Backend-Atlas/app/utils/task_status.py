import logging

from ..celery_app import celery_app

logger = logging.getLogger(__name__)


def build_task_status(task_id: str) -> dict:
    """The status of a Celery task, safe to send to the client.

    A failure's details stay server side: they are logged, and the client
    only gets a generic message.
    """
    task = celery_app.AsyncResult(task_id)
    response = {"task_id": task_id, "state": task.state}

    if task.state == "PENDING":
        response["status"] = "Task is waiting to be processed"
        response["progress_percentage"] = 0
    elif task.state == "PROGRESS":
        info = task.info if isinstance(task.info, dict) else {}
        current = info.get("current", 0)
        total = info.get("total", 1) or 1
        response.update(
            current=current,
            total=total,
            status=info.get("status", ""),
            progress_percentage=round(current / total * 100, 2),
        )
    elif task.state == "SUCCESS":
        response["result"] = task.result
        response["progress_percentage"] = 100
    elif task.state == "FAILURE":
        log_task_failure(task_id, task.info)
        response["error"] = "Task failed"
        response["progress_percentage"] = 0
    else:  # STARTED, RETRY, REVOKED
        response["status"] = task.state
        response["progress_percentage"] = 0

    return response


def log_task_failure(task_id: str, info: object) -> None:
    """Log why a task failed, with its traceback when Celery kept one."""
    exc_info = info if isinstance(info, BaseException) else None
    logger.error("Task %s failed: %r", task_id, info, exc_info=exc_info)
