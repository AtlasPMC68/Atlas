from fastapi import APIRouter
from ..tasks import test_task, process_map
from ..celery_app import celery_app

router = APIRouter(prefix="/test", tags=["Test Celery"])

@router.post("/simple")
async def test_simple_task(name: str = "World"):
    """Lance une tâche simple pour tester Celery"""
    task = test_task.delay(name)
    return {
        "task_id": task.id,
        "status": "Task started",
        "message": f"Task launched for {name}"
    }

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """Récupère l'état d'une tâche"""
    task = celery_app.AsyncResult(task_id)
    
    if task.state == "PENDING":
        response = {
            "task_id": task_id,
            "state": task.state,
            "status": "Task is waiting to be processed"
        }
    elif task.state == "PROGRESS":
        response = {
            "task_id": task_id,
            "state": task.state,
            "current": task.info.get("current", 0),
            "total": task.info.get("total", 1),
            "status": task.info.get("status", "")
        }
    elif task.state == "SUCCESS":
        response = {
            "task_id": task_id,
            "state": task.state,
            "result": task.result
        }
    else:  # FAILURE
        response = {
            "task_id": task_id,
            "state": task.state,
            "error": str(task.info)
        }
    
    return response

@router.get("/active")
async def get_active_tasks():
    """Liste les tâches actives"""
    inspect = celery_app.control.inspect()
    active_tasks = inspect.active()
    return {"active_tasks": active_tasks}