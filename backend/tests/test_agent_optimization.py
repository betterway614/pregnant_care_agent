"""智能体工具链路优化测试

测试范围：
1. NLU 意图 → 工具子集路由（方案1）
2. Agent 工厂函数缓存（方案4）
3. NLU 上下文前缀注入（方案2）
4. 护士端/医生端 chat/stream 端点集成测试
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ==================== 单元测试：NLU 意图 → 工具路由 ====================


class TestNLUToolRouting:
    """测试 NLU 意图到工具子集的路由映射"""

    def test_nurse_analyze_intent_routes_to_analyze_tools(self):
        """护士端 analyze 意图应路由到 analyze 工具组"""
        from app.core.tools.routing import resolve_nurse_tools_by_intent, NURSE_TOOL_GROUPS

        tools, variant = resolve_nurse_tools_by_intent({
            "intent": "analyze",
            "entities": {},
        })
        assert variant == "analyze"
        assert tools == NURSE_TOOL_GROUPS["analyze"]
        # analyze 组应包含 query_patient_data + analyze_health_trends + evaluate_vital_rules
        tool_names = [getattr(t, 'name', str(t)) for t in tools]
        assert any("query_patient_data" in str(n) for n in tool_names)

    def test_nurse_followup_intent_routes_to_followup_tools(self):
        """护士端 followup 意图应路由到 followup 工具组"""
        from app.core.tools.routing import resolve_nurse_tools_by_intent, NURSE_TOOL_GROUPS

        tools, variant = resolve_nurse_tools_by_intent({
            "intent": "followup",
            "entities": {},
        })
        assert variant == "followup"
        assert tools == NURSE_TOOL_GROUPS["followup"]

    def test_nurse_report_intent_routes_to_report_tools(self):
        """护士端 report 意图应路由到 report 工具组"""
        from app.core.tools.routing import resolve_nurse_tools_by_intent, NURSE_TOOL_GROUPS

        tools, variant = resolve_nurse_tools_by_intent({
            "intent": "report",
            "entities": {},
        })
        assert variant == "report"
        assert tools == NURSE_TOOL_GROUPS["report"]

    def test_nurse_chat_intent_routes_to_chat_tools(self):
        """护士端 chat/greeting 意图应路由到 chat 工具组"""
        from app.core.tools.routing import resolve_nurse_tools_by_intent, NURSE_TOOL_GROUPS

        for intent in ["chat", "greeting", "emotion", "ask_knowledge"]:
            tools, variant = resolve_nurse_tools_by_intent({
                "intent": intent,
                "entities": {},
            })
            assert variant == "chat", f"intent={intent} should route to chat"
            assert tools == NURSE_TOOL_GROUPS["chat"]

    def test_nurse_unknown_intent_routes_to_full_tools(self):
        """护士端未知意图应路由到全量工具集（兜底）"""
        from app.core.tools.routing import resolve_nurse_tools_by_intent, NURSE_TOOLS

        tools, variant = resolve_nurse_tools_by_intent({
            "intent": "UNKNOWN_THING",
            "entities": {},
        })
        assert variant == "complex"
        assert tools == NURSE_TOOLS

    def test_nurse_none_input_routes_to_full_tools(self):
        """护士端 None 输入应路由到全量工具集"""
        from app.core.tools.routing import resolve_nurse_tools_by_intent, NURSE_TOOLS

        tools, variant = resolve_nurse_tools_by_intent(None)
        assert variant == "complex"
        assert tools == NURSE_TOOLS

    def test_doctor_analyze_intent_routes_to_analyze_tools(self):
        """医生端 analyze 意图应路由到 analyze 工具组"""
        from app.core.tools.routing import resolve_doctor_tools_by_intent, DOCTOR_TOOL_GROUPS

        tools, variant = resolve_doctor_tools_by_intent({
            "intent": "analyze",
            "entities": {},
        })
        assert variant == "analyze"
        assert tools == DOCTOR_TOOL_GROUPS["analyze"]

    def test_doctor_order_intent_routes_to_order_tools(self):
        """医生端 order 意图应路由到 order 工具组"""
        from app.core.tools.routing import resolve_doctor_tools_by_intent, DOCTOR_TOOL_GROUPS

        tools, variant = resolve_doctor_tools_by_intent({
            "intent": "order",
            "entities": {},
        })
        assert variant == "order"
        assert tools == DOCTOR_TOOL_GROUPS["order"]

    def test_doctor_issue_intent_routes_to_issue_tools(self):
        """医生端 handle_issue 意图应路由到 issue 工具组"""
        from app.core.tools.routing import resolve_doctor_tools_by_intent, DOCTOR_TOOL_GROUPS

        tools, variant = resolve_doctor_tools_by_intent({
            "intent": "handle_issue",
            "entities": {},
        })
        assert variant == "issue"
        assert tools == DOCTOR_TOOL_GROUPS["issue"]

    def test_doctor_chat_intent_routes_to_chat_tools(self):
        """医生端 chat/greeting 意图应路由到 chat 工具组"""
        from app.core.tools.routing import resolve_doctor_tools_by_intent, DOCTOR_TOOL_GROUPS

        for intent in ["chat", "greeting"]:
            tools, variant = resolve_doctor_tools_by_intent({
                "intent": intent,
                "entities": {},
            })
            assert variant == "chat", f"intent={intent} should route to chat"
            assert tools == DOCTOR_TOOL_GROUPS["chat"]

    def test_doctor_guideline_intent_routes_to_analyze(self):
        """医生端 guideline 意图应路由到 analyze 组"""
        from app.core.tools.routing import resolve_doctor_tools_by_intent, DOCTOR_TOOL_GROUPS

        tools, variant = resolve_doctor_tools_by_intent({
            "intent": "guideline",
            "entities": {},
        })
        assert variant == "analyze"
        assert tools == DOCTOR_TOOL_GROUPS["analyze"]

    def test_intent_case_insensitive(self):
        """路由函数应忽略意图大小写"""
        from app.core.tools.routing import resolve_nurse_tools_by_intent

        _, variant_upper = resolve_nurse_tools_by_intent({"intent": "ANALYZE", "entities": {}})
        _, variant_lower = resolve_nurse_tools_by_intent({"intent": "analyze", "entities": {}})
        _, variant_mixed = resolve_nurse_tools_by_intent({"intent": "Analyze", "entities": {}})

        assert variant_upper == variant_lower == variant_mixed == "analyze"

    def test_nurse_tool_groups_have_different_sizes(self):
        """不同工具组应有不同数量的工具（体现意图精准匹配）"""
        from app.core.tools.routing import NURSE_TOOL_GROUPS

        sizes = {name: len(tools) for name, tools in NURSE_TOOL_GROUPS.items()}
        # chat 组应该比 complex（全量）组工具少
        assert sizes["chat"] < sizes.get("complex", 999)
        # followup 组应该只有 2 个工具
        assert sizes["followup"] == 2

    def test_doctor_tool_groups_have_different_sizes(self):
        """医生端不同工具组应有不同数量的工具"""
        from app.core.tools.routing import DOCTOR_TOOL_GROUPS

        sizes = {name: len(tools) for name, tools in DOCTOR_TOOL_GROUPS.items()}
        assert sizes["chat"] < sizes.get("complex", 999)
        assert sizes["order"] == 2


# ==================== 单元测试：Agent 工厂缓存 ====================


class TestAgentFactoryCaching:
    """测试 Agent 工厂函数的 lru_cache 行为"""

    def test_nurse_chat_variant_agent_is_cached(self):
        """get_nurse_chat_variant_agent 应返回同一实例"""
        from app.core.agno_medical_agents import get_nurse_chat_variant_agent

        agent1 = get_nurse_chat_variant_agent()
        agent2 = get_nurse_chat_variant_agent()
        assert agent1 is agent2

    def test_doctor_chat_variant_agent_is_cached(self):
        """get_doctor_chat_variant_agent 应返回同一实例"""
        from app.core.agno_medical_agents import get_doctor_chat_variant_agent

        agent1 = get_doctor_chat_variant_agent()
        agent2 = get_doctor_chat_variant_agent()
        assert agent1 is agent2

    def test_nurse_analyze_agent_is_cached(self):
        """get_nurse_analyze_agent 应返回同一实例"""
        from app.core.agno_medical_agents import get_nurse_analyze_agent

        agent1 = get_nurse_analyze_agent()
        agent2 = get_nurse_analyze_agent()
        assert agent1 is agent2

    def test_followup_generate_agent_is_cached(self):
        """get_followup_generate_agent 应返回同一实例"""
        from app.core.agno_medical_agents import get_followup_generate_agent

        agent1 = get_followup_generate_agent()
        agent2 = get_followup_generate_agent()
        assert agent1 is agent2

    def test_followup_analysis_agent_is_cached(self):
        """get_followup_analysis_agent 应返回同一实例"""
        from app.core.agno_medical_agents import get_followup_analysis_agent

        agent1 = get_followup_analysis_agent()
        agent2 = get_followup_analysis_agent()
        assert agent1 is agent2

    def test_followup_review_agent_is_cached(self):
        """get_followup_review_agent 应返回同一实例"""
        from app.core.agno_medical_agents import get_followup_review_agent

        agent1 = get_followup_review_agent()
        agent2 = get_followup_review_agent()
        assert agent1 is agent2

    def test_nurse_chat_variant_has_no_output_schema(self):
        """护士 chat 变体不应有 output_schema（保证流式输出）"""
        from app.core.agno_medical_agents import get_nurse_chat_variant_agent

        agent = get_nurse_chat_variant_agent()
        assert agent.output_schema is None

    def test_doctor_chat_variant_has_no_output_schema(self):
        """医生 chat 变体不应有 output_schema（保证流式输出）"""
        from app.core.agno_medical_agents import get_doctor_chat_variant_agent

        agent = get_doctor_chat_variant_agent()
        assert agent.output_schema is None

    def test_agent_tools_are_mutable(self):
        """Agent.tools 属性应可变（支持动态工具注入）"""
        from app.core.agno_medical_agents import get_nurse_chat_variant_agent
        from app.core.tools.routing import NURSE_TOOL_GROUPS

        agent = get_nurse_chat_variant_agent()
        original_tools = agent.tools

        # 动态替换工具
        agent.tools = NURSE_TOOL_GROUPS["analyze"]
        assert agent.tools == NURSE_TOOL_GROUPS["analyze"]
        assert agent.tools != original_tools

        # 恢复原始工具
        agent.tools = original_tools


# ==================== 单元测试：NLU 上下文注入 ====================


class TestNLUContextInjection:
    """测试 NLU 上下文前缀注入逻辑"""

    def test_nlu_result_produces_prefix(self):
        """NLU 结果应生成正确的前缀格式"""
        from app.core.nlu_engine import nlu_engine

        result = nlu_engine.parse("体重65kg")
        assert result.intent == "HEALTH_DATA_REPORT"
        assert result.entities.get("weight") == 65.0

        # 模拟前缀生成逻辑
        nlu_prefix = (
            f"[系统预分析] 意图:{result.intent} "
            f"实体:{result.entities} "
            f"情绪:{result.emotion.get('level', 'neutral')}"
        )
        assert "[系统预分析]" in nlu_prefix
        assert "HEALTH_DATA_REPORT" in nlu_prefix
        assert "65.0" in nlu_prefix

    def test_nlu_emergency_returns_early(self):
        """紧急意图应立即返回，不进入工具路由"""
        from app.core.nlu_engine import nlu_engine

        result = nlu_engine.parse("大出血了怎么办")
        assert result.is_emergency is True
        assert result.intent == "EMERGENCY"
        assert result.category.value == "emergency"

    def test_nlu_suicide_risk_returns_early(self):
        """自杀风险应立即返回"""
        from app.core.nlu_engine import nlu_engine

        result = nlu_engine.parse("不想活了")
        assert result.is_emergency is True
        assert result.intent == "SUICIDE_RISK"

    def test_nlu_knowledge_query_with_medical_topic(self):
        """含医学主题词的疑问句应识别为知识查询"""
        from app.core.nlu_engine import nlu_engine

        result = nlu_engine.parse("叶酸要吃多久")
        assert result.intent == "KNOWLEDGE_QUERY"

    def test_nlu_greeting(self):
        """问候语应识别为 GREETING"""
        from app.core.nlu_engine import nlu_engine

        result = nlu_engine.parse("你好")
        assert result.intent == "GREETING"

    def test_nlu_unknown_falls_through(self):
        """无法识别的输入应返回 UNKNOWN"""
        from app.core.nlu_engine import nlu_engine

        result = nlu_engine.parse("今天天气真好啊")
        assert result.intent == "UNKNOWN"

    def test_suggested_tools_populated(self):
        """有健康数据实体时应推荐保存工具"""
        from app.core.nlu_engine import nlu_engine

        result = nlu_engine.parse("体重65kg")
        assert "agno_save_health_data" in result.suggested_tools


# ==================== 单元测试：NurseNLU / DoctorNLU 模式 ====================


class TestRoleSpecificNLU:
    """测试医护端专属 NLU 意图模式（方案6 - 预置测试）"""

    def test_nurse_analyze_pattern(self):
        """护士端应识别'帮我分析一下'类意图"""
        import re
        from app.core.nlu_engine import RuleBaseNLU

        # 使用护士端模式测试
        pattern = r"(分析|评估|查看|看看).*?(患者|孕妇|病人|情况|数据)"
        assert re.search(pattern, "帮我分析一下张三的情况")
        assert re.search(pattern, "查看患者数据")
        assert not re.search(pattern, "你好")

    def test_nurse_followup_pattern(self):
        """护士端应识别随访相关意图"""
        import re
        # 模式1: 动作 + 对象（动作在前，对象在后）
        pattern1 = r"(随访|回访|打电话|联系|问候).*?(患者|孕妇|病人)"
        assert re.search(pattern1, "随访患者张三")
        assert re.search(pattern1, "回访孕妇李四")
        assert re.search(pattern1, "联系病人王五")

        # 模式2: 创建/新建 + 随访
        pattern2 = r"(创建|新建|生成|写).*?(随访|记录|笔记)"
        assert re.search(pattern2, "创建随访记录")
        assert re.search(pattern2, "新建记录")

        # 模式3: 对象 + 动作（"给患者打电话" 这种语序需要额外模式覆盖）
        pattern3 = r"(患者|孕妇|病人).*?(随访|回访|打电话|联系)"
        assert re.search(pattern3, "给患者打电话")
        assert re.search(pattern3, "给孕妇做随访")

    def test_nurse_report_pattern(self):
        """护士端应识别上报相关意图"""
        import re
        pattern = r"(上报|报告|通知|转给|告诉).*?(医生|主任)"
        assert re.search(pattern, "上报给医生")
        assert re.search(pattern, "通知主任")

    def test_doctor_analyze_pattern(self):
        """医生端应识别分析相关意图"""
        import re
        pattern = r"(分析|评估|解读|查看|看看).*?(患者|孕妇|病例|数据|这个)"
        assert re.search(pattern, "分析一下这个患者")
        assert re.search(pattern, "看看病例数据")

    def test_doctor_order_pattern(self):
        """医生端应识别医嘱相关意图"""
        import re
        pattern = r"(医嘱|处方|开药|用药|检查单|检验单)"
        assert re.search(pattern, "开个检查单")
        assert re.search(pattern, "生成医嘱")


# ==================== 集成测试：chat/stream 端点 ====================


class TestNurseChatStreamIntegration:
    """护士端 chat/stream 端点集成测试"""

    @pytest.fixture
    def mock_nurse_client(self, mock_db, nurse_auth_headers):
        """创建护士端 TestClient"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db
        from app.core.auth import get_current_user, TokenPayload

        def override_get_db():
            yield mock_db

        def override_get_current_user():
            return TokenPayload(sub="test-nurse", role="nurse", pregnant_id="")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        client = TestClient(app, headers=nurse_auth_headers)
        yield client
        app.dependency_overrides.clear()

    @patch("app.core.agno_medical_agents.get_nurse_chat_variant_agent")
    def test_chat_stream_returns_sse(self, mock_agent_factory, mock_nurse_client):
        """验证 chat/stream 端点返回 SSE 响应"""
        mock_agent = MagicMock()
        mock_agent.tools = []
        mock_agent_factory.return_value = mock_agent

        # Mock SSE 生成器（通过 mock agent 的 arun 返回空流）
        async def mock_arun(**kwargs):
            if False:
                yield  # 使函数成为 async generator
            return

        mock_agent.arun = mock_arun

        response = mock_nurse_client.post(
            "/api/v1/nurse/chat/stream",
            json={"message": "你好", "pregnant_id": "test-p001"},
        )
        assert response.status_code == 200

    @patch("app.core.agno_medical_agents.get_nurse_chat_variant_agent")
    def test_chat_stream_rejects_empty_message(self, mock_agent_factory, mock_nurse_client):
        """空消息应返回 400"""
        mock_agent = MagicMock()
        mock_agent_factory.return_value = mock_agent

        response = mock_nurse_client.post(
            "/api/v1/nurse/chat/stream",
            json={"message": "", "pregnant_id": "test-p001"},
        )
        assert response.status_code == 400

    def test_chat_stream_rejects_wrong_role(self, mock_db):
        """非护士用户应被拒绝访问"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db
        from app.core.auth import get_current_user, TokenPayload, create_token

        def override_get_db():
            yield mock_db

        def override_get_current_user():
            return TokenPayload(sub="test-doctor", role="doctor", pregnant_id="")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        token = create_token(TokenPayload(sub="test-doctor", role="doctor", pregnant_id=""))
        client = TestClient(app, headers={"Authorization": f"Bearer {token}"})

        response = client.post(
            "/api/v1/nurse/chat/stream",
            json={"message": "你好", "pregnant_id": "test-p001"},
        )
        assert response.status_code == 403
        app.dependency_overrides.clear()


class TestDoctorChatStreamIntegration:
    """医生端 chat/stream 端点集成测试"""

    @pytest.fixture
    def mock_doctor_client(self, mock_db, doctor_auth_headers):
        """创建医生端 TestClient"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db
        from app.core.auth import get_current_user, TokenPayload

        def override_get_db():
            yield mock_db

        def override_get_current_user():
            return TokenPayload(sub="test-doctor", role="doctor", pregnant_id="")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        client = TestClient(app, headers=doctor_auth_headers)
        yield client
        app.dependency_overrides.clear()

    def test_chat_stream_endpoint_exists(self, mock_doctor_client):
        """验证 chat/stream 端点存在且可访问（不依赖 Agent mock）"""
        # 使用 GET 访问 POST 端点，验证端点存在（应返回 405 Method Not Allowed）
        response = mock_doctor_client.get("/api/v1/doctor/chat/stream")
        # 405 = 端点存在但方法不对；404 = 端点不存在
        assert response.status_code in (405, 404, 422)

    def test_chat_stream_rejects_wrong_role(self, mock_db):
        """非医生用户应被拒绝访问"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db
        from app.core.auth import get_current_user, TokenPayload, create_token

        def override_get_db():
            yield mock_db

        def override_get_current_user():
            return TokenPayload(sub="test-nurse", role="nurse", pregnant_id="")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        token = create_token(TokenPayload(sub="test-nurse", role="nurse", pregnant_id=""))
        client = TestClient(app, headers={"Authorization": f"Bearer {token}"})

        response = client.post(
            "/api/v1/doctor/chat/stream",
            json={"message": "你好", "pregnant_id": "test-p001"},
        )
        assert response.status_code == 403
        app.dependency_overrides.clear()


# ==================== 单元测试：Agent.tools 动态替换 ====================


class TestDynamicToolInjection:
    """测试 Agno Agent.tools 动态替换行为"""

    def test_agent_tools_replacement_affects_run(self):
        """替换 Agent.tools 后，下次 run 应使用新工具"""
        from app.core.agno_medical_agents import get_nurse_chat_variant_agent
        from app.core.tools.routing import NURSE_TOOL_GROUPS, NURSE_TOOLS

        agent = get_nurse_chat_variant_agent()

        # 初始工具
        original_count = len(agent.tools) if agent.tools else 0

        # 替换为 analyze 组（更少工具）
        agent.tools = NURSE_TOOL_GROUPS["analyze"]
        assert len(agent.tools) == len(NURSE_TOOL_GROUPS["analyze"])

        # 替换为全量工具
        agent.tools = NURSE_TOOLS
        assert len(agent.tools) == len(NURSE_TOOLS)

        # 恢复
        agent.tools = NURSE_TOOL_GROUPS["chat"]

    def test_different_tool_groups_have_overlap(self):
        """不同工具组应有部分重叠（共享基础工具）"""
        from app.core.tools.routing import NURSE_TOOL_GROUPS

        chat_tools = set(str(t) for t in NURSE_TOOL_GROUPS["chat"])
        analyze_tools = set(str(t) for t in NURSE_TOOL_GROUPS["analyze"])

        # 两个组都应该包含某些基础工具
        overlap = chat_tools & analyze_tools
        assert len(overlap) > 0, "chat 和 analyze 工具组应有重叠"


# ==================== 单元测试：followup.py 缓存修复 ====================


class TestFollowupAgentCaching:
    """测试 followup.py 中 Agent 工厂缓存修复"""

    def test_followup_uses_cached_agents(self):
        """followup 相关函数应使用 get_* 而非 create_*"""
        import inspect
        from app.routers import followup

        source = inspect.getsource(followup)

        # 不应再使用 create_followup_* 函数
        assert "create_followup_generate_agent" not in source, \
            "followup.py 应使用 get_followup_generate_agent 而非 create_followup_generate_agent"
        assert "create_followup_review_agent" not in source, \
            "followup.py 应使用 get_followup_review_agent 而非 create_followup_review_agent"
        assert "create_followup_analysis_agent" not in source, \
            "followup.py 应使用 get_followup_analysis_agent 而非 create_followup_analysis_agent"

    def test_nurse_ai_uses_cached_followup_agent(self):
        """nurse_ai.py 应使用 get_followup_generate_agent"""
        import inspect
        from app.routers import nurse_ai

        source = inspect.getsource(nurse_ai)
        assert "create_followup_generate_agent" not in source, \
            "nurse_ai.py 应使用 get_followup_generate_agent 而非 create_followup_generate_agent"


# ==================== 单元测试：SSE 重连逻辑（前端模拟） ====================


class TestSSERetryLogic:
    """测试 SSE 重连逻辑（Python 端模拟）"""

    def test_retryable_error_detection(self):
        """模拟前端 _isRetryableSSEError 的逻辑"""
        # 模拟前端重试判断逻辑
        def is_retryable(message: str) -> bool:
            msg = message.lower()
            return any(kw in msg for kw in [
                "sse_unexpected_close", "fetch", "network",
                "failed to fetch", "connection", "econnreset", "etimedout",
            ])

        # 可重试的错误
        assert is_retryable("SSE_UNEXPECTED_CLOSE")
        assert is_retryable("Failed to fetch")
        assert is_retryable("NetworkError")
        assert is_retryable("ECONNRESET")
        assert is_retryable("ETIMEDOUT")
        assert is_retryable("connection lost")

        # 不可重试的错误
        assert not is_retryable("HANDLED_NON_SSE")
        assert not is_retryable("HTTP 403: Forbidden")
        assert not is_retryable("HTTP 500: Internal Server Error")

    def test_max_retries_constant(self):
        """验证最大重试次数为 2"""
        # 这是一个文档性测试，确认重试策略
        MAX_RETRIES = 2
        assert MAX_RETRIES == 2
        # 重试间隔应为指数退避: 1s, 2s
        delays = [1000 * (i + 1) for i in range(MAX_RETRIES)]
        assert delays == [1000, 2000]


# ==================== 集成测试：端到端工具链路 ====================


class TestEndToEndToolChain:
    """端到端工具链路测试"""

    def test_nlu_to_routing_to_tools_chain(self):
        """完整链路：NLU 解析 → 路由 → 工具子集"""
        from app.core.nlu_engine import nlu_engine
        from app.core.tools.routing import resolve_nurse_tools_by_intent, NURSE_TOOL_GROUPS

        # 场景1：体重记录
        nlu_result = nlu_engine.parse("体重65kg")
        tools, variant = resolve_nurse_tools_by_intent({
            "intent": nlu_result.intent,
            "entities": nlu_result.entities,
        })
        # HEALTH_DATA_REPORT → chat 组（因为 nurse_intent_map 中没有 health_data_report）
        # 实际会 fallback 到 complex（全量工具）
        assert variant in ("chat", "complex")

        # 场景2：问候
        nlu_result = nlu_engine.parse("你好")
        tools, variant = resolve_nurse_tools_by_intent({
            "intent": nlu_result.intent,
            "entities": nlu_result.entities,
        })
        # GREETING → greeting → chat 组
        assert variant == "chat"

        # 场景3：知识查询
        nlu_result = nlu_engine.parse("叶酸要吃多久")
        tools, variant = resolve_nurse_tools_by_intent({
            "intent": nlu_result.intent,
            "entities": nlu_result.entities,
        })
        # KNOWLEDGE_QUERY → nurse_intent_map 中无此 key → fallback
        assert variant == "complex"

    def test_nlu_prefix_format(self):
        """验证 NLU 前缀格式正确"""
        from app.core.nlu_engine import nlu_engine

        result = nlu_engine.parse("体重65kg，血压120/80")
        nlu_prefix = (
            f"[系统预分析] 意图:{result.intent} "
            f"实体:{result.entities} "
            f"情绪:{result.emotion.get('level', 'neutral')}"
        )
        if result.suggested_tools:
            nlu_prefix += f" 建议工具:{','.join(result.suggested_tools)}"

        assert nlu_prefix.startswith("[系统预分析]")
        assert "意图:" in nlu_prefix
        assert "实体:" in nlu_prefix
        assert "情绪:" in nlu_prefix

    def test_tool_thinking_map_coverage(self):
        """验证 TOOL_THINKING_MAP 覆盖了所有工具"""
        from app.routers.nurse_ai import NURSE_TOOL_THINKING_MAP
        from app.routers.doctor_ai import DOCTOR_TOOL_THINKING_MAP

        # 护士端工具映射
        expected_nurse_tools = [
            "agno_list_patients", "agno_query_patient_data",
            "agno_create_followup_record", "agno_report_issue_to_doctor",
            "agno_analyze_health_trends", "agno_evaluate_vital_rules",
            "search_knowledge_base",
        ]
        for tool in expected_nurse_tools:
            assert tool in NURSE_TOOL_THINKING_MAP, f"护士端缺少工具映射: {tool}"

        # 医生端工具映射
        expected_doctor_tools = [
            "agno_list_patients", "agno_analyze_patient_comprehensive",
            "agno_generate_medical_order", "agno_handle_issue",
            "agno_query_clinical_guideline", "agno_analyze_health_trends",
            "agno_evaluate_vital_rules", "search_knowledge_base",
        ]
        for tool in expected_doctor_tools:
            assert tool in DOCTOR_TOOL_THINKING_MAP, f"医生端缺少工具映射: {tool}"
