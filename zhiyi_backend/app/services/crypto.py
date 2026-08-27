"""
智医 (ZhiYi) — 医疗数据字段级加密服务
基层医疗AI辅助诊疗平台

使用 Fernet（AES-128-CBC + HMAC-SHA256）对敏感字段（如身份证号）做加密存储：
  - 写入数据库前加密（encrypt_text）
  - 读取数据库后解密（decrypt_text）
  - 密钥来自环境变量 FIELD_ENCRYPT_KEY（base64 32 字节）；
    未配置时从 JWT_SECRET_KEY 派生，保证开箱即用。

注意：加密是随机的（每次密文不同），因此加密列不应再设置唯一约束。
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger("zhiyi.crypto")

_FERNET = None


def _get_fernet():
    """懒加载 Fernet 实例（全局单例）。"""
    global _FERNET
    if _FERNET is not None:
        return _FERNET

    from cryptography.fernet import Fernet

    settings = get_settings()
    raw_key = settings.field_encrypt_key.strip()
    if raw_key:
        try:
            key = raw_key.encode("utf-8")
            Fernet(key)  # 校验格式
        except Exception as exc:
            logger.error("FIELD_ENCRYPT_KEY 格式非法，改为从 JWT_SECRET_KEY 派生：%s", exc)
            raw_key = ""
    if not raw_key:
        # 从 JWT 密钥派生稳定 32 字节 key
        digest = hashlib.sha256(settings.jwt_secret_key.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)

    _FERNET = Fernet(key)
    return _FERNET


def encrypt_text(plaintext: Optional[str]) -> Optional[str]:
    """加密明文字段；空值原样返回。"""
    if not plaintext:
        return plaintext
    try:
        return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.error("字段加密失败：%s", exc)
        return plaintext


def decrypt_text(ciphertext: Optional[str]) -> Optional[str]:
    """解密字段；空值原样返回，解密失败时返回原文并告警（避免阻断业务）。"""
    if not ciphertext:
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.warning("字段解密失败（可能为历史明文数据）：%s", exc)
        return ciphertext


def mask_id_number(id_number: Optional[str]) -> Optional[str]:
    """身份证号脱敏：保留前 6 位与后 4 位，中间打码。"""
    if not id_number or len(id_number) < 10:
        return id_number
    return f"{id_number[:6]}**********{id_number[-4:]}"
