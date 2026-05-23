"""通用 JSON 解析工具 - 处理 LLM 返回的各种格式"""
import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _strip_think_tags(text: str) -> str:
    """剥离 qwen/deepseek 等模型的 <think>...</think> 思考标签（支持嵌套）"""
    # 非贪婪匹配，处理嵌套情况
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    return cleaned


def _strip_think_in_values(obj):
    """递归清除已解析 JSON 对象中各字符串字段内的 <think> 标签"""
    if isinstance(obj, str):
        return _strip_think_tags(obj)
    if isinstance(obj, list):
        return [_strip_think_in_values(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _strip_think_in_values(v) for k, v in obj.items()}
    return obj


def _try_parse(text: str) -> Optional[dict]:
    """尝试解析 JSON，支持标准格式和 markdown 代码块"""
    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 提取代码块中的 JSON
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. 提取最外层花括号包裹的 JSON
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = -1

    return None


def parse_llm_json(response: str) -> Optional[dict]:
    """解析 LLM 返回的 JSON，支持多种格式

    支持的格式：
    1. 标准 JSON
    2. Markdown 代码块包裹的 JSON (```json ... ```)
    3. 花括号包裹的 JSON ({ ... })
    4. 包裹在 <think>...</think> 标签中的内容（自动剥离）
    5. JSON 字段值内嵌的 <think> 标签（自动清除）

    Returns:
        解析后的字典，或 None（如果解析失败）
    """
    if not response or not response.strip():
        return None

    # 先剥离顶层 think 标签
    cleaned = _strip_think_tags(response)
    if not cleaned:
        return None

    # 尝试解析
    result = _try_parse(cleaned)
    if result is not None:
        # 清除字段值内可能残留的 think 标签
        return _strip_think_in_values(result)

    # 如果顶层剥离后仍失败，尝试在原始响应中解析
    # （处理 think 标签出现在 JSON 结构内部的情况）
    result = _try_parse(response)
    if result is not None:
        return _strip_think_in_values(result)

    logger.debug("JSON 解析失败，原始响应前200字符: %s", response[:200])
    return None
