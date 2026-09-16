from typing import Any
import pytest
from app.celery_app import celery_app, resolve_redis_url


def test_celery_app_instance() -> None:
    """Verify that the Celery application instance is properly initialized."""
    assert celery_app is not None


def test_resolve_redis_url_prefers_celery_broker_env(monkeypatch: Any) -> None:
    """Verify that resolve_redis_url prioritizes CELERY_BROKER_URL over REDIS_URL when both are set."""
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    assert resolve_redis_url() == "redis://redis:6379/0"


def test_resolve_redis_url_falls_back_to_redis_url_env(monkeypatch: Any) -> None:
    """Verify that resolve_redis_url falls back to REDIS_URL when CELERY_BROKER_URL is unset."""
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    assert resolve_redis_url() == "redis://redis:6379/0"


def test_celery_broker_and_backend() -> None:
    """Verify that Celery broker and result backend URLs start with redis scheme."""
    assert celery_app.conf.broker_url.startswith("redis://")
    assert celery_app.conf.result_backend.startswith("redis://")


def test_celery_task_serializer() -> None:
    """Verify that Celery task serialization settings are configured for JSON format."""
    assert celery_app.conf.task_serializer == "json"
    assert "json" in celery_app.conf.accept_content
    assert celery_app.conf.result_serializer == "json"


def test_celery_timezone_and_utc() -> None:
    """Verify that Celery timezone configuration is set to America/Toronto with UTC enabled."""
    assert celery_app.conf.timezone == "America/Toronto"
    assert celery_app.conf.enable_utc is True


def test_celery_result_expires() -> None:
    """Verify that Celery task result expiration duration is set to 3600 seconds."""
    assert celery_app.conf.result_expires == 3600


def test_celery_task_routes() -> None:
    """Verify that Celery task routing rules map process_map tasks to the maps queue."""
    routes = celery_app.conf.task_routes
    assert "app.tasks.process_map" in routes
    assert routes["app.tasks.process_map"]["queue"] == "maps"
    assert routes.get("app.tasks.something_else", {"queue": "default"})["queue"] == "default"
