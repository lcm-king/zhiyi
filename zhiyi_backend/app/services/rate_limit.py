"""
智医 (ZhiYi) — 基于 Redis 的接口限流

登录 / 注册 / 短信等敏感接口统一限流；Redis 不可用时放行，避免阻断业务。
"""

from __future__ import annotations

import logging
import time

import redis.asyncio as aioredis
from fastapi import HTTPException, status

from app.config import get_settings

logger = logging.getLogger("zhiyi.rate_limit")


async def check_rate_limit(key: str, limit: int = 10, window: int = 60) -> None:
    """对指定 key 计数，超过 limit 时返回 429。"""
    settings = get_settings()
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        bucket = int(time.time()) // window
        redis_key = f"ratelimit:{key}:{bucket}"
        count = await r.incr(redis_key)
        if count == 1:
            await r.expire(redis_key, window * 2)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="请求过于频繁，请稍后再试",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("限流检查失败（放行请求）：%s", exc)
    finally:
        await r.aclose()
