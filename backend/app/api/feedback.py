from __future__ import annotations

from fastapi import APIRouter

from app.schemas import FeedbackRequest
from app.services.feedback import submit_feedback

router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/feedback")
async def feedback(req: FeedbackRequest):
    submit_feedback(
        req.session_id,
        req.message_id,
        req.rating,
        req.comment,
        req.correct_answer,
    )
    return {"ok": True}
