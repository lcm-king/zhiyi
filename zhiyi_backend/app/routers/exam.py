"""
智医 (ZhiYi) — 检查预约路由
基层医疗AI辅助诊疗平台

GET    /api/exams/items              — 检查项目列表（支持按科室筛选）
GET    /api/exams/items/{id}         — 检查项目详情
GET    /api/exams/cart               — 查看购物车
POST   /api/exams/cart               — 加入购物车
PUT    /api/exams/cart/{item_id}     — 更新购物车数量
DELETE /api/exams/cart/{item_id}     — 移出购物车
DELETE /api/exams/cart               — 清空购物车
POST   /api/exams/orders             — 提交预约订单
GET    /api/exams/orders             — 我的预约列表
GET    /api/exams/orders/{id}        — 预约详情
POST   /api/exams/orders/{id}/pay    — 模拟支付
POST   /api/exams/orders/{id}/cancel — 取消预约
GET    /api/exams/orders/{id}/report — 查看检查报告
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.crud import exam_crud
from app.database import get_db, safe_db_call
from app.models import AppointmentStatus, ExamItem, Patient, User, UserRole
from app.schemas import (
    ExamCartItem,
    ExamItemResponse,
    ExamOrderRequest,
    ExamOrderResponse,
    ExamReportInterpretResponse,
    ExamReportUpdate,
    MessageResponse,
)
from app.services.report_generator import generate_interpretation

router = APIRouter()


# =============================================================================
# 检查项目浏览
# =============================================================================

@router.get(
    "/items",
    response_model=list[ExamItemResponse],
    summary="检查项目列表",
)
async def list_exam_items(
    category: Optional[str] = Query(None, description="按科室筛选：影像科/超声科/检验科/心电图室"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[ExamItem]:
    """获取可预约的检查项目列表，支持按科室分类筛选。"""
    if db is None:
        return []
    return await safe_db_call(
        lambda: exam_crud.get_exam_items(db, category=category, skip=skip, limit=limit),
        mock_data=[],
        log_msg="检查项目列表查询失败",
    )


@router.get(
    "/items/{item_id}",
    response_model=ExamItemResponse,
    summary="检查项目详情",
)
async def get_exam_item(
    item_id: int,
    db: Optional[AsyncSession] = Depends(get_db),
) -> ExamItem:
    """获取单个检查项目的详细信息。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    item = await exam_crud.get_exam_item_by_id(db, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="检查项目不存在")
    return item


# =============================================================================
# 购物车（Redis Hash）
# =============================================================================

@router.get(
    "/cart",
    response_model=dict,
    summary="查看购物车",
)
async def get_cart(
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> dict:
    """获取当前患者检查购物车内容。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)
    cart = await exam_crud.get_cart(patient.id)

    # 补充检查项目详情
    items_detail = []
    for item_id, qty in cart.items():
        item = await exam_crud.get_exam_item_by_id(db, item_id)
        if item:
            items_detail.append({
                "exam_item_id": item.id,
                "name": item.name,
                "category": item.category,
                "price": item.price,
                "quantity": qty,
                "subtotal": item.price * qty,
            })

    total = sum(item["subtotal"] for item in items_detail)
    return {
        "patient_id": patient.id,
        "items": items_detail,
        "total_count": len(items_detail),
        "total_price": round(total, 2),
    }


@router.post(
    "/cart",
    response_model=MessageResponse,
    summary="加入购物车",
)
async def add_to_cart(
    payload: ExamCartItem,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """向购物车添加检查项目，已存在则叠加数量。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)

    # 验证检查项目存在
    item = await exam_crud.get_exam_item_by_id(db, payload.exam_item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="检查项目不存在")
    if not item.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该项目暂不可预约")

    await exam_crud.add_to_cart(patient.id, payload.exam_item_id, payload.quantity)
    return MessageResponse(message=f"已将「{item.name}」加入预约清单", data={"item_id": item.id})


@router.put(
    "/cart/{item_id}",
    response_model=MessageResponse,
    summary="更新购物车数量",
)
async def update_cart_item(
    item_id: int,
    quantity: int = Query(..., ge=1, le=99, description="新数量"),
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """更新购物车中某个检查项目的数量。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)
    await exam_crud.update_cart_item(patient.id, item_id, quantity)
    return MessageResponse(message="购物车已更新")


@router.delete(
    "/cart/{item_id}",
    response_model=MessageResponse,
    summary="移出购物车",
)
async def remove_from_cart(
    item_id: int,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """从购物车中移除某个检查项目。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)
    await exam_crud.remove_from_cart(patient.id, item_id)
    return MessageResponse(message="已从预约清单移除")


@router.delete(
    "/cart",
    response_model=MessageResponse,
    summary="清空购物车",
)
async def clear_cart(
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """清空购物车中所有项目。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)
    await exam_crud.clear_cart(patient.id)
    return MessageResponse(message="预约清单已清空")


# =============================================================================
# 预约订单
# =============================================================================

@router.post(
    "/orders",
    response_model=ExamOrderResponse,
    summary="提交预约订单",
)
async def create_exam_order(
    payload: ExamOrderRequest,
    current_user: User = Depends(require_role("patient", "doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> ExamOrderResponse:
    """提交检查预约订单，从购物车中读取项目生成预约记录。

    完成后自动清空购物车。
    """
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    # 患者本人下单使用自己的档案；医生代开单使用 payload.patient_id
    if current_user.role.value == "patient":
        patient = await _get_patient(db, current_user.id)
    else:
        if not payload.patient_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="医生代下单需提供 patient_id")
        result = await db.execute(select(Patient).where(Patient.id == payload.patient_id))
        patient = result.scalar_one_or_none()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="患者档案不存在")

    # 汇总要预约的项目
    items_map: dict[int, int] = {}
    for cart_item in payload.items:
        item = await exam_crud.get_exam_item_by_id(db, cart_item.exam_item_id)
        if not item or not item.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"检查项目 {cart_item.exam_item_id} 不可用",
            )
        items_map[cart_item.exam_item_id] = (
            items_map.get(cart_item.exam_item_id, 0) + cart_item.quantity
        )

    if not items_map:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="预约清单为空")

    # 创建预约记录
    appointments = await exam_crud.create_appointment(
        db=db,
        patient_id=patient.id,
        items=items_map,
        hospital_id=payload.hospital_id,
        appointment_time=payload.appointment_time,
    )

    # 计算总价
    total_price = 0.0
    for a in appointments:
        item = await exam_crud.get_exam_item_by_id(db, a.exam_item_id)
        total_price += item.price if item else 0

    # 清空购物车（仅患者本人下单）
    if current_user.role.value == "patient":
        await exam_crud.clear_cart(patient.id)

    # 组装订单中的项目列表
    exam_item_list: list[ExamItem] = []
    for a in appointments:
        item = await exam_crud.get_exam_item_by_id(db, a.exam_item_id)
        if item:
            exam_item_list.append(item)

    return ExamOrderResponse(
        order_id=appointments[0].order_id,
        order_no=f"EX{appointments[0].order_id}",
        patient_id=patient.id,
        items=[ExamItemResponse.model_validate(item) for item in exam_item_list],
        total_price=round(total_price, 2),
        status="pending",
        appointment_time=payload.appointment_time,
        created_at=appointments[0].created_at,
    )


@router.get(
    "/orders",
    response_model=list[dict],
    summary="我的预约列表",
)
async def list_orders(
    status_filter: Optional[str] = Query(None, alias="status", description="按状态筛选"),
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[dict]:
    """查询当前患者的预约记录列表。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    patient = await _get_patient(db, current_user.id)

    status_enum = None
    if status_filter:
        try:
            status_enum = AppointmentStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"无效的状态值: {status_filter}")

    appointments = await exam_crud.get_appointments_by_patient(
        db, patient.id, status=status_enum
    )

    # 按 order_id 分组
    orders: dict[int, dict] = {}
    for a in appointments:
        item = await exam_crud.get_exam_item_by_id(db, a.exam_item_id)
        oid = a.order_id
        if oid not in orders:
            orders[oid] = {
                "order_id": oid,
                "order_no": f"EX{oid}",
                "status": a.status.value,
                "items": [],
                "total_price": 0,
                "appointment_time": a.appointment_time.isoformat(),
                "created_at": a.created_at.isoformat(),
            }
        if item:
            orders[oid]["items"].append({
                "exam_item_id": item.id,
                "name": item.name,
                "category": item.category,
                "price": item.price,
            })
            orders[oid]["total_price"] += item.price

    return list(orders.values())


@router.get(
    "/orders/{order_id}",
    response_model=dict,
    summary="预约详情",
)
async def get_order_detail(
    order_id: int,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> dict:
    """查看某个订单的详细信息。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    appointments = await exam_crud.get_appointments_by_order_id(db, order_id)
    if not appointments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    items = []
    total = 0.0
    for a in appointments:
        item = await exam_crud.get_exam_item_by_id(db, a.exam_item_id)
        if item:
            items.append({
                "appointment_id": a.id,
                "exam_item_id": item.id,
                "name": item.name,
                "category": item.category,
                "price": item.price,
                "status": a.status.value,
                "report_url": a.report_url,
            })
            total += item.price

    return {
        "order_id": order_id,
        "order_no": f"EX{order_id}",
        "patient_id": appointments[0].patient_id,
        "items": items,
        "total_price": round(total, 2),
        "overall_status": appointments[0].status.value,
        "appointment_time": appointments[0].appointment_time.isoformat(),
        "created_at": appointments[0].created_at.isoformat(),
    }


@router.post(
    "/orders/{order_id}/pay",
    response_model=MessageResponse,
    summary="模拟支付",
)
async def pay_order(
    order_id: int,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """模拟在线支付：将订单所有项目从 pending 更新为 paid。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    appointments = await exam_crud.get_appointments_by_order_id(db, order_id)
    if not appointments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    paid_count = 0
    for a in appointments:
        result = await exam_crud.pay_appointment(db, a.id)
        if result:
            paid_count += 1

    # 支付成功 → 后台延时自动生成报告（演示链路：报告生成中 → 报告已出）
    if paid_count:
        await exam_crud.schedule_auto_report(order_id)

    return MessageResponse(
        message=f"支付成功，{paid_count} 项检查已确认",
        data={"order_id": order_id, "paid_items": paid_count},
    )


@router.post(
    "/orders/{order_id}/cancel",
    response_model=MessageResponse,
    summary="取消预约",
)
async def cancel_order(
    order_id: int,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """取消整个订单的所有预约项目。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    appointments = await exam_crud.get_appointments_by_order_id(db, order_id)
    if not appointments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    for a in appointments:
        await exam_crud.cancel_appointment(db, a.id)

    return MessageResponse(message="预约已取消", data={"order_id": order_id})


@router.get(
    "/appointments",
    response_model=list[dict],
    summary="检查预约列表（医生/管理员）",
)
async def list_appointments(
    status_filter: Optional[str] = Query(None, alias="status", description="按状态筛选"),
    current_user: User = Depends(require_role("doctor", "admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[dict]:
    """医生/管理员查看全部检查预约，用于录入或查看检查报告。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    status_enum = None
    if status_filter:
        try:
            status_enum = AppointmentStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"无效的状态值: {status_filter}")

    appointments = await exam_crud.get_all_appointments(db, status=status_enum)
    result = []
    for a in appointments:
        item = await exam_crud.get_exam_item_by_id(db, a.exam_item_id)
        result.append({
            "appointment_id": a.id,
            "order_id": a.order_id,
            "patient_id": a.patient_id,
            "patient_name": a.patient.name if a.patient else "",
            "exam_item_id": a.exam_item_id,
            "exam_name": item.name if item else "未知项目",
            "category": item.category if item else "",
            "status": a.status.value,
            "appointment_time": a.appointment_time.isoformat() if a.appointment_time else None,
            "has_report": a.report_url is not None or a.report_data is not None,
            "report_data": a.report_data,
            "ai_interpretation": a.ai_interpretation,
        })
    return result


@router.get(
    "/orders/{order_id}/report",
    response_model=dict,
    summary="查看检查报告",
)
async def view_report(
    order_id: int,
    current_user: User = Depends(require_role("patient")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> dict:
    """查看订单关联的检查报告。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    appointments = await exam_crud.get_appointments_by_order_id(db, order_id)
    if not appointments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    reports = []
    for a in appointments:
        item = await exam_crud.get_exam_item_by_id(db, a.exam_item_id)

        # 兜底：已支付/已完成但尚无报告时，按患者病历自动生成（防止后台任务因重启丢失）
        if a.report_data is None and a.status in (
            AppointmentStatus.PAID,
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.COMPLETED,
        ):
            await exam_crud.auto_generate_report(db, a)
            await db.commit()
            await db.refresh(a)

        interpretation = a.ai_interpretation
        if not interpretation and a.report_data:
            interpretation = generate_interpretation(item.name if item else "检查", a.report_data)
            a.ai_interpretation = interpretation
            await db.commit()
        reports.append({
            "appointment_id": a.id,
            "exam_name": item.name if item else "未知项目",
            "status": a.status.value,
            "report_url": a.report_url,
            "report_data": a.report_data,
            "has_report": a.report_url is not None or a.report_data is not None,
            "ai_interpretation": interpretation,
        })

    return {
        "order_id": order_id,
        "order_no": f"EX{order_id}",
        "reports": reports,
        "completed_count": sum(1 for r in reports if r["has_report"]),
    }


@router.put(
    "/appointments/{appointment_id}/report",
    response_model=MessageResponse,
    summary="上传/更新检查报告",
)
async def update_report(
    appointment_id: int,
    payload: ExamReportUpdate,
    current_user: User = Depends(require_role("admin", "doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """医生或管理员上传结构化检查报告。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    appointment = await exam_crud.get_appointment_by_id(db, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预约记录不存在")

    appointment.report_data = payload.report_data.model_dump()
    if payload.report_url:
        appointment.report_url = payload.report_url
    if payload.status:
        from app.models import AppointmentStatus
        appointment.status = AppointmentStatus(payload.status)

    # 自动生成 AI 解读
    item = await exam_crud.get_exam_item_by_id(db, appointment.exam_item_id)
    appointment.ai_interpretation = generate_interpretation(
        item.name if item else "检查", appointment.report_data
    )

    await db.commit()
    await db.refresh(appointment)
    return MessageResponse(message="检查报告已更新并生成 AI 解读")


@router.get(
    "/appointments/{appointment_id}/interpret",
    response_model=ExamReportInterpretResponse,
    summary="AI 解读检查报告",
)
async def interpret_report(
    appointment_id: int,
    current_user: User = Depends(require_role("patient", "doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> ExamReportInterpretResponse:
    """对已完成检查的报告进行 AI 解读。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    appointment = await exam_crud.get_appointment_by_id(db, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预约记录不存在")

    item = await exam_crud.get_exam_item_by_id(db, appointment.exam_item_id)
    report_data = appointment.report_data or {"summary": "", "metrics": []}

    interpretation = generate_interpretation(item.name if item else "检查", report_data)
    appointment.ai_interpretation = interpretation
    await db.commit()

    abnormal = [m for m in report_data.get("metrics", []) if m.get("status") != "normal"]
    suggestions = []
    if abnormal:
        suggestions.append("建议携带报告复诊，由医生综合评估。")
        suggestions.append("关注异常指标变化趋势，必要时复查。")

    return ExamReportInterpretResponse(
        appointment_id=appointment.id,
        exam_name=item.name if item else "未知项目",
        interpretation=interpretation,
        abnormal_items=abnormal,
        suggestions=suggestions,
    )


# =============================================================================
# 内部辅助
# =============================================================================

async def _get_patient(db: AsyncSession, user_id: int) -> Patient:
    """根据 user_id 获取 patient 记录，不存在则 404。"""
    result = await db.execute(select(Patient).where(Patient.user_id == user_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="患者档案不存在，请先完善个人信息",
        )
    return patient
