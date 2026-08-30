"""意图路由：RAG（默认）/ 闲聊 / 转人工。规则式，稳定可解释。"""
from __future__ import annotations

HUMAN_KEYWORDS = ["人工", "转人工", "投诉", "找人", "客服", "电话联系", "联系采购"]
GREETING_KEYWORDS = ["你好", "您好", "hi", "hello", "在吗", "谢谢", "感谢", "拜拜", "再见"]
GREETING_REPLY = (
    "您好，我是青山利康 SRM 供应商助手，可以帮您解答「如何注册入驻、资质准入、"
    "报价投标、合同与订单处理、对账结算、整改与报表查询」等系统使用问题。"
    "您可以直接问我，例如：「如何注册成为青山利康供应商？」"
)
HUMAN_REPLY = (
    "您的问题已记录。如需人工协助，请联系您的青山利康对接采购专员，"
    "或在 SRM 系统内提交工单（人工工单功能后续接入）。"
)


def classify(query: str) -> str:
    q = query.strip().lower()
    if any(k in q for k in HUMAN_KEYWORDS):
        return "human"
    if any(k in q for k in GREETING_KEYWORDS) and len(q) <= 20:
        return "chitchat"
    return "rag"


def route_reply(intent: str) -> str:
    if intent == "human":
        return HUMAN_REPLY
    if intent == "chitchat":
        return GREETING_REPLY
    return ""
