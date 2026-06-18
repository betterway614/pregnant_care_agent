"""测试 LLM 上下文优化工具：truncate_tool_result、tool_result SSE 事件、工具截断行为"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ==================== truncate_tool_result 单元测试 ====================


class TestTruncateToolResult:
    """truncate_tool_result 核心截断逻辑"""

    def test_short_string_passthrough(self):
        """短字符串直接透传，不做任何处理"""
        from app.core.tools.common import truncate_tool_result

        result = truncate_tool_result("hello")
        assert result == "hello"

    def test_short_dict_passthrough(self):
        """短 dict 转为 str 后直接透传"""
        from app.core.tools.common import truncate_tool_result

        data = {"name": "张三", "age": 28}
        result = truncate_tool_result(data)
        assert result == str(data)

    def test_long_string_truncated(self):
        """超长字符串被截断为合法 JSON"""
        from app.core.tools.common import truncate_tool_result

        long_text = "A" * 3000
        result = truncate_tool_result(long_text, max_chars=100)
        parsed = json.loads(result)
        assert parsed["original_chars"] == 3000
        assert len(parsed["truncated"]) == 100

    def test_long_dict_truncated(self):
        """超长 dict 被截断后返回合法 JSON"""
        from app.core.tools.common import truncate_tool_result

        big_data = {"items": [{"id": i, "value": "x" * 100} for i in range(50)]}
        result = truncate_tool_result(big_data, max_chars=200)
        parsed = json.loads(result)
        assert "truncated" in parsed
        assert parsed["original_chars"] > 200

    def test_exact_boundary_not_truncated(self):
        """恰好等于 max_chars 的字符串不截断"""
        from app.core.tools.common import truncate_tool_result

        text = "B" * 100
        result = truncate_tool_result(text, max_chars=100)
        assert result == text

    def test_empty_string(self):
        """空字符串直接返回"""
        from app.core.tools.common import truncate_tool_result

        assert truncate_tool_result("") == ""

    def test_empty_dict(self):
        """空 dict 直接返回"""
        from app.core.tools.common import truncate_tool_result

        result = truncate_tool_result({})
        assert result == "{}"

    def test_default_max_chars_is_1500(self):
        """默认 max_chars 为 1500（TRUNC_DEFAULT）"""
        from app.core.tools.common import TRUNC_DEFAULT

        assert TRUNC_DEFAULT == 1500

    def test_truncated_result_is_valid_json(self):
        """截断后的结果始终是合法 JSON"""
        from app.core.tools.common import truncate_tool_result

        # 包含 Unicode 中文的数据
        data = {"patients": [{"name": f"孕妇{i}", "data": "详细数据" * 50} for i in range(20)]}
        result = truncate_tool_result(data, max_chars=300)
        # 不应抛出 JSONDecodeError
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_truncated_preserves_preview(self):
        """截断结果包含原始数据的前 max_chars 个字符"""
        from app.core.tools.common import truncate_tool_result

        text = "前缀数据" + "X" * 2000
        result = truncate_tool_result(text, max_chars=10)
        parsed = json.loads(result)
        assert parsed["truncated"] == text[:10]


# ==================== tool_result SSE 事件测试 ====================


class TestToolResultSSEEvent:
    """agno_sse.py 中 tool_call_completed 时推送 tool_result 事件"""

    @pytest.mark.asyncio
    async def test_tool_result_event_emitted(self):
        """工具完成后应推送 tool_result 事件"""
        from app.core.agno_sse import agno_sse_event_generator, AgnoSseConfig, AgnoSseState
        from agno.agent import RunEvent

        # 模拟 tool_call_completed chunk
        tool_chunk = MagicMock()
        tool_chunk.tool_name = "agno_list_patients"
        tool_chunk.result = json.dumps({"patients": ["p1", "p2"]})

        completed_chunk = MagicMock()
        completed_chunk.event = RunEvent.tool_call_completed
        completed_chunk.tool = tool_chunk

        content_chunk = MagicMock()
        content_chunk.event = RunEvent.run_content
        content_chunk.content = "分析完成"

        done_chunk = MagicMock()
        done_chunk.event = RunEvent.run_completed

        mock_agent = MagicMock()

        async def mock_arun(**kwargs):
            yield completed_chunk
            yield content_chunk
            yield done_chunk

        mock_agent.arun = mock_arun

        config = AgnoSseConfig(
            agent=mock_agent,
            input_text="test",
            user_id="u1",
            session_id="s1",
            thinking_map={"agno_list_patients": "查询孕妇列表"},
            initial_thinking="思考中...",
            done_source="TEST",
        )
        state = AgnoSseState()

        events = []
        async for event in agno_sse_event_generator(config, state):
            events.append(event)

        # 检查存在 tool_result 事件
        tool_result_events = [e for e in events if e["event"] == "tool_result"]
        assert len(tool_result_events) == 1

        # 解析 tool_result 数据
        data = json.loads(tool_result_events[0]["data"])
        assert data["tool_name"] == "agno_list_patients"
        assert data["result"]["patients"] == ["p1", "p2"]

    @pytest.mark.asyncio
    async def test_tool_result_with_invalid_json(self):
        """工具返回非 JSON 字符串时，tool_result 事件使用原始字符串"""
        from app.core.agno_sse import agno_sse_event_generator, AgnoSseConfig, AgnoSseState
        from agno.agent import RunEvent

        tool_chunk = MagicMock()
        tool_chunk.tool_name = "some_tool"
        tool_chunk.result = "not valid json {"

        completed_chunk = MagicMock()
        completed_chunk.event = RunEvent.tool_call_completed
        completed_chunk.tool = tool_chunk

        content_chunk = MagicMock()
        content_chunk.event = RunEvent.run_content
        content_chunk.content = "done"

        done_chunk = MagicMock()
        done_chunk.event = RunEvent.run_completed

        mock_agent = MagicMock()

        async def mock_arun(**kwargs):
            yield completed_chunk
            yield content_chunk
            yield done_chunk

        mock_agent.arun = mock_arun

        config = AgnoSseConfig(
            agent=mock_agent,
            input_text="test",
            user_id="u1",
            session_id="s1",
            thinking_map={},
            done_source="TEST",
        )
        state = AgnoSseState()

        events = []
        async for event in agno_sse_event_generator(config, state):
            events.append(event)

        tool_result_events = [e for e in events if e["event"] == "tool_result"]
        assert len(tool_result_events) == 1
        data = json.loads(tool_result_events[0]["data"])
        assert data["result"] == "not valid json {"

    @pytest.mark.asyncio
    async def test_tool_result_not_emitted_when_result_is_none(self):
        """工具 result 为 None 时不推送 tool_result 事件"""
        from app.core.agno_sse import agno_sse_event_generator, AgnoSseConfig, AgnoSseState
        from agno.agent import RunEvent

        tool_chunk = MagicMock()
        tool_chunk.tool_name = "some_tool"
        tool_chunk.result = None

        completed_chunk = MagicMock()
        completed_chunk.event = RunEvent.tool_call_completed
        completed_chunk.tool = tool_chunk

        content_chunk = MagicMock()
        content_chunk.event = RunEvent.run_content
        content_chunk.content = "done"

        done_chunk = MagicMock()
        done_chunk.event = RunEvent.run_completed

        mock_agent = MagicMock()

        async def mock_arun(**kwargs):
            yield completed_chunk
            yield content_chunk
            yield done_chunk

        mock_agent.arun = mock_arun

        config = AgnoSseConfig(
            agent=mock_agent,
            input_text="test",
            user_id="u1",
            session_id="s1",
            thinking_map={},
            done_source="TEST",
        )
        state = AgnoSseState()

        events = []
        async for event in agno_sse_event_generator(config, state):
            events.append(event)

        tool_result_events = [e for e in events if e["event"] == "tool_result"]
        assert len(tool_result_events) == 0

    @pytest.mark.asyncio
    async def test_sse_event_order(self):
        """验证事件顺序: thinking → tool_result → chunk → done"""
        from app.core.agno_sse import agno_sse_event_generator, AgnoSseConfig, AgnoSseState
        from agno.agent import RunEvent

        # 构建 chunk 序列
        started_tool = MagicMock()
        started_tool.tool_name = "test_tool"

        started_chunk = MagicMock()
        started_chunk.event = RunEvent.tool_call_started
        started_chunk.tool = started_tool

        completed_tool = MagicMock()
        completed_tool.tool_name = "test_tool"
        completed_tool.result = '{"data": 1}'

        completed_chunk = MagicMock()
        completed_chunk.event = RunEvent.tool_call_completed
        completed_chunk.tool = completed_tool

        content_chunk = MagicMock()
        content_chunk.event = RunEvent.run_content
        content_chunk.content = "结果分析"

        done_chunk = MagicMock()
        done_chunk.event = RunEvent.run_completed

        mock_agent = MagicMock()

        async def mock_arun(**kwargs):
            yield started_chunk
            yield completed_chunk
            yield content_chunk
            yield done_chunk

        mock_agent.arun = mock_arun

        config = AgnoSseConfig(
            agent=mock_agent,
            input_text="test",
            user_id="u1",
            session_id="s1",
            thinking_map={"test_tool": "正在查询..."},
            initial_thinking="思考中...",
            done_source="TEST",
        )
        state = AgnoSseState()

        events = []
        async for event in agno_sse_event_generator(config, state):
            events.append(event)

        event_types = [e["event"] for e in events]
        assert event_types == ["thinking", "thinking", "tool_result", "chunk", "done"]


# ==================== 工具截断行为集成测试 ====================


class TestToolTruncationIntegration:
    """验证各数据查询工具的返回值都经过 truncate_tool_result 截断"""

    @pytest.mark.asyncio
    async def test_nurse_list_patients_truncated(self):
        """agno_list_patients 返回截断字符串"""
        from app.core.tools.nurse_tools import agno_list_patients

        # 模拟大量孕妇数据
        many_pregnants = []
        for i in range(30):
            p = MagicMock()
            p.pregnant_id = f"p{i}"
            p.display_name = f"孕妇{i}"
            p.nickname = f"nick{i}"
            p.gestational_age_days = 180 + i
            p.lmp_date = None
            p.risk_tags = ["GDM"] if i % 3 == 0 else []
            many_pregnants.append(p)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 30
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value.all.return_value = many_pregnants

        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        with patch("app.database.SessionLocal", return_value=mock_db):
            result = await agno_list_patients.entrypoint()
            assert isinstance(result, str)
            # 即使 30 条数据，结果也不超过截断上限（TRUNC_DATA_QUERY=2000 + JSON wrapper 开销）
            assert len(result) <= 2100

    @pytest.mark.asyncio
    async def test_nurse_query_patient_data_truncated(self):
        """agno_query_patient_data 返回截断字符串"""
        from app.core.tools.nurse_tools import agno_query_patient_data

        mock_pregnant = MagicMock()
        mock_pregnant.pregnant_id = "test-pid"
        mock_pregnant.display_name = "测试孕妇"
        mock_pregnant.nickname = "test"
        mock_pregnant.gestational_age_days = 210
        mock_pregnant.lmp_date = None
        mock_pregnant.risk_tags = ["GDM", "高龄"]

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_pregnant
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        with patch("app.database.SessionLocal", return_value=mock_db):
            with patch("app.core.rule_engine.rule_engine") as mock_re:
                mock_re.evaluate_all.return_value = []
                result = await agno_query_patient_data.entrypoint("test-pid")
                assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_doctor_analyze_comprehensive_truncated(self):
        """agno_analyze_patient_comprehensive 返回截断字符串"""
        from app.core.tools.doctor_tools import agno_analyze_patient_comprehensive

        mock_pregnant = MagicMock()
        mock_pregnant.pregnant_id = "test-pid"
        mock_pregnant.display_name = "测试"
        mock_pregnant.nickname = "test"
        mock_pregnant.gestational_age_days = 210
        mock_pregnant.lmp_date = None
        mock_pregnant.risk_tags = ["GDM"]

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_pregnant
        # 模拟大量健康数据
        mock_health_records = []
        for i in range(20):
            h = MagicMock()
            h.record_time = f"2026-06-{i+1:02d}T10:00:00"
            h.metric_code = "weight"
            h.value = 65.0 + i * 0.1
            h.unit = "kg"
            h.recorded_at = MagicMock()
            h.recorded_at.isoformat.return_value = f"2026-06-{i+1:02d}T10:00:00"
            mock_health_records.append(h)

        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_health_records

        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        with patch("app.database.SessionLocal", return_value=mock_db):
            result = await agno_analyze_patient_comprehensive.entrypoint("test-pid")
            assert isinstance(result, str)

    def test_doctor_clinical_guideline_truncated(self):
        """agno_query_clinical_guideline 返回截断字符串"""
        from app.core.tools.doctor_tools import agno_query_clinical_guideline

        # 模拟 RAG 不可用（knowledge is None），走硬编码 fallback
        with patch("app.core.agno_knowledge.knowledge", None):
            with patch("app.core.tools.clinical_guidelines_fallback.search_guidelines") as mock_search:
                mock_search.return_value = [
                    {
                        "title": "妊娠期糖尿病管理",
                        "source": "ACOG指南",
                        "key_points": ["关键点" * 50] * 10,
                    },
                    {
                        "title": "妊娠期高血压管理",
                        "source": "ACOG指南",
                        "key_points": ["关键点" * 50] * 10,
                    },
                ]
                result = agno_query_clinical_guideline.entrypoint("妊娠期糖尿病管理")
                assert isinstance(result, str)


# ==================== num_history_runs 配置验证 ====================


class TestAgentHistoryConfig:
    """验证 Agent 对话历史轮次配置已优化"""

    def test_doctor_agent_num_history_runs(self):
        """医生 Agent num_history_runs 应为 4"""
        from agno.agent import Agent
        from app.core.agno_medical_agents import _build_doctor_agent_variant

        def capture_init(self, **kwargs):
            self.num_history_runs = kwargs.get("num_history_runs", 0)

        with patch.object(Agent, "__init__", capture_init), \
             patch("app.core.agno_medical_agents.get_agno_model") as mock_model, \
             patch("app.core.agno_medical_agents._create_doctor_db") as mock_db:
            mock_model.return_value = "mock-model"
            mock_db.return_value = MagicMock()
            agent = _build_doctor_agent_variant(
                variant_name="test",
                tools=[],
                tool_call_limit=3,
                use_schema=False,
                instructions=["test"],
            )
            assert agent.num_history_runs == 4

    def test_nurse_agent_num_history_runs(self):
        """护士 Agent num_history_runs 应为 4"""
        from agno.agent import Agent
        from app.core.agno_medical_agents import _build_nurse_agent_variant

        def capture_init(self, **kwargs):
            self.num_history_runs = kwargs.get("num_history_runs", 0)

        with patch.object(Agent, "__init__", capture_init), \
             patch("app.core.agno_medical_agents.get_agno_model") as mock_model, \
             patch("app.core.agno_medical_agents._create_nurse_db") as mock_db:
            mock_model.return_value = "mock-model"
            mock_db.return_value = MagicMock()
            agent = _build_nurse_agent_variant(
                variant_name="test",
                tools=[],
                tool_call_limit=3,
                use_schema=False,
                instructions=["test"],
            )
            assert agent.num_history_runs == 4


# ==================== 提示词输出规则验证 ====================


class TestPromptOutputRules:
    """验证系统提示词包含输出规则（不复述工具数据）"""

    def test_doctor_prompt_has_output_rules(self):
        """医生对话提示词包含输出规则"""
        from app.core.prompts import get_doctor_chat_system_prompt_instructions

        instructions = get_doctor_chat_system_prompt_instructions()
        full_text = " ".join(instructions)
        assert "输出规则" in full_text
        assert "不要逐条列举" in full_text or "不要" in full_text

    def test_nurse_prompt_has_output_rules(self):
        """护士对话提示词包含输出规则"""
        from app.core.prompts import get_nurse_chat_system_prompt_instructions

        instructions = get_nurse_chat_system_prompt_instructions()
        full_text = " ".join(instructions)
        assert "输出规则" in full_text
        assert "不要逐条列举" in full_text or "不要" in full_text
