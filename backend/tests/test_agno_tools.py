"""测试 Agno 工具函数"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def test_agno_get_nlu_result_with_session_state():
    """验证 agno_get_nlu_result 从 session_state 读取 NLU 结果"""
    from agno.run import RunContext
    from app.core.agno_tools import agno_get_nlu_result

    ctx = RunContext(
        run_id="test-run",
        session_id="test-session",
        session_state={
            "nlu_result": {
                "intent": "HEALTH_DATA_REPORT",
                "entities": {"weight": 65.0},
                "emotion": {"level": "neutral", "score": 0},
                "is_emergency": False,
            }
        },
    )
    result = agno_get_nlu_result.entrypoint(run_context=ctx)
    assert result["intent"] == "HEALTH_DATA_REPORT"
    assert result["entities"]["weight"] == 65.0


def test_agno_get_nlu_result_from_module_context():
    """验证 agno_get_nlu_result 从模块级上下文读取"""
    from agno.run import RunContext
    from app.core.agno_tools import agno_get_nlu_result, set_nlu_context, pop_nlu_context

    session_id = "test-session-ctx"
    set_nlu_context(session_id, {
        "intent": "EMOTION_EXPRESS",
        "entities": {},
        "emotion": {"level": "medium", "score": 2},
        "is_emergency": False,
    })

    ctx = RunContext(
        run_id="test-run",
        session_id=session_id,
        session_state={},
    )

    result = agno_get_nlu_result.entrypoint(run_context=ctx)
    assert result["intent"] == "EMOTION_EXPRESS"

    pop_nlu_context(session_id)


def test_agno_get_nlu_result_without_context():
    """验证 agno_get_nlu_result 无 context 时返回默认值"""
    from app.core.agno_tools import agno_get_nlu_result

    result = agno_get_nlu_result.entrypoint()
    assert result["intent"] == "UNKNOWN"
    assert "note" in result


def test_agno_check_emergency_normal():
    """验证 agno_check_emergency 对正常消息返回非紧急"""
    from app.core.agno_tools import agno_check_emergency

    result = agno_check_emergency.entrypoint("你好，今天感觉不错")
    assert result["is_emergency"] is False


def test_agno_get_epds_low():
    """验证 EPDS 工具低风险结果"""
    from app.core.agno_tools import agno_get_epds_result

    result = agno_get_epds_result.entrypoint(total_score=5)
    assert result["risk_level"] == "low"


def test_agno_get_epds_high():
    """验证 EPDS 工具高风险结果"""
    from app.core.agno_tools import agno_get_epds_result

    result = agno_get_epds_result.entrypoint(total_score=14)
    assert result["risk_level"] == "high"


@pytest.mark.asyncio
async def test_agno_get_patient_context():
    """验证 agno_get_patient_context 异步工具（返回截断字符串）"""
    from app.core.agno_tools import agno_get_patient_context

    mock_pregnant = MagicMock()
    mock_pregnant.pregnant_id = "test-pid"
    mock_pregnant.display_name = "测试"
    mock_pregnant.nickname = "小明"
    mock_pregnant.gestational_age_days = 210
    mock_pregnant.risk_tags = ["GDM"]

    mock_query = MagicMock()
    mock_query.filter.return_value.first.return_value = mock_pregnant
    mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    mock_db = MagicMock()
    mock_db.query.return_value = mock_query

    with patch("app.database.SessionLocal", return_value=mock_db):
        result = await agno_get_patient_context.entrypoint("test-pid")
        # 优化后返回 truncate_tool_result 字符串
        assert isinstance(result, str)
        assert "test-pid" in result
        assert "30+0" in result
        assert "GDM" in result


# ==================== TOOL_GROUPS 与工具路由测试 ====================


def test_tool_groups_exist():
    """验证 TOOL_GROUPS 包含 5 个场景分组"""
    from app.core.agno_tools import TOOL_GROUPS

    assert "chat" in TOOL_GROUPS
    assert "record" in TOOL_GROUPS
    assert "qa" in TOOL_GROUPS
    assert "emergency" in TOOL_GROUPS
    assert "complex" in TOOL_GROUPS
    assert len(TOOL_GROUPS) == 5


def test_tool_groups_tool_count():
    """验证每个分组的工具数量正确"""
    from app.core.agno_tools import TOOL_GROUPS

    assert len(TOOL_GROUPS["chat"]) == 4  # check_emergency + get_patient_context + get_epds_result + save_health_data
    assert len(TOOL_GROUPS["record"]) == 4
    assert len(TOOL_GROUPS["qa"]) == 2
    assert len(TOOL_GROUPS["emergency"]) == 2


def test_tool_groups_are_disjoint_from_nurse_doctor():
    """验证 TOOL_GROUPS 使用 MEDICAL_TOOLS 中的工具，不与 NURSE/DOCTOR 混用"""
    from app.core.agno_tools import TOOL_GROUPS, MEDICAL_TOOLS, NURSE_TOOLS, DOCTOR_TOOLS

    # 使用工具名比较（工具函数不可哈希）
    def tool_names(tools):
        return {t.name for t in tools}

    all_group_names = set()
    for group in TOOL_GROUPS.values():
        all_group_names.update(tool_names(group))

    medical_names = tool_names(MEDICAL_TOOLS)
    nurse_only_names = tool_names(NURSE_TOOLS) - medical_names
    doctor_only_names = tool_names(DOCTOR_TOOLS) - medical_names

    # 所有分组工具都在 MEDICAL_TOOLS 中
    assert all_group_names.issubset(medical_names)
    # 不包含护士/医生专用工具
    assert all_group_names.isdisjoint(nurse_only_names)
    assert all_group_names.isdisjoint(doctor_only_names)


@pytest.mark.parametrize("intent,expected_variant", [
    # chat 场景
    ("chat", "chat"),
    ("greeting", "chat"),
    ("emotion", "chat"),
    # record 场景
    ("record_weight", "record"),
    ("record_bp", "record"),
    ("record_glucose", "record"),
    ("record_fetal_movement", "record"),
    # qa 场景
    ("ask_knowledge", "qa"),
    # complex 场景（症状/检查需全量工具+知识检索）
    ("ask_symptom", "complex"),
    ("ask_exam", "complex"),
    # emergency
    ("emergency", "emergency"),
])
def test_resolve_tools_by_intent_known(intent, expected_variant):
    """验证已知意图正确路由到对应变体"""
    from app.core.agno_tools import resolve_tools_by_intent, MEDICAL_TOOLS, TOOL_GROUPS

    tools, variant = resolve_tools_by_intent({"intent": intent})
    assert variant == expected_variant
    # complex 变体使用全量工具集（兜底），其他变体使用子集
    if expected_variant == "complex":
        assert tools == MEDICAL_TOOLS
    else:
        assert tools == TOOL_GROUPS[expected_variant]


@pytest.mark.parametrize("intent", [
    "GREETING",
    "Greeting",
    "GREETing",
    "CHAT",
    "Chat",
    "ASK_KNOWLEDGE",
    "Ask_Knowledge",
    "RECORD_WEIGHT",
    "Record_Weight",
    "EMERGENCY",
    "Emergency",
])
def test_resolve_tools_by_intent_case_insensitive(intent):
    """验证意图匹配不区分大小写"""
    from app.core.agno_tools import resolve_tools_by_intent, MEDICAL_TOOLS

    tools, variant = resolve_tools_by_intent({"intent": intent})
    assert tools != MEDICAL_TOOLS  # 应匹配到具体分组
    assert variant != "complex"     # 不应兜底


def test_resolve_tools_by_intent_none():
    """验证 None 输入回退到 complex"""
    from app.core.agno_tools import resolve_tools_by_intent, MEDICAL_TOOLS

    tools, variant = resolve_tools_by_intent(None)
    assert variant == "complex"
    assert tools == MEDICAL_TOOLS


def test_resolve_tools_by_intent_empty_dict():
    """验证空字典回退到 complex"""
    from app.core.agno_tools import resolve_tools_by_intent, MEDICAL_TOOLS

    tools, variant = resolve_tools_by_intent({})
    assert variant == "complex"
    assert tools == MEDICAL_TOOLS


def test_resolve_tools_by_intent_missing_intent_key():
    """验证缺少 intent 键时回退"""
    from app.core.agno_tools import resolve_tools_by_intent, MEDICAL_TOOLS

    tools, variant = resolve_tools_by_intent({"entities": []})
    assert variant == "complex"
    assert tools == MEDICAL_TOOLS


def test_resolve_tools_by_intent_unknown():
    """验证未知意图回退到 complex"""
    from app.core.agno_tools import resolve_tools_by_intent, MEDICAL_TOOLS

    tools, variant = resolve_tools_by_intent({"intent": "nonexistent_intent_xyz"})
    assert variant == "complex"
    assert tools == MEDICAL_TOOLS


def test_resolve_tools_by_intent_returns_tuple():
    """验证返回值格式为 (list, str)"""
    from app.core.agno_tools import resolve_tools_by_intent

    result = resolve_tools_by_intent({"intent": "greeting"})
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], list)
    assert isinstance(result[1], str)


def test_intent_to_group_entries_valid():
    """验证 INTENT_TO_GROUP 的所有 value 都在 TOOL_GROUPS 中存在"""
    from app.core.agno_tools import INTENT_TO_GROUP, TOOL_GROUPS

    for intent, group_name in INTENT_TO_GROUP.items():
        assert group_name in TOOL_GROUPS, f"INTENT_TO_GROUP['{intent}']='{group_name}' 不在 TOOL_GROUPS 中"


# ==================== 护士/医生 TOOL_GROUPS 测试 ====================


def test_nurse_tool_groups_exist():
    """验证 NURSE_TOOL_GROUPS 包含 4 个场景"""
    from app.core.agno_tools import NURSE_TOOL_GROUPS
    assert set(NURSE_TOOL_GROUPS.keys()) == {"analyze", "followup", "report", "chat"}


def test_nurse_tool_groups_tool_count():
    """验证护士各分组工具数量"""
    from app.core.agno_tools import NURSE_TOOL_GROUPS
    assert len(NURSE_TOOL_GROUPS["analyze"]) == 3
    assert len(NURSE_TOOL_GROUPS["followup"]) == 2
    assert len(NURSE_TOOL_GROUPS["report"]) == 2
    assert len(NURSE_TOOL_GROUPS["chat"]) == 3


def test_doctor_tool_groups_exist():
    """验证 DOCTOR_TOOL_GROUPS 包含 4 个场景"""
    from app.core.agno_tools import DOCTOR_TOOL_GROUPS
    assert set(DOCTOR_TOOL_GROUPS.keys()) == {"analyze", "order", "issue", "chat"}


def test_doctor_tool_groups_tool_count():
    """验证医生各分组工具数量"""
    from app.core.agno_tools import DOCTOR_TOOL_GROUPS
    assert len(DOCTOR_TOOL_GROUPS["analyze"]) == 4
    assert len(DOCTOR_TOOL_GROUPS["order"]) == 2
    assert len(DOCTOR_TOOL_GROUPS["issue"]) == 2
    assert len(DOCTOR_TOOL_GROUPS["chat"]) == 5


@pytest.mark.parametrize("intent,expected_variant", [
    ("analyze", "analyze"), ("nurse_analyze", "analyze"),
    ("followup", "followup"), ("create_followup", "followup"),
    ("report", "report"), ("report_issue", "report"),
    ("chat", "chat"), ("greeting", "chat"),
])
def test_resolve_nurse_tools_by_intent(intent, expected_variant):
    """验证护士意图路由"""
    from app.core.agno_tools import resolve_nurse_tools_by_intent, NURSE_TOOLS
    tools, variant = resolve_nurse_tools_by_intent({"intent": intent})
    assert variant == expected_variant
    assert tools != NURSE_TOOLS


@pytest.mark.parametrize("intent,expected_variant", [
    ("analyze", "analyze"), ("doctor_analyze", "analyze"),
    ("order", "order"), ("generate_order", "order"),
    ("handle_issue", "issue"), ("resolve_issue", "issue"),
    ("chat", "chat"), ("greeting", "chat"),
])
def test_resolve_doctor_tools_by_intent(intent, expected_variant):
    """验证医生意图路由"""
    from app.core.agno_tools import resolve_doctor_tools_by_intent, DOCTOR_TOOLS
    tools, variant = resolve_doctor_tools_by_intent({"intent": intent})
    assert variant == expected_variant
    assert tools != DOCTOR_TOOLS


def test_resolve_nurse_tools_none():
    """验证护士 None 输入回退"""
    from app.core.agno_tools import resolve_nurse_tools_by_intent, NURSE_TOOLS
    tools, variant = resolve_nurse_tools_by_intent(None)
    assert variant == "complex"
    assert tools == NURSE_TOOLS


def test_resolve_doctor_tools_none():
    """验证医生 None 输入回退"""
    from app.core.agno_tools import resolve_doctor_tools_by_intent, DOCTOR_TOOLS
    tools, variant = resolve_doctor_tools_by_intent(None)
    assert variant == "complex"
    assert tools == DOCTOR_TOOLS


def test_resolve_nurse_tools_case_insensitive():
    """验证护士意图大小写不敏感"""
    from app.core.agno_tools import resolve_nurse_tools_by_intent
    _, v = resolve_nurse_tools_by_intent({"intent": "ANALYZE"})
    assert v == "analyze"
    _, v = resolve_nurse_tools_by_intent({"intent": "FollowUp"})
    assert v == "followup"


def test_resolve_doctor_tools_case_insensitive():
    """验证医生意图大小写不敏感"""
    from app.core.agno_tools import resolve_doctor_tools_by_intent
    _, v = resolve_doctor_tools_by_intent({"intent": "ANALYZE"})
    assert v == "analyze"
    _, v = resolve_doctor_tools_by_intent({"intent": "Generate_Order"})
    assert v == "order"
