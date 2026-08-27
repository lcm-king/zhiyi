"""
智医 (ZhiYi) — 管理后台路由
基层医疗AI辅助诊疗平台

管理员功能：
  - 医生管理（创建/列表/禁用/删除）
  - 药品管理（CRUD）
  - 检查项目管理（CRUD）
  - 订单管理（查看全部 + 发货）
  - 数据看板（ECharts 统计数据）
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.crud import drug_crud, exam_crud, user_crud
from app.database import get_db, safe_db_call
from app.models import AlertResolution, AuditLog, DeliveryStatus, Drug, DrugOrder, ExamAppointment, PayStatus, User
from app.schemas import (
    AdminDrugCreate,
    AdminDrugUpdate,
    AdminExamItemCreate,
    AdminExamItemUpdate,
    AdminUserCreate,
    AdminUserResponse,
    DashboardResponse,
    DrugItemResponse,
    ExamItemResponse,
    MessageResponse,
)
from app.services.audit import log_audit

router = APIRouter()


# =============================================================================
# 医生管理
# =============================================================================

@router.get(
    "/doctors",
    response_model=list[dict],
    summary="医生列表",
)
async def list_doctors(
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[dict]:
    """获取所有医生账号列表。数据库为空时返回模拟数据。"""
    if db is None:
        return []
    return await safe_db_call(
        lambda: user_crud.get_all_doctors(db),
        mock_data=[],
        log_msg="医生列表查询失败",
    )


@router.post(
    "/doctors",
    response_model=MessageResponse,
    summary="创建医生账号",
)
async def create_doctor(
    payload: AdminUserCreate,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """创建医生账号及其关联的医生档案。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    if payload.role != "doctor":
        raise HTTPException(status_code=400, detail="请使用 doctor 角色")

    try:
        user = await user_crud.create_user_with_profile(
            db,
            username=payload.username,
            phone=payload.phone,
            password=payload.password,
            role="doctor",
            name=payload.name,
            department=payload.department,
            hospital_id=payload.hospital_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    await log_audit(
        db,
        user_id=current_user.id,
        action="doctor_create",
        resource="user",
        resource_id=user.id,
        detail={"name": payload.name, "department": payload.department},
    )
    return MessageResponse(message="医生账号创建成功", data={"user_id": user.id})


@router.put(
    "/doctors/{user_id}/toggle",
    response_model=MessageResponse,
    summary="启用/禁用医生",
)
async def toggle_doctor(
    user_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """切换医生账号的启用/禁用状态。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    user = await user_crud.toggle_user_active(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    await log_audit(
        db,
        user_id=current_user.id,
        action="doctor_toggle",
        resource="user",
        resource_id=user.id,
        detail={"active": user.is_active},
    )
    return MessageResponse(
        message=f"账号已{'启用' if user.is_active else '禁用'}"
    )


@router.delete(
    "/doctors/{user_id}",
    response_model=MessageResponse,
    summary="删除医生",
)
async def delete_doctor(
    user_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """软删除医生账号。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    ok = await user_crud.delete_user(db, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    await log_audit(
        db,
        user_id=current_user.id,
        action="doctor_delete",
        resource="user",
        resource_id=user_id,
    )
    return MessageResponse(message="账号已禁用")


# =============================================================================
# 药品管理
# =============================================================================

@router.get(
    "/drugs",
    response_model=list[DrugItemResponse],
    summary="药品列表（管理端）",
)
async def admin_list_drugs(
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list:
    if db is None:
        return []
    return await safe_db_call(
        lambda: drug_crud.get_drugs(db),
        mock_data=[],
        log_msg="药品列表查询失败",
    )


@router.post(
    "/drugs",
    response_model=MessageResponse,
    summary="新增药品",
)
async def admin_create_drug(
    payload: AdminDrugCreate,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    drug = await drug_crud.create_drug(db, **payload.model_dump())
    await log_audit(
        db,
        user_id=current_user.id,
        action="drug_create",
        resource="drug",
        resource_id=drug.id,
        detail={"name": drug.name, "price": drug.price},
    )
    return MessageResponse(message="药品添加成功", data={"drug_id": drug.id})


@router.put(
    "/drugs/{drug_id}",
    response_model=MessageResponse,
    summary="更新药品",
)
async def admin_update_drug(
    drug_id: int,
    payload: AdminDrugUpdate,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    drug = await drug_crud.update_drug(db, drug_id, **payload.model_dump(exclude_none=True))
    if not drug:
        raise HTTPException(status_code=404, detail="药品不存在")
    await log_audit(
        db,
        user_id=current_user.id,
        action="drug_update",
        resource="drug",
        resource_id=drug.id,
        detail={"name": drug.name},
    )
    return MessageResponse(message="药品已更新")


@router.delete(
    "/drugs/{drug_id}",
    response_model=MessageResponse,
    summary="下架药品",
)
async def admin_delete_drug(
    drug_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    drug = await drug_crud.update_drug(db, drug_id, is_active=False)
    if not drug:
        raise HTTPException(status_code=404, detail="药品不存在")
    await log_audit(
        db,
        user_id=current_user.id,
        action="drug_delete",
        resource="drug",
        resource_id=drug.id,
        detail={"name": drug.name},
    )
    return MessageResponse(message="药品已下架")


# =============================================================================
# 检查项目管理
# =============================================================================

@router.get(
    "/exam-items",
    response_model=list[ExamItemResponse],
    summary="检查项目列表（管理端）",
)
async def admin_list_exam_items(
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list:
    if db is None:
        return []
    return await safe_db_call(
        lambda: exam_crud.get_exam_items(db, is_active=None),
        mock_data=[],
        log_msg="检查项目列表查询失败",
    )


@router.post(
    "/exam-items",
    response_model=MessageResponse,
    summary="新增检查项目",
)
async def admin_create_exam_item(
    payload: AdminExamItemCreate,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    item = await exam_crud.create_exam_item(db, **payload.model_dump())
    await log_audit(
        db,
        user_id=current_user.id,
        action="exam_item_create",
        resource="exam_item",
        resource_id=item.id,
        detail={"name": item.name, "price": item.price},
    )
    return MessageResponse(message="检查项目添加成功", data={"item_id": item.id})


@router.put(
    "/exam-items/{item_id}",
    response_model=MessageResponse,
    summary="更新检查项目",
)
async def admin_update_exam_item(
    item_id: int,
    payload: AdminExamItemUpdate,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    item = await exam_crud.update_exam_item(
        db, item_id, **payload.model_dump(exclude_none=True)
    )
    if not item:
        raise HTTPException(status_code=404, detail="检查项目不存在")
    await log_audit(
        db,
        user_id=current_user.id,
        action="exam_item_update",
        resource="exam_item",
        resource_id=item.id,
        detail={"name": item.name},
    )
    return MessageResponse(message="检查项目已更新")


@router.delete(
    "/exam-items/{item_id}",
    response_model=MessageResponse,
    summary="下架检查项目",
)
async def admin_delete_exam_item(
    item_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    item = await exam_crud.update_exam_item(db, item_id, is_active=False)
    if not item:
        raise HTTPException(status_code=404, detail="检查项目不存在")
    await log_audit(
        db,
        user_id=current_user.id,
        action="exam_item_delete",
        resource="exam_item",
        resource_id=item.id,
        detail={"name": item.name},
    )
    return MessageResponse(message="检查项目已下架")


# =============================================================================
# 订单管理（发货）
# =============================================================================

@router.get(
    "/orders",
    response_model=list[dict],
    summary="所有订单（管理端）",
)
async def admin_list_orders(
    delivery_status: Optional[str] = Query(None),
    current_user: User = Depends(require_role("admin", "doctor")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[dict]:
    """查看所有药品订单（管理员/医生均可），支持按配送状态筛选。"""
    if db is None:
        orders = []
    else:
        ds = DeliveryStatus(delivery_status) if delivery_status else None
        orders = await safe_db_call(
            lambda: drug_crud.get_all_orders_for_delivery(db, delivery_status=ds),
            mock_data=[],
            log_msg="订单列表查询失败",
    )

    result = []
    for o in orders:
        items_summary = ", ".join(
            f"{item.drug.name if item.drug else '未知'}×{item.quantity}"
            for item in o.items
        )
        items = [
            {
                "drug_name": item.drug.name if item.drug else "未知",
                "quantity": item.quantity,
                "need_cold_chain": item.drug.need_cold_chain if item.drug else False,
            }
            for item in o.items
        ]
        cold_chain = any(it["need_cold_chain"] for it in items)
        item_count = len(o.items)
        drug_names = [it["drug_name"] for it in items]
        total_qty = sum(it["quantity"] for it in items)

        # 处方审核：优先使用 RabbitMQ 异步审核结果（消费者回调写入 DB）
        review = None
        if getattr(o, "review_result", None):
            try:
                review = json.loads(o.review_result)
            except (TypeError, ValueError):
                review = None

        if review:
            warnings = review.get("warnings", [])
            risk = review.get("risk", "low")
            ai_review_passed = review.get("passed", len(warnings) == 0)
            suggestion = review.get(
                "suggestion",
                "处方合理，可按常规剂量使用。注意监测不良反应。"
                if ai_review_passed
                else f"处方存在 {len(warnings)} 项风险提示，建议医生复核确认后执行。",
            )
            review_status = (
                getattr(o, "review_status", None) or ("reviewed" if ai_review_passed else "warning")
            )
        else:
            # 兜底：同步规则审核（异步链路不可用或尚未回调时）
            warnings: list[str] = []
            if total_qty >= 5:
                warnings.append("多药联用，需评估药物相互作用风险")
            if item_count >= 3:
                warnings.append(f"同时开具 {item_count} 种药品，建议分批处理主要病症后观察")
            if any("抗生素" in n or "阿莫西林" in n or "头孢" in n for n in drug_names):
                warnings.append("含抗生素类药物，需确认患者无过敏史及感染指征")
            if any("降压" in n or "缓释片" in n for n in drug_names):
                warnings.append("降压药需监测血压，起始剂量宜低，逐步调整")

            ai_review_passed = len(warnings) == 0
            risk = "low"
            if len(warnings) >= 2:
                risk = "high"
            elif len(warnings) == 1:
                risk = "medium"

            suggestion = (
                "处方合理，可按常规剂量使用。注意监测不良反应。"
                if ai_review_passed
                else f"处方存在 {len(warnings)} 项风险提示，建议医生复核确认后执行。"
            )
            review_status = "pending" if o.pay_status.value == "pending" else (
                "reviewed" if ai_review_passed else "warning"
            )

        result.append({
            "id": o.id,
            "order_no": o.order_no,
            "patient_id": o.patient_id,
            "patient_name": o.patient.name if o.patient else f"患者{o.patient_id}",
            "items_summary": items_summary,
            "items": items,
            "cold_chain": cold_chain,
            "total_price": o.total_price,
            "pay_status": o.pay_status.value,
            "delivery_status": o.delivery_status.value,
            "address": o.address,
            "created_at": o.created_at.isoformat(),
            # 处方审核字段
            "review_status": review_status,
            "risk": risk,
            "ai_review": {
                "passed": ai_review_passed,
                "warnings": warnings,
                "suggestion": suggestion,
            },
        })
    return result


@router.post(
    "/orders/{order_id}/ship",
    response_model=MessageResponse,
    summary="管理员发货",
)
async def admin_ship_order(
    order_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """管理员点击发货：更新配送状态 + 生成物流路径。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    order = await drug_crud.ship_order(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="订单无法发货（需已支付且未配送）",
        )

    # 异步生成路径（冷链订单自动附带温度模拟）
    import asyncio
    from app.services.logistics import generate_route

    cold_chain = await drug_crud.order_requires_cold_chain(db, order_id)
    asyncio.create_task(generate_route(order_id, need_cold_chain=cold_chain))

    await log_audit(
        db,
        user_id=current_user.id,
        action="order_ship",
        resource="drug_order",
        resource_id=order_id,
    )
    return MessageResponse(
        message="发货成功，配送路径已生成",
        data={"order_id": order_id, "delivery_status": "shipped"},
    )


# =============================================================================
# 数据看板
# =============================================================================

@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="数据看板",
)
async def get_dashboard(
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> DashboardResponse:
    """运营数据看板：全部指标基于数据库实时聚合，无假数据。"""
    from sqlalchemy import func, select
    from app.models import Diagnosis, Drug, DrugOrder, ExamAppointment, Payment

    if db is None:
        return DashboardResponse()

    today = datetime.utcnow().date()
    month_start = today.replace(day=1)

    # 今日接诊 / 本月服务（诊断 + 检查预约 + 药品订单）
    today_consultations = (await db.execute(
        select(func.count(Diagnosis.id)).filter(func.date(Diagnosis.created_at) == today)
    )).scalar() or 0

    monthly = 0
    monthly += (await db.execute(
        select(func.count(Diagnosis.id)).filter(Diagnosis.created_at >= month_start)
    )).scalar() or 0
    monthly += (await db.execute(
        select(func.count(ExamAppointment.id)).filter(ExamAppointment.created_at >= month_start)
    )).scalar() or 0
    monthly += (await db.execute(
        select(func.count(DrugOrder.id)).filter(DrugOrder.created_at >= month_start)
    )).scalar() or 0

    # 今日药品订单 / 今日检查预约
    drug_orders = (await db.execute(
        select(func.count(DrugOrder.id)).filter(func.date(DrugOrder.created_at) == today)
    )).scalar() or 0
    exam_orders = (await db.execute(
        select(func.count(ExamAppointment.id)).filter(func.date(ExamAppointment.created_at) == today)
    )).scalar() or 0

    # 最近 7 天诊断趋势（真实日期 + 真实数量）
    trend_data: list[int] = []
    trend_labels: list[str] = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = (await db.execute(
            select(func.count(Diagnosis.id)).filter(func.date(Diagnosis.created_at) == day)
        )).scalar() or 0
        trend_data.append(count)
        trend_labels.append(day.strftime("%m-%d"))

    # AI 使用率：use_ai=true 的诊断占比（真实记录）
    total_diag = (await db.execute(select(func.count(Diagnosis.id)))).scalar() or 0
    ai_diag = (await db.execute(
        select(func.count(Diagnosis.id)).filter(Diagnosis.use_ai.is_(True))
    )).scalar() or 0
    ai_usage_rate = round(ai_diag / total_diag * 100, 1) if total_diag else 0.0

    # 待处理告警 = 低库存药品 + 待发货已支付订单（与 /alerts 口径一致，扣除已处理）
    resolved_keys = await _resolved_alert_keys(db)
    low_stock_rows = (await db.execute(
        select(Drug).where(Drug.stock < 50, Drug.is_active == True)
    )).scalars().all()
    low_stock = len([
        drug for drug in low_stock_rows
        if (f"stock_{drug.id}", f"stock:{drug.stock}") not in resolved_keys
    ])
    pending_ship = (await db.execute(
        select(func.count(DrugOrder.id)).where(
            DrugOrder.pay_status == PayStatus.PAID,
            DrugOrder.delivery_status == DeliveryStatus.PENDING,
        )
    )).scalar() or 0
    pending_ship_alerts = (
        1
        if pending_ship > 0 and ("pending_ship", f"pending_ship:{pending_ship}") not in resolved_keys
        else 0
    )
    pending_alerts = low_stock + pending_ship_alerts

    # 服务分布（全量真实计数）
    total_exams = (await db.execute(select(func.count(ExamAppointment.id)))).scalar() or 0
    total_orders = (await db.execute(select(func.count(DrugOrder.id)))).scalar() or 0
    total_payments = (await db.execute(select(func.count(Payment.id)))).scalar() or 0
    service_distribution = [
        {"name": "人工智能诊断", "value": total_diag, "color": "#3B82F6"},
        {"name": "检查预约", "value": total_exams, "color": "#0D9488"},
        {"name": "药品订单", "value": total_orders, "color": "#F59E0B"},
        {"name": "支付流水", "value": total_payments, "color": "#8B5CF6"},
    ]

    return DashboardResponse(
        today_consultations=today_consultations,
        ai_usage_rate=ai_usage_rate,
        drug_order_count=drug_orders,
        pending_alerts=pending_alerts,
        monthly_services=monthly,
        trend_data=trend_data,
        trend_labels=trend_labels,
        service_distribution=service_distribution,
    )


# =============================================================================
# 告警管理
# =============================================================================

async def _resolved_alert_keys(db: AsyncSession) -> set[tuple[str, str]]:
    """读取近 7 天内的告警处理记录，返回 {(alert_id, fingerprint)}。"""
    from sqlalchemy import select

    result = await db.execute(
        select(AlertResolution.alert_id, AlertResolution.fingerprint).where(
            AlertResolution.resolved_at >= datetime.utcnow() - timedelta(days=7)
        )
    )
    return {(row[0], row[1]) for row in result.all()}


async def _alert_fingerprint(db: AsyncSession, alert_id: str) -> str:
    """根据当前条件计算告警指纹，条件变化后视为新告警。"""
    from sqlalchemy import func, select

    if alert_id.startswith("stock_"):
        try:
            drug_id = int(alert_id.split("_", 1)[1])
        except ValueError:
            return "resolved"
        drug = (await db.execute(select(Drug).where(Drug.id == drug_id))).scalar_one_or_none()
        return f"stock:{drug.stock if drug else -1}"
    if alert_id == "pending_ship":
        count = (await db.execute(
            select(func.count(DrugOrder.id)).where(
                DrugOrder.pay_status == PayStatus.PAID,
                DrugOrder.delivery_status == DeliveryStatus.PENDING,
            )
        )).scalar() or 0
        return f"pending_ship:{count}"
    return "resolved"


@router.get(
    "/alerts",
    response_model=list[dict],
    summary="告警列表",
)
async def get_alerts(
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[dict]:
    """获取系统告警列表（库存预警、待发货订单等真实数据）。"""
    if db is None:
        return []

    from sqlalchemy import select, func
    from app.models import Drug

    alerts: list[dict] = []

    # 1. 库存预警
    low_stock_result = await db.execute(
        select(Drug).where(Drug.stock < 50, Drug.is_active == True)
    )
    for drug in low_stock_result.scalars():
        level = "high" if drug.stock < 20 else "medium"
        alerts.append({
            "id": f"stock_{drug.id}",
            "content": f"{drug.name} 库存仅剩 {drug.stock}（低于安全线 50）",
            "level": level,
            "time": "刚刚",
            "action": "确认处理",
        })

    # 2. 待发货订单
    pending_count_result = await db.execute(
        select(func.count(DrugOrder.id)).where(
            DrugOrder.pay_status == PayStatus.PAID,
            DrugOrder.delivery_status == DeliveryStatus.PENDING,
        )
    )
    pending_count = pending_count_result.scalar() or 0
    if pending_count > 0:
        alerts.append({
            "id": "pending_ship",
            "content": f"有 {pending_count} 笔已支付订单待发货",
            "level": "medium",
            "time": "5 分钟前",
            "action": "查看详情",
        })

    # 过滤掉近 7 天内已处理、且条件指纹未变化的告警
    resolved_keys = await _resolved_alert_keys(db)
    alerts = [
        alert
        for alert in alerts
        if (alert["id"], await _alert_fingerprint(db, alert["id"])) not in resolved_keys
    ]
    return alerts


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=MessageResponse,
    summary="标记告警已处理",
)
async def resolve_alert(
    alert_id: str,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """标记告警为已处理并落库，条件指纹未变化时不再重复出现。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    from sqlalchemy import select

    fingerprint = await _alert_fingerprint(db, alert_id)
    existing = await db.execute(
        select(AlertResolution).where(
            AlertResolution.alert_id == alert_id,
            AlertResolution.fingerprint == fingerprint,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        row.resolved_at = datetime.utcnow()
    else:
        db.add(AlertResolution(alert_id=alert_id, fingerprint=fingerprint))

    # 仅保留最近 200 条处理记录，避免无限增长
    old_ids = (
        await db.execute(
            select(AlertResolution.id)
            .order_by(AlertResolution.resolved_at.desc())
            .offset(200)
        )
    ).scalars().all()
    for old_id in old_ids:
        old_row = await db.get(AlertResolution, old_id)
        if old_row:
            await db.delete(old_row)

    await db.commit()
    await log_audit(
        db,
        user_id=current_user.id,
        action="alert_resolve",
        resource="alert",
        detail={"alert_id": alert_id},
    )
    return MessageResponse(message=f"告警 {alert_id} 已处理")


@router.get(
    "/audit-logs",
    response_model=list[dict],
    summary="操作日志",
)
async def list_audit_logs(
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> list[dict]:
    """查询关键操作审计日志，支持按动作筛选。"""
    if db is None:
        return []

    from sqlalchemy import select

    query = (
        select(AuditLog, User)
        .join(User, User.id == AuditLog.user_id, isouter=True)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    if action:
        query = query.where(AuditLog.action == action)

    result = await db.execute(query)
    rows = []
    for audit_row, user in result.all():
        rows.append({
            "id": audit_row.id,
            "user_id": audit_row.user_id,
            "username": user.username if user else "",
            "action": audit_row.action,
            "resource": audit_row.resource,
            "resource_id": audit_row.resource_id,
            "detail": audit_row.detail,
            "ip_address": audit_row.ip_address,
            "created_at": audit_row.created_at.strftime("%Y-%m-%d %H:%M:%S") if audit_row.created_at else "",
        })
    return rows


# =============================================================================
# 导出报表
# =============================================================================

@router.get(
    "/export",
    summary="导出运营报表 (CSV)",
)
async def export_report(
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """导出 CSV 格式的运营报表（含诊断、药品、订单统计 + 库存明细）。"""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    output = io.StringIO()
    output.write('\ufeff')  # BOM for Excel UTF-8
    writer = csv.writer(output)

    writer.writerow(['智医运营报表'])
    writer.writerow(['导出时间', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])

    if db is not None:
        from sqlalchemy import select, func
        from app.models import Diagnosis, Drug, ExamAppointment

        writer.writerow(['指标', '数值'])

        # 诊断统计
        total_diag = await db.execute(select(func.count(Diagnosis.id)))
        writer.writerow(['总诊断次数', total_diag.scalar() or 0])

        today = datetime.utcnow().date()
        today_diag = await db.execute(
            select(func.count(Diagnosis.id)).filter(func.date(Diagnosis.created_at) == today)
        )
        writer.writerow(['今日诊断次数', today_diag.scalar() or 0])

        # 药品统计
        total_drugs = await db.execute(select(func.count(Drug.id)).where(Drug.is_active == True))
        writer.writerow(['在售药品数', total_drugs.scalar() or 0])

        low_stock = await db.execute(select(func.count(Drug.id)).where(Drug.stock < 50))
        writer.writerow(['库存预警药品数', low_stock.scalar() or 0])

        # 订单统计
        total_orders = await db.execute(select(func.count(DrugOrder.id)))
        writer.writerow(['总订单数', total_orders.scalar() or 0])

        pending_orders = await db.execute(
            select(func.count(DrugOrder.id)).where(DrugOrder.delivery_status == DeliveryStatus.PENDING)
        )
        writer.writerow(['待发货订单数', pending_orders.scalar() or 0])

        # 检查预约统计
        total_exams = await db.execute(select(func.count(ExamAppointment.id)))
        writer.writerow(['总检查预约数', total_exams.scalar() or 0])

        writer.writerow([])
        writer.writerow(['库存明细'])
        writer.writerow(['药品名称', '规格', '库存', '价格'])
        drugs_result = await db.execute(select(Drug).where(Drug.is_active == True))
        for drug in drugs_result.scalars():
            writer.writerow([drug.name, drug.specification, drug.stock, drug.price])
    else:
        writer.writerow(['数据库不可用，无数据'])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=zhiyi_report.csv"},
    )

# =============================================================================
# 概览（兼容旧接口）
# =============================================================================

@router.get(
    "/overview",
    response_model=dict,
    summary="管理概览",
)
async def get_overview(
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> dict:
    """管理后台概览（兼容旧版接口，数据来自实时聚合）。"""
    dash = await get_dashboard(current_user=current_user, db=db)
    return {
        "status": "ok",
        "data_source": "实时数据库聚合",
        "pending_alerts": dash.pending_alerts,
        "monthly_services": dash.monthly_services,
        "today_consultations": dash.today_consultations,
        "ai_usage_rate": f"{dash.ai_usage_rate}%",
    }
