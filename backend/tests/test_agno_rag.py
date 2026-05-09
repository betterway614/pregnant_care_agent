"""测试 Agno RAG 引擎"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def test_agno_rag_search_returns_list():
    """验证 search 返回列表格式"""
    from app.core.agno_rag import AgnoRAGEngine

    mock_db = MagicMock()
    mock_rows = [
        MagicMock(
            id=1, doc_title="测试文档", doc_category="guideline",
            content="测试内容", chunk_index=0,
        )
    ]
    mock_db.execute.return_value.fetchall.return_value = mock_rows

    with patch("app.database.SessionLocal", return_value=mock_db):
        with patch("app.config.settings") as mock_settings:
            mock_settings.db_type = "postgres"
            engine = AgnoRAGEngine()
            engine._embedding = MagicMock()
            engine._embedding.embed.return_value = [[0.1] * 1024]
            results = engine.search("测试查询", top_k=1)
            assert isinstance(results, list)
            assert len(results) == 1
            assert results[0]["doc_title"] == "测试文档"


@pytest.mark.asyncio
async def test_agno_rag_ask_returns_dict():
    """验证 ask 返回标准字典格式"""
    from app.core.agno_rag import AgnoRAGEngine

    engine = AgnoRAGEngine()
    engine._embedding = MagicMock()
    engine._embedding.embed.return_value = [[0.1] * 1024]
    engine._llm = AsyncMock()
    engine._llm.chat = AsyncMock(return_value="测试回答")

    with patch.object(engine, "search") as mock_search:
        mock_search.return_value = [
            {"doc_title": "指南", "doc_category": "guideline",
             "content": "知识内容", "similarity": 0.9, "chunk_index": 0}
        ]
        result = await engine.ask("测试问题", patient_context="孕30周")
        assert "answer" in result
        assert "sources" in result
        assert "chunks" in result
        assert result["rag_used"] is True


@pytest.mark.asyncio
async def test_agno_rag_ask_no_results():
    """验证无结果时返回兜底回答"""
    from app.core.agno_rag import AgnoRAGEngine

    engine = AgnoRAGEngine()
    engine._embedding = MagicMock()
    engine._embedding.embed.return_value = [[0.1] * 1024]

    with patch.object(engine, "search") as mock_search:
        mock_search.return_value = []
        result = await engine.ask("不存在的问题")
        assert result["rag_used"] is False
        assert "抱歉" in result["answer"] or "咨询" in result["answer"]
