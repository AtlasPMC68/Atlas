"""Task status endpoints: who may poll a task, and what a failure reveals."""

import logging
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.utils import auth


def _fake_result(state, info=None, result=None):
    return SimpleNamespace(state=state, info=info, result=result)


def _dev_test_client(monkeypatch, roles, task):
    import app.routers.dev_test as router
    import app.utils.task_status as task_status

    monkeypatch.setattr(task_status.celery_app, "AsyncResult", lambda _id: task)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[auth.get_user_from_token] = lambda: {
        "sub": "dev",
        "roles": set(roles),
    }
    return TestClient(app)


def test_an_admin_can_poll_a_dev_test_run_without_a_map_import(monkeypatch):
    # A dev-test run has no MapImport row: /projects/status would 404 on it.
    task = _fake_result("PROGRESS", info={"current": 1, "total": 4, "status": "OCR"})
    res = _dev_test_client(monkeypatch, {"admin"}, task).get("/dev-test-api/status/abc")

    assert res.status_code == 200
    body = res.json()
    assert body["state"] == "PROGRESS"
    assert body["progress_percentage"] == 25
    assert body["status"] == "OCR"


def test_a_non_admin_cannot_poll_a_dev_test_run(monkeypatch):
    res = _dev_test_client(monkeypatch, set(), _fake_result("SUCCESS")).get(
        "/dev-test-api/status/abc"
    )

    assert res.status_code == 403


def test_a_failure_is_logged_but_not_sent_to_the_client(monkeypatch, caplog):
    secret = RuntimeError("password=hunter2 in /srv/atlas/secret.py")
    client = _dev_test_client(monkeypatch, {"admin"}, _fake_result("FAILURE", info=secret))

    with caplog.at_level(logging.ERROR, logger="app.utils.task_status"):
        res = client.get("/dev-test-api/status/abc")

    assert res.status_code == 200
    assert res.json()["error"] == "Task failed"
    assert "hunter2" not in res.text
    assert any("hunter2" in r.getMessage() for r in caplog.records)
