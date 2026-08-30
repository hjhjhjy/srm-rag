"""Prometheus 指标端点（/api/metrics）：请求量、问答量、生成 token、检索命中、反馈。"""
from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

router = APIRouter(prefix="/api", tags=["metrics"])

REQUEST_COUNT = Counter("srm_http_requests_total", "HTTP 请求总数", ["method", "endpoint", "status"])
CHAT_REQUESTS = Counter("srm_chat_requests_total", "问答请求数", ["mode"])  # sync | stream
CHAT_CHARS = Counter("srm_chat_chars_total", "LLM 生成字符数（近似 token）")
RETRIEVAL_HITS = Counter("srm_retrieval_hits_total", "检索命中（>=1 结果）次数")
RETRIEVAL_MISS = Counter("srm_retrieval_miss_total", "检索未命中次数")
FEEDBACK_POS = Counter("srm_feedback_positive_total", "正向反馈数")
FEEDBACK_NEG = Counter("srm_feedback_negative_total", "负向反馈数")
CHAT_LATENCY = Histogram("srm_chat_latency_seconds", "问答响应耗时（秒）")


@router.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
