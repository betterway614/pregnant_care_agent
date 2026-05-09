"""Agno 模型适配器 - 封装 Agno 模型为兼容 LLMClient 接口"""
from typing import AsyncGenerator, Optional
from ..config import settings


def get_agno_model():
    """根据配置返回 Agno 模型实例"""
    from agno.models.openai import OpenAIChat
    from agno.models.ollama import Ollama

    mode = settings.llm_mode

    if mode == "cloud":
        return OpenAIChat(
            id=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
    elif mode == "local":
        return Ollama(
            id=settings.local_model,
            host=settings.ollama_host,
        )
    else:
        # Mock 模式：使用 OpenAIChat 指向一个假地址（不会真正调用）
        return OpenAIChat(
            id="mock-model",
            api_key="mock-key",
            base_url="http://localhost:1/v1",
        )


class AgnoClient:
    """兼容 LLMClient 接口的 Agno 适配器"""

    def __init__(self, agent=None):
        from agno.agent import Agent
        self._agent = agent or Agent(
            model=get_agno_model(),
            markdown=True,
        )

    def _extract_messages(self, messages: list[dict]) -> tuple[str, list[str]]:
        """从消息列表中提取用户消息和系统指令"""
        user_msg = messages[-1]["content"] if messages else ""
        instructions = []
        for m in messages:
            if m["role"] == "system":
                instructions.append(m["content"])
                break
        return user_msg, instructions

    def _create_agent(self, instructions: list[str] | None = None):
        """创建新 Agent 实例（避免指令副作用）"""
        from agno.agent import Agent
        return Agent(
            model=get_agno_model(),
            instructions=instructions or self._agent.instructions,
            markdown=True,
        )

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """异步对话接口"""
        user_msg, instructions = self._extract_messages(messages)
        agent = self._create_agent(instructions) if instructions else self._agent
        response = await agent.arun(user_msg)
        return response.content or ""

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        """异步流式对话接口"""
        user_msg, instructions = self._extract_messages(messages)
        agent = self._create_agent(instructions) if instructions else self._agent
        async for event in agent.arun_stream(user_msg):
            if hasattr(event, "content") and event.content:
                yield event.content

    async def chat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """支持工具调用的对话 - 使用 Agno Agent 的工具循环"""
        user_msg, instructions = self._extract_messages(messages)
        agent = self._create_agent(instructions) if instructions else self._agent
        response = await agent.arun(user_msg)
        return {
            "role": "assistant",
            "content": response.content or "",
            "tool_calls": None,
        }


# 全局缓存
_agno_client_instance: Optional[AgnoClient] = None


def get_agno_client() -> AgnoClient:
    """获取 Agno 客户端单例"""
    global _agno_client_instance
    if _agno_client_instance is None:
        _agno_client_instance = AgnoClient()
    return _agno_client_instance


def reset_agno_client():
    """重置 Agno 客户端"""
    global _agno_client_instance
    _agno_client_instance = None
