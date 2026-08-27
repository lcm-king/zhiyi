"""
支付路由
POST /api/pay/alipay/create  — 创建支付宝扫码支付
POST /api/pay/alipay/notify  — 支付宝异步回调（更新订单状态）
GET  /api/pay/alipay/query   — 查询支付状态（轮询用）
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_role
from app.config import get_settings
from app.crud import drug_crud, exam_crud
from app.database import get_db
from app.models import Patient, User
from app.services.alipay import generate_payment_url, query_payment

logger = logging.getLogger("zhiyi.payment")

router = APIRouter()


class AlipayCreateRequest(BaseModel):
    order_id: int = Field(..., description="订单 ID")
    order_type: str = Field(..., pattern=r"^(exam|drug)$")
    amount: float = Field(default=0.01, gt=0)


@router.post("/alipay/create", summary="创建支付宝扫码支付")
async def create_alipay_payment(
    payload: AlipayCreateRequest,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """生成扫码支付二维码，仅限订单本人。"""
    if db is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="数据库不可用")
    patient = await _current_patient(db, current_user)
    await _ensure_order_owned(db, patient.id, payload.order_type, payload.order_id)

    out_trade_no = (
        f"ZHIYI_{payload.order_type}_{payload.order_id}_{int(payload.amount * 100)}"
        f"_{int(time.time())}"
    )
    subject = (
        "智医检查预约" if payload.order_type == "exam" else "智医药品订单"
    )

    result = generate_payment_url(
        out_trade_no=out_trade_no,
        subject=subject,
        total_amount=payload.amount,
    )

    result["out_trade_no"] = out_trade_no
    return result


@router.get("/alipay/query", summary="查询支付状态")
async def query_alipay_payment(
    out_trade_no: str = Query(...),
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """查询支付宝支付状态，仅限订单本人轮询。"""
    if db is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="数据库不可用")
    parsed = _parse_out_trade_no(out_trade_no)
    if not parsed:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="无效的交易号")
    order_type, order_id = parsed
    patient = await _current_patient(db, current_user)
    await _ensure_order_owned(db, patient.id, order_type, order_id)
    return query_payment(out_trade_no)


@router.post("/alipay/notify", summary="支付宝支付回调")
async def alipay_notify(
    request: Request,
    db: Optional[AsyncSession] = Depends(get_db),
):
    """接收支付宝异步支付结果通知，并同步订单状态。

    支付宝要求：处理成功后返回纯文本 "success"，否则返回 "fail" 等待重试。
    支付成功（TRADE_SUCCESS / TRADE_FINISHED）时：
      - drug 订单：标记为已支付并自动发货（pay_status=paid, delivery_status=shipped）
      - exam 订单：将该 order_id 下所有预约标记为已支付
    同时写入支付流水（payments 表），保证幂等（重复通知不会重复入账）。
    """
    form = await request.form()
    params = dict(form)

    if not verify_sign(params):
        logger.warning("支付宝回调验签失败: out_trade_no=%s", params.get("out_trade_no", ""))
        return "fail"

    trade_status = params.get("trade_status", "")
    out_trade_no = params.get("out_trade_no", "")

    # 非成功状态（如 WAIT_BUYER_PAY / TRADE_CLOSED）无需处理，直接应答
    if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        return "success"

    if db is None:
        logger.error("数据库不可用，支付宝回调暂不处理: %s", out_trade_no)
        return "fail"

    try:
        ok = await _mark_order_paid(
            db,
            out_trade_no=out_trade_no,
            trade_no=params.get("trade_no", ""),
        )
    except Exception as exc:
        logger.exception("支付宝回调处理异常: out_trade_no=%s", out_trade_no)
        return "fail"

    return "success" if ok else "fail"


async def _mark_order_paid(
    db: AsyncSession,
    *,
    out_trade_no: str,
    trade_no: str,
) -> bool:
    """解析 out_trade_no（ZHIYI_{order_type}_{order_id}_{amount_cents}_{ts}）并更新订单状态。"""
    prefix = "ZHIYI_"
    if not out_trade_no.startswith(prefix):
        logger.warning("无法识别的 out_trade_no: %s", out_trade_no)
        return False

    parts = out_trade_no[len(prefix):].split("_")
    if len(parts) < 2:
        logger.warning("out_trade_no 格式不正确: %s", out_trade_no)
        return False

    order_type, order_id_str = parts[0], parts[1]
    amount_cents = parts[2] if len(parts) > 2 else "0"
    try:
        order_id = int(order_id_str)
        amount = round(int(amount_cents) / 100, 2) if amount_cents.isdigit() else 0.0
    except ValueError:
        logger.warning("out_trade_no 解析失败: %s", out_trade_no)
        return False

    # ── 幂等保护：该订单已有成功支付流水则直接应答 ──
    from app.models import Payment, PaymentMethod, PaymentStatus

    existing = await db.execute(
        select(Payment).where(
            Payment.order_id == order_id,
            Payment.order_type == order_type,
            Payment.status == PaymentStatus.SUCCESS,
        )
    )
    if existing.scalar_one_or_none():
        logger.info("支付宝回调重复通知，订单已支付，忽略: %s", out_trade_no)
        return True

    # ── 更新订单状态 ──
    if order_type == "drug":
        from app.crud import drug_crud

        order = await drug_crud.pay_order(db, order_id)  # 支付成功 → 自动发货
        if order is None:
            # 可能已被前端模拟支付接口处理过
            order = await drug_crud.get_order_by_id(db, order_id)
            if not order or order.pay_status.value != "paid":
                logger.warning("药品订单不存在或状态异常，无法回调入账: order_id=%d", order_id)
                return False

        # 支付回调同样触发自动配送（含冷链温度），与前端模拟支付保持口径一致
        try:
            import asyncio
            from app.services.logistics import generate_route

            cold_chain = await drug_crud.order_requires_cold_chain(db, order_id)
            asyncio.create_task(generate_route(order_id, dest_address=order.address, need_cold_chain=cold_chain))
        except Exception as exc:
            logger.warning("支付回调触发配送路线生成失败：order_id=%d, %s", order_id, exc)
    elif order_type == "exam":
        from app.crud import exam_crud

        appointments = await exam_crud.get_appointments_by_order_id(db, order_id)
        if not appointments:
            logger.warning("检查订单不存在，无法回调入账: order_id=%d", order_id)
            return False
        for appointment in appointments:
            await exam_crud.pay_appointment(db, appointment.id)
        # 支付回调同样触发自动出报告（与前端模拟支付口径一致）
        try:
            await exam_crud.schedule_auto_report(order_id)
        except Exception as exc:
            logger.warning("支付回调触发检查报告自动生成失败：order_id=%d, %s", order_id, exc)
    else:
        logger.warning("未知订单类型: %s", order_type)
        return False

    # ── 写入支付流水 ──
    payment = Payment(
        order_id=order_id,
        order_type=order_type,
        amount=amount,
        status=PaymentStatus.SUCCESS,
        payment_method=PaymentMethod.ALIPAY,
        transaction_no=trade_no or f"ALIPAY{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        paid_at=datetime.utcnow(),
    )
    db.add(payment)
    await db.commit()

    logger.info(
        "支付宝回调入账成功: order_type=%s, order_id=%d, amount=%.2f, trade_no=%s",
        order_type, order_id, amount, trade_no,
    )
    return True


async def _current_patient(db: AsyncSession, current_user: User) -> Patient:
    result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
    patient = result.scalar_one_or_none()
    if not patient:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="当前账号未关联患者档案")
    return patient


async def _ensure_order_owned(
    db: AsyncSession,
    patient_id: int,
    order_type: str,
    order_id: int,
) -> None:
    from fastapi import HTTPException

    if order_type == "drug":
        order = await drug_crud.get_order_by_id(db, order_id)
        if not order or order.patient_id != patient_id:
            raise HTTPException(status_code=404, detail="订单不存在")
    elif order_type == "exam":
        appointments = await exam_crud.get_appointments_by_order_id(db, order_id)
        if not appointments or any(a.patient_id != patient_id for a in appointments):
            raise HTTPException(status_code=404, detail="订单不存在")
    else:
        raise HTTPException(status_code=400, detail="无效的订单类型")


def _parse_out_trade_no(out_trade_no: str) -> Optional[tuple[str, int]]:
    prefix = "ZHIYI_"
    if not out_trade_no.startswith(prefix):
        return None
    parts = out_trade_no[len(prefix):].split("_")
    if len(parts) < 2 or parts[0] not in ("drug", "exam"):
        return None
    try:
        return parts[0], int(parts[1])
    except ValueError:
        return None


def verify_sign(params: dict) -> bool:
    """校验支付宝异步通知签名（RSA2）。

    演示/模拟模式（PAY_MOCK=true 或未配置公钥）下跳过验签，便于本地联调。
    """
    from app.services.alipay import PAY_MOCK, _rsa_verify, _sort_params

    sign = params.pop("sign", "")
    params.pop("sign_type", None)

    if PAY_MOCK and get_settings().debug:
        return True

    if not sign:
        logger.warning("支付宝回调缺少 sign 参数")
        return False

    content = _sort_params(params)
    return _rsa_verify(content, sign)
