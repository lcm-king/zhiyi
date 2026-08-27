"""认证安全核心链路测试。"""

from __future__ import annotations

import app.routers.auth as auth_router


def test_demo_login_disabled_returns_403(client, monkeypatch):
    monkeypatch.setattr(auth_router.settings, "demo_login_enabled", False)
    resp = client.post("/api/auth/demo-login?role=admin")
    assert resp.status_code == 403


def test_demo_login_enabled_returns_token(client, monkeypatch):
    monkeypatch.setattr(auth_router.settings, "demo_login_enabled", True)
    resp = client.post("/api/auth/demo-login?role=admin")
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["access_token"]


def test_sms_login_requires_code(client):
    resp = client.post(
        "/api/auth/sms-login?role=patient",
        json={"phone": "13800002001"},
    )
    assert resp.status_code == 422


def test_sms_login_rejects_wrong_code(client, monkeypatch):
    async def fake_verify(phone: str, code: str, redis) -> bool:
        return False

    monkeypatch.setattr("app.services.sms.verify_code", fake_verify)
    resp = client.post(
        "/api/auth/sms-login?role=patient",
        json={"phone": "13800002001", "code": "0000"},
    )
    assert resp.status_code == 400
