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


def test_fgr_backend_config_defaults(monkeypatch):
    monkeypatch.delenv("FGR_BACKEND", raising=False)
    s = Settings(_env_file=None)
    assert s.fgr_backend == "pytorch"


def test_fgr_backend_config_from_env(monkeypatch):
    monkeypatch.setenv("FGR_BACKEND", "rocm")
    s = Settings(_env_file=None)
    assert s.fgr_backend == "rocm"


def test_debug_release_env_is_false(monkeypatch):
    monkeypatch.setenv("DEBUG", "release")
    s = Settings(_env_file=None)
    assert s.debug is False
