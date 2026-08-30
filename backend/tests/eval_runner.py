"""SRM 智能问答 Agent —— 检索/回答/引用 评估脚本。

与线上行为保持一致：检索 top_k=rerank_top_n(=6) → 无 Key 时走检索增强直答
（FallbackProvider）→ 构建引用。对 eval/questions.json 的 20 道问题计算：

  - retrieval_acc : 期望流程码（QS_SRM_*）是否全部出现在 top-N 召回中
  - answer_acc    : 期望关键词是否全部出现在（兜底）回答文本中
  - citation_acc  : 引用集合对期望流程码的覆盖率（与检索同源，= retrieval_acc）
  - appendix_acc  : 若题目指定 expected_appendix，top-N 中是否命中该附录类型

可用 pytest 运行（pytest tests/eval_runner.py），也可直接执行：
  python tests/eval_runner.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# 确保 backend/ 在 sys.path，便于直接运行
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings  # noqa: E402
from app.providers.embedding import get_embedding_provider  # noqa: E402
from app.providers.vectorstore import get_vector_store  # noqa: E402
from app.providers.reranker import get_reranker  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.services.chat import chat_service  # noqa: E402

FLOW_RE = re.compile(r"QS_SRM_[A-Z0-9_]+")
Q_DIR = Path(__file__).resolve().parent / "eval"
Q_FILE = Q_DIR / "questions.json"


def _flow_codes_from_results(results) -> set:
    """从召回结果中抽取所有流程码：元数据优先，doc 文本兜底。"""
    codes = set()
    for r in results:
        md = r.metadata or {}
        fc = md.get("flow_code") or ""
        if fc:
            codes.add(fc.upper())
        # 文本兜底（附录元数据可能为空）
        codes.update(m.upper() for m in FLOW_RE.findall(r.document or ""))
    return codes


def _appendix_types_from_results(results) -> set:
    types = set()
    for r in results:
        md = r.metadata or {}
        at = md.get("appendix_type") or ""
        if at:
            types.add(at)
    return types


def _build_answer(results, question: str) -> str:
    """复刻线上无 Key 路径：检索增强直答。"""
    return chat_service._fallback_answer(results, question)


def _build_citations(results) -> list:
    return chat_service._build_citations(results)


def eval_question(item: dict, retriever: Retriever) -> dict:
    q = item["question"]
    exp_codes = [c.upper() for c in item.get("expected_flow_codes", [])]
    exp_kw = item.get("expected_keywords", [])
    exp_app = item.get("expected_appendix", "")

    results = retriever.retrieve(q, top_k=settings.rerank_top_n)
    answer = _build_answer(results, q)
    citations = _build_citations(results)

    found_codes = _flow_codes_from_results(results)
    found_app = _appendix_types_from_results(results)
    answer_text = answer or ""

    # 检索覆盖率：期望流程码是否全部命中
    if exp_codes:
        missing_codes = [c for c in exp_codes if c not in found_codes]
        retrieval_pass = len(missing_codes) == 0
        retrieval_detail = "OK" if retrieval_pass else f"missing {missing_codes}"
    else:
        # 无期望流程码的题目，用关键词在召回 doc 中的覆盖近似检索质量
        docs = "\n".join((r.document or "") for r in results)
        miss = [k for k in exp_kw if k not in docs]
        retrieval_pass = len(miss) == 0
        retrieval_detail = "no-code(chk kw)" if retrieval_pass else f"kw miss {miss}"

    # 回答关键词覆盖
    missing_kw = [k for k in exp_kw if k not in answer_text]
    answer_pass = len(missing_kw) == 0
    answer_detail = "OK" if answer_pass else f"kw miss {missing_kw}"

    # 引用覆盖（与检索同源）
    if exp_codes:
        missing_cite = [c for c in exp_codes if c not in found_codes]
        citation_pass = len(missing_cite) == 0
    else:
        citation_pass = retrieval_pass

    # 附录命中
    if exp_app:
        appendix_pass = exp_app in found_app
        appendix_detail = "OK" if appendix_pass else f"no {exp_app} in {sorted(found_app)}"
    else:
        appendix_pass = True
        appendix_detail = "n/a"

    # 期望固定编码（如 SRM012 接口）
    code_pass = True
    if item.get("expected_code"):
        code_pass = item["expected_code"].upper() in answer_text.upper()

    return {
        "question": q,
        "n_results": len(results),
        "retrieval_pass": retrieval_pass,
        "retrieval_detail": retrieval_detail,
        "answer_pass": answer_pass,
        "answer_detail": answer_detail,
        "citation_pass": citation_pass,
        "appendix_pass": appendix_pass,
        "appendix_detail": appendix_detail,
        "code_pass": code_pass,
        "found_codes": sorted(found_codes),
        "found_appendix": sorted(found_app),
    }


def main() -> int:
    if not Q_FILE.exists():
        print(f"[ERR] 评测题目缺失: {Q_FILE}")
        return 2
    questions = json.loads(Q_FILE.read_text(encoding="utf-8"))

    embedding = get_embedding_provider()
    store = get_vector_store(dim=getattr(embedding, "dim", 0))
    reranker = get_reranker()
    retriever = Retriever(store, embedding, reranker)

    rows = [eval_question(it, retriever) for it in questions]

    # 聚合
    def rate(key, pred=lambda _: True):
        sub = [r for r in rows if pred(r)]
        if not sub:
            return None, 0
        return sum(r[key] for r in sub) / len(sub), len(sub)

    retrieval_acc, n_ret = rate("retrieval_pass")
    answer_acc, n_ans = rate("answer_pass")
    citation_acc, n_cite = rate("citation_pass")
    # 仅统计指定 expected_appendix 的题目
    appendix_acc, n_app = rate("appendix_pass", lambda r: r["appendix_detail"] != "n/a")
    code_rows = [r for r in rows if not r["code_pass"]]
    code_acc = (len(rows) - len(code_rows)) / len(rows) if rows else None

    # 输出表格
    print("\n=== 逐题评测 ===")
    print(f"{'Q':>2} | {'检索':<4} | {'回答':<4} | {'引用':<4} | {'附录':<4} | 问题 / 备注")
    print("-" * 90)
    for i, r in enumerate(rows, 1):
        print(
            f"{i:>2} | "
            f"{'✓' if r['retrieval_pass'] else '✗':<4} | "
            f"{'✓' if r['answer_pass'] else '✗':<4} | "
            f"{'✓' if r['citation_pass'] else '✗':<4} | "
            f"{'✓' if r['appendix_pass'] else '·':<4} | "
            f"{r['question']}  [{r['retrieval_detail']}]"
        )

    print("\n=== 汇总指标 ===")
    print(f"题目总数            : {len(rows)}")
    print(f"检索准确率(retrieval): {retrieval_acc*100:5.1f}%  (n={n_ret})   目标 ≥90%")
    print(f"回答准确率(answer)  : {answer_acc*100:5.1f}%  (n={n_ans})   目标 ≥85%")
    print(f"引用准确率(citation): {citation_acc*100:5.1f}%  (n={n_cite})   目标 ≥90%")
    if appendix_acc is not None:
        print(f"附录命中率(appendix): {appendix_acc*100:5.1f}%  (n={n_app})   目标 ≥90%")
    if code_acc is not None and any('expected_code' in q for q in questions):
        print(f"固定编码命中(code)  : {code_acc*100:5.1f}%")

    # 失败项明细
    fails = [r for r in rows if not (r["retrieval_pass"] and r["answer_pass"] and r["citation_pass"])]
    if fails:
        print("\n--- 未达标项 ---")
        for r in fails:
            print(f"  · {r['question']}")
            print(f"      retrieval: {r['retrieval_detail']}")
            print(f"      answer   : {r['answer_detail']}")
            print(f"      found_codes={r['found_codes']} found_appendix={r['found_appendix']}")

    # 落盘
    out = {
        "summary": {
            "total": len(rows),
            "retrieval_acc": retrieval_acc,
            "answer_acc": answer_acc,
            "citation_acc": citation_acc,
            "appendix_acc": appendix_acc,
        },
        "rows": rows,
    }
    report_path = Q_DIR / "eval_report.json"
    report_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n评测报告已写入: {report_path}")

    # 判定是否达标
    ok = (
        (retrieval_acc or 0) >= 0.90
        and (answer_acc or 0) >= 0.85
        and (citation_acc or 0) >= 0.90
        and (appendix_acc if appendix_acc is not None else 1.0) >= 0.90
    )
    print("结果:", "达标 ✅" if ok else "未达标 ⚠️")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
