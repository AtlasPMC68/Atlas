import pytest # type: ignore *****Comment to remove unused import warning*****
from fastapi.testclient import TestClient # type: ignore *****Comment to remove unused import warning*****
from app.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Maps Processing API", "status": "running"}

def test_ping():
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"message": "pong"}