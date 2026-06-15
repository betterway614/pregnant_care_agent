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

import ast
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
        s = Settings(_env_file=None)
        assert s.embedding_model == "text-embedding-v3"
        assert s.embedding_dimensions == 1024

    def test_embedding_api_url_default_dashscope(self):
        from app.config import Settings
        s = Settings(_env_file=None)
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
        from app.core.agno_knowledge import create_knowledge
        k = create_knowledge()
        assert isinstance(k.vector_db, PgVector)

    def test_knowledge_max_results(self):
        """验证 max_results 配置正确传递"""
        from app.core.agno_knowledge import create_knowledge
        k = create_knowledge()
        assert k.max_results == 5


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
        """验证 /rag/status 在检索失败时返回 unavailable (含错误详情)"""
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
                assert result["knowledge_status"].startswith("unavailable")

    @pytest.mark.asyncio
    async def test_rag_ask_disabled_raises(self):
        """验证 RAG 关闭时返回 400"""
        from app.routers.chat import rag_ask, RAGAskRequest
        from fastapi import HTTPException
        from app.core.auth import TokenPayload

        mock_user = TokenPayload(sub="test-admin", role="admin", pregnant_id="")

        with patch("app.routers.chat.settings") as mock_settings:
            mock_settings.rag_enabled = False

            req = RAGAskRequest(question="孕期饮食")
            with pytest.raises(HTTPException) as exc_info:
                await rag_ask(req, user=mock_user)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rag_ask_returns_results(self):
        """验证 /rag/ask 返回知识库结果"""
        from app.routers.chat import rag_ask, RAGAskRequest
        from app.core.auth import TokenPayload

        mock_user = TokenPayload(sub="test-admin", role="admin", pregnant_id="")

        mock_doc = MagicMock()
        mock_doc.content = "孕期应补充叶酸0.4mg/天"
        mock_doc.name = "prenatal_guidelines"
        mock_doc.score = 0.95

        with patch("app.routers.chat.settings") as mock_settings:
            mock_settings.rag_enabled = True

            with patch("app.routers.chat.knowledge") as mock_knowledge:
                mock_knowledge.search.return_value = [mock_doc]

                req = RAGAskRequest(question="孕期需要补充什么？")
                resp = await rag_ask(req, user=mock_user)

                assert resp.rag_used is True
                assert len(resp.chunks) > 0
                assert "叶酸" in resp.answer
                assert len(resp.sources) > 0

    @pytest.mark.asyncio
    async def test_rag_ask_empty_results(self):
        """验证 /rag/ask 无结果时返回兜底回复"""
        from app.routers.chat import rag_ask, RAGAskRequest
        from app.core.auth import TokenPayload

        mock_user = TokenPayload(sub="test-admin", role="admin", pregnant_id="")

        with patch("app.routers.chat.settings") as mock_settings:
            mock_settings.rag_enabled = True

            with patch("app.routers.chat.knowledge") as mock_knowledge:
                mock_knowledge.search.return_value = []

                req = RAGAskRequest(question="完全无关的问题xyz")
                resp = await rag_ask(req, user=mock_user)

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


# ==================== Knowledge Filters 角色隔离测试 ====================


class TestKnowledgeFilters:
    """验证三端 Agent 的 knowledge_filters 角色隔离"""

    def _make_mock_model(self):
        mock = MagicMock()
        mock.__class__.__name__ = "MockModel"
        return mock

    def test_pregnant_agent_has_knowledge_filters(self):
        """孕妇端 Agent 设置了 knowledge_filters"""
        from app.core.agno_agent import create_main_agent
        mock_model = self._make_mock_model()
        with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_main_agent()
                assert agent.knowledge_filters is not None
                assert len(agent.knowledge_filters) > 0

    def test_pregnant_agent_filters_exclude_doctor_content(self):
        """孕妇端过滤器仅允许 patient 和 all"""
        from app.core.agno_agent import create_main_agent, _PREGNANT_KNOWLEDGE_FILTERS
        from agno.filters import IN
        mock_model = self._make_mock_model()
        with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_main_agent()
                filters = agent.knowledge_filters
                assert len(filters) == 1
                f = filters[0]
                assert isinstance(f, IN)
                assert f.to_dict()["key"] == "audience"
                assert set(f.to_dict()["values"]) == {"patient", "all"}

    def test_nurse_agent_has_knowledge_filters(self):
        """护士端 Agent 设置了 knowledge_filters"""
        from app.core.agno_medical_agents import create_nurse_agent
        mock_model = self._make_mock_model()
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_nurse_agent()
                assert agent.knowledge_filters is not None
                assert len(agent.knowledge_filters) > 0

    def test_nurse_agent_filters_include_nurse_and_all(self):
        """护士端过滤器允许 nurse 和 all"""
        from app.core.agno_medical_agents import create_nurse_agent
        from agno.filters import IN
        mock_model = self._make_mock_model()
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_nurse_agent()
                filters = agent.knowledge_filters
                assert len(filters) == 1
                f = filters[0]
                assert isinstance(f, IN)
                assert f.to_dict()["key"] == "audience"
                assert set(f.to_dict()["values"]) == {"nurse", "all"}

    def test_doctor_agent_has_knowledge_filters(self):
        """医生端 Agent 设置了 knowledge_filters"""
        from app.core.agno_medical_agents import create_doctor_agent
        mock_model = self._make_mock_model()
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_doctor_agent()
                assert agent.knowledge_filters is not None
                assert len(agent.knowledge_filters) > 0

    def test_doctor_agent_filters_include_doctor_nurse_all(self):
        """医生端过滤器允许 doctor、nurse 和 all"""
        from app.core.agno_medical_agents import create_doctor_agent
        from agno.filters import IN
        mock_model = self._make_mock_model()
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_doctor_agent()
                filters = agent.knowledge_filters
                assert len(filters) == 1
                f = filters[0]
                assert isinstance(f, IN)
                assert f.to_dict()["key"] == "audience"
                assert set(f.to_dict()["values"]) == {"doctor", "nurse", "all"}

    def test_pregnant_cannot_see_doctor_only_content(self):
        """孕妇端与医生端的过滤器不重叠 doctor-only 内容"""
        from app.core.agno_agent import _PREGNANT_KNOWLEDGE_FILTERS
        from app.core.agno_medical_agents import _DOCTOR_KNOWLEDGE_FILTERS
        from agno.filters import IN
        pregnant_values = set(_PREGNANT_KNOWLEDGE_FILTERS[0].to_dict()["values"])
        doctor_values = set(_DOCTOR_KNOWLEDGE_FILTERS[0].to_dict()["values"])
        # 孕妇端不应包含 doctor
        assert "doctor" not in pregnant_values
        # 医生端包含 doctor
        assert "doctor" in doctor_values

    @pytest.mark.parametrize("variant_name,getter", [
        ("chat", "get_chat_agent"),
        ("record", "get_record_agent"),
        ("qa", "get_qa_agent"),
        ("emergency", "get_emergency_agent"),
        ("complex", "get_main_agent"),
    ])
    def test_all_pregnant_variants_have_filters(self, variant_name, getter):
        """孕妇端所有变体的 knowledge_filters 状态

        门控策略 (RAG 灵敏度优化):
          qa/complex → search_knowledge=True  → knowledge_filters is not None
          chat/record/emergency → search_knowledge=False → knowledge_filters is None
        """
        from app.core import agno_agent as mod
        factory = getattr(mod, getter)
        mock_model = self._make_mock_model()
        with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = factory()
                if variant_name in ("qa", "complex"):
                    assert agent.knowledge_filters is not None, (
                        f"{variant_name} should have knowledge_filters (search_knowledge=True)"
                    )
                else:
                    # chat/record/emergency: 主动关闭知识检索，减少 RAG 误触发
                    assert agent.knowledge_filters is None, (
                        f"{variant_name} should NOT have knowledge_filters (search_knowledge=False per gating)"
                    )

    @pytest.mark.parametrize("getter,should_have_filters", [
        ("get_nurse_analyze_agent", True),       # analyze: enable_knowledge=True
        ("get_nurse_followup_agent", False),      # followup: enable_knowledge=False (RAG gating)
        ("get_nurse_report_agent", False),         # report: enable_knowledge=False (RAG gating)
        ("get_nurse_chat_variant_agent", True),   # chat: enable_knowledge=True
        ("get_nurse_agent", True),                 # main: enable_knowledge=True
    ])
    def test_all_nurse_variants_have_filters(self, getter, should_have_filters):
        """护士端变体 knowledge_filters 与 RAG 门控策略一致

        RAG 门控: analyze/chat 开启知识检索，followup/report 关闭以减少 token 浪费。
        """
        from app.core import agno_medical_agents as mod
        factory = getattr(mod, getter)
        mock_model = self._make_mock_model()
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = factory()
                if should_have_filters:
                    assert agent.knowledge_filters is not None, f"{getter} should have knowledge_filters"
                else:
                    assert agent.knowledge_filters is None, f"{getter} should NOT have knowledge_filters (RAG gating: enable_knowledge=False)"

    @pytest.mark.parametrize("getter,should_have_filters", [
        ("get_doctor_analyze_agent", True),       # analyze: enable_knowledge=True
        ("get_doctor_order_agent", False),         # order: enable_knowledge=False (RAG gating)
        ("get_doctor_issue_agent", False),         # issue: enable_knowledge=False (RAG gating)
        ("get_doctor_chat_variant_agent", True),  # chat: enable_knowledge=True
        ("get_doctor_agent", True),                # main: enable_knowledge=True
    ])
    def test_all_doctor_variants_have_filters(self, getter, should_have_filters):
        """医生端变体 knowledge_filters 与 RAG 门控策略一致

        RAG 门控: analyze/chat 开启知识检索，order/issue 关闭以减少 token 浪费。
        """
        from app.core import agno_medical_agents as mod
        factory = getattr(mod, getter)
        mock_model = self._make_mock_model()
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = factory()
                if should_have_filters:
                    assert agent.knowledge_filters is not None, f"{getter} should have knowledge_filters"
                else:
                    assert agent.knowledge_filters is None, f"{getter} should NOT have knowledge_filters (RAG gating: enable_knowledge=False)"


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


# ==================== 临床指南兜底库测试 ====================


class TestClinicalGuidelinesFallback:
    """测试 clinical_guidelines_fallback.py 的指南解析与搜索"""

    def test_all_topics_have_key_points(self):
        """验证所有非别名条目都有实际临床内容"""
        from app.core.tools.clinical_guidelines_fallback import CLINICAL_GUIDELINES

        for key, entry in CLINICAL_GUIDELINES.items():
            if entry.get("_alias_of"):
                continue
            assert len(entry["key_points"]) >= 3, (
                f"Topic '{key}' should have >= 3 key points, got {len(entry.get('key_points', []))}"
            )
            assert entry["title"], f"Topic '{key}' missing title"
            assert entry["source"], f"Topic '{key}' missing source"

    def test_all_aliases_resolve_to_valid_targets(self):
        """验证所有别名指向存在的条目"""
        from app.core.tools.clinical_guidelines_fallback import CLINICAL_GUIDELINES

        for key, entry in CLINICAL_GUIDELINES.items():
            if entry.get("_alias_of"):
                target = entry["_alias_of"]
                assert target in CLINICAL_GUIDELINES, f"Alias '{key}' points to non-existent '{target}'"
                target_entry = CLINICAL_GUIDELINES[target]
                assert not target_entry.get("_alias_of") or target_entry.get("key_points"), (
                    f"Alias '{key}' target '{target}' should be a primary entry with key_points"
                )

    @pytest.mark.parametrize("topic,expected_in_title", [
        ("gdm", "GDM"),
        ("preeclampsia", "子痫前期"),
        ("medication", "用药安全"),
        ("prenatal", "孕期保健"),
        ("fetal_movement", "胎动监测"),
        ("fgr", "FGR"),
        ("lab", "实验室"),
        ("labor", "分娩"),
        ("postpartum", "产后恢复"),
        ("newborn", "新生儿"),
        ("vaccination", "疫苗"),
        ("nutrition", "营养"),
        ("exercise", "运动"),
        ("mental_health", "心理"),
        ("prenatal_diagnosis", "产前筛查"),
        ("travel", "旅行"),
    ])
    def test_direct_match_english(self, topic, expected_in_title):
        """验证英文关键词精确匹配"""
        from app.core.tools.clinical_guidelines_fallback import resolve_guideline

        result = resolve_guideline(topic)
        assert result is not None, f"No match for topic '{topic}'"
        assert expected_in_title in result["title"], (
            f"Expected '{expected_in_title}' in title, got '{result['title']}'"
        )

    @pytest.mark.parametrize("topic,expected_in_title", [
        ("糖尿病", "GDM"),
        ("子痫", "子痫前期"),
        ("高血压", "子痫前期"),
        ("用药", "用药安全"),
        ("产检", "孕期保健"),
        ("孕期", "孕期保健"),
        ("胎动", "胎动监测"),
        ("化验", "实验室"),
        ("分娩", "分娩"),
        ("产后", "产后恢复"),
        ("新生儿", "新生儿"),
        ("疫苗", "疫苗"),
        ("营养", "营养"),
        ("运动", "运动"),
        ("心理", "心理"),
        ("筛查", "产前筛查"),
        ("旅行", "旅行"),
        ("实验室", "实验室"),
    ])
    def test_direct_match_chinese(self, topic, expected_in_title):
        """验证中文关键词精确匹配（含别名解析）"""
        from app.core.tools.clinical_guidelines_fallback import resolve_guideline

        result = resolve_guideline(topic)
        assert result is not None, f"No match for topic '{topic}'"
        assert expected_in_title in result["title"], (
            f"Expected '{expected_in_title}' in title, got '{result['title']}'"
        )

    def test_substring_match_works(self):
        """验证子串匹配：topic 包含关键词时能匹配"""
        from app.core.tools.clinical_guidelines_fallback import resolve_guideline

        # "severe_preeclampsia" 包含 "preeclampsia"
        result = resolve_guideline("severe_preeclampsia_with_complications")
        assert result is not None
        assert "子痫前期" in result["title"]

    def test_unknown_topic_returns_none(self):
        """验证未知主题返回 None"""
        from app.core.tools.clinical_guidelines_fallback import resolve_guideline

        assert resolve_guideline("") is None
        assert resolve_guideline("xyz_nonexistent_topic_123") is None

    def test_search_guidelines_returns_multiple(self):
        """验证 search_guidelines 可返回多条结果"""
        from app.core.tools.clinical_guidelines_fallback import search_guidelines

        results = search_guidelines("怀孕期间高血压子痫前期用药", max_results=5)
        assert len(results) >= 2, f"Should find >= 2 results, got {len(results)}"
        titles = [r["title"] for r in results]
        assert any("子痫前期" in t for t in titles)
        assert any("用药" in t for t in titles)

    def test_search_guidelines_respects_max_results(self):
        """验证 search_guidelines 遵守 max_results 限制"""
        from app.core.tools.clinical_guidelines_fallback import search_guidelines

        results = search_guidelines("pregnancy", max_results=1)
        assert len(results) <= 1

    def test_search_guidelines_no_duplicates(self):
        """验证 search_guidelines 不返回重复条目"""
        from app.core.tools.clinical_guidelines_fallback import search_guidelines

        results = search_guidelines("gdm diabetes medication pregnancy", max_results=10)
        titles = [r["title"] for r in results]
        assert len(titles) == len(set(titles)), f"Duplicate titles found: {titles}"

    def test_every_primary_entry_has_references(self):
        """验证所有主条目都标注了参考文档"""
        from app.core.tools.clinical_guidelines_fallback import CLINICAL_GUIDELINES

        for key, entry in CLINICAL_GUIDELINES.items():
            if entry.get("_alias_of"):
                continue
            refs = entry.get("references", [])
            assert len(refs) >= 1, f"Topic '{key}' should reference at least 1 knowledge doc"


# ==================== 医生工具兜底路径测试 ====================


def _parse_tool_result(result) -> dict:
    """解析 truncate_tool_result 返回的字符串为 dict（兼容已是 dict 的情况）。

    truncate_tool_result 返回 str(dict)（Python repr，单引号），
    截断时返回 json.dumps() 格式。部分路径直接返回 dict。
    """
    import json
    if isinstance(result, dict):
        return result
    try:
        return json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return ast.literal_eval(result)


class TestDoctorToolsFallbackPath:
    """验证 agno_query_clinical_guideline 在 RAG 不可用时的兜底行为

    注意: agno_query_clinical_guideline 被 @tool 装饰器包装为 agno.tools.function.Function 对象，
    调用时需要访问 .entrypoint 属性获取底层函数。
    """

    def test_fallback_returns_expanded_guidelines(self):
        """验证硬编码兜底路径返回完整的临床关键点（而非仅标题）"""
        from app.core.tools.doctor_tools import agno_query_clinical_guideline

        # 模拟 RAG 不可用: knowledge 为 None
        with patch("app.core.agno_knowledge.knowledge", None):
            result = agno_query_clinical_guideline.entrypoint(topic="gdm")
            result = _parse_tool_result(result)

        assert result["source"] == "hardcoded_fallback"
        guidelines = result["guidelines"]
        assert isinstance(guidelines, list)
        assert len(guidelines) >= 1
        # 不应只是标题 — 应包含完整的 key_points
        gdm_text = guidelines[0]
        assert "诊断标准" in gdm_text or "OGTT" in gdm_text or "血糖" in gdm_text
        # 至少有实质性内容
        assert len(gdm_text) > 100, f"Fallback content too short: {len(gdm_text)} chars"

    def test_fallback_unknown_topic_returns_helpful_message(self):
        """验证完全未知主题返回提示信息而非报错"""
        from app.core.tools.doctor_tools import agno_query_clinical_guideline

        with patch("app.core.agno_knowledge.knowledge", None):
            result = agno_query_clinical_guideline.entrypoint(topic="xyz_nonexistent_abcdef")
            result = _parse_tool_result(result)

        assert result["source"] == "hardcoded_fallback"
        assert len(result["guidelines"]) >= 1
        # 应包含帮助提示
        assert "未找到" in result["guidelines"][0] or "建议" in result["guidelines"][0]

    def test_fallback_chinese_query_works(self):
        """验证中文查询能正确解析兜底指南"""
        from app.core.tools.doctor_tools import agno_query_clinical_guideline

        with patch("app.core.agno_knowledge.knowledge", None):
            result = agno_query_clinical_guideline.entrypoint(topic="妊娠期糖尿病饮食")
            result = _parse_tool_result(result)

        assert result["source"] == "hardcoded_fallback"
        assert len(result["guidelines"]) >= 1

    def test_rag_available_uses_knowledge_base(self):
        """验证 RAG 可用时优先走知识库检索"""
        from app.core.tools.doctor_tools import agno_query_clinical_guideline

        mock_doc = MagicMock()
        mock_doc.content = "孕期应补充叶酸0.4mg每天"

        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [mock_doc]

        with patch("app.core.agno_knowledge.knowledge", mock_knowledge):
            result = agno_query_clinical_guideline.entrypoint(topic="prenatal")
            result = _parse_tool_result(result)

        assert result["source"] == "knowledge_base"
        assert "叶酸" in result["guidelines"][0]


# ==================== RAG 健康监控测试 ====================


class TestRAGHealthMonitor:
    """测试 rag_health_monitor.py 的健康探针逻辑"""

    def test_health_status_initial_state(self):
        """验证初始健康状态可读取"""
        from app.core.rag_health_monitor import get_health_status

        status = get_health_status()
        assert "embedding_service" in status
        assert "pgvector" in status
        assert "last_check_time" in status
        assert "degraded" in status
        assert isinstance(status["consecutive_failures"], int)

    def test_check_embedding_service_healthy(self):
        """验证嵌入服务健康探针 — 正常响应"""
        from app.core.rag_health_monitor import _check_embedding_service

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"model_loaded": True, "model_name": "BAAI/bge-m3", "device": "cuda"}

        # _check_embedding_service 内部 import requests，需要 patch 全局 requests.get
        with patch("requests.get", return_value=mock_response):
            result = _check_embedding_service(timeout=1.0)

        assert result["status"] == "healthy"
        assert "bge-m3" in result["detail"]
        assert result["latency_ms"] >= 0

    def test_check_embedding_service_model_not_loaded(self):
        """验证嵌入服务探针 — 模型未加载"""
        from app.core.rag_health_monitor import _check_embedding_service

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"model_loaded": False}

        with patch("requests.get", return_value=mock_response):
            result = _check_embedding_service(timeout=1.0)

        assert result["status"] == "unreachable"
        assert "not loaded" in result["detail"]

    def test_check_embedding_service_connection_refused(self):
        """验证嵌入服务探针 — 连接被拒绝"""
        from app.core.rag_health_monitor import _check_embedding_service
        import requests as r

        with patch("requests.get", side_effect=r.ConnectionError("Connection refused")):
            result = _check_embedding_service(timeout=1.0)

        assert result["status"] == "unreachable"
        assert "refused" in result["detail"].lower()

    def test_check_embedding_service_timeout(self):
        """验证嵌入服务探针 — 超时"""
        from app.core.rag_health_monitor import _check_embedding_service
        import requests as r

        with patch("requests.get", side_effect=r.Timeout("timed out")):
            result = _check_embedding_service(timeout=1.0)

        assert result["status"] == "unreachable"
        assert "timeout" in result["detail"].lower()

    def test_check_pgvector_knowledge_none(self):
        """验证 pgvector 探针 — knowledge 为 None"""
        from app.core.rag_health_monitor import _check_pgvector

        # _check_pgvector 内部 from .agno_knowledge import knowledge
        with patch("app.core.agno_knowledge.knowledge", None):
            result = _check_pgvector(timeout=1.0)

        assert result["status"] == "unreachable"
        assert "None" in result["detail"]

    def test_check_pgvector_healthy(self):
        """验证 pgvector 探针 — 正常检索"""
        from app.core.rag_health_monitor import _check_pgvector

        mock_doc = MagicMock()
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [mock_doc]

        with patch("app.core.agno_knowledge.knowledge", mock_knowledge):
            result = _check_pgvector(timeout=1.0)

        assert result["status"] == "healthy"
        assert "1 chunks" in result["detail"]

    def test_check_pgvector_empty_table(self):
        """验证 pgvector 探针 — 表存在但无数据"""
        from app.core.rag_health_monitor import _check_pgvector

        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = []

        with patch("app.core.agno_knowledge.knowledge", mock_knowledge):
            result = _check_pgvector(timeout=1.0)

        assert result["status"] == "empty"

    def test_check_pgvector_search_error(self):
        """验证 pgvector 探针 — 检索异常"""
        from app.core.rag_health_monitor import _check_pgvector

        mock_knowledge = MagicMock()
        mock_knowledge.search.side_effect = Exception("connection timeout")

        with patch("app.core.agno_knowledge.knowledge", mock_knowledge):
            result = _check_pgvector(timeout=1.0)

        assert result["status"] == "unreachable"

    def test_health_check_job_updates_degraded_flag(self):
        """验证定时健康检查任务更新降级标志"""
        from app.core.rag_health_monitor import _health_check_job, get_health_status

        # 模拟两个服务都不可用
        with patch("app.core.rag_health_monitor._check_embedding_service",
                   return_value={"status": "unreachable", "detail": "mock down", "latency_ms": 5.0}):
            with patch("app.core.rag_health_monitor._check_pgvector",
                       return_value={"status": "unreachable", "detail": "mock down", "latency_ms": 5.0}):
                _health_check_job()

        status = get_health_status()
        assert status["degraded"] is True
        assert status["consecutive_failures"] >= 1

        # 模拟恢复
        with patch("app.core.rag_health_monitor._check_embedding_service",
                   return_value={"status": "healthy", "detail": "ok", "latency_ms": 1.0}):
            with patch("app.core.rag_health_monitor._check_pgvector",
                       return_value={"status": "healthy", "detail": "1 chunks", "latency_ms": 1.0}):
                _health_check_job()

        status = get_health_status()
        assert status["degraded"] is False
        assert status["consecutive_failures"] == 0

    def test_rag_status_endpoint_includes_health_monitor(self):
        """验证增强后的 /rag/status 包含 health_monitor 字段"""
        from app.routers.chat import rag_status

        with patch("app.routers.chat.settings") as mock_settings:
            mock_settings.rag_enabled = True
            mock_settings.rag_search_type = "hybrid"
            mock_settings.embedding_model = "text-embedding-v3"
            mock_settings.embedding_dimensions = 1024
            mock_settings.rag_max_results = 5
            mock_settings.rag_chunk_size = 600
            mock_settings.rag_chunk_overlap = 120
            mock_settings.agno_knowledge_table = "knowledge_chunks"
            mock_settings.embedding_api_url = "http://localhost:8081/v1"

            with patch("app.routers.chat.knowledge") as mock_knowledge:
                mock_doc = MagicMock()
                mock_knowledge.search.return_value = [mock_doc]

                result = rag_status()

        # 新字段
        assert "health_monitor" in result, "rag_status should include health_monitor field"
        assert "embedding_api_url" in result
        assert "chunk_size" in result
        assert "knowledge_table" in result
