"""
智医 (ZhiYi) — Elasticsearch 服务层
基层医疗AI辅助诊疗平台

提供异步 ES 客户端、患者索引管理、全文搜索功能。
ES 必须可用——不可用时直接抛异常，不降级。
"""

from __future__ import annotations

import logging
from typing import Any

from elasticsearch import AsyncElasticsearch, ConnectionError as ESConnectionError

from app.config import get_settings

logger = logging.getLogger("zhiyi.elasticsearch")

settings = get_settings()

_es_client: AsyncElasticsearch | None = None
_index_initialized: bool = False

PATIENT_INDEX = settings.es_index_patients
PATIENT_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "ik_smart_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase"],
                }
            }
        },
    },
    "mappings": {
        "properties": {
            "id": {"type": "integer"},
            "user_id": {"type": "integer"},
            "name": {
                "type": "text",
                "analyzer": "ik_smart_analyzer",
                "fields": {
                    "keyword": {"type": "keyword"},
                    "pinyin": {"type": "text", "analyzer": "standard"},
                },
            },
            "gender": {"type": "keyword"},
            "birth_date": {"type": "date", "format": "yyyy-MM-dd"},
            "phone": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "is_active": {"type": "boolean"},
        }
    },
}


async def get_es_client() -> AsyncElasticsearch:
    """获取 ES 异步客户端单例。ES 不可用时抛出异常。"""
    global _es_client
    if _es_client is not None:
        return _es_client
    _es_client = AsyncElasticsearch(
        hosts=[settings.es_host],
        request_timeout=10,
        max_retries=2,
        retry_on_timeout=True,
    )
    info = await _es_client.info()
    logger.info("ES 连接成功: %s (v%s)", info.get("cluster_name", "unknown"), info["version"]["number"])
    return _es_client


async def ensure_patient_index() -> None:
    """确保患者索引存在，不存在则创建。"""
    global _index_initialized
    if _index_initialized:
        return
    client = await get_es_client()
    exists = await client.indices.exists(index=PATIENT_INDEX)
    if not exists:
        await client.indices.create(index=PATIENT_INDEX, body=PATIENT_MAPPING)
        logger.info("ES 索引已创建: %s", PATIENT_INDEX)
    _index_initialized = True


async def index_patient(patient: dict[str, Any]) -> None:
    """索引单个患者文档。"""
    client = await get_es_client()
    doc = {
        "id": patient["id"],
        "user_id": patient.get("user_id", 0),
        "name": patient.get("name", ""),
        "gender": patient.get("gender", ""),
        "birth_date": patient.get("birth_date", ""),
        "phone": patient.get("phone", ""),
        "is_active": patient.get("is_active", True),
    }
    await client.index(index=PATIENT_INDEX, id=str(patient["id"]), document=doc)


async def bulk_index_patients(patients: list[dict[str, Any]]) -> int:
    """批量索引患者（用于启动时同步全量数据）。"""
    client = await get_es_client()
    await ensure_patient_index()
    for p in patients:
        await index_patient(p)
    await client.indices.refresh(index=PATIENT_INDEX)
    logger.info("ES 批量索引患者: %d 条", len(patients))
    return len(patients)


async def search_patients(
    query: str,
    size: int = 20,
) -> tuple[list[int], int]:
    """ES 全文搜索患者，返回匹配的 patient_id 列表和总数。"""
    await ensure_patient_index()
    client = await get_es_client()

    body = {
        "query": {
            "bool": {
                "should": [
                    {"match": {"name": {"query": query, "boost": 2.0}}},
                    {"match": {"name.pinyin": {"query": query, "boost": 1.5}}},
                    {"wildcard": {"phone": {"value": f"*{query}*", "boost": 1.2}}},
                    {"match": {"phone": {"query": query, "boost": 1.0}}},
                ],
                "minimum_should_match": 1,
            }
        },
        "size": size,
        "_source": ["id"],
    }
    result = await client.search(index=PATIENT_INDEX, body=body)
    hits = result["hits"]["hits"]
    ids = [int(h["_source"]["id"]) for h in hits]
    total = result["hits"]["total"]
    total_count = total["value"] if isinstance(total, dict) else total
    logger.info("ES 搜索 '%s': 命中 %d 条", query, total_count)
    return ids, total_count


async def delete_patient(patient_id: int) -> None:
    """从 ES 删除指定患者文档。"""
    client = await get_es_client()
    await client.delete(index=PATIENT_INDEX, id=str(patient_id), ignore=[404])
