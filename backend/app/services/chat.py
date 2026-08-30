"""ChatService：问答编排核心。

流程：意图路由 →（RAG）混合检索 → 拼装提示词 → LLM 流式生成（无 Key 降级为检索增强直答）
→ 统一输出引用 → 持久化多轮对话。
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid

from app.core.normalize import normalize_cn
from typing import AsyncIterator, Dict, List, Optional

from app.core.config import settings
from app.providers.embedding import get_embedding_provider
from app.providers.llm import get_llm_provider
from app.providers.reranker import get_reranker
from app.providers.vectorstore import get_vector_store
from app.api.metrics import (
    CHAT_CHARS,
    CHAT_LATENCY,
    CHAT_REQUESTS,
    RETRIEVAL_HITS,
    RETRIEVAL_MISS,
)
from app.rag.memory import ConversationStore
from app.rag.prompt import build_messages, format_context
from app.rag.retriever import Retriever
from app.rag.router import classify, route_reply

logger = logging.getLogger("srm.chat")

SUGGESTIONS = [
    "如何注册成为青山利康供应商？",
    "资质准入需要准备哪些材料（阳光协议/保密协议/质量协议）？",
    "收到整改通知（QS_SRM_QM_0001）怎么办？",
    "资质快到期了（提前 60 天预警）怎么处理？",
    "收到询价/竞价/招标单，如何报价？",
    "采购订单怎么接收、确认、发货、退货？",
    "如何发起对账、上传发票？",
    "我有哪些报表可查（绩效/订单执行/合格率/付款进度）？",
]


class ChatService:
    def __init__(self):
        self._retriever: Optional[Retriever] = None
        self._llm = None
        self.store = ConversationStore()

    @property
    def retriever(self) -> Optional[Retriever]:
        if self._retriever is None:
            try:
                embedding = get_embedding_provider()
                store = get_vector_store(dim=getattr(embedding, "dim", 0))
                reranker = get_reranker()
                self._retriever = Retriever(store, embedding, reranker)
            except Exception as e:  # noqa
                logger.error("检索器初始化失败: %s", e)
                self._retriever = None
        return self._retriever

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_provider()
        return self._llm

    def new_session(self) -> str:
        return uuid.uuid4().hex

    def get_suggestions(self) -> List[dict]:
        return [{"q": q} for q in SUGGESTIONS]

    def _build_citations(self, results: List) -> List[dict]:
        cites = []
        for r in results:
            md = r.metadata or {}
            cites.append(
                {
                    "flow_code": md.get("flow_code") or "",
                    "flow_name": md.get("flow_name") or "",
                    "appendix_type": md.get("appendix_type") or "",
                    "code": md.get("code") or "",
                    "module": md.get("module") or "",
                    "source_snippet": (r.document or "")[:220],
                }
            )
        return cites

    async def rewrite_query(self, message: str) -> str:
        """HyDE / 查询改写：用词向量召回时，把口语化问题改写成更利于检索的规范表述。

        仅在有 LLM 时启用；失败则回退原问题。
        """
        if not getattr(self.llm, "available", False):
            return message
        if len(message) > 40:  # 已较具体，跳过改写避免漂移
            return message
        prompt = [
            {
                "role": "system",
                "content": "你是 SRM 供应商系统的检索改写器。把用户的口语化问题改写成"
                "一句便于在《业务蓝图》中检索的规范表述，保留关键词（如流程码、表单名、"
                "资质/对账/订单等），只输出改写后的一句话，不要解释。",
            },
            {"role": "user", "content": f"问题：{message}\n改写："},
        ]
        try:
            out = (await self.llm.acomplete(prompt)).strip()
            return out or message
        except Exception:  # noqa
            return message

    def _fallback_answer(self, results: List, question: str) -> str:
        question = normalize_cn(question)  # 统一异体/新旧字形，保证关键词补摘可命中
        if not results:
            return (
                "当前帮助文档（业务蓝图）中未检索到与您问题直接相关的内容。"
                "建议您联系青山利康对接采购专员，或在 SRM 系统内转人工处理。"
            )
        # 提取问题关键词（用于把深藏在长文片段中的关键信息一并截取出来）
        try:
            import jieba

            q_tokens = {t for t in jieba.lcut(question) if len(t) >= 2}
        except Exception:  # noqa
            q_tokens = {t for t in re.findall(r"[一-龥]{2,}", question)}
        q_tokens |= set(re.findall(r"[A-Za-z0-9_]{2,}", question))

        lines = ["根据《青山利康 SRM 业务蓝图》，为您整理以下相关信息：\n"]
        for i, r in enumerate(results, 1):
            md = r.metadata or {}
            label = md.get("flow_code") or md.get("code") or md.get("flow_name") or f"片段{i}"
            name = md.get("flow_name") or ""
            header = f"【{label}】{name}".rstrip()
            doc = (r.document or "").strip().replace("\n", " ")
            # 头部摘要
            head = doc[:500]
            # 关键词感知补摘：若问题关键词出现在文档更靠后位置，补充其上下文
            extra = ""
            for tok in q_tokens:
                pos = doc.find(tok)
                if pos > 500:
                    start = max(0, pos - 40)
                    end = min(len(doc), pos + 60)
                    extra = " …" + doc[start:end] + "…"
                    break
            snippet = (head + extra).strip()
            snippet = snippet[:700] + ("…" if len(snippet) > 700 else "")
            lines.append(f"{i}. {header}\n   {snippet}\n")
        lines.append(
            "\n（以上为蓝图原文片段的检索直答；配置 DeepSeek API Key 后可获得更自然的归纳回答。）"
        )
        return "\n".join(lines)

    async def stream_answer(self, session_id: str, message: str) -> AsyncIterator[dict]:
        self.store.ensure_session(session_id)
        self.store.add_message(session_id, "user", message)
        t0 = time.time()
        intent = classify(message)

        if intent in ("human", "chitchat"):
            reply = route_reply(intent)
            # 分片流式输出
            for i in range(0, len(reply), 40):
                yield {"type": "delta", "content": reply[i : i + 40]}
            self.store.add_message(session_id, "assistant", reply, citations=[])
            yield {"type": "done", "message_id": 0, "intent": intent}
            return

        # RAG
        results = []
        if self.retriever is not None:
            try:
                q = await self.rewrite_query(message)
                results = self.retriever.retrieve(q, top_k=settings.rerank_top_n)
            except Exception as e:  # noqa
                logger.error("检索失败: %s", e)
        if results:
            RETRIEVAL_HITS.inc()
        else:
            RETRIEVAL_MISS.inc()
        citations = self._build_citations(results)
        confidence = round(max((getattr(r, "score", 0.0) or 0.0) for r in results), 3) if results else 0.0
        yield {"type": "citation", "items": citations, "confidence": confidence}

        context = format_context(results)
        history = self.store.get_history(session_id)
        messages = build_messages(context, message, history)

        answer = ""
        if self.llm.available:
            try:
                async for tok in self.llm.astream(messages):
                    if tok:
                        answer += tok
                        yield {"type": "delta", "content": tok}
            except Exception as e:  # noqa
                logger.error("LLM 流式失败，降级直答: %s", e)
                answer = self._fallback_answer(results, message)
                for i in range(0, len(answer), 40):
                    yield {"type": "delta", "content": answer[i : i + 40]}
        else:
            answer = self._fallback_answer(results, message)
            for i in range(0, len(answer), 40):
                yield {"type": "delta", "content": answer[i : i + 40]}

        CHAT_CHARS.inc(len(answer))
        CHAT_LATENCY.observe(max(0.0, time.time() - t0))
        msg_id = self.store.add_message(session_id, "assistant", answer, citations=citations)
        yield {
            "type": "done",
            "message_id": msg_id,
            "intent": "rag",
            "confidence": confidence,
            "model": getattr(self.llm, "model", "fallback"),
        }


chat_service = ChatService()
