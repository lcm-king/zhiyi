"""
智医 (ZhiYi) — 数据库连接模块
基层医疗AI辅助诊疗平台

使用 SQLAlchemy 2.0 异步引擎连接 MySQL。
当 MySQL 不可用时，get_db 返回 None，路由自动降级到模拟数据。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger("zhiyi.database")
settings = get_settings()

# 标记数据库是否可用
_db_available: Optional[bool] = None

# ── 异步引擎 ───────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    echo=settings.debug,
    connect_args={
        "charset": "utf8mb4",
    },
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def check_db() -> bool:
    """检测数据库是否可达。单次检查结果会缓存。"""
    global _db_available
    if _db_available is not None:
        return _db_available
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        _db_available = True
        logger.info("MySQL 连接验证通过")
    except Exception:
        _db_available = False
        logger.warning("MySQL 不可用，将使用模拟数据降级运行")
    return _db_available


# ── 依赖注入 ───────────────────────────────────────────────
async def get_db() -> Optional[AsyncSession]:
    """FastAPI 依赖：数据库可用时返回 session，不可用时返回 None。

    路由可通过 `if db is None` 判断是否应使用模拟数据。
    """
    if not await check_db():
        yield None
        return

    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── 数据库降级辅助 ─────────────────────────────────────────
from typing import Callable, Coroutine, TypeVar

T = TypeVar("T")


async def safe_db_call(
    db_call: Callable[[], Coroutine[Any, Any, T]],
    mock_data: T,
    *,
    log_msg: str = "数据库不可用",
) -> T:
    """安全调用数据库操作：数据库不可用时返回 mock 数据。"""
    try:
        return await db_call()
    except Exception as exc:
        logger.warning("%s，使用模拟数据：%s", log_msg, exc)
        return mock_data
