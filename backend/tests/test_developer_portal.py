import pytest
from pydantic import SecretStr

from backend.app.core.config import settings
from backend.app.services import ai_gateway


@pytest.mark.asyncio
async def test_developer_portal_requires_root_and_records_role_switches(client, teacher_token, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "DEMO_ROOT_PASSWORD", SecretStr("kvr-test"))
    teacher = {"Authorization": f"Bearer {teacher_token}"}
    assert (await client.get("/api/v1/developer/health", headers=teacher)).status_code == 403

    login = await client.post("/api/v1/auth/login", json={"email": "LEOFELIX", "password": "kvr-test"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert (await client.get("/api/v1/developer/health", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/developer/releases", headers=headers)).status_code == 200
    framework = await client.get("/api/v1/developer/framework", headers=headers)
    assert framework.status_code == 200
    assert any(item["code"] == "CU-6" for item in framework.json())

    updated = await client.put(
        "/api/v1/developer/flags",
        json={"school_id": "school-1", "flag_key": "question_studio", "enabled": False},
        headers=headers,
    )
    assert updated.status_code == 200
    active = await client.get("/api/v1/developer/flags/active", headers=teacher)
    assert active.json()["question_studio"] is False
    await client.put(
        "/api/v1/developer/flags",
        json={"school_id": "school-1", "flag_key": "question_studio", "enabled": True},
        headers=headers,
    )

    workshop = await client.post(
        "/api/v1/developer/workshop",
        json={"kind": "question", "text": "Fractions of a whole", "competency_code": "CU-6"},
        headers=headers,
    )
    assert workshop.status_code == 200
    assert workshop.json()["result"]["competency"] == "CU-6"

    switched = await client.post("/api/v1/auth/demo-root/role", json={"role": "teacher"}, headers=headers)
    assert switched.status_code == 200
    developer = await client.post(
        "/api/v1/auth/demo-root/role",
        json={"role": "developer"},
        headers={"Authorization": f"Bearer {switched.json()['access_token']}"},
    )
    log = await client.get(
        "/api/v1/developer/access",
        headers={"Authorization": f"Bearer {developer.json()['access_token']}"},
    )
    assert log.status_code == 200
    assert any(item["to_role"] == "teacher" and item["from_role"] == "developer" for item in log.json())
    assert (await client.post("/api/v1/developer/roster/reseed", json={"confirm": "no"}, headers=headers)).status_code == 400


@pytest.mark.asyncio
async def test_developer_can_choose_a_listed_gemini_model(client, teacher_token, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "DEMO_ROOT_PASSWORD", SecretStr("kvr-test"))
    ai_gateway.clear_gemini_model_selection()

    async def fake_list():
        return [
            {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
            {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
        ]

    monkeypatch.setattr("backend.app.api.v1.developer.list_gemini_models", fake_list)
    teacher = {"Authorization": f"Bearer {teacher_token}"}
    assert (await client.get("/api/v1/developer/gemini/models", headers=teacher)).status_code == 403

    login = await client.post("/api/v1/auth/login", json={"email": "LEOFELIX", "password": "kvr-test"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    listed = await client.get("/api/v1/developer/gemini/models", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["current"] == settings.GEMINI_MODEL
    assert {item["id"] for item in listed.json()["models"]} >= {"gemini-2.5-flash", "gemini-2.5-pro"}

    chosen = await client.put("/api/v1/developer/gemini/model", json={"model": "gemini-2.5-pro"}, headers=headers)
    assert chosen.status_code == 200
    assert chosen.json()["current"] == "gemini-2.5-pro"
    assert ai_gateway.active_gemini_model() == "gemini-2.5-pro"
    assert (await client.put("/api/v1/developer/gemini/model", json={"model": "not-a-model"}, headers=headers)).status_code == 422
    ai_gateway.clear_gemini_model_selection()
