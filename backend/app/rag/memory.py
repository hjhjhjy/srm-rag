"""多轮对话记忆（SQLite），按 session_id 存取最近 N 轮。"""
from __future__ import annotations

import json
from typing import List, Optional

from app.db import Message, Session, get_session


class ConversationStore:
    def ensure_session(self, session_id: str, title: str = ""):
        with get_session() as s:
            existing = s.get(Session, session_id)
            if existing is None:
                s.add(Session(id=session_id, title=title))
                s.commit()

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: Optional[List[dict]] = None,
    ) -> int:
        self.ensure_session(session_id)
        with get_session() as s:
            m = Message(
                session_id=session_id,
                role=role,
                content=content,
                citations=json.dumps(citations or [], ensure_ascii=False),
            )
            s.add(m)
            s.commit()
            return m.id

    def get_history(self, session_id: str, limit: int = 6) -> List[dict]:
        with get_session() as s:
            rows = (
                s.query(Message)
                .filter(Message.session_id == session_id)
                .order_by(Message.id.desc())
                .limit(limit * 2)
                .all()
            )
            rows = list(reversed(rows))
            return [m.to_dict() for m in rows]

    def set_rating(self, message_id: int, rating: int):
        with get_session() as s:
            m = s.get(Message, message_id)
            if m:
                m.rating = rating
                s.commit()
