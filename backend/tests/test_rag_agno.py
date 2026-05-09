"""测试 RAG Router Agno 集成"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_rag_ask_uses_agno_engine():
    """验证 RAG 问答在 agno_enabled=True 时使用 AgnoRAGEngine"""
    from app.routers.chat import rag_ask, RAGAskRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = True
        mock_settings.rag_enabled = True
        with patch("app.routers.chat.agno_rag_engine") as mock_engine:
            mock_engine.ask = AsyncMock(return_value={
                "answer": "Agno回答",
                "sources": [],
                "chunks": [],
                "rag_used": True,
            })
            with patch("app.routers.chat.SessionLocal") as mock_db:
                mock_db.return_value.query.return_value.filter.return_value.first.return_value = None
                req = RAGAskRequest(question="测试", patient_id="test-pid")
                result = await rag_ask(req)
                assert result.answer == "Agno回答"
                mock_engine.ask.assert_called_once()


@pytest.mark.asyncio
async def test_rag_ask_uses_original_engine():
    """验证 RAG 问答在 agno_enabled=False 时使用原始引擎"""
    from app.routers.chat import rag_ask, RAGAskRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = False
        mock_settings.rag_enabled = True
        with patch("app.routers.chat.rag_engine") as mock_engine:
            mock_engine.ask = AsyncMock(return_value={
                "answer": "原始回答",
                "sources": [],
                "chunks": [],
                "rag_used": True,
            })
            with patch("app.routers.chat.SessionLocal") as mock_db:
                mock_db.return_value.query.return_value.filter.return_value.first.return_value = None
                req = RAGAskRequest(question="测试", patient_id="test-pid")
                result = await rag_ask(req)
                assert result.answer == "原始回答"
