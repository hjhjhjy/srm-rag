"""提示词与上下文拼装。"""
from __future__ import annotations

from typing import List

from app.providers.vectorstore import SearchResult

SYSTEM_PROMPT = """你是「青山利康 SRM 供应商助手」，服务于使用青山利康供应商关系管理（SRM）系统的供应商用户。
你的目标：用专业、友好、简洁的中文，帮助供应商了解并正确使用 SRM 系统（注册入驻、资质准入、样品、询报价/竞价/招投标、合同、订单、整改、对账结算、绩效与各类报表等）。

【严格约束】
1. 只能依据下面提供的《业务蓝图》知识片段回答，不得编造、不得猜测系统实时数据（如具体订单状态、金额、审批进度等未提供的内容）。
2. 知识片段未覆盖的问题，明确告知「当前帮助文档未包含该信息，建议联系青山利康采购专员或在 SRM 系统内转人工」，不要臆测。
3. 每条事实性回答必须在句末或对应位置标注出处，格式：【出处：QS_SRM_SM_0002 资质准入管理】；若来自附录，标注【出处：附录·预警提示 / QS_SRM_SM_0002】或【出处：接口清单 SRM012】。可并列多个出处。
4. 操作类问题用编号步骤给出；若检索命中相关「消息推送 / 预警提示 / 表单文件 / 报表」，主动在末尾提示供应商关注（如「相关提醒：资质到期前 60 天系统会发送预警」）。
5. 不输出其他供应商的隐私或商业信息，不指导任何绕过合规/审批流程的操作。

【回答风格】条理清晰、要点前置、必要时分步骤；中文。"""

HUMAN_TEMPLATE = """请基于以下《业务蓝图》知识片段回答用户问题。若片段不足以回答，请如实说明并引导转人工。

===== 知识片段（自带出处标记）=====
{context}
===== 知识片段结束 =====

用户问题：{question}

请按系统约束回答，并在事实处标注【出处：...】。"""


def _citation_label(r: SearchResult) -> str:
    md = r.metadata or {}
    fc = md.get("flow_code")
    fn = md.get("flow_name") or ""
    at = md.get("appendix_type")
    code = md.get("code")
    if at and code:
        return f"{at}:{code}"
    if fc:
        return f"{fc} {fn}".strip()
    return fn or r.id


def format_context(results: List[SearchResult], max_chars: int = 6000) -> str:
    parts = []
    total = 0
    for i, r in enumerate(results, 1):
        label = _citation_label(r)
        block = f"[片段{i} | 出处标记：{label}]\n{r.document}\n"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n".join(parts)


def build_messages(
    context: str, question: str, history: List[dict] = None
) -> List[dict]:
    history = history or []
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # 注入近几轮对话作为上下文
    for h in history:
        if h.get("role") in ("user", "assistant"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append(
        {
            "role": "user",
            "content": HUMAN_TEMPLATE.format(context=context, question=question),
        }
    )
    return messages
