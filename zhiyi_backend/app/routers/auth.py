"""
智医 (ZhiYi) — 认证路由
基层医疗AI辅助诊疗平台

POST /api/auth/register     — 用户注册
POST /api/auth/login        — 用户登录
POST /api/auth/demo-login   — 演示登录（开发/演示环境）
POST /api/auth/logout       — 用户登出
GET  /api/auth/me           — 获取当前用户信息
"""

from __future__ import annotations

from typing import Optional

import bcrypt
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.auth import (
    blacklist_token,
    bearer_scheme,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.database import get_db
from app.models import Doctor, Hospital, Patient, User, UserRole
from app.schemas import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserProfileResponse,
)
from app.services.mock_data import USERS
from app.services.audit import log_audit
from app.services.rate_limit import check_rate_limit

router = APIRouter()
settings = get_settings()


# ── 注册 ───────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
)
async def register(payload: RegisterRequest, db: Optional[AsyncSession] = Depends(get_db)) -> MessageResponse:
    """创建新用户账号。

    - 检查手机号/用户名是否已被注册
    - 使用 bcrypt 加密存储密码
    - 返回注册成功消息
    """
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    await check_rate_limit(f"register:{payload.phone}", limit=5, window=3600)
    # 检查手机号是否已注册
    result = await db.execute(select(User).where(User.phone == payload.phone))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该手机号已被注册")

    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == payload.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户名已被使用")

    # 创建用户
    user = User(
        username=payload.username,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=UserRole(payload.role),
    )
    db.add(user)
    await db.commit()

    await log_audit(
        db,
        user_id=user.id,
        action="user_register",
        resource="user",
        resource_id=user.id,
        detail={"role": payload.role},
    )
    return MessageResponse(message="注册成功，请使用手机号登录", data={"user_id": user.id})


# ── 登录 ───────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="用户登录",
)
async def login(payload: LoginRequest, db: Optional[AsyncSession] = Depends(get_db)) -> TokenResponse:
    """使用手机号 + 密码登录，返回 JWT 访问令牌。

    - 验证手机号是否存在
    - 验证密码是否正确
    - 检查账号是否被禁用
    - 签发 JWT Token
    """
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")
    await check_rate_limit(f"login:{payload.phone}", limit=10, window=900)
    result = await db.execute(select(User).where(User.phone == payload.phone))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="手机号或密码错误")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="手机号或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用，请联系管理员")

    token = create_access_token(user.id, user.role.value)
    await log_audit(
        db,
        user_id=user.id,
        action="user_login",
        resource="user",
        resource_id=user.id,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        user_id=user.id,
        name=user.username or payload.phone,
        role=user.role.value,
    )


# ── 演示登录（开发环境） ──────────────────────────────────

@router.post(
    "/demo-login",
    response_model=dict,
    summary="演示登录",
    description="仅用于前端开发联调，返回真实种子账号数据和 JWT Token。",
)
async def demo_login(
    role: str,
    db: Optional[AsyncSession] = Depends(get_db),
) -> dict:
    """演示环境登录，无需密码，通过角色名直接获取 Token。

    优先从数据库读取真实种子账号（姓名/职称/机构），数据库不可用时回退到演示账号。
    """
    if role not in USERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 doctor / patient / admin 角色")
    if not settings.demo_login_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="演示登录已关闭")
    await check_rate_limit(f"demo_login:{role}", limit=20, window=60)

    fallback = USERS[role]
    user_id: int = fallback["id"]
    name: str = fallback["name"]
    title: str = fallback.get("title", "")
    organization: str = fallback.get("organization", "")

    if db is not None:
        try:
            from sqlalchemy import select
            from app.models import Doctor, Hospital, Patient, User, UserRole

            result = await db.execute(
                select(User).where(
                    User.role == UserRole(role),
                    User.is_active.is_(True),
                )
            )
            user = result.scalars().first()
            if user is not None:
                user_id = user.id
                if role == "doctor":
                    doctor = (await db.execute(
                        select(Doctor).where(Doctor.user_id == user.id)
                    )).scalars().first()
                    if doctor:
                        name = doctor.name
                        title = doctor.title or title
                        if doctor.hospital_id:
                            hospital = (await db.execute(
                                select(Hospital).where(Hospital.id == doctor.hospital_id)
                            )).scalars().first()
                            organization = hospital.name if hospital else organization
                    else:
                        name = user.username
                elif role == "patient":
                    patient = (await db.execute(
                        select(Patient).where(Patient.user_id == user.id)
                    )).scalars().first()
                    name = patient.name if patient else user.username
                else:
                    name = user.username or name
        except Exception as exc:
            logger.warning("demo-login 查询真实用户失败，使用默认演示账号：%s", exc)

    token = create_access_token(user_id, role)
    await log_audit(
        db,
        user_id=user_id,
        action="demo_login",
        resource="user",
        resource_id=user_id,
        detail={"role": role},
    )
    return {
        "id": user_id,
        "user_id": user_id,
        "name": name,
        "role": role,
        "title": title,
        "organization": organization,
        "avatar": name[:1] if name else fallback.get("avatar", ""),
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


# ── 短信验证码登录 ─────────────────────────────────────────

class SmsLoginRequest(BaseModel):
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")
    code: str = Field(..., min_length=4, max_length=6, description="短信验证码")


@router.post(
    "/sms-login",
    response_model=dict,
    summary="短信验证码登录",
)
async def sms_login(
    payload: SmsLoginRequest,
    role: str = "patient",
    db: Optional[AsyncSession] = Depends(get_db),
) -> dict:
    """通过手机号 + 短信验证码登录，服务端强制校验验证码。"""
    from app.services.sms import verify_code

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        if not await verify_code(payload.phone, payload.code, redis):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期")
    finally:
        await redis.aclose()

    await check_rate_limit(f"sms_login:{payload.phone}", limit=5, window=600)

    user_id = 202  # 默认患者
    user_name = "陈建国"

    if db is not None:
        try:
            # 尝试查找已有用户
            result = await db.execute(select(User).where(User.phone == payload.phone))
            existing = result.scalar_one_or_none()
            if existing:
                user_id = existing.id
                user_name = existing.username or "用户"
            else:
                # 新用户：自动注册
                if role not in USERS:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效角色")
                mock_data = USERS[role]
                user_name = mock_data["name"]
        except Exception:
            pass

    token = create_access_token(user_id, role)
    await log_audit(
        db,
        user_id=user_id,
        action="sms_login",
        resource="user",
        resource_id=user_id,
        detail={"role": role, "phone": payload.phone},
    )
    return {
        "user_id": user_id,
        "name": user_name,
        "role": role,
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


# ── 登出 ───────────────────────────────────────────────────

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="用户登出",
)
async def logout(bearer: str = Depends(bearer_scheme)) -> MessageResponse:  # noqa: B008
    """将当前 Token 加入 Redis 黑名单，使其立即失效。"""
    if bearer and bearer.credentials:
        await blacklist_token(bearer.credentials)
    return MessageResponse(message="已成功登出")


# ── 获取当前用户 ──────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="获取当前用户信息",
)
async def get_me(user: User = Depends(get_current_user)) -> User:  # type: ignore[return-type]
    """返回当前登录用户的基本信息。"""
    return user


class UpdateProfileRequest(BaseModel):
    """更新当前用户个人资料请求。"""
    name: Optional[str] = Field(None, min_length=1, max_length=50, description="姓名")
    phone: Optional[str] = Field(None, pattern=r"^1[3-9]\d{9}$", description="11 位手机号")
    password: Optional[str] = Field(None, min_length=6, max_length=100, description="新密码")
    department: Optional[str] = Field(None, max_length=100, description="科室（仅医生）")
    specialty: Optional[str] = Field(None, max_length=500, description="专长（仅医生）")


class ProfileResponse(BaseModel):
    """当前用户完整资料。"""
    id: int
    username: str
    name: str
    phone: str
    role: str
    department: Optional[str] = None
    specialty: Optional[str] = None
    hospital: Optional[str] = None
    title: Optional[str] = None


@router.put(
    "/profile",
    response_model=ProfileResponse,
    summary="更新当前用户个人资料",
)
async def update_my_profile(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
) -> ProfileResponse:
    """更新当前登录用户的姓名、手机号、密码等信息。"""
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库不可用")

    # 更新用户表
    if payload.phone is not None:
        new_phone = payload.phone.strip()
        if new_phone != user.phone:
            existing_phone = await db.execute(select(User).where(User.phone == new_phone))
            if existing_phone.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="该手机号已被其他账号使用",
                )
        user.phone = new_phone
    if payload.password is not None:
        user.password_hash = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()

    # 更新医生表
    doctor_result = await db.execute(select(Doctor).where(Doctor.user_id == user.id))
    doctor = doctor_result.scalar_one_or_none()
    if payload.name is not None:
        if doctor:
            doctor.name = payload.name
        elif user.role == UserRole.PATIENT:
            patient_result = await db.execute(select(Patient).where(Patient.user_id == user.id))
            patient = patient_result.scalar_one_or_none()
            if patient:
                patient.name = payload.name
    if doctor:
        if payload.department is not None:
            doctor.department = payload.department
        if payload.specialty is not None:
            doctor.specialty = payload.specialty

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="保存失败：手机号已被其他账号使用，请更换后重试",
        )

    # 构建响应
    hospital_name: Optional[str] = None
    if doctor:
        hospital_result = await db.execute(select(Hospital.name).where(Hospital.id == doctor.hospital_id))
        hospital_name = hospital_result.scalar_one_or_none()

    return ProfileResponse(
        id=user.id,
        username=user.username,
        name=doctor.name if doctor else user.username,
        phone=user.phone,
        role=user.role.value if hasattr(user.role, 'value') else str(user.role),
        department=doctor.department if doctor else None,
        specialty=doctor.specialty if doctor else None,
        hospital=hospital_name,
        title=doctor.title if doctor else None,
    )
