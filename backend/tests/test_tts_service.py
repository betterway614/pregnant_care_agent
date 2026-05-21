"""测试 TTS 服务"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTTSServiceBrowserMode:
    """TTS browser 模式测试（默认行为）"""

    @pytest.mark.asyncio
    async def test_browser_mode_returns_none(self):
        """browser 模式返回 None，表示由前端处理"""
        from app.services.tts_service import TTSService

        service = TTSService()
        with patch("app.services.tts_service.get_tts_mode", return_value="browser"):
            result = await service.synthesize("你好", "pregnant")
            assert result is None


class TestTTSServiceLocalMode:
    """TTS local 模式测试（edge-tts）"""

    def test_local_mode_service_creation(self):
        """local 模式服务可正常创建"""
        from app.services.tts_service import TTSService
        service = TTSService()
        assert service is not None

    def test_local_mode_with_edge_tts(self):
        """local 模式可调用 edge-tts（验证依赖存在）"""
        import importlib
        assert importlib.util.find_spec("edge_tts") is not None, "edge-tts 未安装"


class TestTTSServiceUnknownMode:
    """TTS 未知模式降级测试"""

    @pytest.mark.asyncio
    async def test_unknown_mode_returns_none(self):
        """未知模式降级为 browser，返回 None"""
        from app.services.tts_service import TTSService

        service = TTSService()
        with patch("app.services.tts_service.get_tts_mode", return_value="unknown"):
            result = await service.synthesize("你好", "pregnant")
            assert result is None


class TestTTSModeResolver:
    """TTS 模式解析测试"""

    def test_role_specific_mode_takes_priority(self):
        """角色专属模式优先于全局模式"""
        from app.config import get_tts_mode

        with patch("app.config.settings") as mock_settings:
            mock_settings.tts_mode = "browser"
            mock_settings.tts_doctor_mode = "local"
            mode = get_tts_mode("doctor")
            assert mode == "local"

    def test_empty_role_mode_falls_back_to_global(self):
        """空角色模式降级到全局模式"""
        from app.config import get_tts_mode

        with patch("app.config.settings") as mock_settings:
            mock_settings.tts_mode = "local"
            mock_settings.tts_pregnant_mode = ""
            mode = get_tts_mode("pregnant")
            assert mode == "local"

    def test_default_mode_is_browser(self):
        """默认模式为 browser"""
        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.tts_mode == "browser"


class TestTTSRouterConfig:
    """TTS 路由配置端点测试"""

    def test_config_endpoint_browser_mode(self):
        """browser 模式下 /config 返回 available=false"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.routers.tts import router

        app = FastAPI()
        app.include_router(router)

        with patch("app.routers.tts.get_tts_mode", return_value="browser"):
            client = TestClient(app)
            resp = client.get("/api/v1/tts/config?role=pregnant")
            assert resp.status_code == 200
            data = resp.json()
            assert data["mode"] == "browser"
            assert data["available"] is False

    def test_config_endpoint_local_mode(self):
        """local 模式下 /config 返回 available=true"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.routers.tts import router

        app = FastAPI()
        app.include_router(router)

        with patch("app.routers.tts.get_tts_mode", return_value="local"):
            client = TestClient(app)
            resp = client.get("/api/v1/tts/config?role=pregnant")
            assert resp.status_code == 200
            data = resp.json()
            assert data["mode"] == "local"
            assert data["available"] is True

    def test_synthesize_empty_text_returns_400(self):
        """空文本请求返回 400"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.routers.tts import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        resp = client.post("/api/v1/tts/synthesize", json={"text": "", "role": "pregnant"})
        assert resp.status_code == 400
