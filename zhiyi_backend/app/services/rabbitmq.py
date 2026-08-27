"""
智医 (ZhiYi) — RabbitMQ 异步消息服务（第三亮点）
基层医疗AI辅助诊疗平台

职责：
  1. publish_prescription_review   — 发布 AI 处方审核任务（药品下单后触发）
  2. start_prescription_review_consumer — 后台消费者，消费后回调更新 drug_orders 状态

依赖 aio-pika；未安装时自动降级（仅记录日志），不影响主流程。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("zhiyi.rabbitmq")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://localhost:5672/")
EXCHANGE_NAME = "zhiyi.direct"
REVIEW_QUEUE = "prescription.review"
REVIEW_ROUTING_KEY = "prescription.review"


def _load_amqp():
    """懒加载 aio-pika，未安装时返回 None。"""
    try:
        import aio_pika  # noqa: PLC0415
        return aio_pika
    except Exception as exc:  # pragma: no cover
        logger.warning("aio-pika 未安装，RabbitMQ 异步链路不可用：%s", exc)
        return None


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def _ensure_queue(channel, aio_pika) -> Any:
    """声明交换机与队列并绑定（幂等）。"""
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True
    )
    queue = await channel.declare_queue(REVIEW_QUEUE, durable=True)
    await queue.bind(exchange, REVIEW_ROUTING_KEY)
    return exchange, queue


async def publish_prescription_review(
    order_id: int,
    patient_id: int,
    items: list[dict[str, Any]],
    *,
    allergies: Optional[list[str]] = None,
    history: Optional[list[str]] = None,
) -> bool:
    """发布 AI 处方审核任务到 RabbitMQ。

    失败时不抛出异常（仅记录日志），保证下单主流程不受消息中间件影响。
    """
    aio_pika = _load_amqp()
    if aio_pika is None:
        return False

    payload = {
        "type": "prescription.review",
        "order_id": order_id,
        "patient_id": patient_id,
        "items": items,
        "allergies": allergies or [],
        "history": history or [],
        "published_at": _now(),
    }

    connection = None
    try:
        connection = await aio_pika.connect_robust(RABBITMQ_URL, timeout=10)
        async with connection.channel() as channel:
            exchange, _ = await _ensure_queue(channel, aio_pika)
            message = aio_pika.Message(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
                timestamp=datetime.now(),
            )
            await exchange.publish(message, routing_key=REVIEW_ROUTING_KEY)
        logger.info("处方审核任务已发布：order_id=%d, 药品数=%d", order_id, len(items))
        return True
    except Exception as exc:
        logger.warning("处方审核任务发布失败（不影响下单）：order_id=%d, %s", order_id, exc)
        return False
    finally:
        if connection is not None and not connection.is_closed:
            try:
                await connection.close()
            except Exception:  # pragma: no cover
                pass


async def _handle_review_message(message: Any) -> None:
    """处理单条处方审核任务：规则审核 → 回调更新 drug_orders 状态。"""
    async with message.process(requeue=False):
        try:
            body = json.loads(message.body.decode("utf-8"))
        except Exception:
            logger.warning("处方审核消息解析失败，丢弃")
            return

        order_id = body.get("order_id")
        if not order_id:
            logger.warning("处方审核消息缺少 order_id，丢弃")
            return

        try:
            from app.database import async_session_factory
            from app.crud import drug_crud
            from app.services.prescription_review import review_prescription

            async with async_session_factory() as db:
                order = await drug_crud.get_order_by_id(db, order_id)
                if not order:
                    logger.warning("处方审核：订单不存在 order_id=%d，丢弃", order_id)
                    return

                items = body.get("items") or []
                drug_names = [it.get("name") or it.get("drug_name") or "" for it in items]
                total_qty = sum(int(it.get("quantity") or 0) for it in items)
                review = review_prescription(
                    drug_names,
                    quantity=total_qty,
                    allergies=body.get("allergies"),
                )

                updated = await drug_crud.update_prescription_review(db, order_id, review)
                if updated:
                    logger.info(
                        "处方审核回调完成：order_id=%d risk=%s passed=%s warnings=%d",
                        order_id,
                        review["risk"],
                        review["passed"],
                        len(review["warnings"]),
                    )
        except Exception:
            logger.exception("处方审核处理异常：order_id=%s", order_id)


async def start_prescription_review_consumer() -> None:
    """后台消费者：监听 prescription.review 队列，循环处理审核任务。

    在 FastAPI lifespan 中以 asyncio task 启动；连接异常时自动重连。
    """
    aio_pika = _load_amqp()
    if aio_pika is None:
        logger.warning("aio-pika 未安装，跳过处方审核消费者启动")
        return

    while True:
        connection = None
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL, timeout=10)
            async with connection.channel() as channel:
                await channel.set_qos(prefetch_count=10)
                _, queue = await _ensure_queue(channel, aio_pika)
                logger.info("RabbitMQ 处方审核消费者已启动，等待任务…")

                # aio-pika：queue.iterator() 返回异步迭代器，逐条消费并在 process() 内 ack
                async with queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        await _handle_review_message(message)
        except asyncio.CancelledError:
            logger.info("RabbitMQ 处方审核消费者已停止")
            return
        except Exception as exc:
            logger.warning("RabbitMQ 消费者连接异常，5 秒后重连：%s", exc)
            if connection is not None and not connection.is_closed:
                try:
                    await connection.close()
                except Exception:  # pragma: no cover
                    pass
            await asyncio.sleep(5)
