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
    routes = celery_app.conf.task_routes
    assert "app.tasks.process_map" in routes
    assert routes["app.tasks.process_map"]["queue"] == "maps"
    assert routes.get("app.tasks.something_else", {"queue": "default"})["queue"] == "default"
