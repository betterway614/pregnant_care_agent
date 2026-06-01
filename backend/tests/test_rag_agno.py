"""RAG 模块单元测试 + 集成测试

测试范围：
1. agno_knowledge.py — Knowledge 工厂创建
2. config.py — RAG 配置字段
3. chat.py — /rag/ask 和 /rag/status 端点
4. agno_chat_handler.py — TOOL_THINKING_MAP 映射
5. Agent search_knowledge 参数
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ==================== Config 单元测试 ====================


class TestRAGConfig:
    """测试 RAG 相关配置字段"""

    def test_rag_enabled_default_true(self):
        from app.config import Settings
        s = Settings()
        assert s.rag_enabled is True

    def test_rag_search_type_default_hybrid(self):
        from app.config import Settings
        s = Settings()
        assert s.rag_search_type == "hybrid"

    def test_rag_chunk_size_default(self):
        from app.config import Settings
        s = Settings()
        assert s.rag_chunk_size == 600
        assert s.rag_chunk_overlap == 120

    def test_rag_max_results_default(self):
        from app.config import Settings
        s = Settings()
        assert s.rag_max_results == 5

    def test_embedding_model_default(self):
        from app.config import Settings
        s = Settings()
        assert s.embedding_model == "text-embedding-v3"
        assert s.embedding_dimensions == 1024

    def test_embedding_api_url_default_dashscope(self):
        from app.config import Settings
        s = Settings()
        assert "dashscope" in s.embedding_api_url

    def test_agno_database_url_postgres(self):
        from app.config import Settings
        s = Settings(db_type="postgres", db_user="test", db_password="pw", db_host="localhost", db_port=5432, db_name="testdb")
        url = s.agno_database_url
        assert url.startswith("postgresql+psycopg://")
        assert "test:pw@localhost:5432/testdb" in url

    def test_agno_database_url_sqlite_fallback(self):
        from app.config import Settings
        s = Settings(db_type="sqlite")
        url = s.agno_database_url
        assert url.startswith("sqlite:///")


# ==================== Knowledge 工厂单元测试 ====================


class TestAgnoKnowledge:
    """测试 agno_knowledge.py 的 Knowledge 创建"""

    def test_create_knowledge_returns_knowledge_instance(self):
        """验证 create_knowledge() 返回 Knowledge 对象"""
        from app.core.agno_knowledge import create_knowledge
        knowledge = create_knowledge()
        assert knowledge is not None
        # Agno Knowledge 有 vector_db 属性
        assert hasattr(knowledge, 'vector_db')

    def test_knowledge_singleton_exists(self):
        """验证模块级 knowledge 单例已创建"""
        from app.core.agno_knowledge import knowledge
        assert knowledge is not None

    def test_knowledge_has_vector_db(self):
        """验证 Knowledge 配置了 PgVector"""
        from app.core.agno_knowledge import knowledge
        assert knowledge.vector_db is not None

    def test_knowledge_vector_db_is_pgvector(self):
        """验证向量数据库类型为 PgVector"""
        from agno.vectordb.pgvector import PgVector
        from app.core.agno_knowledge import knowledge
        assert isinstance(knowledge.vector_db, PgVector)

    def test_knowledge_max_results(self):
        """验证 max_results 配置正确传递"""
        from app.core.agno_knowledge import knowledge
        assert knowledge.max_results == 5


# ==================== Chat Router 集成测试 ====================


class TestRAGEndpoints:
    """测试 /rag/ask 和 /rag/status 端点"""

    def test_rag_status_returns_config(self):
        """验证 /rag/status 返回正确配置"""
        from app.routers.chat import rag_status
        with patch("app.routers.chat.settings") as mock_settings:
            mock_settings.rag_enabled = True
            mock_settings.rag_search_type = "hybrid"
            mock_settings.embedding_model = "text-embedding-v3"
            mock_settings.embedding_dimensions = 1024
            mock_settings.rag_max_results = 5

            with patch("app.routers.chat.knowledge") as mock_knowledge:
                mock_knowledge.search.return_value = [MagicMock()]

                result = rag_status()
                assert result["enabled"] is True
                assert result["search_type"] == "hybrid"
                assert result["embedding_model"] == "text-embedding-v3"
                assert result["vector_db"] == "pgvector"

    def test_rag_status_handles_search_failure(self):
        """验证 /rag/status 在检索失败时返回 unavailable"""
        from app.routers.chat import rag_status
        with patch("app.routers.chat.settings") as mock_settings:
            mock_settings.rag_enabled = True
            mock_settings.rag_search_type = "hybrid"
            mock_settings.embedding_model = "text-embedding-v3"
            mock_settings.embedding_dimensions = 1024
            mock_settings.rag_max_results = 5

            with patch("app.routers.chat.knowledge") as mock_knowledge:
                mock_knowledge.search.side_effect = Exception("DB connection failed")

                result = rag_status()
                assert result["knowledge_status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_rag_ask_disabled_raises(self):
        """验证 RAG 关闭时返回 400"""
        from app.routers.chat import rag_ask, RAGAskRequest
        from fastapi import HTTPException

        with patch("app.routers.chat.settings") as mock_settings:
            mock_settings.rag_enabled = False

            req = RAGAskRequest(question="孕期饮食")
            with pytest.raises(HTTPException) as exc_info:
                await rag_ask(req)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rag_ask_returns_results(self):
        """验证 /rag/ask 返回知识库结果"""
        from app.routers.chat import rag_ask, RAGAskRequest

        mock_doc = MagicMock()
        mock_doc.content = "孕期应补充叶酸0.4mg/天"
        mock_doc.name = "prenatal_guidelines"
        mock_doc.score = 0.95

        with patch("app.routers.chat.settings") as mock_settings:
            mock_settings.rag_enabled = True

            with patch("app.routers.chat.knowledge") as mock_knowledge:
                mock_knowledge.search.return_value = [mock_doc]

                req = RAGAskRequest(question="孕期需要补充什么？")
                resp = await rag_ask(req)

                assert resp.rag_used is True
                assert len(resp.chunks) > 0
                assert "叶酸" in resp.answer
                assert len(resp.sources) > 0

    @pytest.mark.asyncio
    async def test_rag_ask_empty_results(self):
        """验证 /rag/ask 无结果时返回兜底回复"""
        from app.routers.chat import rag_ask, RAGAskRequest

        with patch("app.routers.chat.settings") as mock_settings:
            mock_settings.rag_enabled = True

            with patch("app.routers.chat.knowledge") as mock_knowledge:
                mock_knowledge.search.return_value = []

                req = RAGAskRequest(question="完全无关的问题xyz")
                resp = await rag_ask(req)

                assert resp.rag_used is False
                assert "抱歉" in resp.answer or "咨询" in resp.answer


# ==================== TOOL_THINKING_MAP 测试 ====================


class TestToolThinkingMap:
    """测试工具名 → 中文描述映射"""

    def test_chat_handler_has_search_knowledge_base(self):
        from app.core.agno_chat_handler import TOOL_THINKING_MAP
        assert "search_knowledge_base" in TOOL_THINKING_MAP
        assert "知识库" in TOOL_THINKING_MAP["search_knowledge_base"]

    def test_nurse_router_has_search_knowledge_base(self):
        from app.routers.nurse_ai import NURSE_TOOL_THINKING_MAP
        assert "search_knowledge_base" in NURSE_TOOL_THINKING_MAP
        assert "知识库" in NURSE_TOOL_THINKING_MAP["search_knowledge_base"]

    def test_doctor_router_has_search_knowledge_base(self):
        from app.routers.doctor_ai import DOCTOR_TOOL_THINKING_MAP
        assert "search_knowledge_base" in DOCTOR_TOOL_THINKING_MAP
        assert "知识库" in DOCTOR_TOOL_THINKING_MAP["search_knowledge_base"]

    def test_no_old_agno_search_knowledge_in_maps(self):
        """验证旧的 agno_search_knowledge 工具名不在映射中"""
        from app.core.agno_chat_handler import TOOL_THINKING_MAP
        from app.routers.nurse_ai import NURSE_TOOL_THINKING_MAP
        from app.routers.doctor_ai import DOCTOR_TOOL_THINKING_MAP

        assert "agno_search_knowledge" not in TOOL_THINKING_MAP
        assert "agno_search_knowledge" not in NURSE_TOOL_THINKING_MAP
        assert "agno_search_knowledge" not in DOCTOR_TOOL_THINKING_MAP


# ==================== Agent search_knowledge 参数测试 ====================


class TestAgentSearchKnowledge:
    """验证所有 Agent 的 search_knowledge=True"""

    def _make_mock_model(self):
        mock = MagicMock()
        mock.__class__.__name__ = "MockModel"
        return mock

    def test_pregnant_agent_search_knowledge_enabled(self):
        from app.core.agno_agent import create_main_agent
        mock_model = self._make_mock_model()
        with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_main_agent()
                assert agent.search_knowledge is True

    def test_nurse_agent_search_knowledge_enabled(self):
        from app.core.agno_medical_agents import create_nurse_agent
        mock_model = self._make_mock_model()
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_nurse_agent()
                assert agent.search_knowledge is True

    def test_doctor_agent_search_knowledge_enabled(self):
        from app.core.agno_medical_agents import create_doctor_agent
        mock_model = self._make_mock_model()
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_doctor_agent()
                assert agent.search_knowledge is True

    def test_pregnant_agent_has_knowledge(self):
        from app.core.agno_agent import create_main_agent
        mock_model = self._make_mock_model()
        with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_main_agent()
                assert agent.knowledge is not None

    def test_no_duplicate_knowledge_tools(self):
        """验证 Agent 没有重复的知识检索工具"""
        from app.core.agno_tools import MEDICAL_TOOLS
        tool_names = [getattr(t, 'name', getattr(t, '__name__', '')) for t in MEDICAL_TOOLS]
        # 不应该有 search_knowledge（已被删除）
        assert "search_knowledge" not in tool_names
        # search_knowledge_base 由框架注入，不在 MEDICAL_TOOLS 中
        assert "search_knowledge_base" not in tool_names


# ==================== 旧模块清理验证 ====================


class TestOldModulesRemoved:
    """验证旧的 RAG 模块已被删除"""

    def test_agno_rag_module_removed(self):
        """验证 agno_rag.py 已删除"""
        rag_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "agno_rag.py")
        assert not os.path.exists(rag_path), "agno_rag.py should be deleted"

    def test_embedding_module_removed(self):
        """验证 embedding.py 已删除"""
        emb_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "embedding.py")
        assert not os.path.exists(emb_path), "embedding.py should be deleted"

    def test_vector_models_module_removed(self):
        """验证 vector_models.py 已删除"""
        vm_path = os.path.join(os.path.dirname(__file__), "..", "app", "models", "vector_models.py")
        assert not os.path.exists(vm_path), "vector_models.py should be deleted"

    def test_core_init_no_old_exports(self):
        """验证 core/__init__.py 不再导出旧模块"""
        from app import core
        assert not hasattr(core, 'rag_engine')
        assert not hasattr(core, 'agno_rag_engine')
        assert not hasattr(core, 'get_embedding_client')
        assert not hasattr(core, 'AgnoKnowledgeAdapter')
        assert hasattr(core, 'knowledge')


# ==================== Ingest 脚本测试 ====================


class TestIngestScript:
    """测试入库脚本逻辑"""

    def test_ingest_skips_when_rag_disabled(self):
        """验证 RAG 关闭时跳过入库"""
        with patch("app.config.settings") as mock_settings:
            mock_settings.rag_enabled = False

            from scripts.ingest_knowledge import ingest
            # 应该直接返回，不报错
            ingest(force=False)

    def test_ingest_finds_markdown_files(self):
        """验证能发现 knowledge_docs 下的 md 文件"""
        docs_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge_docs")
        md_files = [f for f in os.listdir(docs_dir) if f.endswith(".md")]
        # 至少应有 16 篇（6 原有 + 10 新增）
        assert len(md_files) >= 16, f"Expected >= 16 md files, found {len(md_files)}"
