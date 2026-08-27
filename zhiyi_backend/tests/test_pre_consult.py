"""AI 预问诊边界测试：不落正式诊断，医生确认后才转正式就诊。"""

from __future__ import annotations

import app.routers.diagnosis as diagnosis_router
from app.models import AiPreConsultation, Diagnosis
from app.services.langgraph_workflow import DiagnosisState
from conftest import auth_header, db_count


def _fake_state(patient_id: int, symptoms: str) -> DiagnosisState:
    return DiagnosisState(
        patient_id=patient_id,
        symptoms=symptoms,
        patient_name="测试患者",
        extracted_symptoms=["头痛"],
        primary_diagnosis="偏头痛",
        primary_reasoning="测试推理",
        llm_analysis={"urgency": "low"},
        diagnosis_suggestions=[{
            "id": 1,
            "name": "偏头痛",
            "confidence": 80,
            "description": "测试评估",
            "tags": [],
            "tone": "blue",
            "is_primary": True,
            "differential_diagnoses": [],
            "recommended_exams": [],
            "recommended_drugs": [],
        }],
        medication_review={
            "passed": True,
            "warnings": [],
            "recommendations": [],
            "requires_manual_review": False,
            "reviewed_at": "",
        },
        medical_record={
            "preliminary_diagnosis": "偏头痛",
            "treatment_plan": ["休息观察"],
        },
        follow_up_plan={
            "interval_days": 7,
            "watch_items": ["头痛频率"],
            "lifestyle_advice": ["规律作息"],
            "warning_symptoms": ["剧烈头痛立即就医"],
        },
        agent_logs=["[测试] 预问诊工作流"],
        use_ai=False,
        workflow_started="2026-08-16 00:00:00",
    )


async def _fake_workflow(patient_id: int, symptoms: str, **kwargs) -> DiagnosisState:
    return _fake_state(patient_id, symptoms)


def test_pre_consult_does_not_create_diagnosis(client, seeded_patient, monkeypatch):
    monkeypatch.setattr(diagnosis_router, "run_diagnosis_workflow", _fake_workflow)

    resp = client.post(
        "/api/diagnosis/patient-consult",
        headers=auth_header(seeded_patient["user_id"], "patient"),
        json={"symptoms": "反复头痛三天"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_pre_consultation"] is True
    assert body["status"] == "pending"
    assert db_count(Diagnosis) == 0


def test_doctor_confirm_converts_to_diagnosis(
    client,
    seeded_patient,
    seeded_doctor,
    monkeypatch,
):
    monkeypatch.setattr(diagnosis_router, "run_diagnosis_workflow", _fake_workflow)

    pre = client.post(
        "/api/diagnosis/patient-consult",
        headers=auth_header(seeded_patient["user_id"], "patient"),
        json={"symptoms": "反复头痛三天"},
    )
    assert pre.status_code == 200
    pre_id = pre.json()["id"]

    doctor_headers = auth_header(seeded_doctor["user_id"], "doctor")
    queue = client.get("/api/diagnosis/pre-consultations", headers=doctor_headers)
    assert queue.status_code == 200
    assert any(item["id"] == pre_id for item in queue.json())

    confirm = client.post(
        f"/api/diagnosis/pre-consultations/{pre_id}/confirm",
        headers=doctor_headers,
        json={"final_diagnosis": "偏头痛（医生确认）"},
    )
    assert confirm.status_code == 200
    assert db_count(Diagnosis) == 1

    from sqlalchemy import select

    async def _check_status() -> str:
        from conftest import TestSession
        async with TestSession() as session:
            record = (
                await session.execute(
                    select(AiPreConsultation).where(AiPreConsultation.id == pre_id)
                )
            ).scalar_one()
            return record.status

    import asyncio
    assert asyncio.run(_check_status()) == "confirmed"
