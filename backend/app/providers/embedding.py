"""Embedding Provider：生产默认稠密向量（BGE 本地模型 或 OpenAI 兼容 Embedding API）。

这是 RAG 主流做法——用神经网络把文本编码为语义向量，再做向量检索，语义召回远强于
TF-IDF 关键词向量。本项目三种实现：

1. BgeEmbedding         —— sentence-transformers 加载 BGE/M3E 本地模型（生产首选，离线可跑）。
2. ApiEmbedding         —— 调用 OpenAI 兼容 Embedding API（硅基流动/百炼/智谱/火山…），
                           无需本机算力，多在生产环境使用。
3. SklearnTfidf / NumpyTfidf —— TF-IDF 稀疏向量，仅作为「无 GPU/无模型仓库」时的本地
                           开发兜底，不参与生产路径（简历与文档中如实标注）。

模型下载走 `HF_ENDPOINT`（默认 https://hf-mirror.com 国内镜像），适配国内网络环境；
亦可设成本地路径或自建模型仓库。
"""
from __future__ import annotations

import logging
import math
import os
import pickle
import re
from pathlib import Path
from typing import List, Optional

import numpy as np

from app.core.config import settings

logger = logging.getLogger("srm.embedding")

CJK = re.compile(r"[\u4e00-\u9fff]")
TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def _jieba_tokenize(text: str):
    """模块级分词器（可被 pickle 引用），中文按词、其余按原样。"""
    import jieba

    return [t for t in jieba.lcut(text) if t.strip()]


def tokenize(text: str) -> List[str]:
    toks = TOKEN_RE.findall(text.lower())
    cjk = CJK.findall(text)
    toks.extend(cjk)
    toks.extend(cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1))
    return toks


class EmbeddingProvider:
    dim: int = 0

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def ensure_ready(self, corpus: List[str] | None = None):
        return


class BgeEmbedding(EmbeddingProvider):
    """本地稠密向量（BGE / M3E 等 sentence-transformers 模型）。生产首选。"""

    def __init__(self, model_path: str):
        # 国内网络：通过 HF_ENDPOINT 走镜像；如已配 MODELSCOPE 也可改走 modelscope。
        endpoint = settings.hf_endpoint.strip()
        if endpoint:
            os.environ.setdefault("HF_ENDPOINT", endpoint)
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_path)
        self.dim = self.model.get_sentence_embedding_dimension()
        logger.info("BGE 稠密向量已加载，模型=%s 维度=%d", model_path, self.dim)

    def embed(self, texts: List[str]) -> List[List[float]]:
        vecs = self.model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vecs, dtype=np.float32).tolist()


class ApiEmbedding(EmbeddingProvider):
    """OpenAI 兼容 Embedding API（硅基流动/百炼/智谱/火山…）。生产常用，无需本机算力。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        import httpx

        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        self._model = model
        self.dim = self._probe_dim()
        logger.info("Embedding API 已就绪，base=%s 模型=%s 维度=%d", base_url, model, self.dim)

    def _probe_dim(self) -> int:
        try:
            v = self.embed(["探测维度"])[0]
            return len(v)
        except Exception as e:  # noqa
            logger.warning("Embedding API 维度探测失败: %s", e)
            return 0

    def embed(self, texts: List[str]) -> List[List[float]]:
        resp = self._client.post(
            "/embeddings", json={"model": self._model, "input": texts}
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        # API 返回顺序可能与输入不一致，按 index 重排
        data.sort(key=lambda d: d["index"])
        return [d["embedding"] for d in data]


class _BaseTfidf(EmbeddingProvider):
    """TF-IDF 稀疏向量，仅本地开发兜底，不参与生产路径。"""

    def __init__(self, max_features: int = 20000):
        self.max_features = max_features
        self._path = Path(settings.numpy_index_dir) / "tfidf.pkl"
        self._vocab = None
        self._idf = None

    def _load(self):
        if self._vocab is not None:
            return
        if self._path.exists():
            try:
                with open(self._path, "rb") as f:
                    obj = pickle.load(f)
                self._vocab, self._idf = obj["vocab"], obj["idf"]
                self.dim = len(self._vocab)
                logger.info("TF-IDF 已加载，维度=%d", self.dim)
            except Exception as e:  # noqa
                logger.warning("加载 TF-IDF 失败: %s", e)

    def ensure_ready(self, corpus: List[str] | None = None):
        self._load()
        if self._vocab is None and corpus:
            self._fit(corpus)
            self._save()

    def _save(self):
        Path(settings.numpy_index_dir).mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            pickle.dump({"vocab": self._vocab, "idf": self._idf}, f)

    def _fit(self, corpus: List[str]):
        raise NotImplementedError

    def _transform(self, texts: List[str]) -> np.ndarray:
        raise NotImplementedError

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._load()
        if self._vocab is None:
            rng = np.random.default_rng(0)
            return rng.random((len(texts), self.max_features)).tolist()
        return self._transform(texts).astype(np.float32).tolist()


class SklearnTfidf(_BaseTfidf):
    def _fit(self, corpus: List[str]):
        from sklearn.feature_extraction.text import TfidfVectorizer

        try:
            import jieba  # noqa: F401

            tok_kwargs = {"tokenizer": _jieba_tokenize, "token_pattern": None}
        except Exception:  # noqa
            tok_kwargs = {"analyzer": "char_wb", "ngram_range": (1, 3)}
        vec = TfidfVectorizer(
            max_features=self.max_features, sublinear_tf=True, ngram_range=(1, 2),
            **tok_kwargs,
        )
        vec.fit(corpus)
        self._vec = vec
        self._vocab = {t: i for i, t in enumerate(vec.get_feature_names_out())}
        self._idf = vec.idf_
        self.dim = len(self._vocab)
        logger.info("sklearn TF-IDF fit 完成，维度=%d", self.dim)

    def _save(self):
        Path(settings.numpy_index_dir).mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            pickle.dump(
                {"vec": self._vec, "vocab": self._vocab, "idf": self._idf}, f
            )

    def _load(self):
        if getattr(self, "_vec", None) is not None:
            return
        if self._path.exists():
            try:
                with open(self._path, "rb") as f:
                    obj = pickle.load(f)
                self._vec = obj.get("vec")
                self._vocab = obj["vocab"]
                self._idf = obj["idf"]
                self.dim = len(self._vocab)
                logger.info("TF-IDF 已加载，维度=%d", self.dim)
            except Exception as e:  # noqa
                logger.warning("加载 TF-IDF 失败（将重新 fit）: %s", e)
                self._vec = None

    def _transform(self, texts: List[str]) -> np.ndarray:
        if getattr(self, "_vec", None) is None:
            raise RuntimeError("TF-IDF 向量器未初始化，请先 ensure_ready")
        return self._vec.transform(texts).toarray()


class NumpyTfidf(_BaseTfidf):
    def _fit(self, corpus: List[str]):
        from collections import Counter

        df = Counter()
        docs_tokens = []
        for doc in corpus:
            toks = tokenize(doc)
            docs_tokens.append(toks)
            for t in set(toks):
                df[t] += 1
        vocab_list = [t for t, _ in df.most_common(self.max_features)]
        vocab = {t: i for i, t in enumerate(vocab_list)}
        n = len(corpus)
        idf = np.array(
            [math.log((n + 1) / (df[t] + 1)) + 1.0 for t in vocab_list], dtype=np.float32
        )
        self._vocab, self._idf, self.dim = vocab, idf, len(vocab)
        logger.info("numpy TF-IDF fit 完成，维度=%d", self.dim)

    def _transform(self, texts: List[str]) -> np.ndarray:
        V = self.dim
        out = np.zeros((len(texts), V), dtype=np.float32)
        idf = self._idf
        for i, doc in enumerate(texts):
            counts = {}
            toks = tokenize(doc)
            for t in toks:
                if t in self._vocab:
                    counts[t] = counts.get(t, 0) + 1
            if not counts:
                continue
            for t, c in counts.items():
                j = self._vocab[t]
                out[i, j] = (1.0 + math.log(c)) * idf[j]
        norm = np.linalg.norm(out, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
        return out / norm


def get_embedding_provider() -> EmbeddingProvider:
    """按配置返回嵌入提供方。生产默认 bge；api 走 Embedding API；tfidf 仅本地兜底。

    返回顺序：bge → api → tfidf（dev 兜底）。任一步失败均记录告警并降级，不中断启动。
    """
    provider = settings.embedding_provider.lower()
    # 1) 本地 BGE 稠密向量
    if provider in ("bge", "auto"):
        try:
            return BgeEmbedding(settings.bge_model_path)
        except Exception as e:  # noqa
            logger.warning("BGE 稠密向量不可用，尝试下一方案: %s", e)
    # 2) OpenAI 兼容 Embedding API
    if provider in ("api", "auto"):
        if settings.embedding_api_key and settings.embedding_api_base_url:
            try:
                return ApiEmbedding(
                    settings.embedding_api_base_url,
                    settings.embedding_api_key,
                    settings.embedding_api_model,
                )
            except Exception as e:  # noqa
                logger.warning("Embedding API 不可用，尝试下一方案: %s", e)
        else:
            logger.info("未配置 Embedding API Key/Base，跳过 api 方案")
    # 3) TF-IDF 稀疏向量（本地开发兜底，不用于生产）
    try:
        import sklearn  # noqa

        return SklearnTfidf(settings.tfidf_max_features)
    except Exception as e:  # noqa
        logger.warning("sklearn 不可用，使用纯 numpy TF-IDF: %s", e)
        return NumpyTfidf(settings.tfidf_max_features)
