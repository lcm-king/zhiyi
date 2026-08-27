"""
短信验证码路由
POST /api/sms/send    — 发送验证码
POST /api/sms/verify  — 校验验证码
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.rate_limit import check_rate_limit
from app.services.sms import send_verify_code, verify_code

router = APIRouter()


async def _get_redis() -> aioredis.Redis:
    settings = get_settings()
    return aioredis.from_url(settings.redis_url, decode_responses=True)


class SendSmsRequest(BaseModel):
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")


class VerifySmsRequest(BaseModel):
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")
    code: str = Field(..., min_length=4, max_length=6)


@router.post("/send", summary="发送验证码")
async def send_sms(payload: SendSmsRequest):
    """向指定手机号发送短信验证码。"""
    await check_rate_limit(f"sms_send:{payload.phone}", limit=10, window=3600)
    redis = await _get_redis()
    try:
        result = await send_verify_code(payload.phone, redis)
        if not result["ok"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        resp = {"message": result["message"]}
        if "code" in result:
            resp["code"] = result["code"]
        return resp
    finally:
        await redis.aclose()


@router.post("/verify", summary="校验验证码")
async def verify_sms(payload: VerifySmsRequest):
    """校验短信验证码是否正确。"""
    redis = await _get_redis()
    try:
        ok = await verify_code(payload.phone, payload.code, redis)
        if not ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期")
        return {"ok": True, "message": "验证通过"}
    finally:
        await redis.aclose()
