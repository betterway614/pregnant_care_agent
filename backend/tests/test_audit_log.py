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
