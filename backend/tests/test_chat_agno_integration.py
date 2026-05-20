"""测试 Chat Router Agno 集成"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_send_message_uses_agno_when_enabled():
    """验证 agno_enabled=True 时使用 Agno Agent（handle_chat_with_agno）"""
    from app.routers.chat import send_message
    from app.schemas import ChatSendRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = True
        with patch("app.core.agno_chat_handler.handle_chat_with_agno") as mock_handler:
            mock_handler.return_value = MagicMock(
                content="Agno回复",
                session_id="test-sess",
                source="AI_CARE",
            )
            req = ChatSendRequest(
                pregnant_id="test-pid",
                message="你好",
            )
            resp = await send_message(req)
            assert resp.content == "Agno回复"
            mock_handler.assert_called_once_with(req)


@pytest.mark.asyncio
async def test_send_message_uses_original_when_disabled():
    """验证 agno_enabled=False 时使用原始非流式路径"""
    from app.routers.chat import send_message
    from app.schemas import ChatSendRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = False
        mock_settings.rag_enabled = False
        mock_settings.llm_mode = "mock"
        mock_settings.persist_chat_messages = False
        with patch("app.routers.chat.get_llm_client") as mock_get_llm:
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock(return_value="原始回复")
            mock_get_llm.return_value = mock_client
            with patch("app.routers.chat.nlu_engine") as mock_nlu:
                mock_nlu.parse.return_value = MagicMock(
                    intent="GREETING", entities={}, is_emergency=False,
                    emotion={"level": "neutral", "score": 0}
                )
                with patch("app.routers.chat.memory_manager") as mock_mem:
                    mock_mem.should_ask_weight.return_value = False
                    mock_mem.should_ask_bp.return_value = False
                    with patch("app.routers.chat.db_call") as mock_db_call:
                        mock_db_call.return_value = ""
                        req = ChatSendRequest(
                            pregnant_id="test-pid",
                            message="你好",
                        )
                        resp = await send_message(req)
                        assert resp.content == "原始回复"


@pytest.mark.asyncio
async def test_send_message_agno_does_not_save_conversation():
    """验证 agno_enabled=True & persist_chat_messages=False 时不入库"""
    from app.routers.chat import send_message
    from app.schemas import ChatSendRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = True
        mock_settings.persist_chat_messages = False
        with patch("app.core.agno_chat_handler.handle_chat_with_agno") as mock_handler:
            mock_handler.return_value = MagicMock(
                content="不回写",
                session_id="test-sess",
                source="AI_CARE",
            )
            with patch("app.core.agno_chat_handler.conversation_store") as mock_store:
                req = ChatSendRequest(pregnant_id="test-pid", message="你好")
                await send_message(req)
                mock_store.async_save_single.assert_not_called()


@pytest.mark.asyncio
async def test_send_message_original_does_not_save_conversation():
    """验证 agno_enabled=False & persist_chat_messages=False 时不入库"""
    from app.routers.chat import send_message
    from app.schemas import ChatSendRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = False
        mock_settings.rag_enabled = False
        mock_settings.llm_mode = "mock"
        mock_settings.persist_chat_messages = False
        with patch("app.routers.chat.get_llm_client") as mock_get_llm:
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock(return_value="不回写回复")
            mock_get_llm.return_value = mock_client
            with patch("app.routers.chat.nlu_engine") as mock_nlu:
                mock_nlu.parse.return_value = MagicMock(
                    intent="GREETING", entities={}, is_emergency=False,
                    emotion={"level": "neutral", "score": 0}
                )
                with patch("app.routers.chat.memory_manager") as mock_mem:
                    mock_mem.should_ask_weight.return_value = False
                    mock_mem.should_ask_bp.return_value = False
                    with patch("app.routers.chat.db_call") as mock_db_call:
                        mock_db_call.return_value = ""
                        with patch("app.routers.chat.conversation_store") as mock_store:
                            req = ChatSendRequest(pregnant_id="test-pid", message="你好")
                            await send_message(req)
                            mock_store.async_save_single.assert_not_called()
