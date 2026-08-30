"""反馈服务：评分与纠错收集，并同步更新消息评分。"""
from __future__ import annotations

from app.db import Feedback, Message, get_session
from app.rag.memory import ConversationStore

store = ConversationStore()


def submit_feedback(
    session_id: str,
    message_id: int,
    rating: int,
    comment: str = "",
    correct_answer: str = "",
):
    if message_id:
        store.set_rating(message_id, rating)
    with get_session() as s:
        s.add(
            Feedback(
                session_id=session_id,
                message_id=message_id,
                rating=rating,
                comment=comment or "",
                correct_answer=correct_answer or "",
            )
        )
        s.commit()
    return True
