"""对话接口：SSE 流式（主）、同步（测试/降级）、快捷问题。需认证。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.metrics import CHAT_REQUESTS
from app.core.security import Principal, get_current_principal
from app.schemas import ChatRequest, ChatSyncResponse
from app.services.chat import chat_service

router = APIRouter(prefix="/api", tags=["chat"])


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
):
    CHAT_REQUESTS.labels("stream").inc()
    session_id = req.session_id or chat_service.new_session()

    async def event_gen():
        yield _sse({"type": "session", "session_id": session_id})
        async for ev in chat_service.stream_answer(session_id, req.message):
            yield _sse(ev)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/sync", response_model=ChatSyncResponse)
async def chat_sync(
    req: ChatRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
):
    CHAT_REQUESTS.labels("sync").inc()
    session_id = req.session_id or chat_service.new_session()
    answer = ""
    citations = []
    intent = "rag"
    msg_id = 0
    async for ev in chat_service.stream_answer(session_id, req.message):
        if ev["type"] == "delta":
            answer += ev["content"]
        elif ev["type"] == "citation":
            citations = ev["items"]
        elif ev["type"] == "done":
            msg_id = ev.get("message_id", 0)
            intent = ev.get("intent", "rag")
    return ChatSyncResponse(
        answer=answer, citations=citations, session_id=session_id, message_id=msg_id, intent=intent
    )


@router.get("/suggestions")
async def suggestions():
    return {"items": chat_service.get_suggestions()}
