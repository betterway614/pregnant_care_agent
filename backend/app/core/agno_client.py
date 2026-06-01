"""Agno 模型适配器 - 按角色配置云/本地模型，支持降级链"""
import logging
from typing import Literal
from ..config import settings

logger = logging.getLogger(__name__)

_model_cache: dict[str, object] = {}

AgentRole = Literal["pregnant", "nurse", "doctor"]

_DEFAULT_TEMPERATURE: dict[str, float] = {
    "pregnant": 0.7,
    "nurse": 0.3,
    "doctor": 0.3,
}
_DEFAULT_MAX_TOKENS: dict[str, int] = {
    "pregnant": 4096,
    "nurse": 8192,
    "doctor": 8192,
}


def _resolve_model_id(role: AgentRole) -> str:
    """角色专属模型 ID，空则 fallback 全局 llm_model"""
    role_model = getattr(settings, f"llm_{role}_model", "") or ""
    return role_model or settings.llm_model


def _resolve_mode(role: AgentRole) -> str:
    role_mode = getattr(settings, f"llm_{role}_mode", "") or ""
    return role_mode or settings.llm_mode


def _resolve_temperature(role: AgentRole) -> float:
    val = getattr(settings, f"llm_{role}_temperature", None)
    if isinstance(val, (int, float)) and val >= 0:
        return float(val)
    return _DEFAULT_TEMPERATURE.get(role, 0.7)


def _resolve_max_tokens(role: AgentRole) -> int:
    val = getattr(settings, f"llm_{role}_max_tokens", None)
    if isinstance(val, int) and val > 0:
        return val
    return _DEFAULT_MAX_TOKENS.get(role, 2048)


def _get_mode_chain(role: AgentRole) -> list[str]:
    """cloud → local → mock 降级链；角色或全局 mixed 时启用完整链"""
    explicit = getattr(settings, f"llm_{role}_mode", "") or ""
    if explicit and explicit != "mixed":
        return [explicit]
    if settings.llm_mode == "mixed":
        return ["cloud", "local", "mock"]
    return [settings.llm_mode or "cloud"]


def _mode_is_viable(mode: str) -> bool:
    if mode == "cloud" and not settings.llm_api_key:
        return False
    return True


def _build_model(role: AgentRole, mode: str):
    from agno.models.openai import OpenAIChat

    model_id = _resolve_model_id(role)
    temperature = _resolve_temperature(role)
    max_tokens = _resolve_max_tokens(role)

    if mode == "cloud":
        return OpenAIChat(
            id=model_id,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            role_map={"system": "system", "user": "user", "assistant": "assistant", "tool": "tool"},
        )
    if mode == "local":
        local_id = model_id if model_id != settings.llm_model else settings.local_model
        # 优先使用 vLLM/SGLang 等 OpenAI 兼容端点（本地部署推荐）
        if settings.local_base_url:
            return OpenAIChat(
                id=local_id,
                api_key="not-needed",
                base_url=settings.local_base_url,
                temperature=temperature,
                max_tokens=max_tokens,
                role_map={"system": "system", "user": "user", "assistant": "assistant", "tool": "tool"},
            )
        from agno.models.ollama import Ollama
        return Ollama(
            id=local_id,
            host=settings.ollama_host,
            options={"temperature": temperature, "num_predict": max_tokens},
        )
    return OpenAIChat(
        id="mock-model",
        api_key="mock-key",
        base_url="http://localhost:1/v1",
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _create_model(role: AgentRole):
    chain = _get_mode_chain(role)
    for mode in chain:
        if not _mode_is_viable(mode):
            logger.debug("跳过不可用 LLM 模式 role=%s mode=%s", role, mode)
            continue
        try:
            model = _build_model(role, mode)
            if mode != chain[0]:
                logger.info("LLM 降级生效 role=%s mode=%s", role, mode)
            return model
        except Exception as exc:
            logger.warning("创建 LLM 模型失败 role=%s mode=%s: %s", role, mode, exc)
    return _build_model(role, "mock")


def get_agno_model(role: AgentRole = "pregnant"):
    """根据角色和配置返回 Agno 模型实例（缓存）"""
    if role in _model_cache:
        return _model_cache[role]
    _model_cache[role] = _create_model(role)
    return _model_cache[role]


def reset_agno_client(role: AgentRole = None):
    """重置模型缓存（配置变更后调用）"""
    global _model_cache
    if role:
        _model_cache.pop(role, None)
    else:
        _model_cache.clear()
