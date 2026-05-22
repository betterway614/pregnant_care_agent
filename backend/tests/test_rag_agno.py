"""测试 RAG 引擎"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_rag_ask_uses_rag_engine():
    from app.routers.chat import rag_ask, RAGAskRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.rag_enabled = True
        with patch("app.routers.chat.rag_engine") as mock_engine:
            mock_engine.ask = AsyncMock(return_value={
                "answer": "测试回答",
                "sources": [],
                "chunks": [],
                "rag_used": True,
            })
            req = RAGAskRequest(question="孕期饮食注意事项")
            resp = await rag_ask(req)
            assert resp.answer == "测试回答"
            mock_engine.ask.assert_called_once()
