"""测试 ASR 服务"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestASRServiceCloudMode:
    """ASR cloud 模式测试"""

    @pytest.mark.asyncio
    async def test_cloud_calls_dashscope(self):
        """cloud 模式调用 DashScope Paraformer API"""
        from app.services.asr_service import ASRService

        service = ASRService()
        mock_submit_response = MagicMock()
        mock_submit_response.json.return_value = {"output": {"task_id": "task-123"}}
        mock_submit_response.raise_for_status = MagicMock()

        mock_query_response = MagicMock()
        mock_query_response.json.return_value = {
            "output": {
                "task_status": "SUCCEEDED",
                "results": [{"text": "你好医生"}],
            }
        }
        mock_query_response.raise_for_status = MagicMock()

        with (
            patch("app.services.asr_service.get_asr_mode", return_value="cloud"),
            patch("app.services.asr_service.settings") as mock_settings,
            patch("app.services.asr_service.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_settings.asr_cloud_api_key = "test-key"
            mock_settings.asr_cloud_base_url = "https://dashscope.aliyuncs.com/api/v1"
            mock_settings.asr_cloud_model = "paraformer-v2"
            mock_settings.llm_api_key = "fallback-key"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_submit_response
                mock_client.get.return_value = mock_query_response
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await service.transcribe("dGVzdA==", "webm", "pregnant")
                assert result == "你好医生"

    @pytest.mark.asyncio
    async def test_cloud_no_api_key_returns_none(self):
        """cloud 模式无 API Key 时返回 None"""
        from app.services.asr_service import ASRService

        service = ASRService()
        with (
            patch("app.services.asr_service.get_asr_mode", return_value="cloud"),
            patch("app.services.asr_service.settings") as mock_settings,
        ):
            mock_settings.asr_cloud_api_key = ""
            mock_settings.llm_api_key = ""

            result = await service.transcribe("dGVzdA==", "webm", "pregnant")
            assert result is None


class TestASRServiceLocalFunASR:
    """ASR local FunASR API 模式测试"""

    @pytest.mark.asyncio
    async def test_local_calls_funasr_openai_endpoint(self):
        """local 模式默认调用 FunASR OpenAI 风格转录接口"""
        from app.services.asr_service import ASRService

        service = ASRService()
        mock_response = MagicMock()
        mock_response.json.return_value = {"text": "本地识别结果"}
        mock_response.raise_for_status = MagicMock()

        with (
            patch("app.services.asr_service.get_asr_mode", return_value="local"),
            patch("app.services.asr_service.settings") as mock_settings,
        ):
            mock_settings.asr_local_backend = "funasr"
            mock_settings.asr_local_base_url = "http://127.0.0.1:10096"
            mock_settings.asr_local_endpoint = "/v1/audio/transcriptions"
            mock_settings.asr_local_funasr_model = "local-funasr"
            mock_settings.asr_local_api_key = ""
            mock_settings.asr_local_hotword = ""
            mock_settings.asr_local_timeout = 60.0

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await service.transcribe("dGVzdA==", "webm", "pregnant")

        assert result == "本地识别结果"
        _, kwargs = mock_client.post.call_args
        assert kwargs["data"]["model"] == "local-funasr"
        assert "file" in kwargs["files"]
        filename, content, mime_type = kwargs["files"]["file"]
        assert filename == "audio.webm"
        assert content == b"test"
        assert mime_type == "audio/webm"

    @pytest.mark.asyncio
    async def test_local_calls_funasr_recognition_endpoint(self):
        """local 模式也兼容 FunASR /recognition 接口"""
        from app.services.asr_service import ASRService

        service = ASRService()
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "text": "识别成功"}
        mock_response.raise_for_status = MagicMock()

        with (
            patch("app.services.asr_service.get_asr_mode", return_value="local"),
            patch("app.services.asr_service.settings") as mock_settings,
        ):
            mock_settings.asr_local_backend = "funasr"
            mock_settings.asr_local_base_url = "http://127.0.0.1:10096"
            mock_settings.asr_local_endpoint = "/recognition"
            mock_settings.asr_local_funasr_model = "local-funasr"
            mock_settings.asr_local_api_key = ""
            mock_settings.asr_local_hotword = "产检"
            mock_settings.asr_local_timeout = 60.0

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await service.transcribe("dGVzdA==", "wav", "pregnant")

        assert result == "识别成功"
        _, kwargs = mock_client.post.call_args
        assert kwargs["data"]["hotword"] == "产检"
        assert "audio" in kwargs["files"]


class TestASRServiceUnknownMode:
    """ASR 未知模式降级测试"""

    @pytest.mark.asyncio
    async def test_unknown_mode_returns_none(self):
        """未知模式返回 None"""
        from app.services.asr_service import ASRService

        service = ASRService()
        with patch("app.services.asr_service.get_asr_mode", return_value="unknown"):
            result = await service.transcribe("dGVzdA==", "webm", "pregnant")
            assert result is None


class TestASRModeResolver:
    """ASR 模式解析测试"""

    def test_role_specific_mode_takes_priority(self):
        """角色专属模式优先于全局模式"""
        from app.config import get_asr_mode

        with patch("app.config.settings") as mock_settings:
            mock_settings.asr_mode = "cloud"
            mock_settings.asr_nurse_mode = "local"
            mode = get_asr_mode("nurse")
            assert mode == "local"

    def test_empty_role_mode_falls_back_to_global(self):
        """空角色模式降级到全局模式"""
        from app.config import get_asr_mode

        with patch("app.config.settings") as mock_settings:
            mock_settings.asr_mode = "cloud"
            mock_settings.asr_nurse_mode = ""
            mode = get_asr_mode("nurse")
            assert mode == "cloud"

    def test_default_mode_is_cloud(self):
        """默认模式为 cloud（使用 DashScope Paraformer 专用 ASR 服务）"""
        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.asr_mode == "cloud"
        assert s.asr_local_backend == "funasr"
        assert s.asr_local_base_url == "http://127.0.0.1:10096"
