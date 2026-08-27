"""
智医 (ZhiYi) — 认证与授权模块
基层医疗AI辅助诊疗平台

提供 JWT 签发/验证、密码哈希、权限依赖注入等核心安全功能。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import logging

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole

settings = get_settings()
logger = logging.getLogger("zhiyi.auth")

# ── 密码哈希 ───────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── HTTP Bearer 提取器 ─────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """使用 bcrypt 对明文密码进行哈希。"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码与哈希值是否匹配。"""
    return pwd_context.verify(plain, hashed)


# ── JWT ────────────────────────────────────────────────────

def create_access_token(user_id: int, role: str) -> str:
    """签发 JWT 访问令牌，payload 包含 user_id 和 role。"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """解码并验证 JWT 令牌，返回 payload；验证失败则抛出异常。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if "sub" not in payload or "role" not in payload:
            raise JWTError("token missing required claims")
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的访问令牌，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Redis 黑名单（登出） ───────────────────────────────────

async def _get_redis() -> aioredis.Redis:
    """创建 Redis 连接（每次调用建立新连接）。"""
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def blacklist_token(token: str) -> None:
    """将令牌加入 Redis 黑名单（登出时调用）。"""
    r = await _get_redis()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        exp = payload.get("exp", 0)
        ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 1)
        await r.setex(f"blacklist:{token}", ttl, "1")
    except JWTError:
        pass
    finally:
        await r.aclose()


async def is_token_blacklisted(token: str) -> bool:
    """检查令牌是否已被加入黑名单。

    当 Redis 不可用时，优雅降级：假设令牌未失效，避免阻断正常请求。
    """
    try:
        r = await _get_redis()
        try:
            return await r.exists(f"blacklist:{token}") > 0
        finally:
            await r.aclose()
    except Exception as exc:
        logger.warning("Redis 黑名单检查失败，假设令牌有效：%s", exc)
        return False


# ── 认证依赖 ───────────────────────────────────────────────

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Optional[AsyncSession] = Depends(get_db),
) -> User:
    """从请求头 Bearer Token 中解析当前登录用户。

    自动检查令牌有效性、黑名单状态，并查询数据库获取用户对象。
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # 检查黑名单
    if await is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌已失效，请重新登录",
        )

    payload = decode_access_token(token)
    user_id = int(payload["sub"])

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库不可用，无法验证用户身份",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    return user


# ── 角色权限依赖 ───────────────────────────────────────────

def require_role(*allowed_roles: str):
    """返回一个 FastAPI 依赖，限制只有指定角色可访问。

    用法：
        @router.get("/admin-only")
        async def admin_endpoint(user = Depends(require_role("admin"))):
            ...
    """

    async def role_checker(user: User = Depends(get_current_user)) -> User:
        role_value = user.role.value if isinstance(user.role, UserRole) else str(user.role)
        if role_value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，无法访问此资源",
            )
        return user

    return role_checker
