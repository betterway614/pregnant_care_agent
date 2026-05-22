"""测试 Agno 模型适配器"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import app.core.agno_client as client_module
from app.core.agno_client import get_agno_model, reset_agno_client


def _clear_cache():
    client_module._model_cache.clear()


def test_get_agno_model_cloud():
    _clear_cache()
    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "cloud"
        mock_settings.llm_pregnant_mode = "cloud"
        mock_settings.llm_nurse_mode = "cloud"
        mock_settings.llm_doctor_mode = "cloud"
        mock_settings.llm_pregnant_model = ""
        mock_settings.llm_nurse_model = ""
        mock_settings.llm_doctor_model = ""
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_base_url = "https://api.test.com/v1"
        mock_settings.llm_model = "deepseek-chat"
        model = get_agno_model()
        assert model is not None


def test_get_agno_model_local():
    _clear_cache()
    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "local"
        mock_settings.llm_pregnant_mode = "local"
        mock_settings.llm_nurse_mode = "local"
        mock_settings.llm_doctor_mode = "local"
        mock_settings.llm_pregnant_model = ""
        mock_settings.llm_nurse_model = ""
        mock_settings.llm_doctor_model = ""
        mock_settings.ollama_host = "http://localhost:11434"
        mock_settings.local_model = "qwen2.5:7b"
        mock_settings.llm_model = "qwen2.5:7b"
        model = get_agno_model(role="doctor")
        assert model is not None


def test_get_agno_model_cached_by_role():
    _clear_cache()
    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "mock"
        mock_settings.llm_pregnant_mode = "mock"
        mock_settings.llm_nurse_mode = "mock"
        mock_settings.llm_doctor_mode = "mock"
        mock_settings.llm_pregnant_model = ""
        mock_settings.llm_nurse_model = ""
        mock_settings.llm_doctor_model = ""
        mock_settings.llm_model = "mock"
        m1 = get_agno_model("pregnant")
        m2 = get_agno_model("pregnant")
        m3 = get_agno_model("nurse")
        assert m1 is m2
        assert m1 is not m3


def test_reset_agno_client_clears_cache():
    _clear_cache()
    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "mock"
        mock_settings.llm_pregnant_mode = "mock"
        mock_settings.llm_nurse_mode = "mock"
        mock_settings.llm_doctor_mode = "mock"
        mock_settings.llm_pregnant_model = ""
        mock_settings.llm_nurse_model = ""
        mock_settings.llm_doctor_model = ""
        mock_settings.llm_model = "mock"
        get_agno_model()
        assert "pregnant" in client_module._model_cache
        reset_agno_client()
        assert client_module._model_cache == {}


def test_cloud_without_api_key_falls_back_to_mock():
    _clear_cache()
    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "cloud"
        mock_settings.llm_pregnant_mode = ""
        mock_settings.llm_nurse_mode = ""
        mock_settings.llm_doctor_mode = ""
        mock_settings.llm_pregnant_model = ""
        mock_settings.llm_nurse_model = ""
        mock_settings.llm_doctor_model = ""
        mock_settings.llm_api_key = ""
        mock_settings.llm_base_url = "https://api.test.com/v1"
        mock_settings.llm_model = "test-model"
        mock_settings.llm_pregnant_temperature = 0.7
        mock_settings.llm_nurse_temperature = 0.3
        mock_settings.llm_doctor_temperature = 0.3
        mock_settings.llm_pregnant_max_tokens = 2048
        mock_settings.llm_nurse_max_tokens = 4096
        mock_settings.llm_doctor_max_tokens = 4096
        model = get_agno_model()
        assert getattr(model, "id", None) == "mock-model"
