"""
智医 (ZhiYi) — MongoDB 文档存储服务（第二亮点）
基层医疗AI辅助诊疗平台

职责：
  1. patient_profiles 集合 — 患者档案（含就诊 visits、健康趋势），按 patient_id upsert
  2. ai_qa_logs 集合      — AI 医学问答日志（问题/回答/来源/时间）

依赖 motor；未安装或连接失败时自动降级（仅记录日志），不影响 MySQL 主链路。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("zhiyi.mongo")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/zhiyi")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "zhiyi")
PROFILE_COLLECTION = "patient_profiles"
QA_LOG_COLLECTION = "ai_qa_logs"

_client = None  # 全局 Motor 客户端（懒加载单例）


def _load_motor():
    """懒加载 motor，未安装时返回 None。"""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient  # noqa: PLC0415
        return AsyncIOMotorClient
    except Exception as exc:  # pragma: no cover
        logger.warning("motor 未安装，MongoDB 不可用：%s", exc)
        return None


def get_mongo_client():
    """获取全局 MongoDB 异步客户端（懒加载，失败返回 None）。"""
    global _client
    if _client is None:
        motor_cls = _load_motor()
        if motor_cls is None:
            return None
        try:
            _client = motor_cls(MONGO_URL, serverSelectionTimeoutMS=3000)
        except Exception as exc:
            logger.warning("MongoDB 客户端创建失败：%s", exc)
            return None
    return _client


def get_mongo_db():
    """获取 MongoDB 数据库句柄（不可用时返回 None）。"""
    client = get_mongo_client()
    if client is None:
        return None
    return client[MONGO_DB_NAME]


async def upsert_patient_profile(patient_id: int, data: dict[str, Any]) -> bool:
    """将患者完整档案（含 visits / trend）upsert 到 MongoDB patient_profiles。"""
    try:
        db = get_mongo_db()
        if db is None:
            return False
        doc = dict(data)
        doc["patient_id"] = patient_id
        doc["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db[PROFILE_COLLECTION].update_one(
            {"patient_id": patient_id},
            {"$set": doc},
            upsert=True,
        )
        logger.info("MongoDB 患者档案已写入：patient_id=%d", patient_id)
        return True
    except Exception as exc:
        logger.warning("MongoDB 患者档案写入失败 patient_id=%d: %s", patient_id, exc)
        return False


async def get_patient_profile_doc(patient_id: int) -> Optional[dict[str, Any]]:
    """从 MongoDB 读取患者档案文档（不存在返回 None）。"""
    try:
        db = get_mongo_db()
        if db is None:
            return None
        doc = await db[PROFILE_COLLECTION].find_one({"patient_id": patient_id})
        if doc:
            doc.pop("_id", None)
        return doc
    except Exception as exc:
        logger.warning("MongoDB 患者档案读取失败 patient_id=%d: %s", patient_id, exc)
        return None


async def log_ai_qa(
    patient_id: int,
    question: str,
    answer: str,
    *,
    sources: Optional[list[str]] = None,
    related_diseases: Optional[list[dict[str, Any]]] = None,
    use_ai: bool = False,
) -> bool:
    """写入 AI 医学问答日志到 MongoDB ai_qa_logs 集合。"""
    try:
        db = get_mongo_db()
        if db is None:
            return False
        await db[QA_LOG_COLLECTION].insert_one({
            "patient_id": patient_id,
            "question": question,
            "answer": answer,
            "sources": sources or [],
            "related_diseases": related_diseases or [],
            "use_ai": use_ai,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        return True
    except Exception as exc:
        logger.warning("MongoDB AI 问答日志写入失败 patient_id=%d: %s", patient_id, exc)
        return False
