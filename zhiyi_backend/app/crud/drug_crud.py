"""
智医 (ZhiYi) — 药品与订单数据访问层
基层医疗AI辅助诊疗平台

提供药品目录、购物车（Redis Hash）、药品订单的 CRUD 操作。
优化后订单模型：drug_orders（主订单）+ drug_order_items（订单项）。
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
from app.models import DeliveryStatus, Drug, DrugOrder, DrugOrderItem, PayStatus, Prescription

logger = logging.getLogger("zhiyi.drug_crud")
settings = get_settings()

# Redis 购物车 Key
CART_KEY_PREFIX = "cart:drug"
CART_TTL = 7 * 24 * 3600


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


def _cart_key(patient_id: int) -> str:
    return f"{CART_KEY_PREFIX}:{patient_id}"


def _generate_order_no() -> str:
    """生成药品订单编号。"""
    return f"DR{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[:16]}"


# =============================================================================
# 药品目录 CRUD
# =============================================================================

async def get_drugs(
    db: AsyncSession,
    *,
    is_active: bool = True,
    need_prescription: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Drug]:
    """获取药品列表，支持按处方药筛选。"""
    query = select(Drug)
    if is_active:
        query = query.where(Drug.is_active == True)
    if need_prescription is not None:
        query = query.where(Drug.need_prescription == need_prescription)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_drug_by_id(db: AsyncSession, drug_id: int) -> Optional[Drug]:
    result = await db.execute(select(Drug).where(Drug.id == drug_id))
    return result.scalar_one_or_none()


async def create_drug(db: AsyncSession, **kwargs: Any) -> Drug:
    drug = Drug(**kwargs)
    db.add(drug)
    await db.commit()
    await db.refresh(drug)
    return drug


async def update_drug(db: AsyncSession, drug_id: int, **kwargs: Any) -> Optional[Drug]:
    drug = await get_drug_by_id(db, drug_id)
    if not drug:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(drug, key):
            setattr(drug, key, value)
    await db.commit()
    await db.refresh(drug)
    return drug


async def deduct_stock(db: AsyncSession, drug_id: int, quantity: int) -> Optional[Drug]:
    """扣减库存（原子操作）。"""
    drug = await get_drug_by_id(db, drug_id)
    if not drug or drug.stock < quantity:
        return None
    drug.stock -= quantity
    await db.commit()
    await db.refresh(drug)
    return drug


# =============================================================================
# 购物车（Redis Hash）
# =============================================================================

async def get_cart(patient_id: int) -> dict[int, int]:
    r = await _get_redis()
    try:
        raw = await r.hgetall(_cart_key(patient_id))
        return {int(k): int(v) for k, v in raw.items()}
    finally:
        await r.aclose()


async def add_to_cart(patient_id: int, drug_id: int, quantity: int = 1) -> dict[int, int]:
    r = await _get_redis()
    try:
        key = _cart_key(patient_id)
        current = int(await r.hget(key, str(drug_id)) or 0)
        await r.hset(key, str(drug_id), str(current + quantity))
        await r.expire(key, CART_TTL)
        raw = await r.hgetall(key)
        return {int(k): int(v) for k, v in raw.items()}
    finally:
        await r.aclose()


async def update_cart_item(patient_id: int, drug_id: int, quantity: int) -> dict[int, int]:
    r = await _get_redis()
    try:
        key = _cart_key(patient_id)
        if quantity <= 0:
            await r.hdel(key, str(drug_id))
        else:
            await r.hset(key, str(drug_id), str(quantity))
        await r.expire(key, CART_TTL)
        raw = await r.hgetall(key)
        return {int(k): int(v) for k, v in raw.items()}
    finally:
        await r.aclose()


async def remove_from_cart(patient_id: int, drug_id: int) -> dict[int, int]:
    r = await _get_redis()
    try:
        key = _cart_key(patient_id)
        await r.hdel(key, str(drug_id))
        await r.expire(key, CART_TTL)
        raw = await r.hgetall(key)
        return {int(k): int(v) for k, v in raw.items()}
    finally:
        await r.aclose()


async def clear_cart(patient_id: int) -> None:
    r = await _get_redis()
    try:
        await r.delete(_cart_key(patient_id))
    finally:
        await r.aclose()


# =============================================================================
# 药品订单 CRUD（重构后：主订单 + 订单项）
# =============================================================================

async def create_order(
    db: AsyncSession,
    patient_id: int,
    items: dict[int, int],  # {drug_id: quantity}
    address: str,
    prescription_id: Optional[int] = None,
) -> DrugOrder:
    """创建药品订单（一个主订单可包含多种药品）。"""
    # 校验处方（如提供）
    if prescription_id:
        prescription = await db.execute(
            select(Prescription).where(Prescription.id == prescription_id)
        )
        if not prescription.scalar_one_or_none():
            raise ValueError("处方不存在")

    # 先创建主订单占位，计算总价后再更新
    order = DrugOrder(
        patient_id=patient_id,
        prescription_id=prescription_id,
        order_no=_generate_order_no(),
        total_price=0.0,
        pay_status=PayStatus.PENDING,
        delivery_status=DeliveryStatus.PENDING,
        address=address,
    )
    db.add(order)
    await db.flush()  # 获取 order.id

    total_price = 0.0
    for drug_id, qty in items.items():
        drug = await get_drug_by_id(db, drug_id)
        if not drug:
            raise ValueError(f"药品 {drug_id} 不存在")
        if not drug.is_active:
            raise ValueError(f"药品「{drug.name}」已下架")
        if drug.stock < qty:
            raise ValueError(f"药品「{drug.name}」库存不足（剩余 {drug.stock}）")

        drug.stock -= qty
        unit_price = drug.price
        subtotal = round(unit_price * qty, 2)
        total_price += subtotal

        order_item = DrugOrderItem(
            drug_order_id=order.id,
            drug_id=drug_id,
            quantity=qty,
            unit_price=unit_price,
            subtotal=subtotal,
        )
        db.add(order_item)

    order.total_price = round(total_price, 2)
    await db.commit()
    await db.refresh(order)

    logger.info("药品订单创建：order_id=%d, order_no=%s, 药品数=%d", order.id, order.order_no, len(items))
    return order


async def get_orders_by_patient(
    db: AsyncSession,
    patient_id: int,
    *,
    pay_status: Optional[PayStatus] = None,
    delivery_status: Optional[DeliveryStatus] = None,
    limit: int = 20,
) -> list[DrugOrder]:
    """查询患者药品订单。"""
    query = select(DrugOrder).where(DrugOrder.patient_id == patient_id)
    if pay_status:
        query = query.where(DrugOrder.pay_status == pay_status)
    if delivery_status:
        query = query.where(DrugOrder.delivery_status == delivery_status)
    query = query.order_by(DrugOrder.created_at.desc()).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_order_by_id(db: AsyncSession, order_id: int) -> Optional[DrugOrder]:
    result = await db.execute(
        select(DrugOrder)
        .where(DrugOrder.id == order_id)
        .options(
            selectinload(DrugOrder.items).selectinload(DrugOrderItem.drug),
            selectinload(DrugOrder.patient),
        )
    )
    return result.scalar_one_or_none()


async def get_order_by_no(db: AsyncSession, order_no: str) -> Optional[DrugOrder]:
    result = await db.execute(select(DrugOrder).where(DrugOrder.order_no == order_no))
    return result.scalar_one_or_none()


async def get_all_orders_for_delivery(
    db: AsyncSession,
    *,
    delivery_status: Optional[DeliveryStatus] = None,
    limit: int = 200,
) -> list[DrugOrder]:
    """管理员视角：获取所有订单（用于发货管理）。"""
    query = (
        select(DrugOrder)
        .options(
            selectinload(DrugOrder.items).selectinload(DrugOrderItem.drug),
            selectinload(DrugOrder.patient),
        )
        .order_by(DrugOrder.created_at.desc())
    )
    if delivery_status:
        query = query.where(DrugOrder.delivery_status == delivery_status)
    query = query.limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def pay_order(db: AsyncSession, order_id: int) -> Optional[DrugOrder]:
    """支付成功：自动进入发货状态，配送状态更新为 shipped 并记录发货时间。"""
    order = await get_order_by_id(db, order_id)
    if not order or order.pay_status != PayStatus.PENDING:
        return None
    order.pay_status = PayStatus.PAID
    order.delivery_status = DeliveryStatus.SHIPPED  # 支付后自动发货
    if not order.shipped_at:
        order.shipped_at = datetime.utcnow()
    await db.commit()
    await db.refresh(order)
    logger.info("支付成功并自动发货：order_id=%d", order_id)
    return order


async def ship_order(db: AsyncSession, order_id: int) -> Optional[DrugOrder]:
    """管理员发货（兜底）：更新配送状态为 shipped 并记录发货时间。"""
    order = await get_order_by_id(db, order_id)
    if not order or order.pay_status != PayStatus.PAID:
        return None
    order.delivery_status = DeliveryStatus.SHIPPED
    if not order.shipped_at:
        order.shipped_at = datetime.utcnow()
    await db.commit()
    await db.refresh(order)
    logger.info("订单发货：order_id=%d", order_id)
    return order


async def deliver_order(db: AsyncSession, order_id: int) -> Optional[DrugOrder]:
    """配送完成：更新状态为 delivered 并记录送达时间。"""
    order = await get_order_by_id(db, order_id)
    if not order or order.delivery_status != DeliveryStatus.SHIPPED:
        return None
    order.delivery_status = DeliveryStatus.DELIVERED
    order.delivered_at = datetime.utcnow()
    await db.commit()
    await db.refresh(order)
    return order


async def order_requires_cold_chain(db: AsyncSession, order_id: int) -> bool:
    """判断订单是否含冷链药品（任一药品 need_cold_chain=True）。"""
    from app.models import DrugOrderItem

    result = await db.execute(
        select(DrugOrderItem).where(DrugOrderItem.drug_order_id == order_id)
    )
    for item in result.scalars().all():
        drug = await get_drug_by_id(db, item.drug_id)
        if drug and drug.need_cold_chain:
            return True
    return False


async def update_prescription_review(
    db: AsyncSession,
    order_id: int,
    review: dict[str, Any],
) -> Optional[DrugOrder]:
    """RabbitMQ 消费者回调：写入 AI 处方审核结果并更新审核状态。"""
    order = await get_order_by_id(db, order_id)
    if not order:
        return None
    order.review_status = "reviewed" if review.get("passed") else "warning"
    order.review_risk = review.get("risk", "low")
    order.review_result = json.dumps(review, ensure_ascii=False)
    await db.commit()
    await db.refresh(order)
    logger.info("处方审核状态已更新：order_id=%d, status=%s, risk=%s", order_id, order.review_status, order.review_risk)
    return order


# =============================================================================
# 处方 CRUD
# =============================================================================

async def create_prescription(
    db: AsyncSession,
    patient_id: int,
    doctor_id: int,
    items: list[dict[str, Any]],
    diagnosis_id: Optional[int] = None,
) -> Prescription:
    """创建处方及处方项目。"""
    from app.models import PrescriptionItem

    prescription = Prescription(
        patient_id=patient_id,
        doctor_id=doctor_id,
        diagnosis_id=diagnosis_id,
    )
    db.add(prescription)
    await db.flush()

    for it in items:
        drug_id = it["drug_id"]
        drug = await get_drug_by_id(db, drug_id)
        if not drug:
            raise ValueError(f"药品 {drug_id} 不存在")
        item = PrescriptionItem(
            prescription_id=prescription.id,
            drug_id=drug_id,
            dosage=it.get("dosage", ""),
            quantity=it.get("quantity", 1),
            duration_days=it.get("duration_days"),
            instructions=it.get("instructions"),
        )
        db.add(item)

    await db.commit()
    await db.refresh(prescription)
    return prescription


async def get_prescription_by_id(db: AsyncSession, prescription_id: int) -> Optional[Prescription]:
    result = await db.execute(select(Prescription).where(Prescription.id == prescription_id))
    return result.scalar_one_or_none()
