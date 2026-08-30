"""Reranker：生产默认 BGE CrossEncoder（bge-reranker-v2-m3）精排，LLM 重排作为可选回退。

RAG 主流做法：先用 向量召回 + BM25 关键词召回 + RRF 融合 得到候选集，再用一个更小巧的
CrossEncoder 交叉编码器对「query↔chunk」逐对打分精排，相关性判断显著优于向量余弦。
LLM 重排（让大模型对候选排序）在 CrossEncoder 不可用时作为回退，适合低 QPS 内部系统。
"""
from __future__ import annotations

import logging
import re
from typing import List

from app.core.config import settings
from app.providers.vectorstore import SearchResult

logger = logging.getLogger("srm.reranker")


class Reranker:
    def rerank(self, query: str, results: List[SearchResult], top_n: int) -> List[SearchResult]:
        raise NotImplementedError


class IdentityReranker(Reranker):
    def rerank(self, query: str, results: List[SearchResult], top_n: int):
        return results[:top_n]


class BgeReranker(Reranker):
    def __init__(self, model_path: str):
        import os

        endpoint = settings.hf_endpoint.strip()
        if endpoint:
            os.environ.setdefault("HF_ENDPOINT", endpoint)
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_path)
        self.dim = None  # 重排模型无向量维度概念

    def rerank(self, query: str, results: List[SearchResult], top_n: int):
        if not results:
            return []
        pairs = [(query, r.document) for r in results]
        scores = self.model.predict(pairs)
        order = sorted(range(len(results)), key=lambda i: scores[i], reverse=True)
        return [results[i] for i in order[:top_n]]


class LLMReranker(Reranker):
    """用 LLM 充当相关性裁判：对 top-K 候选编号排序，返回重排结果。"""

    def __init__(self):
        from app.providers.llm import get_llm_provider

        self.llm = get_llm_provider()

    def rerank(self, query: str, results: List[SearchResult], top_n: int):
        if not results or not getattr(self.llm, "available", False):
            return results[:top_n]
        cand = results[:12]
        numbered = "\n".join(f"[{i + 1}] {r.document[:400]}" for i, r in enumerate(cand))
        messages = [
            {
                "role": "system",
                "content": "你是检索相关性裁判。根据用户问题，从候选片段中选出最相关的若干个，"
                "只输出编号（如 3,1,5），按相关性降序，最多 5 个，不要任何解释。",
            },
            {
                "role": "user",
                "content": f"用户问题：{query}\n\n候选片段：\n{numbered}\n\n最相关编号：",
            },
        ]
        try:
            out = self.llm.complete(messages)
            picks = [int(x) for x in re.findall(r"\d+", out) if 1 <= int(x) <= len(cand)]
            ordered: List[SearchResult] = []
            for i in picks:
                r = cand[i - 1]
                if r not in ordered:
                    ordered.append(r)
            for r in cand:  # 补齐未被选中的，保持覆盖
                if r not in ordered:
                    ordered.append(r)
            return ordered[:top_n]
        except Exception as e:  # noqa
            logger.warning("LLM 重排失败，回退融合排序: %s", e)
            return results[:top_n]


def get_reranker() -> Reranker:
    # 生产首选 BGE CrossEncoder 精排；其次 LLM 重排（大模型排序）作为回退；最后恒等。
    if settings.reranker_provider.lower() == "identity":
        return IdentityReranker()
    if settings.reranker_provider.lower() in ("bge", "auto"):
        try:
            return BgeReranker(settings.bge_reranker_path)
        except Exception as e:  # noqa
            logger.warning("BGE 重排不可用，尝试 LLM 重排: %s", e)
    if settings.reranker_provider.lower() in ("llm", "auto"):
        try:
            from app.providers.llm import get_llm_provider

            if getattr(get_llm_provider(), "available", False):
                return LLMReranker()
        except Exception as e:  # noqa
            logger.warning("LLM 重排不可用: %s", e)
    logger.warning("无可用重排器，回退融合排序（IdentityReranker）")
    return IdentityReranker()
