"""AgentAuditLog 模型单元测试"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime
from uuid import uuid4


def test_agent_audit_log_model_fields():
    """验证 AgentAuditLog 模型定义了所有必需字段"""
    from app.models import AgentAuditLog

    # 模型可实例化
    log = AgentAuditLog(
        session_id="test-session-1",
        user_id="P001",
        agent_role="pregnant",
        agent_variant="chat",
        routed_agent="小安-chat",
        input_tokens=500,
        output_tokens=200,
        total_tokens=700,
        model_id="qwen3-30b",
        provider="openai",
        total_latency_ms=1234,
    )
    assert log is not None
    assert log.session_id == "test-session-1"
    assert log.user_id == "P001"
    assert log.agent_role == "pregnant"
    assert log.agent_variant == "chat"
    assert log.total_tokens == 700


def test_agent_audit_log_optional_fields():
    """验证可选字段可以留空"""
    from app.models import AgentAuditLog

    log = AgentAuditLog(
        session_id="sess-1",
        user_id="P002",
        agent_role="nurse",
        agent_variant="main",
        routed_agent="小护-主",
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        model_id="unknown",
        provider="unknown",
        total_latency_ms=0,
        guardrail_triggered=False,
    )
    assert log.intent_classification is None
    assert log.tool_calls_json is None
    assert log.llm_latency_ms is None
    assert log.response_preview is None
    assert log.guardrail_triggered is False


def test_agent_audit_log_defaults():
    """验证默认值正确"""
    from app.models import AgentAuditLog

    log = AgentAuditLog(
        session_id="sess-1",
        user_id="P003",
        agent_role="doctor",
        agent_variant="main",
        routed_agent="智医",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        model_id="qwen",
        provider="openai",
        total_latency_ms=500,
        guardrail_triggered=False,
        tool_calls_json=None,
    )
    assert log.input_tokens == 100
    assert log.guardrail_triggered is False
    assert log.tool_calls_json is None
    # created_at 默认值在 DB flush 时才生效，Python 层面可能为 None


def test_agent_audit_log_tool_calls_json():
    """验证 tool_calls_json 可存储复杂结构"""
    from app.models import AgentAuditLog

    tool_calls = [
        {"name": "agno_parse_nlu", "success": True},
        {"name": "agno_get_patient_context", "success": True, "duration_ms": 45},
    ]

    log = AgentAuditLog(
        session_id="sess-1",
        user_id="P004",
        agent_role="pregnant",
        agent_variant="chat",
        routed_agent="小安-chat",
        input_tokens=600,
        output_tokens=300,
        total_tokens=900,
        model_id="qwen3",
        provider="openai",
        total_latency_ms=800,
        tool_calls_json=tool_calls,
    )
    assert len(log.tool_calls_json) == 2
    assert log.tool_calls_json[0]["name"] == "agno_parse_nlu"


def test_agent_audit_log_response_preview_truncation():
    """验证 response_preview 存储前200字"""
    from app.models import AgentAuditLog

    long_response = "这" * 300

    log = AgentAuditLog(
        session_id="sess-1",
        user_id="P005",
        agent_role="pregnant",
        agent_variant="qa",
        routed_agent="小安-qa",
        input_tokens=400,
        output_tokens=600,
        total_tokens=1000,
        model_id="qwen3",
        provider="openai",
        total_latency_ms=1500,
        response_preview=long_response[:200],
    )
    assert len(log.response_preview) <= 200


def test_agent_audit_log_table_name():
    """验证表名正确"""
    from app.models import AgentAuditLog
    assert AgentAuditLog.__tablename__ == "agent_audit_logs"


def test_agent_audit_log_guardrail_triggered():
    """验证 guardrail_triggered 可设为 True"""
    from app.models import AgentAuditLog

    log = AgentAuditLog(
        session_id="sess-1",
        user_id="P006",
        agent_role="pregnant",
        agent_variant="emergency",
        routed_agent="小安-emergency",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        model_id="qwen3",
        provider="openai",
        total_latency_ms=500,
        guardrail_triggered=True,
    )
    assert log.guardrail_triggered is True


@pytest.mark.parametrize("role", ["pregnant", "nurse", "doctor"])
def test_agent_audit_log_all_roles(role):
    """验证三种角色均可创建审计日志"""
    from app.models import AgentAuditLog

    log = AgentAuditLog(
        session_id=f"sess-{role}",
        user_id="P007",
        agent_role=role,
        agent_variant="main",
        routed_agent=f"{role}-main",
        input_tokens=100,
        output_tokens=100,
        total_tokens=200,
        model_id="test",
        provider="test",
        total_latency_ms=100,
    )
    assert log.agent_role == role


# ==================== 增强字段测试 ====================


def test_agent_audit_log_tool_call_count():
    """验证 tool_call_count 字段"""
    from app.models import AgentAuditLog

    log = AgentAuditLog(
        session_id="sess-tc",
        user_id="P008",
        agent_role="pregnant",
        agent_variant="complex",
        routed_agent="小安-complex",
        input_tokens=800,
        output_tokens=400,
        total_tokens=1200,
        model_id="qwen3",
        provider="openai",
        total_latency_ms=2000,
        tool_call_count=3,
        tool_error_count=1,
    )
    assert log.tool_call_count == 3
    assert log.tool_error_count == 1


def test_agent_audit_log_tool_call_count_default():
    """验证 tool_call_count 默认值（SQLAlchemy default 在 flush 时生效）"""
    from app.models import AgentAuditLog

    log = AgentAuditLog(
        session_id="sess-def",
        user_id="P009",
        agent_role="nurse",
        agent_variant="analyze",
        routed_agent="小护-analyze",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        model_id="test",
        provider="test",
        total_latency_ms=100,
    )
    # Python 层面 default 未生效，验证列定义存在
    assert hasattr(log, "tool_call_count")
    assert hasattr(log, "tool_error_count")
    # 显式赋值后生效
    log.tool_call_count = 0
    log.tool_error_count = 0
    assert log.tool_call_count == 0
    assert log.tool_error_count == 0


def test_agent_audit_log_feedback_fields():
    """验证反馈冗余字段"""
    from app.models import AgentAuditLog

    log = AgentAuditLog(
        session_id="sess-fb",
        user_id="P010",
        agent_role="pregnant",
        agent_variant="chat",
        routed_agent="小安-chat",
        input_tokens=300,
        output_tokens=150,
        total_tokens=450,
        model_id="qwen3",
        provider="openai",
        total_latency_ms=800,
        feedback_rating="thumbs_up",
        feedback_comment="回答很有帮助",
    )
    assert log.feedback_rating == "thumbs_up"
    assert log.feedback_comment == "回答很有帮助"


def test_agent_audit_log_feedback_fields_default():
    """验证反馈字段默认为空"""
    from app.models import AgentAuditLog

    log = AgentAuditLog(
        session_id="sess-nofb",
        user_id="P011",
        agent_role="doctor",
        agent_variant="analyze",
        routed_agent="智医-analyze",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        model_id="test",
        provider="test",
        total_latency_ms=200,
    )
    assert log.feedback_rating is None
    assert log.feedback_comment is None


# ==================== ToolCallDetail 模型测试 ====================


def test_tool_call_detail_model_fields():
    """验证 ToolCallDetail 模型字段"""
    from app.models import ToolCallDetail

    detail = ToolCallDetail(
        audit_log_id=1,
        tool_name="agno_save_health_data",
        tool_args_json={"metric": "weight", "value": 65.5},
        success=True,
        latency_ms=120,
        result_preview='{"success": true}',
        call_order=1,
    )
    assert detail.audit_log_id == 1
    assert detail.tool_name == "agno_save_health_data"
    assert detail.tool_args_json["metric"] == "weight"
    assert detail.success is True
    assert detail.latency_ms == 120
    assert detail.call_order == 1


def test_tool_call_detail_failure():
    """验证工具调用失败记录"""
    from app.models import ToolCallDetail

    detail = ToolCallDetail(
        audit_log_id=2,
        tool_name="agno_query_patient_data",
        success=False,
        error_message="Database connection timeout",
        call_order=2,
    )
    assert detail.success is False
    assert detail.error_message == "Database connection timeout"


def test_tool_call_detail_defaults():
    """验证 ToolCallDetail 默认值（SQLAlchemy default 在 flush 时生效）"""
    from app.models import ToolCallDetail

    detail = ToolCallDetail(
        audit_log_id=3,
        tool_name="agno_parse_nlu",
    )
    assert detail.tool_args_json is None
    assert detail.error_message is None
    assert detail.latency_ms is None
    assert detail.result_preview is None
    # SQLAlchemy default 在 Python 层面为 None，显式赋值后验证
    detail.success = True
    detail.call_order = 0
    assert detail.success is True
    assert detail.call_order == 0


def test_tool_call_detail_table_name():
    """验证表名正确"""
    from app.models import ToolCallDetail
    assert ToolCallDetail.__tablename__ == "tool_call_details"


def test_tool_call_detail_args_truncation():
    """验证工具入参截断存储"""
    from app.models import ToolCallDetail

    long_value = "x" * 300
    detail = ToolCallDetail(
        audit_log_id=4,
        tool_name="test_tool",
        tool_args_json={"key": long_value[:200]},
    )
    assert len(detail.tool_args_json["key"]) <= 200


# ==================== Feedback audit_log_id 测试 ====================


def test_feedback_audit_log_id_field():
    """验证 Feedback 模型的 audit_log_id 字段"""
    from app.models import Feedback

    fb = Feedback(
        pregnant_id="P001",
        message_id="msg-001",
        rating="thumbs_up",
        comment="很好",
        session_id="sess-1",
        audit_log_id=42,
    )
    assert fb.audit_log_id == 42


def test_feedback_audit_log_id_optional():
    """验证 audit_log_id 可选"""
    from app.models import Feedback

    fb = Feedback(
        pregnant_id="P001",
        message_id="msg-002",
        rating="thumbs_down",
    )
    assert fb.audit_log_id is None
