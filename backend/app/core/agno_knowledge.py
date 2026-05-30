"""Agno Knowledge — 医学知识库

使用 Agno 原生 Knowledge + PgVector + OpenAIEmbedder。
提供全局 knowledge 单例，供所有 Agent 使用。
"""
from __future__ import annotations

from agno.knowledge.knowledge import Knowledge
from agno.vectordb.pgvector import PgVector, SearchType
from agno.knowledge.embedder.openai import OpenAIEmbedder
from ..config import settings


def create_knowledge() -> Knowledge:
    """创建 Agno Knowledge 实例（全局单例）"""
    search_type = (
        SearchType.hybrid
        if settings.rag_search_type == "hybrid"
        else SearchType.vector
    )

    return Knowledge(
        name="AI-Care 医学知识库",
        description="孕期智能管理平台医学知识库，覆盖产检指南、用药安全、孕期疾病管理等",
        vector_db=PgVector(
            table_name="knowledge_chunks",
            db_url=settings.database_url,
            search_type=search_type,
            embedder=OpenAIEmbedder(
                id=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                api_key=settings.embedding_api_key,
                base_url=settings.embedding_api_url,
            ),
        ),
        max_results=settings.rag_max_results,
    )


# 全局单例 — 供 Agent 和 API 使用
knowledge = create_knowledge()
