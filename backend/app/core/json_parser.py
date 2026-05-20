"""通用 JSON 解析工具 - 处理 LLM 返回的各种格式"""
import re
import json
from typing import Optional


def _strip_think_tags(text: str) -> str:
    """剥离 qwen/deepseek 等模型的 <think>...</think> 思考标签"""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


def parse_llm_json(response: str) -> Optional[dict]:
    """解析 LLM 返回的 JSON，支持多种格式

    支持的格式：
    1. 标准 JSON
    2. Markdown 代码块包裹的 JSON (```json ... ```)
    3. 花括号包裹的 JSON ({ ... })
    4. 包裹在 <think>...</think> 标签中的内容（自动剥离）

    Returns:
        解析后的字典，或 None（如果解析失败）
    """
    if not response or not response.strip():
        return None

    # 先剥离 think 标签
    response = _strip_think_tags(response)
    if not response:
        return None

    # 1. 尝试直接解析
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # 2. 尝试提取代码块中的 JSON
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. 尝试提取花括号包裹的 JSON（贪婪匹配最外层完整 JSON 对象）
    depth = 0
    start = -1
    for i, ch in enumerate(response):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(response[start:i + 1])
                except json.JSONDecodeError:
                    start = -1

    return None
