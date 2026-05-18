"""通用 JSON 解析工具 - 处理 LLM 返回的各种格式"""
import re
import json
from typing import Optional


def parse_llm_json(response: str) -> Optional[dict]:
    """解析 LLM 返回的 JSON，支持多种格式

    支持的格式：
    1. 标准 JSON
    2. Markdown 代码块包裹的 JSON (```json ... ```)
    3. 花括号包裹的 JSON ({ ... })

    Returns:
        解析后的字典，或 None（如果解析失败）
    """
    if not response or not response.strip():
        return None

    response = response.strip()

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

    # 3. 尝试提取花括号包裹的 JSON
    match = re.search(r'\{.*\}', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None
