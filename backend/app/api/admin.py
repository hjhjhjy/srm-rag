"""管理后台接口（仅 admin 角色可访问）：运营统计、知识库概览。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from prometheus_client import REGISTRY
from sqlalchemy import func

from app.core.security import Principal, require_roles
from app.db import Feedback, Message, User, get_session
from app.providers.vectorstore import get_vector_store

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _metric_value(name: str, labels: dict | None = None) -> float:
    for family in REGISTRY.collect():
        if family.name == name:
            for sample in family.samples:
                if labels is None or sample.labels == labels:
                    return float(sample.value)
    return 0.0


@router.get("/stats")
def admin_stats(_: Principal = Depends(require_roles("admin"))):
    with get_session() as s:
        total_sessions = s.query(func.count(Message.session_id.distinct())).scalar() or 0
        total_messages = s.query(func.count(Message.id)).scalar() or 0
        assistant_messages = (
            s.query(func.count(Message.id)).filter(Message.role == "assistant").scalar() or 0
        )
        pos = s.query(func.count(Feedback.id)).filter(Feedback.rating == 1).scalar() or 0
        neg = s.query(func.count(Feedback.id)).filter(Feedback.rating == -1).scalar() or 0
        suppliers = s.query(func.count(User.id)).filter(User.role == "supplier").scalar() or 0

    store = get_vector_store()
    kb_count = store.count() if store else 0
    retrieval_hits = _metric_value("srm_retrieval_hits_total")
    retrieval_miss = _metric_value("srm_retrieval_miss_total")
    chat_sync = _metric_value("srm_chat_requests_total", {"mode": "sync"})
    chat_stream = _metric_value("srm_chat_requests_total", {"mode": "stream"})

    return {
        "conversations": int(total_sessions),
        "messages": int(total_messages),
        "assistant_messages": int(assistant_messages),
        "feedback_positive": int(pos),
        "feedback_negative": int(neg),
        "supplier_accounts": int(suppliers),
        "kb_chunks": int(kb_count),
        "retrieval_hits": int(retrieval_hits),
        "retrieval_miss": int(retrieval_miss),
        "chat_sync": int(chat_sync),
        "chat_stream": int(chat_stream),
    }
