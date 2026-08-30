"""混合检索：向量召回 + BM25 关键词召回 + RRF 融合 +（可选）重排 + 元数据过滤。

默认 numpy 向量库自带 docs/ids/metadata，可直接构建 BM25 关键词召回；若使用 Chroma 且无
本地语料暴露，则退化为纯向量召回（仍可用）。流程码 QS_SRM_*/SRM### 自动转为元数据过滤。
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from app.core.normalize import normalize_cn
from app.providers.embedding import EmbeddingProvider
from app.providers.reranker import Reranker
from app.providers.vectorstore import SearchResult, VectorStore

logger = logging.getLogger("srm.retriever")

FLOW_RE = re.compile(r"QS_SRM_[A-Z0-9_]+", re.IGNORECASE)
SRM_RE = re.compile(r"SRM\s?\d+", re.IGNORECASE)

# 用户意图关键词 → 附录类型加权。蓝图附录按 form/message/warning/report/interface 分类，
# 当问题意图明确指向某类附录（如“提交材料”→form、“报表”→report）时，对命中附录显著提权，
# 解决纯向量/BM25 融合下“正文 subflow 压过关键附录”导致的召回不精准问题。
_INTENT_RULES: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"文件|材料|提交|资料|表单|协议|清单|上传|证件|证书|执照|身份证|营业执照|首营|填|必备|准备|报价|询价|竞价|招标|投标|整改|对账|发票|单据|退货|发货|收货|确认|订单|样"), "form", 0.18),
    (re.compile(r"通知|消息|短信|查收|提醒|告知|函|发送|收取|收到"), "message", 0.15),
    (re.compile(r"预警|到期|超时|逾期|临期|提前|过期"), "warning", 0.15),
    (re.compile(r"报表|统计|绩效|合格率|进度|查询|分析|看板|指标|明细|查看|哪里"), "report", 0.18),
    (re.compile(r"接口|对接|集成|同步|\bAPI\b|报文|SRM\d+"), "interface", 0.18),
]


def tokenize(text: str) -> List[str]:
    try:
        import jieba

        toks = [t for t in jieba.lcut(text) if t.strip()]
    except Exception:  # noqa
        toks = text.split()
    # 保留数字/字母连续 token（流程码、编号）
    toks += re.findall(r"[A-Za-z0-9_]+", text)
    return toks


class Retriever:
    def __init__(self, store: VectorStore, embedding: EmbeddingProvider, reranker: Reranker):
        self.store = store
        self.embedding = embedding
        self.reranker = reranker
        self._bm25 = None
        self._bm25_ids: List[str] = []
        self._bm25_docs: List[str] = []
        self._build_bm25()

    def _build_bm25(self):
        docs = getattr(self.store, "docs", None)
        ids = getattr(self.store, "ids", None)
        if not docs or not ids:
            logger.info("向量库未暴露本地语料，跳过 BM25 关键词召回")
            return
        try:
            from rank_bm25 import BM25Okapi

            self._bm25_docs = docs
            self._bm25_ids = ids
            self._bm25 = BM25Okapi([tokenize(d) for d in docs])
            logger.info("BM25 构建完成，文档数=%d", len(docs))
        except Exception as e:  # noqa
            logger.warning("BM25 构建失败: %s", e)

    def _detect_filter(self, query: str) -> dict:
        where = {}
        m = FLOW_RE.search(query)
        if m:
            where["flow_code"] = m.group(0).upper()
        return where

    def _bm25_search(self, query: str, top_k: int = 20) -> List[SearchResult]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        out = []
        for i in order:
            if scores[i] <= 0:
                continue
            out.append(
                SearchResult(self._bm25_ids[i], float(scores[i]), {}, self._bm25_docs[i])
            )
        return out

    def retrieve(self, query: str, top_k: int = 6, vector_top: int = 20) -> List[SearchResult]:
        query = normalize_cn(query)  # 统一异体/新旧字形（如 对帐→对账）
        where = self._detect_filter(query)
        q_emb = self.embedding.embed([query])[0]
        vec_res = self.store.query(q_emb, top_k=vector_top, where=where or None)
        bm25_res = self._bm25_search(query, top_k=vector_top)

        fused: dict[str, float] = {}
        # 向量按相似度排序
        for rank, r in enumerate(sorted(vec_res, key=lambda x: x.score, reverse=True)):
            fused[r.id] = fused.get(r.id, 0) + 1.0 / (rank + 60)
        for rank, r in enumerate(bm25_res):
            fused[r.id] = fused.get(r.id, 0) + 1.0 / (rank + 60)

        # 重建 SearchResult（优先向量元数据）
        by_id = {r.id: r for r in vec_res}
        by_id_bm = {r.id: r for r in bm25_res}
        # 子流程正文略加权，确保流程说明也能浮现
        for i in list(fused.keys()):
            if by_id.get(i) and by_id[i].metadata.get("chunk_type") == "subflow":
                fused[i] += 0.08

        # 附录类型意图加权：问题意图明确指向某类附录时，对已进入候选的该类附录提权
        for i in list(fused.keys()):
            sr = by_id.get(i) or by_id_bm.get(i)
            at = (sr.metadata.get("appendix_type") if sr else "") or ""
            if at:
                for pat, atype, boost in _INTENT_RULES:
                    if at == atype and pat.search(query):
                        fused[i] += boost
                        break

        # 流程感知附录提权：若某流程正文(subflow)已召回，则其「同流程」附录(form/message/
        # warning/report/interface)一并提权。这比“按类型全量注入”更精准——避免 75 个 form
        # 互相挤占，而让与问题流程真正相关的附录（如 RM_0003 对账单、SM_0003 样品确认单、
        # SC_0001 报价截止、QM_0001 整改预警）浮现。
        cand_flows = set()
        for i in list(fused.keys()):
            sr = by_id.get(i)
            if sr and sr.metadata.get("chunk_type") == "subflow":
                f = sr.metadata.get("flow_code")
                if f:
                    cand_flows.add(f)
        if cand_flows and hasattr(self.store, "meta"):
            for idx, m in enumerate(self.store.meta):
                if m.get("chunk_type") != "appendix":
                    continue
                if m.get("flow_code") in cand_flows:
                    cid = self.store.ids[idx]
                    if cid not in by_id and cid not in by_id_bm:
                        by_id_bm[cid] = SearchResult(
                            cid, 0.0, m, self.store.docs[idx]
                        )
                    fused[cid] = fused.get(cid, 0.0) + 0.22

        # 附录类型「轻量」预注入：对命意图的类型全量注入（boost 0.12），用于“有哪些报表 /
        # 提交哪些材料 / 订单预警”等需要把该类附录整体纳入排序的宽泛意图。boost(0.12) 低于
        # 流程感知(0.16)，因此与问题流程真正相关的附录仍优先；流程感知则保证具体流程的关键
        # 附录（如 RM_0003 对账单、SM_0003 样品确认单）不被大量同类附录挤占。
        _mw_boost = {atype: boost for _, atype, boost in _INTENT_RULES}
        mw_types = {atype for pat, atype, _ in _INTENT_RULES if pat.search(query)}
        if mw_types and hasattr(self.store, "meta"):
            for idx, m in enumerate(self.store.meta):
                if m.get("chunk_type") != "appendix":
                    continue
                at = m.get("appendix_type") or ""
                if at not in mw_types:
                    continue
                cid = self.store.ids[idx]
                if cid not in by_id and cid not in by_id_bm:
                    by_id_bm[cid] = SearchResult(cid, 0.0, m, self.store.docs[idx])
                fused[cid] = fused.get(cid, 0.0) + 0.12

        cand_ids = sorted(fused, key=lambda i: fused[i], reverse=True)[:40]
        cands: List[SearchResult] = []
        for i in cand_ids:
            r = by_id.get(i) or by_id_bm.get(i)
            if r:
                cands.append(r)

        if self.reranker and not isinstance(self.reranker, type(None)):
            try:
                cands = self.reranker.rerank(query, cands, top_k)
            except Exception as e:  # noqa
                logger.warning("重排失败，使用融合排序: %s", e)
                cands = cands[:top_k]
        else:
            cands = cands[:top_k]
        return cands[:top_k]
