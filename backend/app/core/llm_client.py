"""LLM客户端抽象层 - 支持云端/本地双模式切换"""
import os
import json
import httpx
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class LLMClient(ABC):
    """大模型调用抽象基类"""

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        ...

    @abstractmethod
    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        ...

    @abstractmethod
    async def chat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """支持工具调用的对话，返回 {role, content, tool_calls}"""
        ...


class CloudAPIClient(LLMClient):
    """开发阶段：云端API (兼容 OpenAI 接口)"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        # 统一 HTTP 客户端超时：连接 15s，读取 120s（LLM 生成需要时间）
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=15.0, read=120.0)
        )
        self._logger = __import__("loguru").logger

    @staticmethod
    def _fix_roles(messages: list[dict]) -> list[dict]:
        """OpenAI SDK v2 可能把 'system' 转成 'developer'，但 Qwen API 不接受 'developer'"""
        fixed = []
        for m in messages:
            if m.get("role") == "developer":
                m = {**m, "role": "system"}
            fixed.append(m)
        return fixed

    def _build_client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=self.http_client,
        )

    async def chat(self, messages: list[dict], **kwargs) -> str:
        client = self._build_client()
        self._logger.info("LLM chat 开始 model={}", self.model)
        import time
        t0 = time.time()
        try:
            resp = await client.chat.completions.create(
                model=self.model,
                messages=self._fix_roles(messages),
                **kwargs
            )
            elapsed = time.time() - t0
            self._logger.info("LLM chat 完成 ({:.1f}s)", elapsed)
            return resp.choices[0].message.content or ""
        except Exception as e:
            elapsed = time.time() - t0
            self._logger.warning("LLM chat 失败 ({:.1f}s): {}", elapsed, e)
            raise

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        client = self._build_client()
        self._logger.info("LLM chat_stream 开始 model={}", self.model)
        try:
            stream = await client.chat.completions.create(
                model=self.model,
                messages=self._fix_roles(messages),
                stream=True,
                **kwargs
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            self._logger.info("LLM chat_stream 完成")
        except Exception as e:
            self._logger.warning("LLM chat_stream 失败: {}", e)
            raise

    async def chat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """使用 OpenAI 原生 function calling"""
        client = self._build_client()
        self._logger.info("LLM chat_with_tools 开始 model={}", self.model)
        import time
        t0 = time.time()
        try:
            resp = await client.chat.completions.create(
                model=self.model,
                messages=self._fix_roles(messages),
                tools=tools,
                tool_choice="auto",
                **kwargs
            )
            elapsed = time.time() - t0
            self._logger.info("LLM chat_with_tools 完成 ({:.1f}s)", elapsed)
            choice = resp.choices[0]
            msg = choice.message
            result = {"role": "assistant", "content": msg.content or "", "tool_calls": None}
            if msg.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            return result
        except Exception as e:
            elapsed = time.time() - t0
            self._logger.warning("LLM chat_with_tools 失败 ({:.1f}s): {}", elapsed, e)
            raise


class LocalOllamaClient(LLMClient):
    """竞赛阶段：本地GPU Ollama推理"""

    def __init__(self, host: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.host = host.rstrip("/")
        self.model = model

    async def chat(self, messages: list[dict], **kwargs) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.host}/api/chat", json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": kwargs.get("max_tokens", 2048)}
            })
            return resp.json()["message"]["content"]

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{self.host}/api/chat", json={
                "model": self.model,
                "messages": messages,
                "stream": True,
                "options": {"num_predict": kwargs.get("max_tokens", 2048)}
            }) as resp:
                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if data.get("message", {}).get("content"):
                                yield data["message"]["content"]
                        except json.JSONDecodeError:
                            continue

    async def chat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """使用 Ollama tools API"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": kwargs.get("max_tokens", 2048)},
        }
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.host}/api/chat", json=payload)
            data = resp.json()
            msg = data.get("message", {})
            result = {"role": "assistant", "content": msg.get("content", ""), "tool_calls": None}
            if "tool_calls" in msg:
                result["tool_calls"] = msg["tool_calls"]
            return result


def _build_client_for_mode(mode: str) -> LLMClient:
    """根据模式字符串构建 LLM 客户端实例。"""
    from ..config import settings

    if mode == "cloud":
        return CloudAPIClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    elif mode == "local":
        if settings.local_base_url:
            return CloudAPIClient(
                api_key="not-needed",
                base_url=settings.local_base_url,
                model=settings.local_model,
            )
        else:
            return LocalOllamaClient(
                host=settings.ollama_host,
                model=settings.local_model,
            )
    else:
        from .mock_llm_client import MockLLMClient
        return MockLLMClient()


_llm_client_instance: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """获取 LLM 客户端单例（全局配置）。"""
    from ..config import settings
    global _llm_client_instance
    if _llm_client_instance is None:
        _llm_client_instance = _build_client_for_mode(settings.llm_mode)
    return _llm_client_instance


_pregnant_llm_client_instance: LLMClient | None = None


def get_pregnant_llm_client() -> LLMClient:
    """获取 Pregnant 专用 LLM 客户端单例。"""
    from ..config import settings
    global _pregnant_llm_client_instance
    if _pregnant_llm_client_instance is None:
        mode = settings.llm_pregnant_mode if settings.llm_mode == "mixed" else settings.llm_mode
        _pregnant_llm_client_instance = _build_client_for_mode(mode)
    return _pregnant_llm_client_instance


def reset_llm_client():
    """重置LLM客户端（配置变更后调用）"""
    global _llm_client_instance, _pregnant_llm_client_instance
    _llm_client_instance = None
    _pregnant_llm_client_instance = None
