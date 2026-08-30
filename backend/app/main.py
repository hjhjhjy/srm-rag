"""FastAPI 入口：企业级装配（CORS 收紧 / 限流 / 结构化日志 / 请求ID / 鉴权 / 指标）。"""
from __future__ import annotations

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import admin, auth, chat, feedback, health, kb, metrics
from app.api.metrics import REQUEST_COUNT
from app.core.config import settings
from app.core.logging_config import configure_logging, new_request_id, request_context
from app.core.ratelimit import limiter, rate_limit_handler
from app.db import ensure_default_admin

configure_logging()
logger = logging.getLogger("srm.main")

DESCRIPTION = """
青山利康 **SRM 供应商智能问答助手** —— 面向供应商的企业级 RAG Agent。

- 基于《SRM 业务蓝图》的检索增强生成（RAG），答案带蓝图流程码（QS_SRM_*）出处引用
- 真 LLM 生成（DeepSeek），离线环境自动降级为检索增强直答
- 混合检索（向量 + BM25 + RRF）+ 意图/流程感知加权 + LLM 重排
- 鉴权：JWT（供应商/管理员 RBAC）+ 服务级 API Key；限流；结构化日志；Prometheus 指标
- 通过 iframe 嵌入 SRM 系统，零代码赋能供应商自助问答
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_default_admin()
    logger.info("SRM 助手启动完成", extra={"cors": allow_origins, "llm_provider": settings.llm_provider})
    yield


app = FastAPI(
    title="青山利康 SRM 供应商智能问答助手",
    version="1.0.0",
    description=DESCRIPTION,
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS：显式 origins；仅当非通配时才允许携带凭证，避免 credentials + * 冲突
if settings.cors_origins.strip() == "*":
    allow_origins = ["*"]
    allow_credentials = False
else:
    allow_origins = settings.cors_origin_list
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流（slowapi，按客户端 IP）
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    rid = new_request_id()
    with request_context(rid):
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
        return response


app.include_router(health.router)
app.include_router(chat.router)
app.include_router(feedback.router)
app.include_router(kb.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(metrics.router)


@app.get("/")
async def root():
    return {
        "service": "SRM Supplier Assistant",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
        "metrics": "/api/metrics",
        "login": "/api/auth/login",
    }
