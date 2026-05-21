"""测试 ASR 服务"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestASRServiceLLMMode:
    """ASR llm 模式测试（默认行为）"""

    @pytest.mark.asyncio
    async def test_llm_mode_returns_none(self):
        """llm 模式返回 None，表示由调用方使用多模态 LLM"""
        from app.services.asr_service import ASRService

        service = ASRService()
        with patch("app.services.asr_service.get_asr_mode", return_value="llm"):
            result = await service.transcribe("dGVzdA==", "webm", "pregnant")
            assert result is None

    @pytest.mark.asyncio
    async def test_llm_mode_nurse(self):
        """llm 模式护士端同样返回 None"""
        from app.services.asr_service import ASRService

        service = ASRService()
        with patch("app.services.asr_service.get_asr_mode", return_value="llm"):
            result = await service.transcribe("dGVzdA==", "webm", "nurse")
            assert result is None

    @pytest.mark.asyncio
    async def test_llm_mode_doctor(self):
        """llm 模式医生端同样返回 None"""
        from app.services.asr_service import ASRService

        service = ASRService()
        with patch("app.services.asr_service.get_asr_mode", return_value="llm"):
            result = await service.transcribe("dGVzdA==", "webm", "doctor")
            assert result is None


class TestASRServiceCloudMode:
    """ASR cloud 模式测试"""

    @pytest.mark.asyncio
    async def test_cloud_calls_dashscope(self):
        """cloud 模式调用 DashScope Paraformer API"""
        from app.services.asr_service import ASRService

        service = ASRService()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {
                "results": [{"transcription_url": "https://example.com/result"}]
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_t_response = MagicMock()
        mock_t_response.json.return_value = {
            "transcripts": [{"text": "你好医生"}]
        }

        with patch("app.services.asr_service.get_asr_mode", return_value="cloud"), \
             patch("app.services.asr_service.settings") as mock_settings:
            mock_settings.asr_cloud_api_key = "test-key"
            mock_settings.asr_cloud_base_url = "https://dashscope.aliyuncs.com/api/v1"
            mock_settings.asr_cloud_model = "paraformer-v2"
            mock_settings.llm_api_key = "fallback-key"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.get.return_value = mock_t_response
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await service.transcribe("dGVzdA==", "webm", "pregnant")
                assert result == "你好医生"

    @pytest.mark.asyncio
    async def test_cloud_no_api_key_returns_none(self):
        """cloud 模式无 API Key 时返回 None"""
        from app.services.asr_service import ASRService

        service = ASRService()
        with patch("app.services.asr_service.get_asr_mode", return_value="cloud"), \
             patch("app.services.asr_service.settings") as mock_settings:
            mock_settings.asr_cloud_api_key = ""
            mock_settings.llm_api_key = ""

            result = await service.transcribe("dGVzdA==", "webm", "pregnant")
            assert result is None


class TestASRServiceUnknownMode:
    """ASR 未知模式降级测试"""

    @pytest.mark.asyncio
    async def test_unknown_mode_returns_none(self):
        """未知模式降级为 llm，返回 None"""
        from app.services.asr_service import ASRService

        service = ASRService()
        with patch("app.services.asr_service.get_asr_mode", return_value="unknown"):
            result = await service.transcribe("dGVzdA==", "webm", "pregnant")
            assert result is None


class TestASRModeResolver:
    """ASR 模式解析测试"""

    def test_role_specific_mode_takes_priority(self):
        """角色专属模式优先于全局模式"""
        from app.config import Settings, get_asr_mode

        with patch("app.config.settings") as mock_settings:
            mock_settings.asr_mode = "llm"
            mock_settings.asr_nurse_mode = "cloud"
            mode = get_asr_mode("nurse")
            assert mode == "cloud"

    def test_empty_role_mode_falls_back_to_global(self):
        """空角色模式降级到全局模式"""
        from app.config import Settings, get_asr_mode

        with patch("app.config.settings") as mock_settings:
            mock_settings.asr_mode = "cloud"
            mock_settings.asr_nurse_mode = ""
            mode = get_asr_mode("nurse")
            assert mode == "cloud"

    def test_default_mode_is_llm(self):
        """默认模式为 llm"""
        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.asr_mode == "llm"
