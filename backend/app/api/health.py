from __future__ import annotations

import time

from fastapi import APIRouter

from app.core.config import settings
from app.services.chat import chat_service

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    llm_ok = "ok" if getattr(chat_service.llm, "available", False) else "fallback(no-key)"
    kb_ok = "ok" if (chat_service.retriever is not None) else "empty"
    return {
        "status": "ok",
        "llm": llm_ok,
        "vectorstore": kb_ok,
        "kb_version": settings.kb_version,
        "ts": int(time.time()),
    }
