"""VectorStore：生产默认 pgvector（PostgreSQL 向量扩展），本地开发兜底用 numpy / chroma。

三种实现共用同一接口（add / query / count / delete_collection）：
- PgVectorStore  : 生产环境。向量存 PostgreSQL + pgvector 扩展，ANN 检索走 `<=>` 算子 +
                  IVFFLAT/HNSW 索引；同时把 docs/ids/meta 载入内存以支持混合检索中的 BM25 与
                  流程感知提权。最适合「已有 Postgres、需要持久化与事务」的场景。
- NumpyVectorStore: 零依赖本地索引（vectors.npy + meta.json），用于无 DB 的开发/测试。
- ChromaVectorStore: 轻量本地向量库，可选。

`VECTORSTORE_PROVIDER=auto` 时优先 pgvector（可达则用），否则 numpy。
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from app.core.config import settings

logger = logging.getLogger("srm.vectorstore")


class SearchResult:
    def __init__(self, id: str, score: float, metadata: dict, document: str):
        self.id = id
        self.score = score  # 相似度（越大越好）
        self.metadata = metadata
        self.document = document


class VectorStore:
    def add(self, ids, embeddings, metadatas, documents):
        raise NotImplementedError

    def query(self, embedding: List[float], top_k: int = 20, where: Optional[dict] = None) -> List[SearchResult]:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def delete_collection(self):
        raise NotImplementedError


class PgVectorStore(VectorStore):
    """pgvector 向量库（PostgreSQL 向量扩展）。生产默认。

    表结构 srm_kb(id text PK, embedding vector, metadata jsonb, document text)。
    稠密检索直接在 PG 内用余弦距离（embedding <=> :q）排序；BM25 与流程感知提权所需
    的 docs/ids/meta 在初始化与写入时同步到内存。
    """

    def __init__(self, dsn: str, table: str = "srm_kb", dim: int = 0):
        import psycopg2

        self.dsn = dsn
        self.table = table
        self.dim = dim
        self._conn = psycopg2.connect(dsn)
        self._ensure_table(dim)
        self.ids: List[str] = []
        self.meta: List[dict] = []
        self.docs: List[str] = []
        self._load_memory()

    def _ensure_table(self, dim: int):
        cur = self._conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        # 维度在首次建表时确定；dim=0 时退化为可容纳任意维度（用 text 占位，查询仍走 PG）
        if dim and dim > 0:
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} ("
                "  id text PRIMARY KEY,"
                f" embedding vector({dim}),"
                "  metadata jsonb DEFAULT '{{}}',"
                "  document text"
                ");"
            )
            # 生产用 IVFFLAT 索引（小数据量精确搜索亦可；列表数按经验取 sqrt(n) 量级）
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS {self.table}_emb_idx "
                f"ON {self.table} USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
            )
        else:
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} ("
                "  id text PRIMARY KEY,"
                "  embedding text,"
                "  metadata jsonb DEFAULT '{{}}',"
                "  document text"
                ");"
            )
        self._conn.commit()
        cur.close()

    def _load_memory(self):
        cur = self._conn.cursor()
        cur.execute(f"SELECT id, metadata, document FROM {self.table};")
        rows = cur.fetchall()
        cur.close()
        self.ids = [r[0] for r in rows]
        self.meta = [r[1] or {} for r in rows]
        self.docs = [r[2] or "" for r in rows]
        logger.info("pgvector 内存镜像已载入，条目=%d", len(self.ids))

    def add(self, ids, embeddings, metadatas, documents):
        cur = self._conn.cursor()
        data = [
            (
                i,
                np.asarray(e, dtype=np.float32).tolist(),
                json.dumps(m, ensure_ascii=False),
                d,
            )
            for i, e, m, d in zip(ids, embeddings, metadatas, documents)
        ]
        cur.execute(f"TRUNCATE TABLE {self.table};")
        from psycopg2.extras import execute_values

        execute_values(
            cur,
            f"INSERT INTO {self.table} (id, embedding, metadata, document) VALUES %s",
            data,
            template="(%s, %s::vector, %s::jsonb, %s)",
        )
        self._conn.commit()
        cur.close()
        self._load_memory()
        logger.info("pgvector 已写入 %d 条", len(ids))

    def count(self) -> int:
        cur = self._conn.cursor()
        cur.execute(f"SELECT count(*) FROM {self.table};")
        n = cur.fetchone()[0]
        cur.close()
        return n

    def delete_collection(self):
        cur = self._conn.cursor()
        cur.execute(f"TRUNCATE TABLE {self.table};")
        self._conn.commit()
        cur.close()
        self.ids = self.meta = self.docs = []

    def query(self, embedding: List[float], top_k: int = 20, where: Optional[dict] = None):
        q = np.asarray(embedding, dtype=np.float32).tolist()
        sql = (
            f"SELECT id, 1 - (embedding <=> %s::vector) AS sim, metadata, document "
            f"FROM {self.table}"
        )
        params: list = [q]
        if where:
            clauses = []
            for k, v in where.items():
                clauses.append(f"(metadata->>'{k}') = %s")
                params.append(v)
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY embedding <=> %s::vector LIMIT %s;"
        params.append(q)
        params.append(top_k)
        cur = self._conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return [
            SearchResult(r[0], float(r[1]), r[2] or {}, r[3] or "") for r in rows
        ]


class NumpyVectorStore(VectorStore):
    def __init__(self, index_dir: str):
        self.dir = Path(index_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.vecs: Optional[np.ndarray] = None
        self.ids: List[str] = []
        self.meta: List[dict] = []
        self.docs: List[str] = []
        self._load()

    def _path(self, name: str) -> Path:
        return self.dir / name

    def _load(self):
        try:
            if self._path("vectors.npy").exists():
                self.vecs = np.load(self._path("vectors.npy"))
            if self._path("meta.json").exists():
                data = json.loads(self._path("meta.json").read_text(encoding="utf-8"))
                self.ids = data["ids"]
                self.meta = data["meta"]
                self.docs = data["docs"]
            if self.vecs is not None and len(self.ids) != self.vecs.shape[0]:
                logger.warning("numpy 索引不一致，重建")
                self.vecs = None
                self.ids = self.meta = self.docs = []
        except Exception as e:  # noqa
            logger.warning("加载 numpy 索引失败: %s", e)

    def _save(self):
        if self.vecs is not None:
            np.save(self._path("vectors.npy"), self.vecs)
        self._path("meta.json").write_text(
            json.dumps(
                {"ids": self.ids, "meta": self.meta, "docs": self.docs},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def add(self, ids, embeddings, metadatas, documents):
        embs = [np.asarray(e, dtype=np.float32) for e in embeddings]
        merged: dict[str, tuple] = {}
        if self.vecs is not None and len(self.ids) == len(self.vecs):
            for k, v, m, d in zip(self.ids, self.vecs, self.meta, self.docs):
                merged[k] = (v, m, d)
        for k, v, m, d in zip(ids, embs, metadatas, documents):
            merged[k] = (v, m, d)
        self.ids = list(merged.keys())
        self.meta = [merged[k][1] for k in self.ids]
        self.docs = [merged[k][2] for k in self.ids]
        self.vecs = np.stack([merged[k][0] for k in self.ids]).astype(np.float32)
        self._save()

    def count(self) -> int:
        return len(self.ids)

    def delete_collection(self):
        for f in ("vectors.npy", "meta.json"):
            p = self._path(f)
            if p.exists():
                try:
                    p.unlink()
                except OSError as e:  # 沙箱 safe-delete 可能拒绝 unlink，忽略并在 _save 时覆盖
                    logger.warning("删除 %s 失败（沙箱限制），将直接覆盖: %s", p, e)
        self.vecs = None
        self.ids = self.meta = self.docs = []

    def query(self, embedding: List[float], top_k: int = 20, where: Optional[dict] = None):
        if self.vecs is None or len(self.ids) == 0:
            return []
        q = np.array(embedding, dtype=np.float32)
        norm = np.linalg.norm(q) or 1.0
        vn = self.vecs / (np.linalg.norm(self.vecs, axis=1, keepdims=True) + 1e-9)
        sims = vn @ (q / norm)
        if where:
            mask = np.ones(len(self.ids), dtype=bool)
            for k, v in where.items():
                for i, m in enumerate(self.meta):
                    if m.get(k) != v:
                        mask[i] = False
            sims = np.where(mask, sims, -1.0)
        order = np.argsort(-sims)[:top_k]
        out = []
        for i in order:
            if sims[i] <= -0.999:
                continue
            out.append(SearchResult(self.ids[i], float(sims[i]), self.meta[i], self.docs[i]))
        return out


class ChromaVectorStore(VectorStore):
    def __init__(self, persist_dir: str, dim: int):
        import chromadb

        self.client = chromadb.PersistentClient(path=persist_dir)
        self.coll = self.client.get_or_create_collection("srm_kb")
        self.dim = dim

    def add(self, ids, embeddings, metadatas, documents):
        self.coll.upsert(
            ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents
        )

    def count(self) -> int:
        return self.coll.count()

    def delete_collection(self):
        try:
            self.client.delete_collection("srm_kb")
        except Exception:  # noqa
            pass

    def query(self, embedding: List[float], top_k: int = 20, where: Optional[dict] = None):
        res = self.coll.query(
            query_embeddings=[embedding], n_results=top_k, where=where or None
        )
        out = []
        if not res["ids"]:
            return out
        for i, eid in enumerate(res["ids"][0]):
            out.append(
                SearchResult(
                    eid,
                    float(res["distances"][0][i]) if res.get("distances") else 0.0,
                    (res["metadatas"][0][i] or {}),
                    res["documents"][0][i] or "",
                )
            )
        return out


_STORE: Optional[VectorStore] = None


def get_vector_store(dim: int = 0) -> VectorStore:
    global _STORE
    if _STORE is not None:
        return _STORE
    provider = settings.vectorstore_provider.lower()
    # 生产默认 pgvector；auto 时可达则用，否则 numpy 兜底。
    if provider in ("pgvector", "auto"):
        if provider == "pgvector" or provider == "auto":
            try:
                _STORE = PgVectorStore(settings.pgvector_dsn, settings.pgvector_table, dim)
                logger.info("使用 pgvector 向量库（表=%s）", settings.pgvector_table)
                return _STORE
            except Exception as e:  # noqa
                logger.warning("pgvector 不可用，降级 numpy: %s", e)
    if provider in ("chroma", "auto"):
        try:
            _STORE = ChromaVectorStore(settings.chroma_persist_dir, dim)
            logger.info("使用 Chroma 向量库")
            return _STORE
        except Exception as e:  # noqa
            logger.warning("Chroma 不可用，降级 numpy: %s", e)
    _STORE = NumpyVectorStore(settings.numpy_index_dir)
    logger.info("使用内置 numpy 向量库")
    return _STORE
