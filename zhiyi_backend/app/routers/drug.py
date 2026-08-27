"""
智医 (ZhiYi) — 药品采购路由（优化版）
基层医疗AI辅助诊疗平台

GET    /api/drugs/items              — 药品目录列表
GET    /api/drugs/items/{id}         — 药品详情
GET    /api/drugs/cart               — 查看购物车
POST   /api/drugs/cart               — 加入购物车
PUT    /api/drugs/cart/{id}          — 更新数量
DELETE /api/drugs/cart/{id}          — 移除
DELETE /api/drugs/cart               — 清空
POST   /api/drugs/orders             — 提交订单
GET    /api/drugs/orders             — 我的订单
GET    /api/drugs/orders/{id}        — 订单详情
GET    /api/drugs/orders/{id}/status — 物流状态
POST   /api/drugs/orders/{id}/pay    — 模拟支付
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.crud import drug_crud
from app.database import get_db, safe_db_call
from app.models import DeliveryStatus, Doctor, Drug, DrugOrder, Patient, PayStatus, User
from app.schemas import (
    DrugCartItem,
    DrugItemResponse,
    DrugOrderRequest,
    DrugOrderResponse,
    DrugOrderStatusResponse,
    MessageResponse,
    PaymentRequest,
    PaymentResponse,
)
from app.services.audit import log_audit

router = APIRouter()


# =============================================================================
# 药品目录
# =============================================================================

@router.get(
    "/items",
    response_model=list[DrugItemResponse],
    summary="药品目录列表",
)
async def list_drugs(
    need_prescription: Optional[bool] = Query(None, description="筛选处方药/非处方药"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list:
    """获取上架药品列表。数据库为空时返回模拟数据。"""
    if db is None:
        return []
    return await safe_db_call(
        lambda: drug_crud.get_drugs(db, need_prescription=need_prescription, skip=skip, limit=limit),
        mock_data=[],
        log_msg="药品列表查询失败",
    )


@router.get(
    "/items/{drug_id}",
    response_model=DrugItemResponse,
    summary="药品详情",
)
async def get_drug(drug_id: int, db: Optional[AsyncSession] = Depends(get_db)) -> Drug:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    drug = await drug_crud.get_drug_by_id(db, drug_id)
    if not drug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="药品不存在")
    return drug


# =============================================================================
# 购物车
# =============================================================================

@router.get("/cart", response_model=dict, summary="查看购物车")
async def get_cart(
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> dict:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)
    cart = await drug_crud.get_cart(patient.id)

    items_detail = []
    for drug_id, qty in cart.items():
        drug = await drug_crud.get_drug_by_id(db, drug_id)
        if drug:
            items_detail.append({
                "drug_id": drug.id,
                "name": drug.name,
                "specification": drug.specification,
                "price": drug.price,
                "quantity": qty,
                "subtotal": round(drug.price * qty, 2),
            })

    total = sum(it["subtotal"] for it in items_detail)
    return {
        "patient_id": patient.id,
        "items": items_detail,
        "total_count": len(items_detail),
        "total_price": round(total, 2),
    }


@router.post("/cart", response_model=MessageResponse, summary="加入购物车")
async def add_to_cart(
    payload: DrugCartItem,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)
    drug = await drug_crud.get_drug_by_id(db, payload.drug_id)
    if not drug or not drug.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="药品不存在或已下架")
    if drug.stock < payload.quantity:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"库存不足（剩余 {drug.stock}）")

    await drug_crud.add_to_cart(patient.id, payload.drug_id, payload.quantity)
    return MessageResponse(message=f"已将「{drug.name}」加入购物车")


@router.put("/cart/{drug_id}", response_model=MessageResponse, summary="更新数量")
async def update_cart(
    drug_id: int,
    quantity: int = Query(..., ge=1, le=99),
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)
    await drug_crud.update_cart_item(patient.id, drug_id, quantity)
    return MessageResponse(message="购物车已更新")


@router.delete("/cart/{drug_id}", response_model=MessageResponse, summary="移除")
async def remove_from_cart(
    drug_id: int,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)
    await drug_crud.remove_from_cart(patient.id, drug_id)
    return MessageResponse(message="已从购物车移除")


@router.delete("/cart", response_model=MessageResponse, summary="清空购物车")
async def clear_cart(
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)
    await drug_crud.clear_cart(patient.id)
    return MessageResponse(message="购物车已清空")


# =============================================================================
# 药品订单
# =============================================================================

@router.post("/orders", response_model=DrugOrderResponse, summary="提交订单")
async def create_order(
    payload: DrugOrderRequest,
    current_user: User = Depends(require_role("patient", "doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> DrugOrderResponse:
    """提交药品订单，自动扣减库存并清空购物车。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    # 鎮ｈ€呮湰浜轰笅鍗曚娇鍗曚娇鐢ㄨ嚜宸辨。妗堬紱鍖荤敓浠ｅ紑鍗曚娇鐢 payload.patient_id
    if current_user.role.value == "patient":
        patient = await _get_patient(db, current_user.id)
    else:
        if not payload.patient_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="医生代下单需提供 patient_id")
        result = await db.execute(select(Patient).where(Patient.id == payload.patient_id))
        patient = result.scalar_one_or_none()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="患者档案不存在")

    items_map: dict[int, int] = {}
    for it in payload.items:
        items_map[it.drug_id] = items_map.get(it.drug_id, 0) + it.quantity

    prescription_id = await _resolve_order_prescription(
        db, patient, current_user, items_map, payload.prescription_id
    )

    try:
        order = await drug_crud.create_order(
            db, patient.id, items_map, payload.address, prescription_id=prescription_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 立即加载关联对象（避免 greenlet 错误）
    await db.refresh(order, attribute_names=['items'])
    await log_audit(
        db,
        user_id=current_user.id,
        action="drug_order_create",
        resource="drug_order",
        resource_id=order.id,
        detail={"patient_id": patient.id, "prescription_id": prescription_id},
    )
    rx_map = await _prescription_dosage_map(db, order.prescription_id)
    items_data = []
    for item in order.items:
        drug = await drug_crud.get_drug_by_id(db, item.drug_id)
        rx = rx_map.get(item.drug_id, {})
        items_data.append({
            "id": item.id,
            "drug_id": item.drug_id,
            "drug_name": drug.name if drug else "未知",
            "specification": drug.specification if drug else "",
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "subtotal": item.subtotal,
            "need_cold_chain": drug.need_cold_chain if drug else False,
            "dosage": rx.get("dosage", ""),
            "instructions": rx.get("instructions", ""),
        })

    # 娓呯┖璐墿杞嬶紙浠呮偅鑰呮湰浜轰笅鍗曪級
    if current_user.role.value == "patient":
        await drug_crud.clear_cart(patient.id)

    # 异步发布 AI 处方审核任务（RabbitMQ），失败不影响下单
    try:
        import asyncio
        from app.crud import user_crud
        from app.services.rabbitmq import publish_prescription_review

        review_items = []
        for item in order.items:
            drug = await drug_crud.get_drug_by_id(db, item.drug_id)
            review_items.append({
                "drug_id": item.drug_id,
                "name": drug.name if drug else "",
                "quantity": item.quantity,
            })
        profile = await user_crud.get_patient_profile(db, patient.id)
        allergies = profile.get("allergies", []) if profile else []
        asyncio.create_task(
            publish_prescription_review(
                order.id,
                patient.id,
                review_items,
                allergies=allergies,
            )
        )
    except Exception as exc:
        import logging
        logging.getLogger("zhiyi.drug").warning("发布处方审核任务失败：%s", exc)

    cold_chain = any(it.get("need_cold_chain") for it in items_data)
    return DrugOrderResponse(
        id=order.id,
        order_no=order.order_no,
        patient_id=order.patient_id,
        prescription_id=order.prescription_id,
        items=items_data,
        total_price=order.total_price,
        pay_status=order.pay_status.value,
        delivery_status=order.delivery_status.value,
        address=order.address,
        created_at=order.created_at,
        cold_chain=cold_chain,
    )


@router.get("/orders", response_model=list[DrugOrderResponse], summary="我的订单")
async def list_orders(
    pay_status: Optional[str] = Query(None, alias="pay_status"),
    delivery_status: Optional[str] = Query(None, alias="delivery_status"),
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[DrugOrderResponse]:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)

    ps = PayStatus(pay_status) if pay_status else None
    ds = DeliveryStatus(delivery_status) if delivery_status else None

    orders = await drug_crud.get_orders_by_patient(
        db, patient.id, pay_status=ps, delivery_status=ds
    )
    return [await _build_order_async(db, o) for o in orders]


@router.get("/orders/{order_id}", response_model=DrugOrderResponse, summary="订单详情")
async def get_order(
    order_id: int,
    current_user: User = Depends(require_role("patient", "admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> DrugOrderResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    order = await drug_crud.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
    # 患者只能看自己的订单
    if current_user.role.value == "patient":
        patient = await _get_patient(db, current_user.id)
        if order.patient_id != patient.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看此订单")
    return await _build_order_async(db, order)


@router.get(
    "/orders/{order_id}/status",
    response_model=DrugOrderStatusResponse,
    summary="物流状态",
)
async def get_order_status(
    order_id: int,
    current_user: User = Depends(require_role("patient", "admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> DrugOrderStatusResponse:
    """查询订单物流状态（含配送轨迹）。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    order = await drug_crud.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
    if current_user.role.value == "patient":
        patient = await _get_patient(db, current_user.id)
        if order.patient_id != patient.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看此订单")

    from app.services.logistics import get_cached_position, get_cached_temperatures

    current_pos = await get_cached_position(order_id)
    tracking = _build_tracking(order)
    cold_chain = await drug_crud.order_requires_cold_chain(db, order_id)
    temps = await get_cached_temperatures(order_id)

    # 预计送达时间：基于真实发货时间 + 1 小时（模拟配送约 60 秒，留出余量）
    estimated_arrival = None
    if order.delivery_status == DeliveryStatus.SHIPPED and order.shipped_at:
        eta = order.shipped_at + timedelta(hours=1)
        estimated_arrival = f"预计 {eta.strftime('%H:%M')} 前送达"

    return DrugOrderStatusResponse(
        order_id=order.id,
        order_no=order.order_no,
        status=order.pay_status.value,
        delivery_status=order.delivery_status.value,
        estimated_arrival=estimated_arrival,
        shipped_at=order.shipped_at.isoformat() if order.shipped_at else None,
        delivered_at=order.delivered_at.isoformat() if order.delivered_at else None,
        cold_chain=cold_chain,
        current_temperature=temps[-1] if temps else None,
        temperature_history=temps or [],
        tracking_points=tracking,
        current_position=current_pos,
    )


@router.post("/orders/{order_id}/pay", response_model=PaymentResponse, summary="支付并自动发货")
async def pay_order(
    order_id: int,
    payload: PaymentRequest,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> PaymentResponse:
    """支付成功后自动发货，异步生成配送路径并推送实时位置。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)
    order = await drug_crud.get_order_by_id(db, order_id)
    if not order or order.patient_id != patient.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单无法支付")

    from app.models import Payment, PaymentMethod, PaymentStatus

    if order.pay_status != PayStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单已支付或已退款")

    # 支付并自动发货（pay_order 内已将 delivery_status 设为 shipped）
    paid_order = await drug_crud.pay_order(db, order_id)
    if not paid_order:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单支付失败")

    payment = Payment(
        order_id=order_id,
        order_type="drug",
        amount=order.total_price,
        status=PaymentStatus.SUCCESS,
        payment_method=PaymentMethod(payload.payment_method),
        transaction_no=f"MOCK{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        paid_at=datetime.utcnow(),
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    # 异步生成配送路径（不阻塞支付响应），冷链订单自动附带温度模拟
    import asyncio as _asyncio
    from app.services.logistics import generate_route

    cold_chain = await drug_crud.order_requires_cold_chain(db, order_id)
    _asyncio.create_task(generate_route(order_id, need_cold_chain=cold_chain))

    return PaymentResponse(
        payment_id=payment.id,
        order_id=order_id,
        order_type="drug",
        amount=payment.amount,
        status=payment.status.value,
        paid_at=payment.paid_at.strftime("%Y-%m-%d %H:%M:%S") if payment.paid_at else None,
    )


# =============================================================================
# 辅助
# =============================================================================

async def _get_patient(db: AsyncSession, user_id: int) -> Patient:
    result = await db.execute(select(Patient).where(Patient.user_id == user_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="患者档案不存在")
    return patient


async def _resolve_order_prescription(
    db: AsyncSession,
    patient: Patient,
    current_user: User,
    items_map: dict[int, int],
    prescription_id: Optional[int],
) -> Optional[int]:
    """处方药强制校验：患者下单需关联医生确认处方，医生代下单自动建档。"""
    from app.models import Prescription, PrescriptionItem, PrescriptionStatus

    rx_drugs: list[Drug] = []
    for drug_id, qty in items_map.items():
        drug = await drug_crud.get_drug_by_id(db, drug_id)
        if not drug or not drug.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="药品不存在或已下架")
        if drug.stock < qty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"药品「{drug.name}」库存不足（剩余 {drug.stock}）",
            )
        if drug.need_prescription:
            rx_drugs.append(drug)

    if not rx_drugs:
        return prescription_id

    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if role == "doctor":
        if prescription_id:
            await _validate_prescription_coverage(db, patient.id, prescription_id, rx_drugs)
            return prescription_id

        doctor_result = await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))
        doctor = doctor_result.scalar_one_or_none()
        if not doctor:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前用户没有关联的医生档案")
        prescription = await drug_crud.create_prescription(
            db,
            patient_id=patient.id,
            doctor_id=doctor.id,
            items=[
                {
                    "drug_id": drug.id,
                    "dosage": "",
                    "quantity": items_map[drug.id],
                    "instructions": "按医嘱",
                }
                for drug in rx_drugs
            ],
        )
        return prescription.id

    if not prescription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="订单包含处方药，需关联医生确认的处方",
        )
    await _validate_prescription_coverage(db, patient.id, prescription_id, rx_drugs)
    return prescription_id


async def _validate_prescription_coverage(
    db: AsyncSession,
    patient_id: int,
    prescription_id: int,
    rx_drugs: list[Drug],
) -> None:
    """校验处方归属、确认状态及是否覆盖本次订单中的处方药。"""
    from app.models import Prescription, PrescriptionItem, PrescriptionStatus

    result = await db.execute(select(Prescription).where(Prescription.id == prescription_id))
    prescription = result.scalar_one_or_none()
    if not prescription or prescription.patient_id != patient_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="处方不存在或不属于当前患者")
    if prescription.status != PrescriptionStatus.CONFIRMED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="处方尚未确认，无法购买处方药")

    item_result = await db.execute(
        select(PrescriptionItem.drug_id).where(PrescriptionItem.prescription_id == prescription_id)
    )
    rx_ids = {row[0] for row in item_result.all()}
    missing = [drug.name for drug in rx_drugs if drug.id not in rx_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"处方未包含药品：{'、'.join(missing)}",
        )


async def _build_order_async(db: AsyncSession, order: DrugOrder) -> DrugOrderResponse:
    """异步：直接从DB查items，避免greenlet懒加载错误。"""
    from sqlalchemy import select as sa_select
    from app.models import DrugOrderItem

    rx_map = await _prescription_dosage_map(db, order.prescription_id)
    result = await db.execute(
        sa_select(DrugOrderItem).where(DrugOrderItem.drug_order_id == order.id)
    )
    order_items = result.scalars().all()

    items = []
    cold_chain = False
    for item in order_items:
        drug = await drug_crud.get_drug_by_id(db, item.drug_id)
        if drug and drug.need_cold_chain:
            cold_chain = True
        rx = rx_map.get(item.drug_id, {})
        items.append({
            "id": item.id,
            "drug_id": item.drug_id,
            "drug_name": drug.name if drug else "未知",
            "specification": drug.specification if drug else "",
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "subtotal": item.subtotal,
            "need_cold_chain": drug.need_cold_chain if drug else False,
            "dosage": rx.get("dosage", ""),
            "instructions": rx.get("instructions", ""),
        })
    return DrugOrderResponse(
        id=order.id,
        order_no=order.order_no,
        patient_id=order.patient_id,
        prescription_id=order.prescription_id,
        items=items,
        total_price=order.total_price,
        pay_status=order.pay_status.value,
        delivery_status=order.delivery_status.value,
        address=order.address,
        created_at=order.created_at,
        cold_chain=cold_chain,
    )


async def _prescription_dosage_map(db: AsyncSession, prescription_id: Optional[int]) -> dict:
    """按处方查询每种药品的用法用量与注意事项，返回 {drug_id: {dosage, instructions}}。"""
    if not prescription_id:
        return {}
    from sqlalchemy import select as sa_select
    from app.models import PrescriptionItem

    result = await db.execute(
        sa_select(PrescriptionItem).where(PrescriptionItem.prescription_id == prescription_id)
    )
    rows = result.scalars().all()
    return {
        r.drug_id: {"dosage": r.dosage or "", "instructions": r.instructions or ""}
        for r in rows
    }


def _build_drug_order_response(order: DrugOrder) -> DrugOrderResponse:
    items = []
    for item in order.items:
        drug = item.drug
        items.append({
            "id": item.id,
            "drug_id": item.drug_id,
            "drug_name": drug.name if drug else "未知",
            "specification": drug.specification if drug else "",
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "subtotal": item.subtotal,
        })
    return DrugOrderResponse(
        id=order.id,
        order_no=order.order_no,
        patient_id=order.patient_id,
        prescription_id=order.prescription_id,
        items=items,
        total_price=order.total_price,
        pay_status=order.pay_status.value,
        delivery_status=order.delivery_status.value,
        address=order.address,
        created_at=order.created_at,
    )


def _build_tracking(order: DrugOrder) -> list[dict]:
    """根据订单真实时间构建物流时间线（创建/发货/签收均来自数据库）。"""
    delivery_status = order.delivery_status
    fmt = lambda dt: dt.strftime("%m-%d %H:%M") if dt else None  # noqa: E731

    tracking = [
        {"time": fmt(order.created_at) or "订单已创建", "location": "订单已创建", "status": "completed"},
    ]

    if delivery_status in (DeliveryStatus.SHIPPED, DeliveryStatus.DELIVERED):
        tracking.append({"time": fmt(order.shipped_at) or "已发货", "location": "已出库，配送中", "status": "completed"})
        tracking.append({"time": "配送中", "location": "配送员正在派送", "status": "active"})

    if delivery_status == DeliveryStatus.DELIVERED:
        tracking[-1]["status"] = "completed"
        tracking.append({"time": fmt(order.delivered_at) or "已送达", "location": "已送达", "status": "completed"})

    return tracking
