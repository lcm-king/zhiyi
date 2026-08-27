"""
智医 (ZhiYi) — 检查预约数据访问层
基层医疗AI辅助诊疗平台

提供检查项目、购物车（Redis Hash）、预约订单的 CRUD 操作。
购物车复用第二阶段电商技术栈，使用 Redis Hash 存储。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import async_session_factory
from app.models import (
    AppointmentStatus,
    ExamAppointment,
    ExamItem,
    Patient,
    PayStatus,
)

logger = logging.getLogger("zhiyi.exam_crud")
settings = get_settings()

# Redis 购物车 Key 前缀
CART_KEY_PREFIX = "cart:exam"
CART_TTL = 7 * 24 * 3600  # 7 天过期


# =============================================================================
# Redis 帮助函数
# =============================================================================

async def _get_redis() -> aioredis.Redis:
    """创建 Redis 连接。"""
    return aioredis.from_url(settings.redis_url, decode_responses=True)


def _cart_key(patient_id: int) -> str:
    """生成购物车 Redis Key：cart:exam:{patient_id}"""
    return f"{CART_KEY_PREFIX}:{patient_id}"


# =============================================================================
# 检查项目 CRUD
# =============================================================================

async def get_exam_items(
    db: AsyncSession,
    *,
    category: Optional[str] = None,
    is_active: bool = True,
    skip: int = 0,
    limit: int = 50,
) -> list[ExamItem]:
    """获取检查项目列表，支持按分类筛选。"""
    query = select(ExamItem)
    if category:
        query = query.where(ExamItem.category == category)
    if is_active:
        query = query.where(ExamItem.is_active == True)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_exam_item_by_id(db: AsyncSession, item_id: int) -> Optional[ExamItem]:
    """根据 ID 获取单个检查项目。"""
    result = await db.execute(select(ExamItem).where(ExamItem.id == item_id))
    return result.scalar_one_or_none()


async def create_exam_item(db: AsyncSession, **kwargs: Any) -> ExamItem:
    """管理员新增检查项目。"""
    item = ExamItem(**kwargs)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_exam_item(db: AsyncSession, item_id: int, **kwargs: Any) -> Optional[ExamItem]:
    """管理员更新检查项目。"""
    item = await get_exam_item_by_id(db, item_id)
    if not item:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(item, key):
            setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return item


# =============================================================================
# 购物车操作（Redis Hash）
# =============================================================================

async def get_cart(patient_id: int) -> dict[int, int]:
    """获取患者检查购物车。

    Redis Hash: field=exam_item_id (str), value=quantity (str)
    返回 {exam_item_id: quantity}
    """
    r = await _get_redis()
    try:
        raw = await r.hgetall(_cart_key(patient_id))
        return {int(k): int(v) for k, v in raw.items()}
    finally:
        await r.aclose()


async def add_to_cart(patient_id: int, exam_item_id: int, quantity: int = 1) -> dict[int, int]:
    """向购物车添加检查项目，如果已存在则叠加数量。"""
    r = await _get_redis()
    try:
        key = _cart_key(patient_id)
        current = int(await r.hget(key, str(exam_item_id)) or 0)
        new_qty = current + quantity
        await r.hset(key, str(exam_item_id), str(new_qty))
        await r.expire(key, CART_TTL)

        raw = await r.hgetall(key)
        return {int(k): int(v) for k, v in raw.items()}
    finally:
        await r.aclose()


async def update_cart_item(patient_id: int, exam_item_id: int, quantity: int) -> dict[int, int]:
    """更新购物车中某个项目的数量。"""
    r = await _get_redis()
    try:
        key = _cart_key(patient_id)
        if quantity <= 0:
            await r.hdel(key, str(exam_item_id))
        else:
            await r.hset(key, str(exam_item_id), str(quantity))
        await r.expire(key, CART_TTL)

        raw = await r.hgetall(key)
        return {int(k): int(v) for k, v in raw.items()}
    finally:
        await r.aclose()


async def remove_from_cart(patient_id: int, exam_item_id: int) -> dict[int, int]:
    """从购物车移除某个项目。"""
    r = await _get_redis()
    try:
        key = _cart_key(patient_id)
        await r.hdel(key, str(exam_item_id))
        await r.expire(key, CART_TTL)

        raw = await r.hgetall(key)
        return {int(k): int(v) for k, v in raw.items()}
    finally:
        await r.aclose()


async def clear_cart(patient_id: int) -> None:
    """清空购物车。"""
    r = await _get_redis()
    try:
        await r.delete(_cart_key(patient_id))
    finally:
        await r.aclose()


# =============================================================================
# 预约订单 CRUD
# =============================================================================

async def create_appointment(
    db: AsyncSession,
    patient_id: int,
    items: dict[int, int],  # {exam_item_id: quantity}
    hospital_id: int,
    appointment_time: datetime,
) -> list[ExamAppointment]:
    """创建检查预约订单。

    为每个检查项目分别创建一条预约记录，共享同一个 order_id。
    """
    # 生成订单号
    order_id = int(datetime.utcnow().timestamp() * 1000) % 100000000

    appointments: list[ExamAppointment] = []
    for exam_item_id, quantity in items.items():
        for _ in range(quantity):
            appointment = ExamAppointment(
                patient_id=patient_id,
                exam_item_id=exam_item_id,
                hospital_id=hospital_id,
                appointment_time=appointment_time,
                status=AppointmentStatus.PENDING,
                order_id=order_id,
            )
            db.add(appointment)
            appointments.append(appointment)

    await db.commit()
    for a in appointments:
        await db.refresh(a)

    logger.info("检查预约订单创建：order_id=%d, 项目数=%d", order_id, len(appointments))
    return appointments


async def get_appointments_by_patient(
    db: AsyncSession,
    patient_id: int,
    *,
    status: Optional[AppointmentStatus] = None,
    limit: int = 20,
) -> list[ExamAppointment]:
    """查询患者的预约记录。"""
    query = select(ExamAppointment).where(
        ExamAppointment.patient_id == patient_id
    )
    if status:
        query = query.where(ExamAppointment.status == status)
    query = query.order_by(ExamAppointment.created_at.desc()).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_appointment_by_id(
    db: AsyncSession,
    appointment_id: int,
) -> Optional[ExamAppointment]:
    """获取单条预约记录。"""
    result = await db.execute(
        select(ExamAppointment).where(ExamAppointment.id == appointment_id)
    )
    return result.scalar_one_or_none()


async def get_appointments_by_order_id(
    db: AsyncSession,
    order_id: int,
) -> list[ExamAppointment]:
    """根据订单号查询所有关联的预约记录。"""
    result = await db.execute(
        select(ExamAppointment).where(ExamAppointment.order_id == order_id)
    )
    return list(result.scalars().all())


async def get_all_appointments(
    db: AsyncSession,
    status: Optional[AppointmentStatus] = None,
) -> list[ExamAppointment]:
    """获取全部检查预约（医生/管理员视角），可按状态过滤，按预约时间倒序。"""
    query = (
        select(ExamAppointment)
        .options(selectinload(ExamAppointment.patient))
        .order_by(ExamAppointment.appointment_time.desc())
    )
    if status:
        query = query.where(ExamAppointment.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def pay_appointment(
    db: AsyncSession,
    appointment_id: int,
) -> Optional[ExamAppointment]:
    """模拟支付：将预约状态从 pending 更新为 paid。"""
    appointment = await get_appointment_by_id(db, appointment_id)
    if not appointment:
        return None
    if appointment.status != AppointmentStatus.PENDING:
        return None

    appointment.status = AppointmentStatus.PAID
    await db.commit()
    await db.refresh(appointment)

    logger.info("检查预约支付成功：appointment_id=%d", appointment_id)
    return appointment


async def confirm_appointment(
    db: AsyncSession,
    appointment_id: int,
) -> Optional[ExamAppointment]:
    """医院确认预约。"""
    appointment = await get_appointment_by_id(db, appointment_id)
    if not appointment or appointment.status != AppointmentStatus.PAID:
        return None
    appointment.status = AppointmentStatus.CONFIRMED
    await db.commit()
    await db.refresh(appointment)
    return appointment


async def complete_appointment(
    db: AsyncSession,
    appointment_id: int,
    report_url: Optional[str] = None,
) -> Optional[ExamAppointment]:
    """完成检查并上传报告链接。"""
    appointment = await get_appointment_by_id(db, appointment_id)
    if not appointment:
        return None
    appointment.status = AppointmentStatus.COMPLETED
    if report_url:
        appointment.report_url = report_url
    await db.commit()
    await db.refresh(appointment)
    return appointment


async def auto_generate_report(
    db: AsyncSession,
    appointment: ExamAppointment,
    *,
    force: bool = False,
) -> Optional[ExamAppointment]:
    """按患者病历自动生成结构化检查报告与 AI 解读（演示链路）。

    仅当预约尚未有报告数据时生成；医生人工上传（update_report）不受影响。
    同一 (patient_id, exam_item_id) 生成的报告数据确定性一致。
    """
    if appointment.report_data is not None and not force:
        return appointment
    if appointment.status not in (
        AppointmentStatus.PAID,
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.COMPLETED,
    ):
        return appointment

    from app.crud import user_crud
    from app.services.report_generator import generate_interpretation, generate_report_data

    profile = await user_crud.get_patient_profile(db, appointment.patient_id) or {}
    item = await get_exam_item_by_id(db, appointment.exam_item_id)
    exam_name = item.name if item else "检查"

    report_data = generate_report_data(
        patient_id=appointment.patient_id,
        exam_item_id=appointment.exam_item_id,
        exam_name=exam_name,
        age=profile.get("age"),
        gender=profile.get("gender"),
        allergies=profile.get("allergies", []),
        past_history=profile.get("past_history", []),
        family_history=profile.get("family_history", []),
        lifestyle=profile.get("lifestyle", {}),
    )
    appointment.report_data = report_data
    appointment.ai_interpretation = generate_interpretation(exam_name, report_data)
    if appointment.status != AppointmentStatus.COMPLETED:
        appointment.status = AppointmentStatus.COMPLETED

    logger.info(
        "检查报告自动生成：appointment_id=%d, exam=%s, source=ai-dynamic",
        appointment.id,
        exam_name,
    )
    return appointment


async def schedule_auto_report(order_id: int, delay_seconds: int = 25) -> None:
    """支付成功后延时自动生成报告（后台任务，失败不影响主流程）。"""
    import asyncio

    async def _worker() -> None:
        await asyncio.sleep(delay_seconds)
        try:
            async with async_session_factory() as db:
                appointments = await get_appointments_by_order_id(db, order_id)
                for appointment in appointments:
                    await auto_generate_report(db, appointment)
                await db.commit()
        except Exception:
            logger.exception("自动生成检查报告失败：order_id=%d", order_id)

    asyncio.create_task(_worker())


async def cancel_appointment(
    db: AsyncSession,
    appointment_id: int,
) -> Optional[ExamAppointment]:
    """取消预约。"""
    appointment = await get_appointment_by_id(db, appointment_id)
    if not appointment:
        return None
    appointment.status = AppointmentStatus.CANCELLED
    await db.commit()
    await db.refresh(appointment)
    return appointment
