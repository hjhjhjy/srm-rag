"""LLM Provider：DeepSeek（OpenAI 兼容，支持流式）为主，无 Key 时降级。

降级说明：当未配置 API Key，`available=False`，由 ChatService 直接基于检索片段合成答案
（检索增强直答），保证应用在无外部依赖时仍可完整演示 RAG 流程。
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("srm.llm")


class LLMProvider:
    available: bool = True

    async def astream(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        raise NotImplementedError

    async def acomplete(self, messages: List[Dict[str, str]]) -> str:
        out = []
        async for t in self.astream(messages):
            out.append(t)
        return "".join(out)

    def complete(self, messages: List[Dict[str, str]]) -> str:
        """同步生成（阻塞）。用于同步检索链路（重排）等无法 await 的场景。"""
        raise NotImplementedError


class DeepSeekProvider(LLMProvider):
    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url.rstrip("/")
        self.model = settings.deepseek_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self.available = bool(self.api_key)

    async def astream(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        if not self.api_key:
            yield ""
            return
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.error("DeepSeek 错误 %s: %s", resp.status_code, body[:500])
                    yield f"[LLM 调用失败: {resp.status_code}]"
                    return
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:  # noqa
                        continue

    def complete(self, messages: List[Dict[str, str]]) -> str:
        if not self.api_key:
            return ""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            if resp.status_code != 200:
                logger.error("DeepSeek 同步错误 %s: %s", resp.status_code, resp.text[:500])
                return ""
            try:
                return resp.json()["choices"][0]["message"]["content"] or ""
            except Exception as e:  # noqa
                logger.error("DeepSeek 同步解析失败: %s", e)
                return ""


class FallbackProvider(LLMProvider):
    available = False

    async def astream(self, messages: List[Dict[str, str]]):
        yield ""
        return

    def complete(self, messages: List[Dict[str, str]]) -> str:
        return ""


def get_llm_provider() -> LLMProvider:
    p = settings.llm_provider.lower()
    if p == "deepseek":
        prov = DeepSeekProvider()
        if prov.available:
            return prov
        logger.warning("未配置 DEEPSEEK_API_KEY，LLM 进入检索增强直答降级模式")
        return FallbackProvider()
    # 预留混元/通义：结构同 DeepSeek（OpenAI 兼容网关），此处统一走 DeepSeek 实现占位
    logger.warning("LLM 提供商 %s 未单独实现，使用降级模式", p)
    return FallbackProvider()
