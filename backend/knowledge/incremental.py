"""增量 Manifest：记录 chunk_id ↔ content_hash，支撑重建时的变更统计与去重。

注：因 TF-IDF 向量化器需在全语料上 fit 以保证维度一致，v1 每次构建对全量语料重新向量化并
upsert（store 按 id 覆盖）；Manifest 用于变更统计与状态展示。
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from app.core.config import settings


class Manifest:
    def __init__(self, path: str = None):
        self.path = path or str(Path(settings.numpy_index_dir) / "manifest.db")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS chunks (chunk_id TEXT PRIMARY KEY, hash TEXT, updated_at TEXT)"
        )
        self.conn.commit()

    def get_all(self) -> dict:
        cur = self.conn.execute("SELECT chunk_id, hash FROM chunks")
        return {r[0]: r[1] for r in cur.fetchall()}

    def upsert(self, items: list):
        now = dt.datetime.utcnow().isoformat()
        self.conn.executemany(
            "INSERT OR REPLACE INTO chunks (chunk_id, hash, updated_at) VALUES (?,?,?)",
            [(i[0], i[1], now) for i in items],
        )
        self.conn.commit()

    def delete_missing(self, known_ids: set):
        all_ids = [r[0] for r in self.conn.execute("SELECT chunk_id FROM chunks").fetchall()]
        missing = [i for i in all_ids if i not in known_ids]
        if missing:
            self.conn.executemany(
                "DELETE FROM chunks WHERE chunk_id=?", [(i,) for i in missing]
            )
            self.conn.commit()
        return missing
