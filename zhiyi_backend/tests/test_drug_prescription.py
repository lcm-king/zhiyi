"""处方药购买合规测试：无处方拦截，医生代下单自动建档。"""

from __future__ import annotations

from conftest import auth_header


async def _noop_publish(*args, **kwargs):
    return None


def _patch_rabbit(monkeypatch):
    monkeypatch.setattr(
        "app.services.rabbitmq.publish_prescription_review",
        _noop_publish,
    )


def test_patient_rx_order_without_prescription_blocked(
    client,
    seeded_patient,
    seeded_drug,
    monkeypatch,
):
    _patch_rabbit(monkeypatch)
    resp = client.post(
        "/api/drugs/orders",
        headers=auth_header(seeded_patient["user_id"], "patient"),
        json={
            "items": [{"drug_id": seeded_drug["id"], "quantity": 1}],
            "address": "测试收货地址 100 号",
        },
    )
    assert resp.status_code == 400
    assert "处方" in resp.json().get("detail", "")


def test_doctor_order_creates_prescription(
    client,
    seeded_patient,
    seeded_doctor,
    seeded_drug,
    monkeypatch,
):
    _patch_rabbit(monkeypatch)
    resp = client.post(
        "/api/drugs/orders",
        headers=auth_header(seeded_doctor["user_id"], "doctor"),
        json={
            "items": [{"drug_id": seeded_drug["id"], "quantity": 1}],
            "address": "测试收货地址 100 号",
            "patient_id": seeded_patient["patient_id"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["prescription_id"] is not None
