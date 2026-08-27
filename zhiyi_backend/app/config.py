"""
智医 (ZhiYi) — 应用配置模块
基层医疗AI辅助诊疗平台

使用 pydantic-settings 从环境变量 / .env 文件加载配置，
所有配置项集中管理，类型安全。
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置，自动从 .env 文件和系统环境变量加载。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 运行模式 ──
    debug: bool = True
    log_level: str = "INFO"
    # 演示登录开关：仅本地联调开启，生产环境必须设为 false
    demo_login_enabled: bool = False

    # ── MySQL ──
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "zhiyi"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── JWT ──
    jwt_secret_key: str = "change-me-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 天
    # 字段级加密（Fernet base64 32 字节），未配置时从 JWT_SECRET_KEY 派生
    field_encrypt_key: str = ""

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"
    redis_session_ttl: int = 604800  # 7 天

    # ── CORS ──
    allowed_origins: str = '["http://localhost:5173","http://127.0.0.1:5173"]'

    # ── 高德地图 ──
    amap_js_api_key: str = ""
    amap_server_api_key: str = ""
    amap_base_url: str = "https://restapi.amap.com/v3"

    # ── 物流模拟 ──
    # 收货地址无法识别城市时使用的默认城市（changsha / shanghai）
    default_logistics_city: str = "changsha"

    # ── 通义千问 AI（DashScope，当前对话大模型：Qwen3.7-max）──
    qwen_api_key: str = ""
    qwen_chat_model: str = "qwen3.7-max"
    qwen_embedding_model: str = "text-embedding-v4"
    qwen_api_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ── SiliconFlow AI（千问 DashScope 免费额度耗尽时的备用 provider）──
    # 与千问同为 OpenAI 兼容格式；chat 使用 Qwen/Qwen3-8B，embedding 使用 BAAI/bge-m3
    siliconflow_api_key: str = ""
    siliconflow_api_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_chat_model: str = "Qwen/Qwen3-8B"
    siliconflow_embedding_model: str = "BAAI/bge-m3"

    # ── OpenCode Go（可选备用，当前对话大模型为 Qwen3.7-max）──
    # 官方地址：https://opencode.ai/go；API 地址：https://opencode.ai/zen/go/v1
    opencodego_api_key: str = ""
    opencodego_api_url: str = "https://opencode.ai/zen/go/v1"
    opencodego_chat_model: str = "deepseek-v4-flash"

    # ── ChromaDB ──
    chroma_host: str = "localhost"
    chroma_port: str = "8000"

    # ── Elasticsearch ──
    es_host: str = "http://localhost:9201"
    es_index_patients: str = "zhiyi_patients"

    # ── 应用元信息 ──
    api_title: str = "智医服务接口"
    api_version: str = "0.1.0"
    api_description: str = "基层医疗AI辅助诊疗平台 · FastAPI 后端服务"

    # ── 派生属性 ──

    @property
    def database_url(self) -> str:
        """构建 MySQL 异步连接字符串（aiomysql 驱动）。"""
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4&use_unicode=1"
        )

    @property
    def database_url_sync(self) -> str:
        """构建 MySQL 同步连接字符串（pymysql 驱动），用于 Alembic 迁移。"""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def cors_origins(self) -> list[str]:
        """解析 CORS 允许来源列表。"""
        try:
            origins: Any = json.loads(self.allowed_origins)
            if isinstance(origins, list):
                return origins
        except (json.JSONDecodeError, TypeError):
            pass
        return [origin.strip() for origin in self.allowed_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    """返回缓存的单例配置实例。"""
    settings = Settings()
    weak_secrets = {
        "change-me-to-a-random-secret-key",
        "change-me-to-a-random-secret-key-at-least-32-chars",
        "zhiyi-jwt-secret-key-change-in-production-2026",
    }
    if not settings.debug and (
        settings.jwt_secret_key in weak_secrets or len(settings.jwt_secret_key) < 32
    ):
        raise RuntimeError(
            "生产环境必须配置强度足够的 JWT_SECRET_KEY（至少 32 字符），"
            "禁止使用默认值"
        )
    return settings
