"""
智医 (ZhiYi) — AI 智能诊断路由
基层医疗AI辅助诊疗平台

POST /api/diagnosis/assist    — AI 辅助诊断（完整 5-Agent 工作流）
POST /api/diagnosis/record    — 生成并存储结构化病历
GET  /api/diagnosis/history   — 查询诊断历史
GET  /api/diagnosis/{id}      — 查看诊断详情
POST /api/diagnosis/qa        — 医学知识库问答
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.crud import drug_crud, user_crud
from app.database import get_db
from app.models import AiPreConsultation, Diagnosis, Doctor, Drug, ExamItem, Patient, Prescription, User
from app.schemas import (
    DiagnosisQARequest,
    DiagnosisQAResponse,
    DiagnosisRequest,
    DiagnosisResponse,
    DiagnosisSuggestion,
    ExamRecommendation,
    DrugRecommendation,
    FollowUpPlan,
    MedicalRecord,
    MedicalRecordRequest,
    MedicalRecordResponse,
    MedicationReview,
    MessageResponse,
    PatientAssistRequest,
    PatientAssistResponse,
    PatientConsultRequest,
    PreConsultConfirmRequest,
    PreConsultationListItem,
    PreConsultationResponse,
)
from app.services.knowledge_base import search_diseases
from app.services.langgraph_workflow import run_diagnosis_workflow
from app.services.audit import log_audit

router = APIRouter()
logger = logging.getLogger("zhiyi.diagnosis")


# =============================================================================
# AI 辅助诊断
# =============================================================================

@router.post(
    "/assist",
    response_model=DiagnosisResponse,
    summary="AI 辅助诊断",
    description="输入患者症状描述，执行完整的 5-Agent 诊断工作流，返回推荐诊断列表。",
)
async def ai_diagnosis_assist(
    payload: DiagnosisRequest,
    current_user: User = Depends(require_role("doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> DiagnosisResponse:
    """AI 辅助诊断端点（医生专用）。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    patient_result = await db.execute(select(Patient).where(Patient.id == payload.patient_id))
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="患者不存在")

    doctor_result = await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))
    doctor = doctor_result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前用户没有关联的医生档案")

    return await _run_and_persist_diagnosis(
        db=db,
        patient=patient,
        doctor=doctor,
        symptoms=payload.symptoms,
    )


@router.post(
    "/patient-consult",
    response_model=PreConsultationResponse,
    summary="AI 预问诊",
    description="患者提交症状描述，AI 生成预问诊草稿与就医建议，不落正式就诊记录；正式诊断需由医生确认后生成。",
)
async def patient_online_consult(
    payload: PatientConsultRequest,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> PreConsultationResponse:
    """患者 AI 预问诊端点：生成健康参考草稿，不生成正式就诊记录。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    # 当前登录用户对应的患者档案
    patient_result = await db.execute(
        select(Patient).where(Patient.user_id == current_user.id)
    )
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前账号未关联患者档案")

    return await _run_and_persist_pre_consultation(
        db=db,
        patient=patient,
        symptoms=payload.symptoms,
    )


async def _run_diagnosis_state(
    *,
    db: AsyncSession,
    patient: Patient,
    symptoms: str,
) -> Any:
    """执行 5-Agent 诊断工作流（异常时降级规则引擎），返回工作流状态。"""
    # 从真实健康档案读取过敏/病史
    profile = await user_crud.get_patient_profile(db, patient.id)
    allergies: list[str] = profile.get("allergies", []) if profile else []
    history: list[str] = profile.get("past_history", []) if profile else []
    age: Optional[int] = profile.get("age") if profile else None
    gender: Optional[str] = profile.get("gender") if profile else None

    # 执行诊断工作流（异常时兜底返回规则引擎结果）
    try:
        state = await run_diagnosis_workflow(
            patient_id=patient.id,
            symptoms=symptoms,
            patient_name=patient.name,
            patient_allergies=allergies,
            patient_history=history,
            patient_age=age,
            patient_gender=gender,
        )
    except Exception as exc:
        logger.exception("诊断工作流异常，使用规则引擎兜底")
        # 兜底：直接走规则引擎
        from app.services.langgraph_workflow import DiagnosisState
        from app.services.langgraph_workflow import (
            agent_diagnosis_suggestion,
            agent_differential_diagnosis,
            agent_medical_record,
            agent_medication_review,
            agent_symptom_analysis,
        )
        from datetime import datetime
        state = DiagnosisState(
            patient_id=patient.id,
            patient_name=patient.name,
            symptoms=symptoms,
            patient_allergies=allergies,
            patient_history=history,
            patient_age=age,
            patient_gender=gender,
            workflow_started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        state = await agent_symptom_analysis(state)
        state = await agent_differential_diagnosis(state)
        state = await agent_diagnosis_suggestion(state)
        state = await agent_medication_review(state)
        state = await agent_medical_record(state)
        state.agent_logs.append(f"[系统] 诊断工作流异常已恢复: {exc}")

    return state


async def _run_and_persist_diagnosis(
    *,
    db: AsyncSession,
    patient: Patient,
    doctor: Doctor,
    symptoms: str,
) -> DiagnosisResponse:
    """医生端共享诊断流程：执行工作流 → 解析推荐 ID → 落库正式诊断。"""
    state = await _run_diagnosis_state(db=db, patient=patient, symptoms=symptoms)

    # 将推荐名称解析为真实数据库 ID
    suggestions = await _resolve_recommendation_ids(db, state.diagnosis_suggestions)
    state.diagnosis_suggestions = suggestions

    # 持久化完整诊断记录
    diagnosis_record = Diagnosis(
        patient_id=patient.id,
        doctor_id=doctor.id,
        symptoms=symptoms,
        extracted_symptoms=state.extracted_symptoms,
        ai_suggestions=json.dumps(suggestions, ensure_ascii=False),
        final_diagnosis=(
            state.primary_diagnosis
            or state.medical_record.get("preliminary_diagnosis")
        ),
        treatment_plan=json.dumps(state.medical_record.get("treatment_plan", []), ensure_ascii=False),
        medical_record=state.medical_record,
        medication_review=state.medication_review,
        follow_up_plan=state.follow_up_plan,
        use_ai=state.use_ai,
    )
    db.add(diagnosis_record)
    await db.commit()
    await db.refresh(diagnosis_record)

    await log_audit(
        db,
        user_id=doctor.user_id,
        action="diagnosis_create",
        resource="diagnosis",
        resource_id=diagnosis_record.id,
        detail={"patient_id": patient.id, "use_ai": state.use_ai},
    )
    return _build_diagnosis_response(diagnosis_record, suggestions, state)


async def _run_and_persist_pre_consultation(
    *,
    db: AsyncSession,
    patient: Patient,
    symptoms: str,
) -> PreConsultationResponse:
    """患者端 AI 预问诊：执行工作流但不落正式诊断，由医生确认后转正式就诊。"""
    state = await _run_diagnosis_state(db=db, patient=patient, symptoms=symptoms)
    suggestions = await _resolve_recommendation_ids(db, state.diagnosis_suggestions)
    state.diagnosis_suggestions = suggestions

    record = AiPreConsultation(
        patient_id=patient.id,
        symptoms=symptoms,
        extracted_symptoms=state.extracted_symptoms,
        ai_suggestions=json.dumps(suggestions, ensure_ascii=False),
        primary_diagnosis=(
            state.primary_diagnosis
            or state.medical_record.get("preliminary_diagnosis")
        ),
        primary_reasoning=state.primary_reasoning,
        medication_review=state.medication_review,
        medical_record=state.medical_record,
        follow_up_plan=state.follow_up_plan,
        urgency=_resolve_urgency(state),
        suggested_department=_suggested_department(state),
        status="pending",
        use_ai=state.use_ai,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    await log_audit(
        db,
        user_id=patient.user_id,
        action="pre_consult",
        resource="ai_pre_consultation",
        resource_id=record.id,
        detail={"primary_diagnosis": record.primary_diagnosis},
    )
    return _build_pre_consult_response(record, suggestions, state)


def _resolve_urgency(state: Any) -> str:
    """从工作流状态中解析紧急程度，缺省 low。"""
    raw = ""
    if isinstance(state.llm_analysis, dict):
        raw = str(state.llm_analysis.get("urgency") or "").lower()
    if raw not in ("low", "medium", "high"):
        raw = "low"
    return raw


def _suggested_department(state: Any) -> str:
    """根据知识库匹配结果推断建议就诊科室。"""
    if state.matched_diseases:
        dep = (state.matched_diseases[0].get("category") or "").strip()
        if dep and dep != "AI 推理":
            return dep
    return "全科 / 内科"


# =============================================================================
# AI 预问诊确认（医生端）
# =============================================================================

@router.get(
    "/pre-consultations",
    response_model=list[PreConsultationListItem],
    summary="预问诊列表",
)
async def list_pre_consultations(
    status: Optional[str] = Query(None, pattern="^(pending|confirmed|dismissed)$"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role("doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[PreConsultationListItem]:
    """医生端查看 AI 预问诊队列，待确认记录转为正式就诊。"""
    if db is None:
        return []

    query = (
        select(AiPreConsultation, Patient)
        .join(Patient, Patient.id == AiPreConsultation.patient_id)
        .order_by(AiPreConsultation.created_at.desc())
        .limit(limit)
    )
    if status:
        query = query.where(AiPreConsultation.status == status)

    result = await db.execute(query)
    items: list[PreConsultationListItem] = []
    for pre, patient in result.all():
        suggestions = _parse_json_field(pre.ai_suggestions, [])
        items.append(PreConsultationListItem(
            id=pre.id,
            patient_id=pre.patient_id,
            patient_name=patient.name,
            symptoms=pre.symptoms,
            primary_diagnosis=pre.primary_diagnosis or "",
            urgency=pre.urgency or "low",
            suggested_department=pre.suggested_department or "",
            status=pre.status,
            suggestions_count=len(suggestions) if isinstance(suggestions, list) else 0,
            created_at=pre.created_at.strftime("%Y-%m-%d %H:%M") if pre.created_at else "",
        ))
    return items


@router.get(
    "/pre-consultations/{pre_consult_id}",
    response_model=PreConsultationResponse,
    summary="预问诊详情",
)
async def get_pre_consultation_detail(
    pre_consult_id: int,
    current_user: User = Depends(require_role("doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> PreConsultationResponse:
    """查看单条 AI 预问诊的完整草稿内容。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    result = await db.execute(
        select(AiPreConsultation).where(AiPreConsultation.id == pre_consult_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预问诊记录不存在")
    return _build_pre_consult_response(record)


@router.post(
    "/pre-consultations/{pre_consult_id}/confirm",
    response_model=DiagnosisResponse,
    summary="确认预问诊并生成正式就诊",
)
async def confirm_pre_consultation(
    pre_consult_id: int,
    payload: PreConsultConfirmRequest,
    current_user: User = Depends(require_role("doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> DiagnosisResponse:
    """医生确认 AI 预问诊，生成正式诊断记录；可同时开具处方。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    result = await db.execute(
        select(AiPreConsultation).where(AiPreConsultation.id == pre_consult_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预问诊记录不存在")
    if record.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该预问诊已处理")

    doctor_result = await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))
    doctor = doctor_result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前用户没有关联的医生档案")

    final_diagnosis = (payload.final_diagnosis or record.primary_diagnosis or "").strip()
    medical_record = dict(_parse_json_field(record.medical_record, {}) or {})
    if final_diagnosis:
        medical_record["preliminary_diagnosis"] = final_diagnosis

    if payload.treatment_plan:
        try:
            parsed_plan = json.loads(payload.treatment_plan)
        except (TypeError, ValueError):
            parsed_plan = [payload.treatment_plan]
        if not isinstance(parsed_plan, list):
            parsed_plan = [payload.treatment_plan]
        treatment_plan = json.dumps(parsed_plan, ensure_ascii=False)
    else:
        treatment_plan = json.dumps(medical_record.get("treatment_plan", []), ensure_ascii=False)

    diagnosis_record = Diagnosis(
        patient_id=record.patient_id,
        doctor_id=doctor.id,
        symptoms=record.symptoms,
        extracted_symptoms=record.extracted_symptoms or [],
        ai_suggestions=record.ai_suggestions,
        final_diagnosis=final_diagnosis or None,
        treatment_plan=treatment_plan,
        medical_record=medical_record,
        medication_review=_parse_json_field(record.medication_review, {}) or {},
        follow_up_plan=_parse_json_field(record.follow_up_plan, {}) or {},
        use_ai=bool(record.use_ai),
    )
    db.add(diagnosis_record)
    await db.flush()

    if payload.prescription_items:
        await drug_crud.create_prescription(
            db,
            patient_id=record.patient_id,
            doctor_id=doctor.id,
            items=[it.model_dump() for it in payload.prescription_items],
            diagnosis_id=diagnosis_record.id,
        )

    record.status = "confirmed"
    record.confirmed_diagnosis_id = diagnosis_record.id
    record.confirmed_by_doctor_id = doctor.id
    record.confirmed_at = datetime.now()
    await db.commit()
    await db.refresh(diagnosis_record)

    await log_audit(
        db,
        user_id=doctor.user_id,
        action="diagnosis_confirm",
        resource="diagnosis",
        resource_id=diagnosis_record.id,
        detail={"final_diagnosis": final_diagnosis},
    )
    return _build_diagnosis_response_from_record(diagnosis_record)


# =============================================================================
# 生成病历
# =============================================================================

@router.post(
    "/record",
    response_model=MedicalRecordResponse,
    summary="生成结构化病历",
)
async def generate_medical_record(
    payload: MedicalRecordRequest,
    current_user: User = Depends(require_role("doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MedicalRecordResponse:
    """基于诊断结果生成结构化电子病历并持久化。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    result = await db.execute(select(Diagnosis).where(Diagnosis.id == payload.diagnosis_id))
    diagnosis = result.scalar_one_or_none()
    if not diagnosis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="诊断记录不存在")

    if payload.final_diagnosis:
        diagnosis.final_diagnosis = payload.final_diagnosis
    if payload.treatment_plan:
        diagnosis.treatment_plan = payload.treatment_plan

    await db.commit()
    await db.refresh(diagnosis)

    record = diagnosis.medical_record if diagnosis.medical_record else {}
    medical_record = MedicalRecord(**record) if record else MedicalRecord()

    return MedicalRecordResponse(
        id=diagnosis.id,
        patient_id=diagnosis.patient_id,
        doctor_id=diagnosis.doctor_id,
        chief_complaint=diagnosis.symptoms,
        present_illness=record.get("present_illness", ""),
        physical_exam=json.dumps(record.get("physical_examination", {}), ensure_ascii=False),
        final_diagnosis=diagnosis.final_diagnosis,
        treatment_plan=diagnosis.treatment_plan,
        medical_record=medical_record,
        created_at=diagnosis.created_at.strftime("%Y-%m-%d %H:%M"),
    )


# =============================================================================
# 诊断历史
# =============================================================================

@router.get(
    "/history",
    response_model=list[DiagnosisResponse],
    summary="查询诊断历史",
)
async def get_diagnosis_history(
    patient_id: int | None = None,
    limit: int = 10,
    current_user: User = Depends(require_role("doctor", "patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[DiagnosisResponse]:
    """查询诊断历史记录，可按患者筛选，返回完整字段。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    # 患者只能查看自己的诊断记录（强制用登录用户的 patient_id，忽略路径参数）
    if current_user.role.value == "patient":
        result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
        me = result.scalar_one_or_none()
        if not me:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="患者档案不存在")
        patient_id = me.id

    query = select(Diagnosis).order_by(Diagnosis.created_at.desc()).limit(limit)
    if patient_id:
        query = query.where(Diagnosis.patient_id == patient_id)
    result = await db.execute(query)
    records = result.scalars().all()

    return [_build_diagnosis_response_from_record(record) for record in records]


# =============================================================================
# =============================================================================
# 删除诊断记录
# =============================================================================

@router.delete(
    "/history/{diagnosis_id}",
    response_model=MessageResponse,
    summary="删除诊断记录",
)
async def delete_diagnosis_record(
    diagnosis_id: int,
    current_user: User = Depends(require_role("doctor", "admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """删除指定诊断记录（医生本人或管理员），并解除关联的预问诊/处方引用。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    result = await db.execute(select(Diagnosis).where(Diagnosis.id == diagnosis_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="诊断记录不存在")

    if current_user.role.value == "doctor":
        doctor_result = await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))
        doctor = doctor_result.scalar_one_or_none()
        if not doctor or doctor.id != record.doctor_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能删除自己创建的诊断记录")

    # 解除关联引用，避免外键约束阻止删除
    pre_result = await db.execute(
        select(AiPreConsultation).where(AiPreConsultation.confirmed_diagnosis_id == diagnosis_id)
    )
    for pre in pre_result.scalars().all():
        pre.confirmed_diagnosis_id = None

    rx_result = await db.execute(
        select(Prescription).where(Prescription.diagnosis_id == diagnosis_id)
    )
    for rx in rx_result.scalars().all():
        rx.diagnosis_id = None

    await db.delete(record)
    await db.commit()

    await log_audit(
        db,
        user_id=current_user.id,
        action="diagnosis_delete",
        resource="diagnosis",
        resource_id=diagnosis_id,
        detail={"patient_id": record.patient_id},
    )
    return MessageResponse(message="诊断记录已删除")

# 诊断详情
# =============================================================================

@router.get(
    "/{diagnosis_id}",
    response_model=MedicalRecordResponse,
    summary="查看诊断详情",
)
async def get_diagnosis_detail(
    diagnosis_id: int,
    current_user: User = Depends(require_role("doctor", "patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MedicalRecordResponse:
    """查看单条诊断记录的完整详情（含病历）。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    result = await db.execute(select(Diagnosis).where(Diagnosis.id == diagnosis_id))
    diagnosis = result.scalar_one_or_none()
    if not diagnosis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="诊断记录不存在")

    # 患者只能查看自己的诊断详情
    if current_user.role.value == "patient":
        patient_result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
        me = patient_result.scalar_one_or_none()
        if not me or diagnosis.patient_id != me.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能查看自己的诊断记录")

    record = diagnosis.medical_record if diagnosis.medical_record else {}
    medical_record = MedicalRecord(**record) if record else MedicalRecord()

    return MedicalRecordResponse(
        id=diagnosis.id,
        patient_id=diagnosis.patient_id,
        doctor_id=diagnosis.doctor_id,
        chief_complaint=diagnosis.symptoms,
        present_illness=record.get("present_illness", ""),
        physical_exam=json.dumps(record.get("physical_examination", {}), ensure_ascii=False),
        final_diagnosis=diagnosis.final_diagnosis,
        treatment_plan=diagnosis.treatment_plan,
        medical_record=medical_record,
        created_at=diagnosis.created_at.strftime("%Y-%m-%d %H:%M"),
    )


# =============================================================================
# 医学知识库问答
# =============================================================================

@router.post(
    "/qa",
    response_model=DiagnosisQAResponse,
    summary="医学知识库问答",
)
async def medical_qa(
    payload: DiagnosisQARequest,
    current_user: User = Depends(require_role("doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> DiagnosisQAResponse:
    """基于 RAG（ChromaDB 向量检索 + Qwen LLM 推理）的医学知识库问答。"""
    answer: str
    related: list[dict[str, Any]] = []

    # ── RAG 路径：ChromaDB 检索 + Qwen 推理 ──
    try:
        from app.config import get_settings
        from app.services.langgraph_workflow import get_qwen_embeddings, _call_qwen
        import chromadb

        settings = get_settings()
        if settings.qwen_api_key or settings.siliconflow_api_key:
            # Step 1: 向量检索
            query_vectors = await get_qwen_embeddings([payload.question])
            if query_vectors:
                client = chromadb.HttpClient(
                    host=settings.chroma_host or "localhost",
                    port=int(settings.chroma_port or 8000),
                )
                collection = client.get_or_create_collection("disease_knowledge")
                results = collection.query(query_embeddings=query_vectors, n_results=5)

                # 构建知识库上下文
                from app.services.knowledge_base import DISEASE_KNOWLEDGE
                disease_map = {d["id"]: d for d in DISEASE_KNOWLEDGE}
                contexts: list[str] = []
                matched_ids: list[str] = []
                if results.get("ids") and results["ids"][0]:
                    for i, did in enumerate(results["ids"][0]):
                        if did in disease_map:
                            d = disease_map[did]
                            matched_ids.append(did)
                            contexts.append(
                                f"[{i + 1}] {d['name']}（{d.get('category', '')}）："
                                f"症状：{'；'.join(d.get('typical_symptoms', [])[:3])}；"
                                f"诊断：{'；'.join(d.get('diagnostic_criteria', [])[:2])}；"
                                f"治疗：{'；'.join(d.get('treatment_principles', [])[:3])}"
                            )

                # Step 2: LLM 推理生成回答
                if contexts:
                    system_prompt = (
                        "你是资深医学知识助手。请根据知识库检索到的疾病信息，"
                        "用专业但通俗的中文回答用户问题。回答应包含相关知识、临床要点、"
                        "注意事项三部分。如果是用药问题，重点说明药物相互作用和禁忌。"
                    )
                    user_prompt = (
                        f"【知识库检索结果】\n{chr(10).join(contexts)}\n\n"
                        f"【用户问题】{payload.question}"
                    )
                    ai_answer = await _call_qwen(system_prompt, user_prompt, timeout=10.0)
                    answer = ai_answer
                else:
                    answer = "当前知识库中未找到与该问题直接相关的信息，建议补充更详细的描述或咨询专科医生。"

                # 相关疾病
                related = [
                    {"id": did, "name": disease_map[did]["name"],
                     "category": disease_map[did]["category"], "match_score": 50}
                    for did in matched_ids
                ]
                # 记录 AI 问答日志到 MongoDB（ai_qa_logs）
                try:
                    from app.services.mongo import log_ai_qa

                    await log_ai_qa(
                        payload.patient_id or 0,
                        payload.question,
                        answer,
                        sources=contexts[:3],
                        related_diseases=related,
                        use_ai=True,
                    )
                except Exception:
                    pass
                return DiagnosisQAResponse(answer=answer, sources=contexts[:3], related_diseases=related)
    except Exception as exc:
        logger.warning("RAG QA 失败，降级关键词检索：%s", exc)

    # ── 降级：关键词检索 ──
    matched = search_diseases(payload.question, top_k=3)
    if not matched:
        try:
            from app.services.mongo import log_ai_qa

            await log_ai_qa(
                payload.patient_id or 0,
                payload.question,
                "当前知识库中未找到与该问题直接相关的疾病信息，建议补充更详细的症状描述或咨询专科医生。",
                use_ai=False,
            )
        except Exception:
            pass
        return DiagnosisQAResponse(
            answer="当前知识库中未找到与该问题直接相关的疾病信息，建议补充更详细的症状描述或咨询专科医生。",
            sources=[],
            related_diseases=[],
        )

    top = matched[0]
    answer = (
        f"根据您的问题，最相关的疾病是「{top['name']}」（{top['category']}）。\n\n"
        f"典型症状：{'; '.join(top['typical_symptoms'][:3])}。\n"
        f"诊断要点：{top['diagnostic_criteria'][0]}。\n"
        f"治疗原则：{'; '.join(top['treatment_principles'][:3])}。\n\n"
        f"还需与以下疾病鉴别：{', '.join(top['differential_diagnoses'][:3])}。"
    )

    disease_names = [d["name"] for d in matched]
    related = [
        {"id": d["id"], "name": d["name"], "category": d["category"], "match_score": d.get("match_score", 0)}
        for d in matched
    ]

    # 记录 AI 问答日志到 MongoDB（ai_qa_logs）
    try:
        from app.services.mongo import log_ai_qa

        await log_ai_qa(
            payload.patient_id or 0,
            payload.question,
            answer,
            sources=disease_names,
            related_diseases=related,
            use_ai=False,
        )
    except Exception:
        pass
    return DiagnosisQAResponse(answer=answer, sources=disease_names, related_diseases=related)


# =============================================================================
# 患者智能助手（对话式健康咨询）
# =============================================================================

@router.post(
    "/patient-assist",
    response_model=PatientAssistResponse,
    summary="患者智能助手",
    description="患者对话式健康咨询：结合本人健康档案 + 83 种疾病知识库（RAG）+ 大模型推理，返回个性化建议。",
)
async def patient_assist(
    payload: PatientAssistRequest,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> PatientAssistResponse:
    """患者智能助手：知识库检索 → 结合档案 → 大模型组织回答（LLM 不可用时本地结构化回答）。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    # 当前登录用户对应的患者档案
    patient_result = await db.execute(
        select(Patient).where(Patient.user_id == current_user.id)
    )
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前账号未关联患者档案")

    profile = await user_crud.get_patient_profile(db, patient.id) or {}
    allergies: list[str] = profile.get("allergies", []) or []
    history: list[str] = profile.get("past_history", []) or []
    family_history: list[str] = profile.get("family_history", []) or []
    lifestyle: dict[str, Any] = profile.get("lifestyle", {}) or {}
    age: Optional[int] = profile.get("age")
    gender: Optional[str] = profile.get("gender")

    # 档案摘要（用于回答前缀 + LLM 上下文）
    context_bits: list[str] = []
    if age:
        context_bits.append(f"{age} 岁")
    if gender:
        context_bits.append("男" if str(gender).upper() in ("M", "MALE", "男") else "女")
    if allergies:
        context_bits.append(f"过敏史：{'、'.join(allergies[:3])}")
    if history:
        context_bits.append(f"既往史：{'、'.join(history[:3])}")
    if family_history:
        context_bits.append(f"家族史：{'、'.join(family_history[:3])}")
    if lifestyle:
        life_items = []
        for key in ("smoking", "smoke", "drinking", "alcohol", "exercise", "sleep"):
            val = lifestyle.get(key)
            if val:
                life_items.append(f"{key}={val}")
        if life_items:
            context_bits.append("生活方式：" + "；".join(life_items[:4]))
    profile_summary = "；".join(context_bits) if context_bits else "档案暂未填写"

    # Step 1: 知识库检索（本地关键词/规则引擎，离线可用）
    matched = search_diseases(
        payload.question,
        top_k=3,
        patient_history=history,
        patient_allergies=allergies,
    )

    # Step 2: 尝试大模型推理（千问 → SiliconFlow 自动降级）
    use_ai = False
    answer = ""
    if matched:
        try:
            from app.services.langgraph_workflow import _call_qwen

            context_parts = []
            for i, d in enumerate(matched):
                context_parts.append(
                    f"[{i + 1}] {d['name']}（{d.get('category', '')}）\n"
                    f"  典型症状：{'；'.join(d.get('typical_symptoms', [])[:3])}\n"
                    f"  诊断要点：{'；'.join(d.get('diagnostic_criteria', [])[:2])}\n"
                    f"  治疗原则：{'；'.join(d.get('treatment_principles', [])[:3])}"
                )
            system_prompt = (
                "你是智医平台的健康助手，面向患者提供通俗、温暖、负责任的健康咨询。"
                "必须基于提供的知识库检索结果回答，不得编造。回答结构："
                "1) 直接回应咨询；2) 结合患者档案给出针对性提醒；"
                "3) 就医建议（何时需要去医院）；4) 一句温暖收尾。"
                "用中文、口语化、避免长篇大论（400 字以内）。"
            )
            user_prompt = (
                f"【患者档案】{profile_summary}\n\n"
                f"【知识库检索结果】\n{chr(10).join(context_parts)}\n\n"
                f"【患者问题】{payload.question}"
            )
            llm_answer = await _call_qwen(system_prompt, user_prompt, timeout=20.0)
            answer = llm_answer.strip().strip("`")
            if answer:
                use_ai = True
        except Exception as exc:
            logger.warning("患者助手 LLM 推理失败，使用本地结构化回答：%s", exc)

    # Step 3: LLM 不可用/无匹配时，本地结构化回答
    if not answer:
        answer = _build_local_assist_answer(
            question=payload.question,
            matched=matched,
            profile_summary=profile_summary,
        )

    related = [
        {"id": d.get("id"), "name": d.get("name"), "category": d.get("category"),
         "match_score": d.get("match_score", 0)}
        for d in matched
    ]

    # 记录 AI 问答日志到 MongoDB（ai_qa_logs）
    try:
        from app.services.mongo import log_ai_qa

        await log_ai_qa(
            patient.id,
            payload.question,
            answer,
            sources=[d.get("name", "") for d in matched],
            related_diseases=related,
            use_ai=use_ai,
        )
    except Exception:
        pass

    return PatientAssistResponse(
        answer=answer,
        related_diseases=related,
        use_ai=use_ai,
        profile_summary=profile_summary,
    )


def _build_local_assist_answer(
    *,
    question: str,
    matched: list[dict[str, Any]],
    profile_summary: str,
) -> str:
    """本地结构化回答（无大模型可用时）。"""
    lines: list[str] = [f"关于「{question[:50]}」："]
    if not matched:
        lines.append(
            "当前知识库暂未检索到与您描述高度相关的疾病信息，建议补充更具体的症状（部位、持续时长、伴随表现），"
            "或前往附近社区卫生服务中心就诊评估。"
        )
        return "\n".join(lines)

    top = matched[0]
    lines.append(
        f"可能与「{top['name']}」（{top['category']}）相关，典型表现包括："
        f"{'；'.join(top.get('typical_symptoms', [])[:2])}。"
    )
    if len(matched) > 1:
        names = "、".join(d["name"] for d in matched[1:])
        lines.append(f"同时需与以下情况鉴别：{names}。")

    if profile_summary and "未填写" not in profile_summary:
        lines.append(f"结合您的档案（{profile_summary}），建议重点关注与之相关的指标与症状变化。")
    else:
        lines.append("建议在健康档案中补充过敏史与既往史，可获得更精准的提醒。")

    lines.append(
        f"就医建议：如症状持续不缓解、进行性加重或出现剧烈疼痛、意识改变、呼吸困难等，"
        "请立即就近就医或拨打 120。建议检查：「" + "、".join(top.get("recommended_exams", [])[:3]) + "」。"
    )
    return "\n".join(lines)


# =============================================================================
# 内部辅助函数
# =============================================================================
def _parse_json_field(value: Any, default: Any = None) -> Any:
    """兼容字符串与对象两种 JSON 存储格式。"""
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default
    return value


def _parse_suggestions(suggestions_data: Any) -> list[DiagnosisSuggestion]:
    """将 AI 建议 JSON（字符串或列表）解析为响应对象。"""
    data = _parse_json_field(suggestions_data, []) or []
    if not isinstance(data, list):
        data = []
    return [
        DiagnosisSuggestion(
            id=s.get("id", i + 1),
            name=s.get("name", ""),
            confidence=s.get("confidence", 0),
            description=s.get("description", ""),
            tags=s.get("tags", []),
            tone=s.get("tone", "blue"),
            is_primary=bool(s.get("is_primary", False)),
            differential_diagnoses=s.get("differential_diagnoses", []),
            recommended_exams=[ExamRecommendation(**e) for e in s.get("recommended_exams", [])],
            recommended_drugs=[DrugRecommendation(**d) for d in s.get("recommended_drugs", [])],
        )
        for i, s in enumerate(data)
    ]


def _build_pre_consult_response(
    record: AiPreConsultation,
    suggestions: Optional[list[dict[str, Any]]] = None,
    state: Any = None,
) -> PreConsultationResponse:
    """从 AI 预问诊记录构建响应。"""
    parsed_suggestions = (
        [DiagnosisSuggestion(**s) for s in suggestions]
        if suggestions is not None
        else _parse_suggestions(record.ai_suggestions)
    )
    medication_review = _parse_json_field(record.medication_review, {}) or {}
    medical_record = _parse_json_field(record.medical_record, {}) or {}
    follow_up_plan = _parse_json_field(record.follow_up_plan, {}) or {}

    return PreConsultationResponse(
        id=record.id,
        patient_id=record.patient_id,
        symptoms=record.symptoms,
        extracted_symptoms=record.extracted_symptoms or [],
        suggestions=parsed_suggestions,
        primary_diagnosis=record.primary_diagnosis or "",
        primary_reasoning=record.primary_reasoning or "",
        medication_review=MedicationReview(**medication_review),
        medical_record=MedicalRecord(**medical_record),
        follow_up_plan=FollowUpPlan(**follow_up_plan) if follow_up_plan else FollowUpPlan(interval_days=0),
        agent_logs=state.agent_logs if state is not None else [],
        generated_at=record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
        use_ai=bool(record.use_ai),
        status=record.status,
        urgency=record.urgency or "low",
        suggested_department=record.suggested_department or "",
        is_pre_consultation=True,
    )


def _build_diagnosis_response(
    diagnosis_record: Diagnosis,
    suggestions: list[dict[str, Any]],
    state: Any,
) -> DiagnosisResponse:
    """从工作流状态构建诊断响应。"""
    return DiagnosisResponse(
        id=diagnosis_record.id,
        patient_id=diagnosis_record.patient_id,
        symptoms=diagnosis_record.symptoms,
        extracted_symptoms=state.extracted_symptoms,
        suggestions=[DiagnosisSuggestion(**s) for s in suggestions],
        primary_diagnosis=getattr(state, "primary_diagnosis", ""),
        primary_reasoning=getattr(state, "primary_reasoning", ""),
        medication_review=MedicationReview(**state.medication_review),
        medical_record=MedicalRecord(**state.medical_record),
        follow_up_plan=FollowUpPlan(**state.follow_up_plan),
        agent_logs=state.agent_logs,
        generated_at=state.workflow_started,
        use_ai=state.use_ai,
    )


def _build_diagnosis_response_from_record(record: Diagnosis) -> DiagnosisResponse:
    """从数据库诊断记录构建完整响应（用于历史查询）。"""
    suggestions = _parse_suggestions(record.ai_suggestions)
    medication_review = _parse_json_field(record.medication_review, {}) or {}
    medical_record = _parse_json_field(record.medical_record, {}) or {}
    follow_up_plan = _parse_json_field(record.follow_up_plan, {}) or {}

    return DiagnosisResponse(
        id=record.id,
        patient_id=record.patient_id,
        symptoms=record.symptoms,
        extracted_symptoms=record.extracted_symptoms or [],
        suggestions=suggestions,
        primary_diagnosis=record.final_diagnosis or "",
        primary_reasoning="",
        medication_review=MedicationReview(**medication_review),
        medical_record=MedicalRecord(**medical_record),
        follow_up_plan=FollowUpPlan(**follow_up_plan) if follow_up_plan else FollowUpPlan(interval_days=0),
        agent_logs=[],
        generated_at=record.created_at.strftime("%Y-%m-%d %H:%M"),
        use_ai=bool(record.use_ai),
    )


async def _resolve_recommendation_ids(
    db: AsyncSession,
    suggestions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """将诊断建议中的检查/药品名称解析为数据库真实 ID。"""


    exam_items = (await db.execute(select(ExamItem))).scalars().all()
    drugs = (await db.execute(select(Drug))).scalars().all()

    # 预加载数据
    exam_records: list[dict] = [
        {"id": e.id, "name": e.name.lower(), "category": (e.category or "").lower()}
        for e in exam_items
    ]
    drug_records: list[dict] = [
        {"id": d.id, "name": d.name.lower(), "spec": (d.specification or "").lower()}
        for d in drugs
    ]

    # 检查项目别名映射 (知识库名 → 数据库ID匹配关键词)
    EXAM_ALIASES: dict[str, str] = {
        "心脏超声": "心脏超声",
        "超声心动图": "心脏超声",
        "心电图": "心电图",
        "常规心电图": "心电图",
        "胸部x线": "胸部",
        "胸部 x 线": "胸部",
        "胸片": "胸部",
        "胸部ct": "胸部",
        "血常规": "血常规",
        "血常规+crp": "血常规",
        "血常规 + crp": "血常规",
        "血常规+生化全项": "血常规",
        "生化全项": "生化全项",
        "肾功能+电解质": "生化全项",
        "肾功能": "生化全项",
        "电解质": "生化全项",
        "腹部超声": "腹部",
        "腹部b超": "腹部",
        "b超": "腹部",
        "b超检查": "腹部",
        "动态血压监测": "心电图",
        "眼底检查": "心电图",
        "尿微量白蛋白": "生化全项",
        "bnp": "胸部",
        "nt-probnp": "胸部",
        "bnp/nt-probnp": "胸部",
        "肺功能": "胸部",
        "肺功能检查": "胸部",
        "超声": "腹部",
        "ct": "胸部",
        "mri": "胸部",
        "x线": "胸部",
        "x 线": "胸部",
    }

    # 药品别名映射
    DRUG_ALIASES: dict[str, str] = {
        "硝苯地平": "硝苯地平",
        "氨氯地平": "硝苯地平",
        "呋塞米": "硝苯地平",
        "螺内酯": "硝苯地平",
        "美托洛尔": "硝苯地平",
        "厄贝沙坦": "硝苯地平",
        "氢氯噻嗪": "硝苯地平",
        "沙库巴曲缬沙坦": "硝苯地平",
        "达格列净": "二甲双胍",
        "恩格列净": "二甲双胍",
        "二甲双胍": "二甲双胍",
        "阿莫西林": "阿莫西林",
        "头孢": "阿莫西林",
        "阿奇霉素": "阿莫西林",
        "左氧氟沙星": "阿莫西林",
        "布洛芬": "布洛芬",
        "对乙酰氨基酚": "布洛芬",
        "阿司匹林": "布洛芬",
        "氯雷他定": "氯雷他定",
        "西替利嗪": "氯雷他定",
        "阿托伐他汀": "阿托伐他汀",
        "瑞舒伐他汀": "阿托伐他汀",
        "辛伐他汀": "阿托伐他汀",
    }

    for suggestion in suggestions:
        for exam in suggestion.get("recommended_exams", []):
            name = exam.get("exam_name", "")
            name_lower = name.lower().strip()
            alias_key = EXAM_ALIASES.get(name_lower, "")
            exam["exam_item_id"] = _find_exam_id(name_lower, alias_key, exam_records)

        for drug in suggestion.get("recommended_drugs", []):
            name = drug.get("drug_name", "")
            name_lower = name.lower().strip()
            alias_key = DRUG_ALIASES.get(name_lower, "")
            drug["drug_id"] = _find_drug_id(name_lower, alias_key, drug_records)

    return suggestions


def _find_exam_id(name_lower: str, alias_key: str, records: list[dict]) -> int | None:
    """用名称和别名匹配检查项目ID。"""
    # 精确匹配
    for r in records:
        if name_lower == r["name"]:
            return r["id"]
    # 别名匹配
    if alias_key:
        for r in records:
            if alias_key.lower() in r["name"]:
                return r["id"]
    # 部分匹配
    for r in records:
        if _partial_match(name_lower, r["name"]):
            return r["id"]
    return None


def _find_drug_id(name_lower: str, alias_key: str, records: list[dict]) -> int | None:
    """用名称和别名匹配药品ID。"""
    for r in records:
        if name_lower == r["name"]:
            return r["id"]
    if alias_key:
        for r in records:
            if alias_key.lower() in r["name"]:
                return r["id"]
    for r in records:
        if _partial_match(name_lower, r["name"]):
            return r["id"]
    return None


def _partial_match(query: str, target: str) -> bool:
    """部分匹配：query 的任意 2 字片段出现在 target 中。"""
    if len(query) < 2:
        return query in target
    for i in range(len(query) - 1):
        if query[i : i + 2] in target:
            return True
    return False
