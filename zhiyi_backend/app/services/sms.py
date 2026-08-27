"""
容联云通讯 SMS 服务
发送验证码 + 验证校验
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import time
from datetime import datetime
from os import getenv
from urllib.request import Request, urlopen

import redis.asyncio as aioredis

CLOOPEN_BASE = getenv("CLOOPEN_BASE_URL", "https://app.cloopen.com:8883")
ACCOUNT_SID = getenv("CLOOPEN_ACCOUNT_SID", "")
AUTH_TOKEN = getenv("CLOOPEN_AUTH_TOKEN", "")
APP_ID = getenv("CLOOPEN_APP_ID", "")
TEMPLATE_ID = getenv("CLOOPEN_TEMPLATE_ID", "1")
SMS_MOCK = getenv("SMS_MOCK", "false").lower() == "true"

# Redis 存验证码，5 分钟过期
VERIFY_PREFIX = "sms:verify:"
VERIFY_TTL = 300  # 5 minutes
RATE_LIMIT_PREFIX = "sms:rate:"
RATE_LIMIT_TTL = 60  # 60 秒内只能发一次


def _generate_code() -> str:
    return f"{random.randint(1000, 9999)}"


def _sign(timestamp: str) -> str:
    """容联云 SIG 签名：MD5(AccountSid + AuthToken + timestamp) 的大写十六进制"""
    raw = f"{ACCOUNT_SID}{AUTH_TOKEN}{timestamp}"
    return hashlib.md5(raw.encode()).hexdigest().upper()


def _build_authorization(timestamp: str) -> str:
    """容联云 Authorization 头：Base64(AccountSid + : + timestamp)"""
    raw = f"{ACCOUNT_SID}:{timestamp}"
    return base64.b64encode(raw.encode()).decode()


async def send_verify_code(phone: str, redis: aioredis.Redis) -> dict:
    """发送短信验证码到手机号。返回 {ok, message, code(仅mock)}"""
    code = _generate_code()

    # Mock 模式：直接返回验证码，不真正发短信
    if SMS_MOCK:
        await redis.setex(f"{VERIFY_PREFIX}{phone}", VERIFY_TTL, code)
        return {"ok": True, "message": "验证码已发送（演示模式）", "code": code}
    if not ACCOUNT_SID:
        return {"ok": False, "message": "短信服务未配置，无法发送验证码"}

    # 频率限制
    rate_key = f"{RATE_LIMIT_PREFIX}{phone}"
    if await redis.get(rate_key):
        return {"ok": False, "message": "发送太频繁，请 60 秒后再试"}

    # 存 Redis
    await redis.setex(f"{VERIFY_PREFIX}{phone}", VERIFY_TTL, code)
    await redis.setex(rate_key, RATE_LIMIT_TTL, "1")

    # 调用容联云 API
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    sig = _sign(timestamp)
    auth = _build_authorization(timestamp)

    url = f"{CLOOPEN_BASE}/2013-12-26/Accounts/{ACCOUNT_SID}/SMS/TemplateSMS?sig={sig}"
    body = json.dumps({
        "to": phone,
        "appId": APP_ID,
        "templateId": TEMPLATE_ID,
        "datas": [code],
    }).encode()

    try:
        req = Request(url, data=body, method="POST")
        req.add_header("Accept", "application/json")
        req.add_header("Content-Type", "application/json;charset=utf-8")
        req.add_header("Authorization", auth)
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("statusCode") == "000000":
                return {"ok": True, "message": "验证码已发送"}
            return {"ok": False, "message": data.get("statusMsg", "短信发送失败")}
    except Exception as e:
        return {"ok": False, "message": f"短信发送失败：{e}"}


async def verify_code(phone: str, code: str, redis: aioredis.Redis) -> bool:
    """验证短信验证码。"""
    stored = await redis.get(f"{VERIFY_PREFIX}{phone}")
    if not stored:
        return False
    if isinstance(stored, bytes):
        stored = stored.decode()
    if stored != code:
        return False
    await redis.delete(f"{VERIFY_PREFIX}{phone}")
    return True
