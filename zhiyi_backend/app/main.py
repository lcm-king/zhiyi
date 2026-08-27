"""
智医 (ZhiYi) — FastAPI 应用入口
基层医疗AI辅助诊疗平台

组装路由、中间件、生命周期事件。
启动：uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.config import get_settings

# ── 配置（必须在 router 导入之前加载，确保 .env 变量可用）──
settings = get_settings()

from app.database import engine
from app.models import Base  # noqa: F401 — 确保所有模型被 SQLAlchemy 注册
from app.routers import admin, auth, diagnosis, drug, exam, logistics, payment, profile, sms

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("zhiyi")


# ── 生命周期 ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭事件处理。"""
    # 启动：验证数据库连通性
    logger.info("智医后端服务启动中…")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库连接验证通过，表结构已同步")

        # 同步 MySQL 患者数据到 Elasticsearch
        try:
            from app.crud.user_crud import get_all_patients
            from app.database import async_session_factory
            from app.services.elasticsearch import bulk_index_patients, ensure_patient_index

            async with async_session_factory() as es_db:
                patients = await get_all_patients(es_db, limit=500)
                if patients:
                    await ensure_patient_index()
                    count = await bulk_index_patients(patients)
                    logger.info("ES 索引同步完成: %d 患者", count)
        except Exception as exc:
            logger.error("ES 索引同步失败，搜索功能不可用: %s", exc)
    except Exception as exc:
        logger.warning("数据库连接失败：%s — 将以演示模式运行", exc)

    # 启动 RabbitMQ 处方审核消费者（异步后台任务，失败自动重连）
    rabbit_consumer_task = None
    try:
        import asyncio
        from app.services.rabbitmq import start_prescription_review_consumer

        rabbit_consumer_task = asyncio.create_task(start_prescription_review_consumer())
    except Exception as exc:
        logger.warning("RabbitMQ 消费者启动失败：%s", exc)

    # 后台自动初始化知识库（ChromaDB 向量索引，幂等；缺失时自动补跑）
    kb_init_task = None
    try:
        import asyncio
        from app.services.index_knowledge_base import index_knowledge_base

        kb_init_task = asyncio.create_task(index_knowledge_base())
    except Exception as exc:
        logger.warning("知识库自动初始化任务启动失败：%s", exc)

    yield

    # 关闭：清理资源
    logger.info("智医后端服务关闭，正在释放数据库连接…")
    for task in (rabbit_consumer_task, kb_init_task):
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    await engine.dispose()


# ── 请求日志中间件 ─────────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录每个 HTTP 请求的方法、路径和耗时。"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        logger.info(
            "%s %s → %d (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed * 1000,
        )
        return response


# ── 创建应用 ───────────────────────────────────────────────

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    lifespan=lifespan,
)

# ── 中间件 ─────────────────────────────────────────────────

app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 全局异常处理 ───────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """捕获未处理的异常，返回统一格式错误响应。"""
    logger.exception("未处理的异常：%s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "ok": False,
            "message": "服务器内部错误，请稍后重试",
            "detail": str(exc) if settings.debug else None,
        },
    )


# ── 注册路由 ───────────────────────────────────────────────

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(diagnosis.router, prefix="/api/diagnosis", tags=["智能诊疗"])
app.include_router(exam.router, prefix="/api/exams", tags=["检查预约"])
app.include_router(drug.router, prefix="/api/drugs", tags=["药品采购"])
app.include_router(logistics.router, prefix="/api/logistics", tags=["物流追踪"])
app.include_router(profile.router, prefix="/api/profile", tags=["健康档案"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理后台"])
app.include_router(sms.router, prefix="/api/sms", tags=["短信验证"])
app.include_router(payment.router, prefix="/api/pay", tags=["支付"])


# ── 健康检查 ───────────────────────────────────────────────

@app.get("/health", tags=["系统"])
async def health_check() -> dict[str, Any]:
    """服务健康检查端点。"""
    return {
        "status": "ok",
        "service": "zhiyi-backend",
        "version": settings.api_version,
        "debug": settings.debug,
    }
