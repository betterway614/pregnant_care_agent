"""测试 Agno 配置项"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Settings


def test_agno_config_defaults():
    """验证默认配置值"""
    s = Settings()
    assert s.agno_enabled is False
    assert s.agno_model_id == "gpt-4o"
    assert s.agno_knowledge_dir == "data/knowledge"


def test_agno_config_from_env(monkeypatch):
    """验证环境变量覆盖"""
    monkeypatch.setenv("AGNO_ENABLED", "true")
    monkeypatch.setenv("AGNO_MODEL_ID", "deepseek-chat")
    s = Settings()
    assert s.agno_enabled is True
    assert s.agno_model_id == "deepseek-chat"
