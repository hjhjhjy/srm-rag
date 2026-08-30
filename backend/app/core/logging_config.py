"""结构化日志（structlog JSON）+ 请求 ID 上下文，便于企业级可观测与链路追踪。"""
from __future__ import annotations

import contextvars
import logging
import sys
import uuid
from typing import Optional

import structlog

REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)


def new_request_id() -> str:
    rid = uuid.uuid4().hex[:16]
    REQUEST_ID.set(rid)
    return rid


class request_context:
    """在请求生命周期内绑定 request_id 到日志上下文。"""

    def __init__(self, rid: Optional[str] = None):
        self.rid = rid or new_request_id()
        self._token = None

    def __enter__(self):
        self._token = structlog.contextvars.bind_contextvars(request_id=self.rid)
        return self

    def __exit__(self, *exc):
        structlog.contextvars.clear_contextvars()
        self._token = None
