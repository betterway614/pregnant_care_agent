"""测试 Chat Router Agno 集成"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from app.core.auth import TokenPayload


@pytest.mark.asyncio
async def test_send_message_uses_agno_handler():
    """验证 send_message 委托给 handle_chat_with_agno"""
    from app.routers.chat import send_message
    from app.schemas import ChatSendRequest

    mock_user = TokenPayload(sub="test-admin", role="admin", pregnant_id="")

    with patch("app.routers.chat.handle_chat_with_agno") as mock_handler:
        mock_handler.return_value = MagicMock(
            content="Agno回复",
            session_id="test-sess",
            source="AI_CARE",
        )
        req = ChatSendRequest(pregnant_id="test-pid", message="你好")
        resp = await send_message(req, user=mock_user)
        assert resp.content == "Agno回复"
        mock_handler.assert_called_once_with(req)


@pytest.mark.asyncio
async def test_send_message_agno_does_not_save_conversation():
    """验证 persist_chat_messages=False 时不入库"""
    from app.routers.chat import send_message
    from app.schemas import ChatSendRequest

    mock_user = TokenPayload(sub="test-admin", role="admin", pregnant_id="")

    with patch("app.core.agno_chat_handler.settings") as mock_settings:
        mock_settings.persist_chat_messages = False
        with patch("app.routers.chat.handle_chat_with_agno") as mock_handler:
            mock_handler.return_value = MagicMock(
                content="不回写",
                session_id="test-sess",
                source="AI_CARE",
            )
            with patch("app.core.agno_chat_handler.conversation_store") as mock_store:
                req = ChatSendRequest(pregnant_id="test-pid", message="你好")
                await send_message(req, user=mock_user)
                mock_store.async_save_single.assert_not_called()
