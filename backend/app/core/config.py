"""全局配置（pydantic-settings 读取 .env）。所有配置均有默认值，缺失即进入降级模式。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根：backend/ 的上一级
ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    hunyuan_api_key: str = ""
    qwen_api_key: str = ""
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1200

    # Embedding：生产默认走稠密向量（BGE / M3E 类本地模型或 OpenAI 兼容 Embedding API）。
    # 可选值：bge（本地 sentence-transformers 模型，最先尝试）| api（OpenAI 兼容 Embedding API）
    #        | tfidf（TF-IDF 稀疏向量，仅限无 GPU/无模型仓库的本地开发兜底，不用于生产）
    embedding_provider: str = "bge"
    # 本地稠密向量模型（HuggingFace 仓库名或本地路径）。
    # 生产常用：BAAI/bge-large-zh-v1.5（1024维）、BAAI/bge-m3（多语言/多向量）、BAAI/bge-small-zh-v1.5（512维，轻量）。
    # 本地已内置 bge-small-zh-v1.5 权重（app/data/models/bge-small-zh-v1.5），离线优先加载，避免运行时联网拉取。
    bge_model_path: str = str(BACKEND / "app" / "data" / "models" / "bge-small-zh-v1.5")
    # OpenAI 兼容 Embedding API（当 embedding_provider=api 时启用）。
    # 国内常用：硅基流动 BAAI/bge-m3、阿里百炼 text-embedding-v3/v4、智谱 embedding-3、火山 doubao-embedding。
    embedding_api_base_url: str = ""
    embedding_api_key: str = ""
    embedding_api_model: str = "BAAI/bge-m3"
    # HuggingFace 镜像端点（国内生产环境拉取模型用，如 hf-mirror.com 或自建模型仓库）。
    hf_endpoint: str = "https://hf-mirror.com"
    tfidf_max_features: int = 20000

    # Reranker：生产默认 bge-reranker-v2-m3（CrossEncoder 精排）。
    reranker_provider: str = "bge"
    bge_reranker_path: str = "BAAI/bge-reranker-v2-m3"
    rerank_top_n: int = 8

    # Vector store：生产默认 pgvector（PostgreSQL 向量扩展）；本地开发可切 numpy / chroma。
    vectorstore_provider: str = "pgvector"
    pgvector_dsn: str = "postgresql://srm:srm_pass@localhost:5432/srm"
    pgvector_table: str = "srm_kb"
    chroma_persist_dir: str = str(BACKEND / "app" / "data" / "chroma")
    numpy_index_dir: str = str(BACKEND / "app" / "data" / "numpy_index")

    @field_validator("chroma_persist_dir", "numpy_index_dir", mode="before")
    @classmethod
    def _resolve_data_dir(cls, v):
        # .env 可能写相对路径（如 backend/app/data/...），统一相对 ROOT 解析为绝对路径，
        # 避免依赖进程 cwd 导致路径错乱（历史遗留会出现 backend/backend/... 重复段）。
        p = Path(v)
        if not p.is_absolute():
            return str((ROOT / p).resolve())
        return str(p)

    # Knowledge
    docx_path: str = str(
        Path("D:/work/青山利康/蓝图或功能开发需求文档/青山利康SRM项目-业务蓝图V5.0.docx")
    )
    kb_version: str = "V5.0"

    # Service
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"
    iframe_allowed_origins: str = "*"
    kb_rebuild_key: str = ""
    rate_limit_per_min: int = 60

    # 安全 / 鉴权（企业级）
    jwt_secret: str = ""  # 生产必须设置强随机值；为空时生成开发用密钥并告警
    jwt_algorithm: str = "HS256"
    access_token_expire_min: int = 1440  # 24h
    api_keys: str = "srm_dev_demo_key"  # 逗号分隔的服务级 API Key（供 SRM 后端 / iframe 调用）；生产务必改为强随机值并通过环境变量覆盖
    admin_username: str = "admin"
    admin_password: str = "Admin@123"  # 首次启动创建，生产请改
    metrics_enabled: bool = True

    # SQLite
    sqlite_path: str = str(BACKEND / "app" / "data" / "srm_agent.db")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def iframe_allowed_list(self) -> list[str]:
        return [o.strip() for o in self.iframe_allowed_origins.split(",") if o.strip()]


settings = Settings()
