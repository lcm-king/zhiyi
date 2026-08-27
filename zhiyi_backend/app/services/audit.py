"""
智医 (ZhiYi) — 审计日志服务

关键操作（登录、诊断、处方、发货、后台管理等）统一落库，
审计失败不影响业务主流程。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

logger = logging.getLogger("zhiyi.audit")


async def log_audit(
    db: Optional[AsyncSession],
    *,
    user_id: Optional[int],
    action: str,
    resource: Optional[str] = None,
    resource_id: Optional[int] = None,
    detail: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """写入一条审计日志，异常时仅记录 warning，不阻断业务。"""
    if db is None:
        return
    try:
        db.add(AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            detail=detail,
            ip_address=ip_address,
        ))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("审计日志写入失败 action=%s: %s", action, exc)
