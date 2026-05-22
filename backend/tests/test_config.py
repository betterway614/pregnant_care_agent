"""测试 Agno 配置项"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Settings


def test_agno_config_defaults(monkeypatch):
    """验证默认配置值"""
    monkeypatch.delenv("AGNO_ENABLED", raising=False)
    s = Settings(_env_file=None)
    assert s.agno_enabled is True
    assert s.agno_knowledge_dir == "data/knowledge"
    assert s.llm_mode == "cloud"


def test_agno_config_from_env(monkeypatch):
    """验证环境变量覆盖"""
    monkeypatch.setenv("AGNO_ENABLED", "false")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    s = Settings(_env_file=None)
    assert s.agno_enabled is False
    assert s.llm_model == "deepseek-chat"
