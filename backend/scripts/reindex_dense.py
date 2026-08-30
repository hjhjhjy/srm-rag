"""用稠密向量（BGE）重建本地 numpy 索引：复用已解析的 meta.json 中的真实 chunk 文本。

适用场景：本地验证/演示。生产构建仍以 knowledge/build_kb.py（从 docx 全链路）为准。
用法：
  python scripts/reindex_dense.py            # 默认 BGE 稠密向量，写入 numpy_index
  python scripts/reindex_dense.py --backup   # 重建前先备份旧 TF-IDF 索引到 *_tfidf.bak
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("srm.reindex_dense")

BACKEND = Path(__file__).resolve().parents[1]
INDEX_DIR = BACKEND / "app" / "data" / "numpy_index"
META_PATH = INDEX_DIR / "meta.json"
VECTORS_PATH = INDEX_DIR / "vectors.npy"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup", action="store_true", help="重建前备份旧索引")
    args = ap.parse_args()

    import numpy as np
    from app.core.config import settings
    from app.providers.embedding import get_embedding_provider
    from app.providers.vectorstore import NumpyVectorStore

    if not META_PATH.exists():
        raise SystemExit(f"缺少 {META_PATH}，请先用 build_kb 生成知识库")

    data = json.loads(META_PATH.read_text(encoding="utf-8"))
    ids, metas, docs = data["ids"], data["meta"], data["docs"]
    logger.info("加载真实 chunk 文本 %d 条", len(docs))

    if args.backup and VECTORS_PATH.exists():
        bak = INDEX_DIR / "vectors_tfidf.bak.npy"
        shutil.copy(VECTORS_PATH, bak)
        logger.info("已备份旧 TF-IDF 向量 -> %s", bak)

    emb = get_embedding_provider()
    emb.ensure_ready(docs)
    logger.info("稠密向量化中（维度=%d）...", getattr(emb, "dim", 0))
    vectors = emb.embed(docs)

    store = NumpyVectorStore(str(INDEX_DIR))
    store.delete_collection()
    store.add(ids, vectors, metas, docs)
    logger.info("稠密向量索引重建完成：%d 条，维度=%d", store.count(), getattr(emb, "dim", 0))


if __name__ == "__main__":
    main()
