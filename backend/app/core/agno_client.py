"""Agno 模型适配器 - 封装 Agno 模型为兼容 LLMClient 接口

支持按角色（pregnant/nurse/doctor）配置不同模型：
- pregnant: 孕妇端智能体（小安），可使用云模型
- nurse: 护士端智能体（小护），可使用本地模型
- doctor: 医生端智能体（智医），可使用本地模型
"""
from typing import AsyncGenerator, Literal, Optional
from ..config import settings

# 按角色缓存模型实例
_model_cache: dict[str, object] = {}

# 角色类型定义
AgentRole = Literal["pregnant", "nurse", "doctor"]


def _create_model(mode: str, model_id: str = None, api_key: str = None, base_url: str = None):
    """创建 Agno 模型实例"""
    from agno.models.openai import OpenAIChat
    from agno.models.ollama import Ollama

    if mode == "cloud":
        return OpenAIChat(
            id=model_id or settings.llm_model,
            api_key=api_key or settings.llm_api_key,
            base_url=base_url or settings.llm_base_url,
            role_map={"system": "system", "user": "user", "assistant": "assistant", "tool": "tool"},
        )
    elif mode == "local":
        return Ollama(
            id=model_id or settings.local_model,
            host=base_url or settings.ollama_host,
        )
    else:
        return OpenAIChat(
            id="mock-model",
            api_key="mock-key",
            base_url="http://localhost:1/v1",
        )


def get_agno_model(role: AgentRole = "pregnant"):
    """根据角色和配置返回 Agno 模型实例

    配置优先级：
    1. 角色专属配置（llm_pregnant_mode / llm_nurse_mode / llm_doctor_mode）
    2. 全局配置（llm_mode）

    Args:
        role: 智能体角色，可选 "pregnant"（孕妇端）、"nurse"（护士端）、"doctor"（医生端）

    Returns:
        Agno 模型实例
    """
    global _model_cache

    # 检查缓存
    if role in _model_cache:
        return _model_cache[role]

    # 根据角色确定模型配置
    if role == "pregnant":
        # 孕妇端：优先使用 llm_pregnant_mode，否则使用 llm_mode
        mode = settings.llm_pregnant_mode if settings.llm_pregnant_mode else settings.llm_mode
    elif role == "nurse":
        # 护士端：优先使用 llm_nurse_mode，否则使用 llm_mode
        mode = settings.llm_nurse_mode if settings.llm_nurse_mode else settings.llm_mode
    elif role == "doctor":
        # 医生端：优先使用 llm_doctor_mode，否则使用 llm_mode
        mode = settings.llm_doctor_mode if settings.llm_doctor_mode else settings.llm_mode
    else:
        mode = settings.llm_mode

    # 创建并缓存模型实例
    _model_cache[role] = _create_model(mode)
    return _model_cache[role]


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
        async for event in agent.arun(input=user_msg, stream=True):
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


def reset_agno_client(role: AgentRole = None):
    """重置 Agno 客户端和模型缓存

    Args:
        role: 指定角色则只清除该角色的模型缓存，否则清除所有缓存
    """
    global _agno_client_instance, _model_cache

    if role:
        _model_cache.pop(role, None)
    else:
        _model_cache.clear()

    _agno_client_instance = None
