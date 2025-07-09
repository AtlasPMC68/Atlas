import pytest
from httpx import AsyncClient
from app.main import app
from app.auth import fake_users_db
from app.utils import get_password_hash

@pytest.mark.asyncio
async def test_login_success():
    hashed_password = get_password_hash("password")
    fake_users_db["user@example.com"] = {
        "username": "user@example.com",
        "hashed_password": hashed_password,
    }

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/token", data={"username": "user@example.com", "password": "password"})
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data

@pytest.mark.asyncio
async def test_login_fail():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/token", data={"username": "user@example.com", "password": "wrongpass"})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_protected_route_requires_auth():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/users/me")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_protected_route_with_token():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        login_resp = await ac.post("/token", data={"username": "user@example.com", "password": "password"})
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        response = await ac.get("/users/me", headers=headers)
    assert response.status_code == 200
    json_resp = response.json()
    assert json_resp["username"] == "user@example.com"
