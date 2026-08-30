"""将解析后的 docx elements 切分为结构化 chunk（子流程 + 附录逐行 + 模块概述 + 前言）。

元数据携带 module / flow_code / flow_name / appendix_type / code，供检索过滤与引用溯源。
"""
from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Tuple

from app.core.normalize import normalize_cn

FLOW_RE = re.compile(r"QS_SRM_[A-Za-z0-9_]+")
SRM_RE = re.compile(r"SRM\d+", re.IGNORECASE)
MODULE_RE = re.compile(r"第[一二三四五六七八九十]+部分\s*([^（(]+)")
TOC_RE = re.compile(r"^[\u4e00-\u9fa5A-Za-z·、，。\s]+[0-9]+\s*$")  # 目录页码噪声

APPENDIX_MAP = {
    "接口清单": "interface",
    "消息推送": "message",
    "预警提示": "warning",
    "表单/文件": "form",
    "表单/文件清单": "form",
    "涉及报表": "report",
}

MODULE_CODE_BY_KEY = ["MD", "SM", "SC", "CM", "PO", "QM", "RM", "RD"]


def _clean_flow_code(s: str) -> str:
    m = FLOW_RE.search(s)
    return m.group(0).upper() if m else ""


def _is_appendix_heading(text: str) -> str:
    for k, v in APPENDIX_MAP.items():
        if text.startswith(k) or k in text:
            return v
    # 处理 "一、接口清单" 之类
    for k, v in APPENDIX_MAP.items():
        if k in text:
            return v
    return ""


def chunk(elements: List[Tuple[str, object]]) -> List[Dict]:
    chunks: List[Dict] = []
    module = ""
    module_intro: List[str] = []
    in_appendix = ""
    buffer: List[str] = []
    cur_meta: Dict = {}
    last_heading = ""
    appendix_counter = 0

    def flush_subflow():
        nonlocal buffer, cur_meta
        if buffer and cur_meta.get("flow_code"):
            text = normalize_cn("\n".join(buffer).strip())
            if text:
                chunks.append(
                    {
                        "chunk_id": f"subflow:{cur_meta['flow_code']}",
                        "text": text,
                        "metadata": {
                            "chunk_type": "subflow",
                            "module": module,
                            "flow_code": cur_meta["flow_code"],
                            "flow_name": cur_meta.get("flow_name", ""),
                        },
                    }
                )
        buffer = []
        cur_meta = {}

    def flush_intro():
        nonlocal module_intro
        txt = normalize_cn("\n".join(module_intro).strip())
        if txt:
            chunks.append(
                {
                    "chunk_id": f"module:{module or 'intro'}",
                    "text": txt,
                    "metadata": {
                        "chunk_type": "module_overview",
                        "module": module,
                        "flow_code": "",
                        "flow_name": module,
                    },
                }
            )
        module_intro = []

    for kind, payload in elements:
        if kind == "p":
            text = payload if isinstance(payload, str) else ""
            # 过滤目录页码噪声
            if TOC_RE.match(text.strip()) and len(text) < 40:
                continue
            mmod = MODULE_RE.search(text)
            if mmod and ("部分" in text):
                # 新模块：先收尾
                flush_subflow()
                flush_intro()
                module = mmod.group(1).strip()
                in_appendix = ""
                continue
            ap = _is_appendix_heading(text)
            if ap:
                flush_subflow()
                in_appendix = ap
                continue
            # 子流程开始？
            fc = _clean_flow_code(text)
            if fc:
                flush_subflow()
                flush_intro()
                in_appendix = ""
                name = ""
                nm = re.search(r"流程名称[:：]\s*([^|]+)", text)
                if nm:
                    name = nm.group(1).strip()
                else:
                    name = last_heading
                cur_meta = {"flow_code": fc, "flow_name": name}
                buffer = [text]
                continue
            # 普通段落
            if text.strip():
                if not re.match(r"^\s*[\u4e00-\u9fa5]{1,2}\s*$", text):  # 跳过单字噪声
                    last_heading = text if len(text) <= 30 else last_heading
                if in_appendix:
                    pass  # 附录标题下的说明性段落忽略，逐行靠表格
                else:
                    if cur_meta.get("flow_code"):
                        buffer.append(text)
                    else:
                        module_intro.append(text)
        elif kind == "table":
            rows = payload if isinstance(payload, list) else []
            joined = "\n".join(rows)
            # 检测「流程信息表」（含 流程编号：QS_SRM）=> 新子流程起点
            start_row = None
            for r in rows:
                if "流程编号" in r and FLOW_RE.search(r):
                    start_row = r
                    break
            if start_row is not None:
                flush_subflow()
                flush_intro()
                in_appendix = ""
                fc = FLOW_RE.search(start_row).group(0).upper()
                nm = re.search(r"流程名称[:：]\s*([^|]+)", start_row)
                name = nm.group(1).strip() if nm else last_heading
                cur_meta = {"flow_code": fc, "flow_name": name}
                buffer = ["[流程信息] " + start_row]
                continue
            if in_appendix:
                for idx, row in enumerate(rows):
                    fc = _clean_flow_code(row)
                    code = ""
                    cm = SRM_RE.search(row)
                    if cm:
                        code = cm.group(0).upper().replace(" ", "")
                    appendix_counter += 1
                    chunks.append(
                        {
                            "chunk_id": f"appendix:{in_appendix}:{code or appendix_counter}",
                            "text": normalize_cn(row),
                            "metadata": {
                                "chunk_type": "appendix",
                                "appendix_type": in_appendix,
                                "code": code,
                                "flow_code": fc,
                                "module": module,
                                "flow_name": "",
                            },
                        }
                    )
            else:
                # 子流程内的表格：整表作为文本块并入当前子流程
                if cur_meta.get("flow_code"):
                    buffer.append("[表格]\n" + joined)
                else:
                    module_intro.append("[表格]\n" + joined)

    flush_subflow()
    flush_intro()
    # 收尾：若仍处于附录且模块未结束，已逐行处理；无需额外 flush
    return chunks


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
