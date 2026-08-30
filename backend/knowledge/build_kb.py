"""知识库构建入口：docx → 解析 → 分块 → 向量化 → 写入向量库 + 更新 Manifest。

可作为脚本运行：python build_kb.py [--module SM] [--force]
或由 /api/kb/rebuild 调用。
"""
from __future__ import annotations

import argparse
import logging
import time
from collections import Counter

from app.core.config import settings
from knowledge.chunking import chunk, content_hash
from knowledge.incremental import Manifest
from knowledge.parse_docx import parse_docx
from app.providers.embedding import get_embedding_provider
from app.providers.vectorstore import get_vector_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("srm.build_kb")


def build(docx_path: str = None, module_filter: str = "") -> dict:
    docx_path = docx_path or settings.docx_path
    t0 = time.time()
    logger.info("解析 docx: %s", docx_path)
    elements = parse_docx(docx_path)
    logger.info("解析元素数: %d", len(elements))

    chunks = chunk(elements)
    logger.info("切分 chunk 数: %d", len(chunks))

    if module_filter:
        chunks = [c for c in chunks if module_filter in (c["metadata"].get("module", ""))]

    corpus = [c["text"] for c in chunks]
    hashes = [content_hash(t) for t in corpus]

    emb = get_embedding_provider()
    emb.ensure_ready(corpus)
    logger.info("向量化中（维度=%d）...", getattr(emb, "dim", 0))
    vectors = emb.embed(corpus)

    store = get_vector_store(dim=getattr(emb, "dim", 0))
    store.delete_collection()
    ids = [c["chunk_id"] for c in chunks]
    metas = [c["metadata"] for c in chunks]
    store.add(ids, vectors, metas, corpus)

    manifest = Manifest()
    prev = manifest.get_all()
    items = list(zip(ids, hashes))
    manifest.upsert(items)
    manifest.delete_missing(set(ids))

    changed = sum(1 for i, h in items if prev.get(i) != h)
    by_type = Counter(c["metadata"].get("chunk_type") for c in chunks)
    by_module = Counter(c["metadata"].get("module") for c in chunks)

    stats = {
        "total_chunks": len(chunks),
        "changed": changed,
        "store_count": store.count(),
        "by_type": dict(by_type),
        "by_module": dict(by_module),
        "embedding": type(emb).__name__,
        "vectorstore": type(store).__name__,
        "elapsed_sec": round(time.time() - t0, 2),
    }
    logger.info("构建完成: %s", stats)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", default=None)
    ap.add_argument("--module", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    stats = build(args.docx, args.module)
    print(stats)


if __name__ == "__main__":
    main()
