"""全局限流（slowapi）：按客户端 IP 限制请求频率，落实配置中的 rate_limit_per_min。"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.core.config import settings


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "anonymous"


limiter = Limiter(
    key_func=_client_key,
    default_limits=[f"{settings.rate_limit_per_min}/minute"],
)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "请求过于频繁，请稍后再试", "retry_after": getattr(exc, "retry_after", None)},
    )
