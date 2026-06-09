"""测试小安对话 ASR 预处理 + /chat/asr 端点 + 流式对话 ASR 集成"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.auth import get_current_user, TokenPayload

# 测试用音频数据
TEST_AUDIO_B64 = "dGVzdA=="  # "test" 的 base64
TEST_AUDIO_FORMAT = "webm"


# ======================================================================
# 单元测试：_transcribe_audio_pregnant
# ======================================================================

class TestTranscribePregnant:
    """_transcribe_audio_pregnant 测试"""

    @pytest.mark.asyncio
    async def test_cloud_mode_calls_asr_service(self):
        """cloud 模式应调用 asr_service.transcribe 并返回转录文本"""
        from app.core.agno_chat_handler import _transcribe_audio_pregnant

        with patch("app.core.agno_chat_handler.get_asr_mode", return_value="cloud"):
            with patch("app.services.asr_service.asr_service") as mock_asr:
                mock_asr.transcribe = AsyncMock(return_value="你好医生")
                with patch("app.services.asr_service.asr_service", mock_asr):
                    result = await _transcribe_audio_pregnant(TEST_AUDIO_B64, TEST_AUDIO_FORMAT)
                    assert result == "你好医生"

    @pytest.mark.asyncio
    async def test_local_mode_calls_asr_service(self):
        """local 模式应调用 asr_service.transcribe 并返回转录文本"""
        from app.core.agno_chat_handler import _transcribe_audio_pregnant

        with patch("app.core.agno_chat_handler.get_asr_mode", return_value="local"):
            mock_asr = MagicMock()
            mock_asr.transcribe = AsyncMock(return_value="本地转录结果")
            with patch.dict("sys.modules", {"app.services.asr_service": MagicMock(asr_service=mock_asr)}):
                result = await _transcribe_audio_pregnant(TEST_AUDIO_B64, TEST_AUDIO_FORMAT)
                assert result == "本地转录结果"

    @pytest.mark.asyncio
    async def test_asr_failure_returns_error_text(self):
        """ASR 转录失败时返回错误提示文本"""
        from app.core.agno_chat_handler import _transcribe_audio_pregnant

        with patch("app.core.agno_chat_handler.get_asr_mode", return_value="cloud"):
            mock_asr = MagicMock()
            mock_asr.transcribe = AsyncMock(return_value=None)
            with patch.dict("sys.modules", {"app.services.asr_service": MagicMock(asr_service=mock_asr)}):
                result = await _transcribe_audio_pregnant(TEST_AUDIO_B64, TEST_AUDIO_FORMAT)
                assert "语音识别失败" in result


# ======================================================================
# 单元测试：_build_multimodal_input 带 transcribed_text 参数
# ======================================================================

class TestBuildMultimodalInputWithASR:
    """_build_multimodal_input AUDIO 始终使用转录文本测试"""

    def test_transcribed_text_returns_plain_string(self):
        """有 transcribed_text 时应返回纯文本字符串"""
        from app.core.agno_chat_handler import _build_multimodal_input
        from app.schemas import ChatSendRequest

        req = ChatSendRequest(
            pregnant_id="test-pid",
            message="请听取以下语音并给出回复",
            message_type="AUDIO",
            audio_data=TEST_AUDIO_B64,
            audio_format=TEST_AUDIO_FORMAT,
        )
        result = _build_multimodal_input(req, transcribed_text="你好，我想问一下产检的事")
        assert result == "你好，我想问一下产检的事"
        assert isinstance(result, str)

    def test_no_transcribed_text_returns_error_text(self):
        """AUDIO 类型 transcribed_text 为 None 时应返回错误提示文本"""
        from app.core.agno_chat_handler import _build_multimodal_input
        from app.schemas import ChatSendRequest

        req = ChatSendRequest(
            pregnant_id="test-pid",
            message="请听取以下语音并给出回复",
            message_type="AUDIO",
            audio_data=TEST_AUDIO_B64,
            audio_format=TEST_AUDIO_FORMAT,
        )
        result = _build_multimodal_input(req, transcribed_text=None)
        assert isinstance(result, str)
        assert "语音识别失败" in result

    def test_text_message_ignores_transcribed_text(self):
        """纯文本消息不受 transcribed_text 参数影响"""
        from app.core.agno_chat_handler import _build_multimodal_input
        from app.schemas import ChatSendRequest

        req = ChatSendRequest(
            pregnant_id="test-pid",
            message="你好",
            message_type="TEXT",
        )
        result = _build_multimodal_input(req, transcribed_text="不应该出现")
        assert result == "你好"

    def test_image_message_ignores_transcribed_text(self):
        """图片消息忽略 transcribed_text，返回文本字符串（图片通过 _build_images 单独传递）"""
        from app.core.agno_chat_handler import _build_multimodal_input
        from app.schemas import ChatSendRequest

        req = ChatSendRequest(
            pregnant_id="test-pid",
            message="请分析这张图片",
            message_type="IMAGE",
            audio_data=TEST_AUDIO_B64,
            audio_format="jpeg",
        )
        result = _build_multimodal_input(req, transcribed_text="图片描述文字")
        assert isinstance(result, str)
        assert "图片" in result


# ======================================================================
# 集成测试：/chat/asr 端点
# ======================================================================

class TestChatASREndpoint:
    """POST /api/v1/chat/asr 端点集成测试"""

    def _make_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routers.chat import router

        app = FastAPI()
        app.include_router(router)
        mock_user = TokenPayload(sub="test-admin", role="admin", pregnant_id="")
        app.dependency_overrides[get_current_user] = lambda: mock_user
        return TestClient(app)

    def test_asr_endpoint_success(self):
        """ASR 端点返回转录文本"""
        client = self._make_client()

        with patch("app.core.agno_chat_handler._transcribe_audio_pregnant",
                   new_callable=AsyncMock, return_value="你好医生"):
            resp = client.post("/api/v1/chat/asr", json={
                "audio_data": TEST_AUDIO_B64,
                "audio_format": TEST_AUDIO_FORMAT,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["text"] == "你好医生"
            assert data["success"] is True

    def test_asr_endpoint_failure(self):
        """转录失败时返回 success=false"""
        client = self._make_client()

        with patch("app.core.agno_chat_handler._transcribe_audio_pregnant",
                   new_callable=AsyncMock, return_value="（语音识别失败，请重试或使用文字输入）"):
            resp = client.post("/api/v1/chat/asr", json={
                "audio_data": TEST_AUDIO_B64,
                "audio_format": TEST_AUDIO_FORMAT,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False

    def test_asr_endpoint_default_format(self):
        """不传 audio_format 时默认为 webm"""
        client = self._make_client()

        with patch("app.core.agno_chat_handler._transcribe_audio_pregnant",
                   new_callable=AsyncMock, return_value="转录文本") as mock_asr:
            resp = client.post("/api/v1/chat/asr", json={
                "audio_data": TEST_AUDIO_B64,
            })
            assert resp.status_code == 200
            mock_asr.assert_called_once_with(TEST_AUDIO_B64, "webm")


# ======================================================================
# 集成测试：handle_chat_with_agno_stream ASR 预处理
# ======================================================================

class TestStreamWithASRPreprocessing:
    """handle_chat_with_agno_stream ASR 预处理集成测试"""

    @pytest.mark.asyncio
    async def test_audio_with_asr_returns_transcribed_text_in_done(self):
        """音频消息 ASR 转录后，done 事件应包含 transcribed_text"""
        from app.core.agno_chat_handler import handle_chat_with_agno_stream
        from app.schemas import ChatSendRequest

        mock_agent = MagicMock()

        async def mock_arun(*args, **kwargs):
            yield MagicMock(event="RunContent", content="小安回复", tool=None)

        mock_agent.arun = mock_arun

        req = ChatSendRequest(
            pregnant_id="test-pid-12345",
            message="请听取以下语音并给出回复",
            session_id="test-sess",
            message_type="AUDIO",
            audio_data=TEST_AUDIO_B64,
            audio_format=TEST_AUDIO_FORMAT,
        )

        with patch("app.core.agno_chat_handler._transcribe_audio_pregnant",
                   new_callable=AsyncMock, return_value="我想问一下产检时间"), \
             patch("app.core.agno_agent.AGENT_VARIANT_MAP", {"complex": lambda: mock_agent}), \
             patch("app.core.agno_chat_handler.settings") as mock_settings:
            mock_settings.persist_chat_messages = False

            events = []
            async for event in handle_chat_with_agno_stream(req):
                events.append(event)

            event_types = [e["event"] for e in events]
            assert "thinking" in event_types
            assert "done" in event_types

            done_event = [e for e in events if e["event"] == "done"][0]
            import json
            done_data = json.loads(done_event["data"])
            assert done_data["transcribed_text"] == "我想问一下产检时间"

    @pytest.mark.asyncio
    async def test_text_message_no_asr(self):
        """纯文本消息不触发 ASR 预处理"""
        from app.core.agno_chat_handler import handle_chat_with_agno_stream
        from app.schemas import ChatSendRequest

        mock_agent = MagicMock()

        async def mock_arun(*args, **kwargs):
            yield MagicMock(event="RunContent", content="回复", tool=None)

        mock_agent.arun = mock_arun

        req = ChatSendRequest(
            pregnant_id="test-pid-12345",
            message="你好",
            session_id="test-sess",
            message_type="TEXT",
        )

        with patch("app.core.agno_chat_handler._transcribe_audio_pregnant",
                   new_callable=AsyncMock) as mock_asr, \
             patch("app.core.agno_agent.AGENT_VARIANT_MAP", {"complex": lambda: mock_agent}), \
             patch("app.core.agno_chat_handler.settings") as mock_settings:
            mock_settings.persist_chat_messages = False

            events = []
            async for event in handle_chat_with_agno_stream(req):
                events.append(event)

            mock_asr.assert_not_called()

    @pytest.mark.asyncio
    async def test_audio_asr_failure_returns_error_text_to_agent(self):
        """ASR 转录失败时 agent 收到错误提示文本"""
        from app.core.agno_chat_handler import handle_chat_with_agno_stream
        from app.schemas import ChatSendRequest

        mock_agent = MagicMock()

        async def mock_arun(*args, **kwargs):
            input_arg = kwargs.get("input") or (args[0] if args else None)
            assert isinstance(input_arg, str)
            assert "语音识别失败" in input_arg
            yield MagicMock(event="RunContent", content="回复", tool=None)

        mock_agent.arun = mock_arun

        req = ChatSendRequest(
            pregnant_id="test-pid-12345",
            message="请听取以下语音并给出回复",
            session_id="test-sess",
            message_type="AUDIO",
            audio_data=TEST_AUDIO_B64,
            audio_format=TEST_AUDIO_FORMAT,
        )

        with patch("app.core.agno_chat_handler._transcribe_audio_pregnant",
                   new_callable=AsyncMock,
                   return_value="（语音识别失败，请重试或使用文字输入）"), \
             patch("app.core.agno_agent.AGENT_VARIANT_MAP", {"complex": lambda: mock_agent}), \
             patch("app.core.agno_chat_handler.settings") as mock_settings:
            mock_settings.persist_chat_messages = False

            events = []
            async for event in handle_chat_with_agno_stream(req):
                events.append(event)

            done_event = [e for e in events if e["event"] == "done"][0]
            import json
            done_data = json.loads(done_event["data"])
            assert done_data["transcribed_text"] == "（语音识别失败，请重试或使用文字输入）"


# ======================================================================
# 集成测试：handle_chat_with_agno 非流式 ASR 预处理
# ======================================================================

class TestNonStreamWithASRPreprocessing:
    """handle_chat_with_agno 非流式 ASR 预处理测试"""

    @pytest.mark.asyncio
    async def test_audio_uses_transcribed_text(self):
        """音频消息使用 ASR 转录文本作为 agent input"""
        from app.core.agno_chat_handler import handle_chat_with_agno
        from app.schemas import ChatSendRequest

        mock_agent = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "小安回复"
        mock_agent.arun = AsyncMock(return_value=mock_response)

        req = ChatSendRequest(
            pregnant_id="test-pid-12345",
            message="请听取以下语音并给出回复",
            session_id="test-sess",
            message_type="AUDIO",
            audio_data=TEST_AUDIO_B64,
            audio_format=TEST_AUDIO_FORMAT,
        )

        with patch("app.core.agno_chat_handler._transcribe_audio_pregnant",
                   new_callable=AsyncMock, return_value="产检时间是什么时候"), \
             patch("app.core.agno_agent.AGENT_VARIANT_MAP", {"complex": lambda: mock_agent}), \
             patch("app.core.agno_chat_handler.settings") as mock_settings, \
             patch("app.core.nlu_engine.nlu_engine.parse", side_effect=RuntimeError("NLU mock")):
            mock_settings.persist_chat_messages = False

            resp = await handle_chat_with_agno(req)

            call_kwargs = mock_agent.arun.call_args
            agent_input = call_kwargs.kwargs.get("input") or call_kwargs.args[0]
            assert agent_input == "产检时间是什么时候"
            assert resp.content == "小安回复"


# ======================================================================
# 配置测试：asr_pregnant_mode 默认值
# ======================================================================

class TestASRPregnantConfig:
    """asr_pregnant_mode 配置测试"""

    def test_default_pregnant_mode_is_empty(self):
        """asr_pregnant_mode 默认值应为空（跟随全局 asr_mode）"""
        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.asr_pregnant_mode == ""

    def test_pregnant_mode_priority_over_global(self):
        """pregnant 角色模式应优先于全局模式"""
        from app.config import get_asr_mode

        with patch("app.config.settings") as mock_settings:
            mock_settings.asr_mode = "cloud"
            mock_settings.asr_pregnant_mode = "local"
            mode = get_asr_mode("pregnant")
            assert mode == "local"

    def test_empty_pregnant_mode_falls_back_to_global(self):
        """pregnant 模式为空时降级到全局模式"""
        from app.config import get_asr_mode

        with patch("app.config.settings") as mock_settings:
            mock_settings.asr_mode = "local"
            mock_settings.asr_pregnant_mode = ""
            mode = get_asr_mode("pregnant")
            assert mode == "local"
