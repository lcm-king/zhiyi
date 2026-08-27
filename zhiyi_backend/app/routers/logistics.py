"""
智医 (ZhiYi) — 物流追踪路由
基层医疗AI辅助诊疗平台

GET     /api/logistics/{order_id}         — HTTP 物流状态查询
POST    /api/logistics/{order_id}/ship    — 管理员发货（生成路线 + 触发配送）
WS      /api/logistics/ws/{order_id}      — WebSocket 实时位置推送
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.config import get_settings
from app.crud import drug_crud
from app.database import get_db
from app.models import DeliveryStatus, User
from app.schemas import DrugOrderStatusResponse, MessageResponse
from app.services.logistics import (
    generate_route,
    get_cached_position,
    get_cached_route,
    get_cached_route_meta,
    start_delivery_stream,
)

logger = logging.getLogger("zhiyi.logistics_router")
settings = get_settings()

router = APIRouter()


# =============================================================================
# HTTP：物流状态查询
# =============================================================================

@router.get(
    "/{order_id}",
    response_model=DrugOrderStatusResponse,
    summary="查询物流状态",
)
async def get_logistics_status(
    order_id: int,
    db: Optional[AsyncSession] = Depends(get_db),
) -> dict:
    """查询订单物流状态和当前配送位置。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    order = await drug_crud.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    items_summary = ", ".join(
        f"{item.drug.name if item.drug else '未知'}×{item.quantity}" for item in order.items
    )

    # 获取 Redis 缓存的实时位置
    current_pos = await get_cached_position(order_id)

    # 构建物流轨迹（基于真实时间戳）
    tracking = _build_tracking(order)

    # 冷链信息
    cold_chain = await drug_crud.order_requires_cold_chain(db, order_id)
    from app.services.logistics import get_cached_temperatures
    temps = await get_cached_temperatures(order_id)

    estimated_arrival = None
    if order.delivery_status == DeliveryStatus.SHIPPED and order.shipped_at:
        from datetime import timedelta
        eta = order.shipped_at + timedelta(hours=1)
        estimated_arrival = f"预计 {eta.strftime('%H:%M')} 前送达"

    return {
        "order_id": order.id,
        "order_no": order.order_no,
        "items_summary": items_summary,
        "status": order.pay_status.value,
        "delivery_status": order.delivery_status.value,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "cold_chain": cold_chain,
        "current_temperature": temps[-1] if temps else None,
        "temperature_history": temps or [],
        "estimated_arrival": estimated_arrival,
        "current_position": current_pos,
        "hub": await get_cached_route_meta(order_id),
        "route": await get_cached_route(order_id),
        "tracking_points": tracking,
    }


def _build_tracking(order: Any) -> list[dict]:
    """根据订单真实时间戳构建物流时间线。"""
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


# =============================================================================
# HTTP：管理员发货
# =============================================================================

@router.post(
    "/{order_id}/ship",
    response_model=MessageResponse,
    summary="管理员发货",
)
async def ship_order(
    order_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Optional[AsyncSession] = Depends(get_db),
) -> MessageResponse:
    """管理员点击发货：更新订单状态为配送中，并生成模拟配送路径。

    生成的路由存入 Redis，供 WebSocket 端点读取并推送。
    """
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    order = await drug_crud.ship_order(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="订单状态不允许发货（需已支付）",
        )

    # 异步生成配送路径（不阻塞 HTTP 响应）
    asyncio.create_task(generate_route(order_id, dest_address=order.address))

    logger.info("管理员发货：order_id=%d", order_id)
    return MessageResponse(
        message="发货成功，配送路径已生成",
        data={"order_id": order_id, "delivery_status": "shipped"},
    )


# =============================================================================
# WebSocket：实时位置推送
# =============================================================================

@router.websocket("/ws/{order_id}")
async def logistics_websocket(
    websocket: WebSocket,
    order_id: int,
    token: str = Query(...),
):
    """WebSocket 端点：实时推送配送车辆位置。

    连接参数：ws://host:8000/api/logistics/ws/{order_id}?token={jwt_token}
    认证方式：URL 查询参数传递 JWT Token（WebSocket 不支持自定义头）

    推送消息格式：
        {"type": "position_update", "order_id": 1, "position": {...}, "progress": 45.2, "status": "中转站已发出，正在配送"}
        {"type": "delivery_complete", "order_id": 1, "position": {...}, "status": "已送达"}
    """
    # ── JWT 认证 ──
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub", 0))
        role = payload.get("role", "")
    except JWTError:
        await websocket.close(code=4001, reason="无效的访问令牌")
        return

    if role not in ("patient", "admin"):
        await websocket.close(code=4003, reason="权限不足")
        return

    # 接受连接
    await websocket.accept()
    logger.info("WebSocket 连接建立：order_id=%d, user_id=%d", order_id, user_id)

    try:
        # 推送缓存的当前位置
        cached_pos = await get_cached_position(order_id)
        if cached_pos:
            await websocket.send_json({
                "type": "cached_position",
                "order_id": order_id,
                "position": cached_pos,
                "status": "配送中",
            })

        # 获取配送路线（含冷链温度曲线）
        from app.services.logistics import get_cached_route, get_cached_temperatures
        route = await get_cached_route(order_id)
        temperatures = await get_cached_temperatures(order_id)

        if route:
            # 发送路线总览
            await websocket.send_json({
                "type": "route_overview",
                "order_id": order_id,
                "total_points": len(route),
                "start": route[0],
                "end": route[-1],
                "route": route,
                "cold_chain": bool(temperatures),
                "hub": await get_cached_route_meta(order_id),
            })

            # 启动逐点推送（冷链订单附带 2-8℃ 温度）
            await start_delivery_stream(
                order_id,
                route,
                websocket.send_json,
                temperatures=temperatures,
                hub=await get_cached_route_meta(order_id),
            )
        else:
            # 没有路线：查询订单状态
            from app.crud.drug_crud import get_order_by_id, order_requires_cold_chain
            from app.database import async_session_factory

            async with async_session_factory() as db:
                order = await get_order_by_id(db, order_id)
                cold_chain = await order_requires_cold_chain(db, order_id) if order else False

            if order and order.delivery_status.value == "shipped":
                # 已发货但路线缺失/缓存过期：按需立即生成，无需管理员再次操作
                await websocket.send_json({
                    "type": "waiting",
                    "order_id": order_id,
                    "message": "路线生成中，请稍候…",
                })
                route = await generate_route(order_id, dest_address=order.address, need_cold_chain=cold_chain)
                if route:
                    temperatures = await get_cached_temperatures(order_id)
                    await websocket.send_json({
                        "type": "route_overview",
                        "order_id": order_id,
                        "total_points": len(route),
                        "start": route[0],
                        "end": route[-1],
                        "route": route,
                        "cold_chain": cold_chain,
                        "hub": await get_cached_route_meta(order_id),
                    })
                    await start_delivery_stream(
                        order_id,
                        route,
                        websocket.send_json,
                        temperatures=temperatures,
                        hub=await get_cached_route_meta(order_id),
                    )
                    return
                await websocket.send_json({
                    "type": "waiting",
                    "order_id": order_id,
                    "message": "路线生成失败，请稍后刷新重试",
                })
            else:
                # 未支付/未发货：给出明确状态，而非误导性的“等待管理员发货”
                await websocket.send_json({
                    "type": "waiting",
                    "order_id": order_id,
                    "message": "订单尚未支付，支付后将自动安排冷链/常温配送",
                })

            # 保持连接，等待推送
            while True:
                try:
                    data = await websocket.receive_text()
                    if data == "ping":
                        await websocket.send_text("pong")
                except WebSocketDisconnect:
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开：order_id=%d", order_id)
    except Exception as exc:
        logger.error("WebSocket 错误：order_id=%d, %s", order_id, exc)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
