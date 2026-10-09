import pytest
from app.celery_app import celery_app

def test_celery_app_instance():
    assert celery_app is not None

def test_celery_broker_and_backend():
    assert celery_app.conf.broker_url.startswith("redis://")
    assert celery_app.conf.result_backend.startswith("redis://")

def test_celery_task_serializer():
    assert celery_app.conf.task_serializer == "json"
    assert "json" in celery_app.conf.accept_content
    assert celery_app.conf.result_serializer == "json"

def test_celery_timezone_and_utc():
    assert celery_app.conf.timezone == "America/Toronto"
    assert celery_app.conf.enable_utc is True

def test_celery_result_expires():
    assert celery_app.conf.result_expires == 3600

def test_celery_task_routes():
    # The worker consumes only "default" (docker-compose), so every task goes there.
    routes = celery_app.conf.task_routes
    assert routes == {"app.tasks.*": {"queue": "default"}}
