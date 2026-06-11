"""Agno Knowledge — 医学知识库

使用 Agno 原生 Knowledge + PgVector + OpenAIEmbedder。
支持动态 RAG 配置：检索策略、分词策略、Reranker、元数据过滤。
"""
from __future__ import annotations

from typing import Any, Optional

from agno.knowledge.knowledge import Knowledge
from agno.vectordb.pgvector import PgVector, SearchType
from agno.knowledge.embedder.openai import OpenAIEmbedder
from ..config import settings

import logging

logger = logging.getLogger(__name__)


def _build_reranker(config: dict | None = None):
    """根据配置构建 Reranker 实例"""
    cfg = config or {}
    provider = cfg.get("reranker_provider", settings.reranker_provider) or ""
    model = cfg.get("reranker_model", settings.reranker_model) or ""

    if not provider or not model:
        return None

    if provider == "cohere":
        try:
            from agno.knowledge.reranker.cohere import CohereReranker
            return CohereReranker(model=model)
        except ImportError:
            logger.warning("CohereReranker 未安装，请 pip install cohere")
            return None

    if provider == "infinity":
        base_url = cfg.get("reranker_base_url", settings.reranker_base_url) or ""
        if not base_url:
            logger.warning("InfinityReranker 需要配置 reranker_base_url")
            return None
        try:
            from agno.knowledge.reranker.infinity import InfinityReranker
            return InfinityReranker(base_url=base_url, model=model)
        except ImportError:
            logger.warning("InfinityReranker 未安装")
            return None

    return None


# 用于存储 RAG 是否被降级以及降级原因（供外部查询）
_rag_degraded: bool = False
_rag_degraded_reason: str = ""


def is_rag_degraded() -> bool:
    """检查 RAG 是否已降级（pgvector 不可用等）"""
    return _rag_degraded


def get_rag_degraded_reason() -> str:
    """获取 RAG 降级原因"""
    return _rag_degraded_reason


def create_knowledge(config: dict | None = None) -> Optional[Knowledge]:
    """创建 Agno Knowledge 实例

    Args:
        config: 可选的运行时配置覆盖，用于动态调整 RAG 参数。
                支持字段: rag_search_type, rag_max_results, rag_chunk_size,
                embedding_model, embedding_dimensions, reranker_provider, reranker_model 等。

    Returns:
        Knowledge 实例，或 None（当 RAG 不可用时降级返回 None）。
        调用方应在返回 None 时跳过 RAG 检索。
    """
    global _rag_degraded, _rag_degraded_reason

    if not settings.rag_enabled:
        logger.warning(
            "[RAG] rag_enabled=False，知识库未启用。"
            "设置 RAG_ENABLED=true 并确保 pgvector PostgreSQL 可用以启用检索增强生成。"
        )
        _rag_degraded = True
        _rag_degraded_reason = "rag_enabled is False"
        return None

    if settings.db_type != "postgres":
        logger.warning(
            "[RAG] 当前 db_type=%s，PgVector 需要 PostgreSQL。"
            "知识库已降级——检索增强生成不可用。"
            "请将 DB_TYPE 设置为 postgres 并确保 pgvector 扩展已安装。",
            settings.db_type,
        )
        _rag_degraded = True
        _rag_degraded_reason = f"db_type is '{settings.db_type}', requires 'postgres' for PgVector"
        return None

    cfg = config or {}

    search_type_str = cfg.get("rag_search_type", settings.rag_search_type)
    search_type = (
        SearchType.hybrid if search_type_str == "hybrid" else SearchType.vector
    )

    embedder_model = cfg.get("embedding_model", settings.embedding_model)
    embedder_dims = cfg.get("embedding_dimensions", settings.embedding_dimensions)

    reranker = _build_reranker(cfg)
    max_results = cfg.get("rag_max_results", settings.rag_max_results)

    pgvector_kwargs: dict[str, Any] = {
        "table_name": settings.agno_knowledge_table,
        "db_url": settings.agno_database_url,
        "search_type": search_type,
        "embedder": OpenAIEmbedder(
            id=embedder_model,
            dimensions=embedder_dims,
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_api_url,
        ),
    }
    if reranker:
        pgvector_kwargs["reranker"] = reranker

    knowledge = Knowledge(
        name="AI-Care 医学知识库",
        description="孕期智能管理平台医学知识库，覆盖产检指南、用药安全、孕期疾病管理等",
        vector_db=PgVector(**pgvector_kwargs),
        max_results=max_results,
    )

    _rag_degraded = False
    _rag_degraded_reason = ""
    logger.info(
        "[RAG] Knowledge 创建完成: search_type=%s, max_results=%s, embedder=%s, reranker=%s, db_type=%s",
        search_type_str, max_results, embedder_model,
        type(reranker).__name__ if reranker else "none",
        settings.db_type,
    )
    return knowledge


# 全局单例 — 供 Agent 和 API 使用；若 RAG 不可用则为 None（非静默降级）
knowledge = create_knowledge()


def get_rag_config() -> dict:
    """获取当前 RAG 配置快照（供 API 返回）"""
    return {
        "enabled": settings.rag_enabled,
        "search_type": settings.rag_search_type,
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "chunking_strategy": settings.rag_chunking_strategy,
        "max_results": settings.rag_max_results,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "embedding_api_url": settings.embedding_api_url,
        "reranker_provider": settings.reranker_provider,
        "reranker_model": settings.reranker_model,
        "reranker_base_url": settings.reranker_base_url,
        "vector_db_table": settings.agno_knowledge_table,
    }
