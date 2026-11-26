"""API-backed demo persona and demo-root login (synthetic seed data only)."""
import pytest
from pydantic import SecretStr


PERSONAS = ("admin", "principal", "teacher", "student", "parent")


@pytest.mark.asyncio
async def test_seeded_demo_personas_login_with_demo123(client):
    for role in PERSONAS:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": f"{role}@lumeneios.demo", "password": "demo123"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["access_token"]
        assert body["user"]["role"] == role
        assert body["user"]["email"] == f"{role}@lumeneios.demo"
        assert body["user"].get("demo_root") is False


@pytest.mark.asyncio
async def test_demo_root_login_and_role_switch(client, monkeypatch):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "DEMO_ROOT_PASSWORD", SecretStr("KVR"))

    root = await client.post(
        "/api/v1/auth/login",
        json={"email": "LEOFELIX", "password": "KVR"},
    )
    assert root.status_code == 200, root.text
    root_body = root.json()
    assert root_body["user"]["demo_root"] is True
    assert root_body["user"]["role"] == "developer"
    token = root_body["access_token"]

    switched = await client.post(
        "/api/v1/auth/demo-root/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "teacher"},
    )
    assert switched.status_code == 200, switched.text
    teacher = switched.json()
    assert teacher["user"]["role"] == "teacher"
    assert teacher["user"]["email"] == "teacher@lumeneios.demo"
    assert teacher["user"]["demo_root"] is True

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {teacher['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["role"] == "teacher"
    assert me.json()["demo_root"] is True


@pytest.mark.asyncio
async def test_demo_root_rejected_when_disabled(client, monkeypatch):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "DEMO_ROOT_PASSWORD", SecretStr(""))
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "leofelix@lumeneios.demo", "password": "KVR"},
    )
    assert response.status_code == 401
