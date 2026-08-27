"""
智医 (ZhiYi) — 知识库向量化索引脚本
将 83 种疾病诊断知识存入 ChromaDB，供 RAG 语义检索使用。

使用方法：
    python -m app.services.index_knowledge_base
"""
from __future__ import annotations

import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import get_settings
from app.services.knowledge_base import DISEASE_KNOWLEDGE
from app.services.langgraph_workflow import get_qwen_embeddings

logger = logging.getLogger("zhiyi.index_kb")


async def index_knowledge_base(force: bool = False):
    settings = get_settings()
    if not settings.siliconflow_api_key:
        logger.error("未配置 SILICONFLOW_API_KEY（embedding），无法生成向量")
        return

    # 导入 chromadb
    try:
        import chromadb
    except ImportError:
        logger.error("chromadb 未安装，请运行: pip install chromadb")
        return

    client = chromadb.HttpClient(
        host=settings.chroma_host or "localhost",
        port=int(settings.chroma_port or "8000"),
    )
    # 使用余弦距离空间：distance = 1 - cosine_similarity，
    # 这样 score = (1 - dist) * 100 才是真正的相似度，且与 bge-m3 单位向量匹配。
    collection_meta = {"hnsw:space": "cosine"}
    if force:
        try:
            client.delete_collection("disease_knowledge")
            logger.info("已删除旧知识库集合（force 模式）")
        except Exception as exc:
            logger.warning("删除旧集合失败（可能不存在）：%s", exc)
    collection = client.get_or_create_collection(
        "disease_knowledge", metadata=collection_meta
    )

    # 检查是否已索引
    existing = collection.count()
    if existing >= len(DISEASE_KNOWLEDGE):
        logger.info("知识库已索引 %d 条，跳过", existing)
        return

    logger.info("开始索引 %d 种疾病到 ChromaDB…", len(DISEASE_KNOWLEDGE))

    # 批量生成 embedding（每批 10 条避免 API 限流）
    batch_size = 10
    ids = []
    embeddings = []
    documents = []
    metadatas = []

    for i in range(0, len(DISEASE_KNOWLEDGE), batch_size):
        batch = DISEASE_KNOWLEDGE[i:i + batch_size]
        texts = [
            f"{d['name']}：{'；'.join(d.get('typical_symptoms', []))}。"
            f"体征：{'；'.join(d.get('signs', []))}。"
            f"诊断：{'；'.join(d.get('diagnostic_criteria', []))}"
            for d in batch
        ]

        try:
            batch_vectors = await get_qwen_embeddings(texts)
        except Exception as exc:
            logger.warning("批次 %d embedding 失败：%s", i // batch_size, exc)
            continue

        for j, d in enumerate(batch):
            ids.append(d["id"])
            embeddings.append(batch_vectors[j])
            documents.append(
                f"{d['name']}（{d.get('category', '')}）："
                f"{'；'.join(d.get('typical_symptoms', []))}。"
                f"诊断标准：{'；'.join(d.get('diagnostic_criteria', []))}"
            )
            metadatas.append({
                "name": d["name"],
                "category": d.get("category", ""),
            })

        logger.info("已处理 %d/%d 条", min(i + batch_size, len(DISEASE_KNOWLEDGE)), len(DISEASE_KNOWLEDGE))
        await asyncio.sleep(0.5)  # API 限流保护

    # 写入 ChromaDB
    collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    logger.info("知识库向量化完成：%d 条疾病已存入 ChromaDB", len(ids))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    force = "--force" in sys.argv or "-f" in sys.argv
    asyncio.run(index_knowledge_base(force=force))
