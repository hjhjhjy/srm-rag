from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException

from app.core.config import settings
from app.core.security import Principal, require_roles
from knowledge.build_kb import build

router = APIRouter(prefix="/api", tags=["kb"])

STATUS_FILE = Path(settings.numpy_index_dir) / "kb_status.json"

_last = {"state": "idle", "progress": 0, "stats": {}, "updated_at": 0}


def _save_status(state: str, progress: int, stats: dict = None):
    _last.update({"state": state, "progress": progress, "updated_at": int(time.time())})
    if stats is not None:
        _last["stats"] = stats
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(_last, ensure_ascii=False), encoding="utf-8")


def _run_build(module: str):
    try:
        _save_status("running", 30)
        stats = build(settings.docx_path, module)
        _save_status("done", 100, stats)
    except Exception as e:  # noqa
        _save_status("error", 0, {"error": str(e)})


@router.post("/kb/rebuild")
async def kb_rebuild(
    req: dict = None,
    background: BackgroundTasks = None,
    _: Principal = Depends(require_roles("admin")),
    x_kb_key: str = Header(None, alias="X-KB-Key"),
):
    if settings.kb_rebuild_key and x_kb_key != settings.kb_rebuild_key:
        raise HTTPException(status_code=403, detail="KB 重建密钥错误")
    module = (req or {}).get("module", "") if req else ""
    _save_status("queued", 5)
    if background is not None:
        background.add_task(_run_build, module)
    else:
        _run_build(module)
    return {"job_id": "kb-build", "state": _last["state"]}


@router.get("/kb/status")
async def kb_status():
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa
            pass
    return _last
