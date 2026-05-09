"""Agno Knowledge 适配器

将现有 agno_rag.py 的向量检索包装为 Agno Knowledge 兼容接口，
不依赖 pgvector Python 包，继续使用原始 SQL 查询 PostgreSQL pgvector 扩展。

使用方式：
1. 直接使用 agno_knowledge.search() — 通过适配器调用现有 RAG 引擎
2. Agent tool (agno_search_knowledge) — 已在 agno_tools.py 中定义
"""
from __future__ import annotations

from typing import Optional
from dataclasses import dataclass


@dataclass
class KnowledgeResult:
    """知识检索结果"""
    content: str
    doc_title: str
    doc_category: str
    similarity: float
    chunk_index: int


class AgnoKnowledgeAdapter:
    """Agno Knowledge 适配器 - 包装现有 RAG 引擎为 Agno 兼容接口

    核心价值：
    - 不改变现有 pgvector SQL 查询逻辑
    - 提供 Agno Knowledge 风格的 search() 接口
    - 可被 Agno Agent 的 knowledge 参数使用
    """

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        """延迟加载 RAG 引擎"""
        if self._engine is None:
            from .agno_rag import agno_rag_engine
            self._engine = agno_rag_engine
        return self._engine

    async def search(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> list[KnowledgeResult]:
        """知识检索 — Agno Knowledge 兼容接口

        Args:
            query: 查询文本
            top_k: 返回结果数
            category: 按分类过滤 (guideline / drug / education)
            filters: 额外过滤条件（预留）

        Returns:
            list[KnowledgeResult]
        """
        # 使用现有 RAG 引擎的 search 方法
        raw_results = self.engine.search(query, top_k=top_k, category=category)

        return [
            KnowledgeResult(
                content=r["content"],
                doc_title=r["doc_title"],
                doc_category=r["doc_category"],
                similarity=r["similarity"],
                chunk_index=r["chunk_index"],
            )
            for r in raw_results
        ]

    async def asearch(self, query: str, top_k: int = 5, **kwargs) -> list[dict]:
        """异步知识检索 — 返回 dict 格式（供 Agent tool 使用）"""
        results = await self.search(query, top_k=top_k, **kwargs)
        return [
            {
                "content": r.content,
                "doc_title": r.doc_title,
                "doc_category": r.doc_category,
                "similarity": r.similarity,
            }
            for r in results
        ]


# 全局单例
agno_knowledge = AgnoKnowledgeAdapter()
