from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str = ""
    message: str


class ChatSyncResponse(BaseModel):
    answer: str
    citations: list
    session_id: str
    message_id: int
    intent: str = "rag"


class FeedbackRequest(BaseModel):
    session_id: str
    message_id: int = 0
    rating: int = 0
    comment: str = ""
    correct_answer: str = ""


class KBRebuildRequest(BaseModel):
    force: bool = False
    module: str = ""
