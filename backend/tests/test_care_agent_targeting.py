"""护士/医生端对话目标解析与工具链路测试。"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _FakePatientDb:
    def __init__(self):
        self._patients = [
            SimpleNamespace(pregnant_id="PT_01", display_name="孕妇01", hospital_id="H001"),
            SimpleNamespace(pregnant_id="PT_20", display_name="孕妇20", hospital_id="H020"),
        ]

    def query(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._patients


def test_extracts_explicit_patient_number_from_nurse_message():
    from app.core.patient_targeting import extract_patient_target_mention

    mention = extract_patient_target_mention("帮我查一下孕妇20最近的情况，有异常就直接处理")

    assert mention is not None
    assert mention.raw == "孕妇20"
    assert "孕妇20" in mention.display_name_candidates


def test_resolves_patient_20_instead_of_falling_back_to_current_patient():
    from app.core.patient_targeting import resolve_patient_target_from_text

    result = resolve_patient_target_from_text(
        "帮我查一下孕妇20最近的情况，有异常就直接处理",
        db=_FakePatientDb(),
        fallback_pregnant_id="PT_01",
    )

    assert result.explicit is True
    assert result.pregnant_id == "PT_20"
    assert result.display_name == "孕妇20"
    assert result.source == "display_name"


def test_no_explicit_patient_keeps_existing_context_patient():
    from app.core.patient_targeting import resolve_patient_target_from_text

    result = resolve_patient_target_from_text(
        "帮我看一下最近情况",
        db=_FakePatientDb(),
        fallback_pregnant_id="PT_01",
    )

    assert result.explicit is False
    assert result.pregnant_id == "PT_01"


def test_explicit_target_in_session_state_overrides_wrong_tool_argument():
    from agno.run import RunContext
    from app.core.tools.common import _resolve_pid

    ctx = RunContext(
        run_id="run-targeting",
        session_id="session-targeting",
        user_id="PT_01",
        session_state={"explicit_patient_target_id": "PT_20"},
    )

    assert _resolve_pid("", ctx) == "PT_20"
    assert _resolve_pid("PT_01", ctx) == "PT_20"


def test_check_recent_patient_status_routes_to_complex_chain():
    from app.core.nlu_engine import nlu_engine
    from app.core.tools.routing import resolve_nurse_tools_by_intent, resolve_doctor_tools_by_intent

    nlu = nlu_engine.parse("帮我查一下孕妇20最近的情况，有异常就直接处理")

    assert nlu.intent == "CHECK_PATIENT_STATUS"
    _, nurse_variant = resolve_nurse_tools_by_intent({"intent": nlu.intent, "entities": nlu.entities})
    _, doctor_variant = resolve_doctor_tools_by_intent({"intent": nlu.intent, "entities": nlu.entities})
    assert nurse_variant == "complex"
    assert doctor_variant == "complex"


def test_chinese_number_patient_status_routes_to_complex_chain():
    from app.core.nlu_engine import nlu_engine
    from app.core.patient_targeting import extract_patient_target_mention
    from app.core.tools.routing import resolve_nurse_tools_by_intent

    message = "孕妇二十最近怎么样"
    mention = extract_patient_target_mention(message)
    nlu = nlu_engine.parse(message)
    _, nurse_variant = resolve_nurse_tools_by_intent({"intent": nlu.intent, "entities": nlu.entities})

    assert mention is not None
    assert mention.normalized_token == "20"
    assert nlu.intent == "CHECK_PATIENT_STATUS"
    assert nurse_variant == "complex"
