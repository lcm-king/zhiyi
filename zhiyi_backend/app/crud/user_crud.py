"""
智医 (ZhiYi) — 用户管理数据访问层
基层医疗AI辅助诊疗平台

管理员视角的用户 CRUD 操作，含关联的医生/患者档案管理。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.models import Doctor, Gender, Patient, PatientHealthProfile, User, UserRole

logger = logging.getLogger("zhiyi.user_crud")


# =============================================================================
# 用户 CRUD
# =============================================================================

async def get_all_users(
    db: AsyncSession,
    *,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[User]:
    """获取用户列表，支持按角色和状态筛选。"""
    query = select(User)
    if role:
        query = query.where(User.role == UserRole(role))
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    query = query.offset(skip).limit(limit).order_by(User.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_phone(db: AsyncSession, phone: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.phone == phone))
    return result.scalar_one_or_none()


async def create_user_with_profile(
    db: AsyncSession,
    username: str,
    phone: str,
    password: str,
    role: str,
    *,
    name: Optional[str] = None,
    department: Optional[str] = None,
    hospital_id: Optional[int] = None,
    title: Optional[str] = None,
    gender: Optional[str] = None,
    birth_date: Optional[str] = None,
) -> User:
    """管理员创建用户，同时创建关联的医生/患者档案。"""
    # 检查唯一性
    existing_phone = await get_user_by_phone(db, phone)
    if existing_phone:
        raise ValueError("该手机号已被注册")

    existing_name = await db.execute(select(User).where(User.username == username))
    if existing_name.scalar_one_or_none():
        raise ValueError("该用户名已被使用")

    # 创建用户
    user = User(
        username=username,
        phone=phone,
        password_hash=hash_password(password),
        role=UserRole(role),
        hospital_id=hospital_id,
        is_active=True,
    )
    db.add(user)
    await db.flush()  # 获取 user.id

    # 创建关联档案
    if role == "doctor":
        doctor = Doctor(
            user_id=user.id,
            name=name or username,
            department=department or "",
            hospital_id=hospital_id or 1,
            title=title or "医师",
        )
        db.add(doctor)
    elif role == "patient":
        patient = Patient(
            user_id=user.id,
            name=name or username,
            gender=Gender(gender) if gender else Gender.M,
            birth_date=datetime.strptime(birth_date, "%Y-%m-%d") if birth_date else datetime(1990, 1, 1),
            phone=phone,
        )
        db.add(patient)

    await db.commit()
    await db.refresh(user)
    logger.info("管理员创建用户：id=%d, username=%s, role=%s", user.id, username, role)
    return user


async def toggle_user_active(db: AsyncSession, user_id: int) -> Optional[User]:
    """切换用户启用/禁用状态。"""
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    user.is_active = not user.is_active
    await db.commit()
    await db.refresh(user)
    logger.info("用户状态变更：id=%d, active=%s", user_id, user.is_active)
    return user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    """软删除用户（设为禁用）。"""
    user = await get_user_by_id(db, user_id)
    if not user:
        return False
    user.is_active = False
    await db.commit()
    logger.info("用户已禁用：id=%d", user_id)
    return True


# =============================================================================
# 医生档案查询
# =============================================================================

async def get_all_doctors(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """获取所有医生列表（含关联用户信息）。"""
    result = await db.execute(
        select(Doctor, User)
        .join(User, Doctor.user_id == User.id)
        .offset(skip)
        .limit(limit)
        .order_by(Doctor.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": d.id,
            "user_id": d.user_id,
            "name": d.name,
            "department": d.department,
            "title": d.title,
            "specialty": d.specialty,
            "is_active": u.is_active,
            "username": u.username,
            "phone": u.phone,
            "created_at": u.created_at.isoformat(),
        }
        for d, u in rows
    ]


async def get_patient_profile(db: AsyncSession, patient_id: int) -> Optional[dict[str, Any]]:
    """获取患者档案（含年龄计算、健康档案），用于诊断工作流。"""
    result = await db.execute(
        select(Patient, User, PatientHealthProfile)
        .join(User, Patient.user_id == User.id)
        .outerjoin(PatientHealthProfile, PatientHealthProfile.patient_id == Patient.id)
        .where(Patient.id == patient_id)
    )
    row = result.first()
    if not row:
        return None
    patient, user, profile = row
    from datetime import date
    today = date.today()
    birth = patient.birth_date.date() if hasattr(patient.birth_date, "date") else patient.birth_date
    age = today.year - birth.year - (
        (today.month, today.day) < (birth.month, birth.day)
    )
    return {
        "id": patient.id,
        "user_id": user.id,
        "name": patient.name,
        "gender": patient.gender.value,
        "birth_date": birth.strftime("%Y-%m-%d"),
        "age": age,
        "phone": patient.phone,
        "is_active": user.is_active,
        "allergies": profile.allergies if profile else [],
        "past_history": profile.past_history if profile else [],
        "family_history": profile.family_history if profile else [],
        "lifestyle": profile.lifestyle if profile else {},
    }


async def get_health_profile(db: AsyncSession, patient_id: int) -> Optional[PatientHealthProfile]:
    """获取患者健康档案记录。"""
    result = await db.execute(
        select(PatientHealthProfile).where(PatientHealthProfile.patient_id == patient_id)
    )
    return result.scalar_one_or_none()


async def update_health_profile(
    db: AsyncSession,
    patient_id: int,
    *,
    allergies: Optional[list[str]] = None,
    past_history: Optional[list[str]] = None,
    family_history: Optional[list[str]] = None,
    lifestyle: Optional[dict[str, Any]] = None,
) -> PatientHealthProfile:
    """更新患者健康档案，不存在则创建。"""
    profile = await get_health_profile(db, patient_id)
    if not profile:
        profile = PatientHealthProfile(
            patient_id=patient_id,
            allergies=allergies or [],
            past_history=past_history or [],
            family_history=family_history or [],
            lifestyle=lifestyle or {},
        )
        db.add(profile)
    else:
        if allergies is not None:
            profile.allergies = allergies
        if past_history is not None:
            profile.past_history = past_history
        if family_history is not None:
            profile.family_history = family_history
        if lifestyle is not None:
            profile.lifestyle = lifestyle
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_all_patients(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """获取所有患者列表。"""
    result = await db.execute(
        select(Patient, User)
        .join(User, Patient.user_id == User.id)
        .offset(skip)
        .limit(limit)
        .order_by(Patient.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": p.id,
            "user_id": p.user_id,
            "name": p.name,
            "gender": p.gender.value,
            "birth_date": p.birth_date.strftime("%Y-%m-%d"),
            "phone": p.phone,
            "is_active": u.is_active,
        }
        for p, u in rows
    ]


async def get_patients_by_ids(
    db: AsyncSession,
    patient_ids: list[int],
) -> list[dict[str, Any]]:
    """按 ID 列表批量查询患者（配合 ES 搜索使用）。"""
    if not patient_ids:
        return []
    result = await db.execute(
        select(Patient, User)
        .join(User, Patient.user_id == User.id)
        .where(Patient.id.in_(patient_ids))
        .order_by(Patient.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": p.id,
            "user_id": p.user_id,
            "name": p.name,
            "gender": p.gender.value,
            "birth_date": p.birth_date.strftime("%Y-%m-%d"),
            "phone": p.phone,
            "is_active": u.is_active,
        }
        for p, u in rows
    ]
