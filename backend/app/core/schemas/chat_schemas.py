"""对话相关结构化输出 Schema"""
from pydantic import BaseModel, Field


class ChatOutput(BaseModel):
    """对话输出 — 用于流式对话场景"""
    content: str = Field(description="回复内容")
    tools_used: list[str] = Field(default_factory=list, description="使用的工具列表")
