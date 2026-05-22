"""Agno structured output 解析工具"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from .json_parser import parse_llm_json


def extract_structured_content(content: Any) -> dict | None:
    """从 Agno RunOutput.content 提取 dict

    output_schema 模式下 content 可能是 Pydantic 对象或 JSON 字符串。
    """
    if content is None:
        return None
    if isinstance(content, BaseModel):
        return content.model_dump()
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return parse_llm_json(text)
    return None
