"""Agno SSE 流式事件生成器 — 孕妇/护士/医生三端共用

封装 Agno Agent 的 SSE 流式输出逻辑，消除 nurse_ai / doctor_ai / agno_chat_handler
中三份重复的 RunEvent 处理代码。调用方只需提供角色特定的配置，不需要关心
tool_call_started / run_content / run_completed 等底层事件处理。

使用方式:
    state = AgnoSseState()
    config = AgnoSseConfig(agent=..., input_text=..., ...)
    async for event in agno_sse_event_generator(config, state):
        yield event
    # 循环结束后从 state 读取 run_response / full_response / elapsed_ms 做审计日志
"""
from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from agno.agent import RunEvent
from loguru import logger

from .formatters import format_structured_output_to_markdown


@dataclass
class AgnoSseState:
    """SSE 流式生成过程中填充的可变状态，调用方在循环结束后读取用于审计日志等。"""
    full_response: str = ""
    run_response: Any = None        # Agno RunResponse (run_completed chunk)
    tool_steps: list[str] = field(default_factory=list)
    content_streamed: bool = False
    elapsed_ms: int = 0


@dataclass
class AgnoSseConfig:
    """单次 SSE 流式会话的不可变角色特定参数。

    Required:
        agent          — 已创建的路由 Agno Agent 实例
        input_text     — Agent 输入文本（可能已经过 NLU 上下文注入)
        user_id        — Agent session user_id
        session_id     — Agent 多轮对话上下文 key
        thinking_map   — tool_name → 中文描述 (如 {"agno_query_patient_data": "正在查询..."})
        initial_thinking — 首个 thinking 事件显示的文本 (如 "小护正在思考...")
        error_log_message — 异常时 logger.error 的前缀
        error_chunk_content — 异常时发送给前端的友好提示文本
        done_source    — done 事件 JSON 中的 source 字段 ("AI_CARE" / "NURSE_AI" / "DOCTOR_AI")

    Optional:
        images         — Agno Image 列表 (仅孕妇端需要，用于多模态)
        done_extra     — 合并到 done 事件 JSON 中的额外字段
    """
    agent: Any
    input_text: str
    user_id: str
    session_id: str
    thinking_map: dict[str, str]
    initial_thinking: str = "正在思考..."
    error_log_message: str = "Agno stream error"
    error_chunk_content: str = "\n\n抱歉，AI服务暂时不可用，请稍后再试。"
    done_source: str = "AI"
    images: list[Any] | None = None
    done_extra: dict[str, Any] | None = None


async def agno_sse_event_generator(
    config: AgnoSseConfig,
    state: AgnoSseState,
) -> AsyncGenerator[dict[str, str], None]:
    """Agno Agent SSE 流式事件生成器 — 三端共用。

    事件顺序:
        thinking (初始) → (tool thinking)* → chunk* → [fallback chunk] → done

    state 在生成过程中被逐步填充：tool_steps, full_response, run_response,
    content_streamed, elapsed_ms。调用方在 async for 循环结束后读取。
    """
    t0 = time.time()

    # 1. 初始思考状态
    yield {"event": "thinking", "data": config.initial_thinking}

    run_response = None
    content_streamed = False
    tool_steps: list[str] = []

    try:
        # 2. Agent 流式推理
        arun_kwargs: dict[str, Any] = dict(
            input=config.input_text,
            stream=True,
            stream_events=True,
            user_id=config.user_id,
            session_id=config.session_id,
        )
        if config.images:
            arun_kwargs["images"] = config.images

        async for chunk in config.agent.arun(**arun_kwargs):
            event = chunk.event

            if event == RunEvent.tool_call_started and chunk.tool is not None:
                tool_name = getattr(chunk.tool, "tool_name", "") or ""
                thinking_msg = config.thinking_map.get(
                    tool_name, f"正在处理（{tool_name}）..."
                )
                yield {"event": "thinking", "data": thinking_msg}

            elif event == RunEvent.tool_call_completed and chunk.tool is not None:
                tool_name = getattr(chunk.tool, "tool_name", "") or ""
                step_desc = config.thinking_map.get(tool_name, "")
                if step_desc and step_desc not in tool_steps:
                    tool_steps.append(step_desc)

            elif event == RunEvent.run_content:
                if chunk.content and isinstance(chunk.content, str):
                    content_streamed = True
                    state.full_response += chunk.content
                    yield {"event": "chunk", "data": chunk.content}

            elif event == RunEvent.run_completed:
                run_response = chunk

        # 3. 兜底：Agent 使用 output_schema 时 run_content 不会触发，
        #    结构化输出需从 run_response.content 提取并发送到前端。
        if not content_streamed and run_response is not None:
            fallback_text = format_structured_output_to_markdown(run_response.content)
            if fallback_text:
                state.full_response = fallback_text
                yield {"event": "chunk", "data": fallback_text}

    except Exception:
        logger.error(
            "{}: {}", config.error_log_message, traceback.format_exc()
        )
        yield {"event": "chunk", "data": config.error_chunk_content}

    # 4. 填充共享状态
    state.run_response = run_response
    state.content_streamed = content_streamed
    state.tool_steps = tool_steps
    state.elapsed_ms = int((time.time() - t0) * 1000)

    # 5. 发送 done 事件
    done_data: dict[str, Any] = {
        "source": config.done_source,
        "session_id": config.session_id,
        "tool_steps": tool_steps,
    }
    if config.done_extra:
        done_data.update(config.done_extra)

    yield {
        "event": "done",
        "data": json.dumps(done_data),
    }
