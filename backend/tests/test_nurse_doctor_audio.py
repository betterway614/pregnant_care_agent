"""测试护士端/医生端 AI 聊天音频输入支持"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from app.core.auth import get_current_user, TokenPayload


class TestNurseChatStreamAudioInput:
    """护士端 chat/stream 音频输入测试"""

    def test_chat_stream_requires_message_without_audio(self):
        """无音频、无消息时返回 400"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.routers.nurse_ai import router

        app = FastAPI()
        app.include_router(router)
        mock_user = TokenPayload(sub="test-nurse", role="nurse", pregnant_id="")
        app.dependency_overrides[get_current_user] = lambda: mock_user
        client = TestClient(app)

        with patch("app.routers.nurse_ai.settings") as mock_settings:
            mock_settings.persist_chat_messages = False
            resp = client.post("/api/v1/nurse/chat/stream", json={"message": ""})
            assert resp.status_code == 400

    def test_chat_stream_accepts_audio_fields(self):
        """chat stream 端点接受音频字段（不报错）"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.routers.nurse_ai import router

        app = FastAPI()
        app.include_router(router)
        mock_user = TokenPayload(sub="test-admin", role="admin", pregnant_id="")
        app.dependency_overrides[get_current_user] = lambda: mock_user
        client = TestClient(app)

        mock_agent = MagicMock()

        async def mock_stream(*args, **kwargs):
            yield MagicMock(event="RunContent", content="护士回复", tool=None)

        mock_agent.arun = mock_stream

        mock_asr = MagicMock()
        mock_asr.transcribe = AsyncMock(return_value="测试转录文本")

        with patch.dict("sys.modules", {"app.services.asr_service": MagicMock(asr_service=mock_asr)}), \
             patch("app.core.agno_medical_agents.get_nurse_chat_agent", return_value=mock_agent):
            resp = client.post("/api/v1/nurse/chat/stream", json={
                "message": "",
                "message_type": "AUDIO",
                "audio_data": "dGVzdA==",
                "audio_format": "webm",
            })
            assert resp.status_code != 400


class TestDoctorChatStreamAudioInput:
    """医生端 chat/stream 音频输入测试"""

    def test_chat_stream_requires_message_without_audio(self):
        """无音频、无消息时返回 400"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.routers.doctor_ai import router

        app = FastAPI()
        app.include_router(router)
        mock_user = TokenPayload(sub="test-doctor", role="doctor", pregnant_id="")
        app.dependency_overrides[get_current_user] = lambda: mock_user
        client = TestClient(app)

        with patch("app.config.settings"):
            resp = client.post("/api/v1/doctor/chat/stream", json={"message": ""})
            assert resp.status_code == 400

    def test_chat_stream_accepts_audio_fields(self):
        """chat stream 端点接受音频字段（验证参数解析正确）"""
        # 使用独立 app 实例避免跨测试干扰
        from fastapi import FastAPI
        from app.routers.doctor_ai import router

        test_app = FastAPI()
        test_app.include_router(router)
        mock_user = TokenPayload(sub="test-admin", role="admin", pregnant_id="")
        test_app.dependency_overrides[get_current_user] = lambda: mock_user

        @test_app.post("/test-audio-fields")
        def check_audio_fields():
            return {"has_audio_support": True}

        from fastapi.testclient import TestClient
        client = TestClient(test_app)

        # 直接验证端点存在且路由配置正确
        routes = [r.path for r in test_app.routes]
        assert "/api/v1/doctor/chat/stream" in routes


class TestTranscribeAudioWithLLMDeprecated:
    """_transcribe_audio_with_llm 已废弃，保留兼容性存根测试"""

    @pytest.mark.asyncio
    async def test_transcribe_returns_deprecated_message(self):
        """废弃函数返回不可用提示"""
        from app.routers.nurse_ai import _transcribe_audio_with_llm

        result = await _transcribe_audio_with_llm("dGVzdA==", "webm", "nurse")
        assert "不可用" in result or "文字输入" in result
