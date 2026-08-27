"""
智医 (ZhiYi) — 患者健康档案路由
基层医疗AI辅助诊疗平台

GET    /api/profile/{patient_id}        — 获取患者健康档案
PUT    /api/profile/{patient_id}        — 更新健康档案
GET    /api/profile/{patient_id}/visits — 就诊记录
GET    /api/profile/{patient_id}/trend  — 健康趋势数据
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, require_role
from app.crud import user_crud
from app.database import get_db
from app.models import Diagnosis, Doctor, ExamAppointment, Patient, User
from app.schemas import MessageResponse, PatientListItem, PatientProfileResponse, PatientProfileUpdate

router = APIRouter()


@router.get(
    "/patients",
    response_model=list[PatientListItem],
    summary="患者列表",
)
async def list_patients(
    current_user: User = Depends(require_role("doctor", "admin")),
    db: Optional[AsyncSession] = Depends(get_db),
    search: Optional[str] = Query(None, description="按姓名/手机号搜索"),
) -> list[PatientListItem]:
    """获取患者列表，供医生选择患者进行诊断。搜索走 Elasticsearch。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    if search and search.strip():
        from app.services.elasticsearch import search_patients
        es_ids, _ = await search_patients(search.strip())
        patients = await user_crud.get_patients_by_ids(db, es_ids) if es_ids else []
    else:
        patients = await user_crud.get_all_patients(db, limit=100)

    return [PatientListItem(**p) for p in patients]


@router.get(
    "/{patient_id}",
    response_model=PatientProfileResponse,
    summary="患者健康档案",
)
async def get_profile(
    patient_id: int,
    current_user: User = Depends(require_role("doctor", "patient", "admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> PatientProfileResponse:
    """获取患者完整健康档案（医生/患者本人/管理员）。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    # 患者只能查看自己的档案（强制用登录用户的 patient_id，忽略路径参数，避免前端传错 user_id）
    if current_user.role.value == "patient":
        patient_result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
        me = patient_result.scalar_one_or_none()
        if not me:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="患者档案不存在")
        patient_id = me.id

    profile = await user_crud.get_patient_profile(db, patient_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="患者不存在")

    recent_visits = await _get_recent_visits(db, patient_id)
    health_trend = await _get_health_trend(db, patient_id)
    visit_count = await _get_visit_count(db, patient_id)
    recent_reports = await _get_recent_reports(db, patient_id)

    response = PatientProfileResponse(
        patient_id=profile["id"],
        name=profile["name"],
        gender=profile["gender"],
        birth_date=profile["birth_date"],
        phone=profile["phone"],
        age=profile.get("age", 0),
        allergies=profile.get("allergies", []),
        past_history=profile.get("past_history", []),
        family_history=profile.get("family_history", []),
        lifestyle=profile.get("lifestyle", {}),
        recent_visits=recent_visits,
        visit_count=visit_count,
        recent_reports=recent_reports,
        health_trend=health_trend,
    )

    # 同步写入 MongoDB patient_profiles（含就诊 visits + 健康趋势）
    try:
        from app.services.mongo import upsert_patient_profile

        await upsert_patient_profile(
            patient_id,
            {
                "name": response.name,
                "gender": response.gender,
                "birth_date": response.birth_date,
                "phone": response.phone,
                "age": response.age,
                "allergies": response.allergies,
                "past_history": response.past_history,
                "family_history": response.family_history,
                "lifestyle": response.lifestyle,
                "recent_visits": recent_visits,
                "visit_count": visit_count,
                "recent_reports": recent_reports,
                "health_trend": health_trend,
            },
        )
    except Exception as exc:
        import logging
        logging.getLogger("zhiyi.profile").warning("MongoDB 档案同步失败：%s", exc)

    return response


@router.put(
    "/{patient_id}",
    response_model=MessageResponse,
    summary="更新健康档案",
)
async def update_profile(
    patient_id: int,
    payload: PatientProfileUpdate,
    current_user: User = Depends(require_role("doctor", "patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """更新患者健康档案（医生或患者本人）。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    if current_user.role.value == "patient":
        patient_result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
        me = patient_result.scalar_one_or_none()
        if not me or me.id != patient_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能更新自己的档案")

    patient = await db.execute(select(Patient).where(Patient.id == patient_id))
    if not patient.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="患者不存在")

    await user_crud.update_health_profile(
        db,
        patient_id,
        allergies=payload.allergies,
        past_history=payload.past_history,
        family_history=payload.family_history,
        lifestyle=payload.lifestyle,
    )

    # 同步更新 MongoDB patient_profiles 文档
    try:
        from app.services.mongo import upsert_patient_profile

        profile = await user_crud.get_patient_profile(db, patient_id)
        if profile:
            await upsert_patient_profile(
                patient_id,
                {
                    "name": profile.get("name", ""),
                    "gender": profile.get("gender", ""),
                    "birth_date": profile.get("birth_date", ""),
                    "phone": profile.get("phone", ""),
                    "age": profile.get("age", 0),
                    "allergies": payload.allergies or profile.get("allergies", []),
                    "past_history": payload.past_history or profile.get("past_history", []),
                    "family_history": payload.family_history or profile.get("family_history", []),
                    "lifestyle": payload.lifestyle or profile.get("lifestyle", {}),
                },
            )
    except Exception as exc:
        import logging
        logging.getLogger("zhiyi.profile").warning("MongoDB 档案更新同步失败：%s", exc)

    return MessageResponse(message="健康档案已更新")


@router.get(
    "/{patient_id}/visits",
    response_model=list[dict[str, Any]],
    summary="就诊记录",
)
async def get_visits(
    patient_id: int,
    current_user: User = Depends(require_role("doctor", "patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[dict[str, Any]]:
    """获取患者就诊记录（来自诊断记录）。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    if current_user.role.value == "patient":
        patient_result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
        me = patient_result.scalar_one_or_none()
        if not me:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="患者档案不存在")
        patient_id = me.id

    return await _get_recent_visits(db, patient_id)


@router.get(
    "/{patient_id}/trend",
    response_model=list[dict[str, Any]],
    summary="健康趋势",
)
async def get_health_trend(
    patient_id: int,
    current_user: User = Depends(require_role("doctor", "patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[dict[str, Any]]:
    """获取患者健康趋势（基于诊断记录和检查记录生成）。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    if current_user.role.value == "patient":
        patient_result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
        me = patient_result.scalar_one_or_none()
        if not me:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="患者档案不存在")
        patient_id = me.id

    return await _get_health_trend(db, patient_id)


# =============================================================================
# 内部辅助
# =============================================================================

async def _get_recent_visits(db: AsyncSession, patient_id: int, limit: int = 10) -> list[dict[str, Any]]:
    """获取最近就诊记录。"""
    result = await db.execute(
        select(Diagnosis, Doctor)
        .join(Doctor, Diagnosis.doctor_id == Doctor.id)
        .options(selectinload(Doctor.hospital))
        .where(Diagnosis.patient_id == patient_id)
        .order_by(Diagnosis.created_at.desc())
        .limit(limit)
    )
    visits = []
    for diag, doctor in result.all():
        visits.append({
            "date": diag.created_at.strftime("%Y-%m-%d %H:%M"),
            "hospital": doctor.hospital.name if doctor.hospital else "",
            "doctor": doctor.name,
            "diagnosis": diag.final_diagnosis or "AI 辅助诊断待确认",
            "treatment": diag.treatment_plan or "",
        })
    return visits


async def _get_health_trend(db: AsyncSession, patient_id: int) -> list[dict[str, Any]]:
    """生成健康趋势（真实数据驱动，不做随机/写死模拟）。

    数据来源：
      1. Diagnosis 诊断记录（就诊频次）
      2. ExamAppointment 检查预约（完成数 + 结构化报告 + AI 解读）
      3. 健康档案风险因子（慢性病史 / 过敏史 / 家族史）

    按自然周聚合最近 8 周；没有任何记录的周不出现，避免伪造数据。
    无任何就诊/检查记录时返回空数组，由前端展示“暂无数据”空态。
    """
    diag_result = await db.execute(
        select(Diagnosis.created_at)
        .where(Diagnosis.patient_id == patient_id)
    )
    diag_dates = [row[0] for row in diag_result.all() if row[0]]

    exam_result = await db.execute(
        select(ExamAppointment.appointment_time, ExamAppointment.status,
               ExamAppointment.report_data, ExamAppointment.ai_interpretation)
        .where(ExamAppointment.patient_id == patient_id)
    )
    exam_rows = exam_result.all()

    if not diag_dates and not exam_rows:
        return []

    # 档案风险因子（真实档案）
    try:
        profile = await user_crud.get_patient_profile(db, patient_id) or {}
    except Exception:
        profile = {}
    risk_penalty = (
        len(profile.get("past_history", []) or []) * 3
        + len(profile.get("allergies", []) or []) * 1
        + len(profile.get("family_history", []) or []) * 1
    )

    today = date.today()
    # 本周一
    monday = today - timedelta(days=today.weekday())
    weeks: list[tuple[date, int, int, int]] = []
    for i in range(7, -1, -1):
        start = monday - timedelta(weeks=i)
        weeks.append((start, 0, 0, 0))

    def _week_index(dt: datetime) -> int:
        d = dt.date() if hasattr(dt, "date") else dt
        if d >= monday:
            idx = (d - monday).days // 7
            return idx if 0 <= idx < len(weeks) else -1
        # 周一之前但属于上一个自然周的日期（如周日的记录）归到上一周
        weeks_before = (monday - d).days
        idx = (weeks_before + 6) // 7
        return idx if 0 <= idx < len(weeks) else -1

    for d in diag_dates:
        idx = _week_index(d)
        if idx >= 0:
            weeks[idx] = (weeks[idx][0], weeks[idx][1] + 1, weeks[idx][2], weeks[idx][3])

    done_statuses = {"completed", "done", "finished", "reported", "COMPLETED", "DONE", "FINISHED"}
    for appt_time, status, report_data, ai_text in exam_rows:
        idx = _week_index(appt_time)
        if idx < 0:
            continue
        _, visits, exams_done, exams_ai = weeks[idx]
        done = (status or "") in done_statuses or bool(report_data)
        weeks[idx] = (weeks[idx][0], visits, exams_done + (1 if done else 0), exams_ai + (1 if ai_text else 0))

    trend: list[dict[str, Any]] = []
    for start, visits, exams_done, exams_ai in weeks:
        if visits == 0 and exams_done == 0:
            continue
        # 健康指数 = 基础分 − 慢性病/过敏/家族史风险 − 本周就诊波动 + 主动检查管理
        score = 88 - risk_penalty - visits * 2 + exams_done * 2 + exams_ai
        score = max(55, min(95, score))
        trend.append({
            "date": start.strftime("%m-%d"),
            "score": score,
            "visits": visits,
            "exams": exams_done,
        })
    return trend


async def _get_visit_count(db: AsyncSession, patient_id: int) -> int:
    """真实就诊次数：统计 Diagnosis 诊断记录总数。"""
    result = await db.execute(
        select(func.count()).select_from(Diagnosis).where(Diagnosis.patient_id == patient_id)
    )
    return int(result.scalar_one() or 0)


async def _get_recent_reports(db: AsyncSession, patient_id: int, limit: int = 3) -> list[dict[str, Any]]:
    """最新检查报告：来自 ExamAppointment 的真实报告数据（结构化报告或 AI 解读）。"""
    from app.models import ExamAppointment

    result = await db.execute(
        select(ExamAppointment)
        .options(selectinload(ExamAppointment.exam_item), selectinload(ExamAppointment.hospital))
        .where(
            ExamAppointment.patient_id == patient_id,
            or_(
                ExamAppointment.report_data.isnot(None),
                ExamAppointment.ai_interpretation.isnot(None),
            ),
        )
        .order_by(ExamAppointment.created_at.desc())
        .limit(limit)
    )
    reports = []
    for a in result.scalars().all():
        item = a.exam_item
        hospital = a.hospital
        dt = a.created_at or a.appointment_time
        ai_text = a.ai_interpretation or ""
        reports.append({
            "appointment_id": a.id,
            "order_id": a.order_id,
            "exam_name": item.name if item else "检查项目",
            "hospital": hospital.name if hospital else "",
            "date": dt.strftime("%Y-%m-%d %H:%M") if dt else "",
            "summary": (ai_text[:80] + ("…" if len(ai_text) > 80 else "")) if ai_text else "",
            "has_interpretation": bool(ai_text),
            "status": a.status.value if a.status else "pending",
        })
    return reports
