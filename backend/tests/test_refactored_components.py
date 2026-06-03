"""
重构组件测试 — 验证 SOLID 原则合规性

测试内容:
1. 接口层 (Protocol) — 结构化子类型验证
2. DI 容器 — 服务注册和解析
3. 警报动作注册表 — OCP 合规
4. ASR/TTS 后端策略 — OCP 合规
5. 模板选择器 — OCP 合规
6. 状态机 — 集中状态转换
7. 工具拆分 — 向后兼容
"""
import pytest
import pytest_asyncio
import asyncio


# ==================== 1. 接口层测试 ====================


class TestInterfaces:
    """验证 Protocol 结构化子类型"""

    def test_in_memory_kv_store_conforms_to_protocol(self):
        """InMemoryKeyValueStore 应满足 KeyValueStore 协议"""
        from app.interfaces.storage import KeyValueStore
        from app.services.memory_store import InMemoryKeyValueStore

        store = InMemoryKeyValueStore()
        # Protocol 结构化检查：只要有正确的方法签名即可
        assert hasattr(store, "get")
        assert hasattr(store, "set")
        assert hasattr(store, "delete")
        assert hasattr(store, "get_all")
        assert hasattr(store, "clear")

    def test_in_memory_kv_store_functional(self):
        """InMemoryKeyValueStore 功能测试"""
        from app.services.memory_store import InMemoryKeyValueStore

        store = InMemoryKeyValueStore()
        store.set("ns1", "key1", "value1")
        assert store.get("ns1", "key1") == "value1"

        store.set("ns1", "key2", "value2")
        assert store.get_all("ns1") == {"key1": "value1", "key2": "value2"}

        store.delete("ns1", "key1")
        assert store.get("ns1", "key1") is None

        store.clear("ns1")
        assert store.get_all("ns1") == {}

    def test_in_memory_kv_store_namespace_isolation(self):
        """不同命名空间应互相隔离"""
        from app.services.memory_store import InMemoryKeyValueStore

        store = InMemoryKeyValueStore()
        store.set("ns1", "key", "value1")
        store.set("ns2", "key", "value2")
        assert store.get("ns1", "key") == "value1"
        assert store.get("ns2", "key") == "value2"

    def test_mock_asr_backend_conforms_to_protocol(self):
        """MockASRBackend 应满足 ASRBackend 协议"""
        from app.services.asr_backends import MockASRBackend

        backend = MockASRBackend()
        assert hasattr(backend, "transcribe")

    def test_mock_tts_backend_conforms_to_protocol(self):
        """MockTTSBackend 应满足 TTSBackend 协议"""
        from app.services.tts_backends import MockTTSBackend

        backend = MockTTSBackend()
        assert hasattr(backend, "synthesize")


# ==================== 2. DI 容器测试 ====================


class TestContainer:
    """验证 DI 容器功能"""

    def test_container_register_and_resolve(self):
        """容器应支持注册和解析服务"""
        from app.container import Container

        c = Container()

        class DummyService:
            pass

        c.register_factory(DummyService, lambda: DummyService())
        instance = c.resolve(DummyService)
        assert isinstance(instance, DummyService)

    def test_container_singleton_caching(self):
        """单例注册应返回同一实例"""
        from app.container import Container

        c = Container()

        class DummyService:
            pass

        c.register_singleton(DummyService, lambda: DummyService())
        instance1 = c.resolve(DummyService)
        instance2 = c.resolve(DummyService)
        assert instance1 is instance2

    def test_container_unregistered_raises(self):
        """解析未注册的服务应抛出 ValueError"""
        from app.container import Container

        c = Container()
        with pytest.raises(ValueError, match="未注册"):
            c.resolve(type("Unknown", (), {}))

    def test_container_factory_not_cached(self):
        """工厂模式每次应创建新实例"""
        from app.container import Container

        c = Container()

        class DummyService:
            pass

        c.register_factory(DummyService, lambda: DummyService())
        instance1 = c.resolve(DummyService)
        instance2 = c.resolve(DummyService)
        assert instance1 is not instance2


# ==================== 3. 警报动作注册表测试 ====================


class TestAlertActions:
    """验证警报动作注册表 OCP 合规"""

    def test_builtin_actions_registered(self):
        """应有 9 个内置动作"""
        from app.services.alert_actions import list_actions

        actions = list_actions()
        assert len(actions) == 9
        assert "confirm" in actions
        assert "dismiss" in actions
        assert "escalate" in actions
        assert "nurse_escalate" in actions

    def test_get_action_returns_handler(self):
        """get_action 应返回动作处理器"""
        from app.services.alert_actions import get_action

        handler = get_action("confirm")
        assert handler is not None
        assert hasattr(handler, "execute")

    def test_get_unknown_action_returns_none(self):
        """获取未知动作应返回 None"""
        from app.services.alert_actions import get_action

        assert get_action("nonexistent") is None

    def test_register_custom_action(self):
        """应能注册自定义动作（OCP 核心）"""
        from app.services.alert_actions import register_action, get_action, list_actions

        class CustomAction:
            def execute(self, alert, payload, db):
                return {"message": "custom"}

        register_action("custom_test", CustomAction())
        assert "custom_test" in list_actions()
        handler = get_action("custom_test")
        assert handler is not None

    def test_confirm_action_sets_status(self):
        """ConfirmAction 应设置 confirmed 状态"""
        from app.services.alert_actions import ConfirmAction

        class FakeAlert:
            status = "PENDING"
            reviewed_by = None

        action = FakeAlert()
        result = ConfirmAction().execute(action, {}, None)
        assert action.status == "confirmed"
        assert result["new_status"] == "confirmed"

    def test_nurse_escalate_escalates_incrementally(self):
        """NurseEscalateAction 应逐级升级"""
        from app.services.alert_actions import NurseEscalateAction

        class FakeAlert:
            level = "YELLOW"

        alert = FakeAlert()
        NurseEscalateAction().execute(alert, {}, None)
        assert alert.level == "ORANGE"


# ==================== 4. 模板选择器测试 ====================


class TestTemplateSelector:
    """验证模板选择器 OCP 合规"""

    def test_fgr_high_risk_template(self):
        """FGR 风险应选择 fgr_high_risk 模板"""
        from app.services.followup_template_selector import select_template

        tid, _ = select_template(["FGR"], 20)
        assert tid == "fgr_high_risk"

    def test_gdm_template(self):
        """GDM 风险应选择 gdm 模板"""
        from app.services.followup_template_selector import select_template

        tid, _ = select_template(["GDM"], 30)
        assert tid == "gdm"

    def test_early_pregnancy_template(self):
        """早孕期应选择 early_pregnancy 模板"""
        from app.services.followup_template_selector import select_template

        tid, _ = select_template([], 8)
        assert tid == "early_pregnancy"

    def test_late_pregnancy_template(self):
        """晚孕期应选择 late_pregnancy 模板"""
        from app.services.followup_template_selector import select_template

        tid, _ = select_template([], 32)
        assert tid == "late_pregnancy"

    def test_standard_fallback(self):
        """无匹配时应回退到 standard"""
        from app.services.followup_template_selector import select_template

        tid, _ = select_template([], 20)
        assert tid == "standard"

    def test_register_custom_template_rule(self):
        """应能注册自定义模板规则（OCP 核心）"""
        from app.services.followup_template_selector import (
            register_template_rule, TemplateRule, select_template,
        )

        register_template_rule(TemplateRule(
            template_id="custom_test",
            priority=200,
            risk_tag="CUSTOM_TEST",
        ))
        tid, _ = select_template(["CUSTOM_TEST"], 20)
        assert tid == "custom_test"


# ==================== 5. 状态机测试 ====================


class TestStateMachine:
    """验证状态机集中管理"""

    def test_valid_transitions(self):
        """合法转换应成功"""
        from app.core.state_machine import followup_fsm, FollowUpStatus

        assert followup_fsm.transition(FollowUpStatus.DRAFT, "start") == FollowUpStatus.IN_PROGRESS
        assert followup_fsm.transition(FollowUpStatus.IN_PROGRESS, "complete") == FollowUpStatus.COMPLETED
        assert followup_fsm.transition(FollowUpStatus.COMPLETED, "confirm") == FollowUpStatus.CONFIRMED
        assert followup_fsm.transition(FollowUpStatus.CONFIRMED, "archive") == FollowUpStatus.ARCHIVED

    def test_invalid_transition_raises(self):
        """非法转换应抛出 InvalidTransition"""
        from app.core.state_machine import followup_fsm, FollowUpStatus, InvalidTransition

        with pytest.raises(InvalidTransition):
            followup_fsm.transition(FollowUpStatus.DRAFT, "confirm")

    def test_can_transition(self):
        """can_transition 应正确判断"""
        from app.core.state_machine import followup_fsm, FollowUpStatus

        assert followup_fsm.can_transition(FollowUpStatus.DRAFT, "start") is True
        assert followup_fsm.can_transition(FollowUpStatus.DRAFT, "confirm") is False

    def test_allowed_triggers(self):
        """allowed_triggers 应返回当前状态的所有合法触发"""
        from app.core.state_machine import followup_fsm, FollowUpStatus

        triggers = followup_fsm.allowed_triggers(FollowUpStatus.DRAFT)
        assert "start" in triggers
        assert "confirm" not in triggers

    def test_reject_transition(self):
        """应支持驳回到 DRAFT"""
        from app.core.state_machine import followup_fsm, FollowUpStatus

        assert followup_fsm.transition(FollowUpStatus.COMPLETED, "reject") == FollowUpStatus.DRAFT


# ==================== 6. 工具拆分测试 ====================


class TestToolsSplit:
    """验证工具拆分后向后兼容"""

    def test_medical_tools_count(self):
        """MEDICAL_TOOLS 应包含所有主对话工具"""
        from app.core.agno_tools import MEDICAL_TOOLS
        assert len(MEDICAL_TOOLS) == 9

    def test_nurse_tools_count(self):
        """NURSE_TOOLS 应包含护士工具"""
        from app.core.agno_tools import NURSE_TOOLS
        assert len(NURSE_TOOLS) == 5

    def test_doctor_tools_count(self):
        """DOCTOR_TOOLS 应包含医生工具"""
        from app.core.agno_tools import DOCTOR_TOOLS
        assert len(DOCTOR_TOOLS) == 6

    def test_tools_importable_from_facade(self):
        """所有工具应可从 agno_tools 门面模块导入"""
        from app.core.agno_tools import (
            agno_parse_nlu, agno_check_emergency,
            agno_save_health_data, agno_get_patient_context,
            agno_evaluate_vital_rules, agno_analyze_health_trends,
            agno_get_epds_result, agno_should_ask_weight, agno_should_ask_bp,
            agno_query_patient_data, agno_create_followup_record,
            agno_analyze_patient_comprehensive, agno_generate_medical_order,
            agno_handle_issue, agno_query_clinical_guideline,
        )

    def test_nlu_context_importable_from_facade(self):
        """NLU 上下文函数应可从门面模块导入"""
        from app.core.agno_tools import (
            set_nlu_context, get_nlu_context, pop_nlu_context,
            _nlu_context, _nlu_context_lock,
        )

    def test_routing_functions_importable(self):
        """路由函数应可从门面模块导入"""
        from app.core.agno_tools import (
            resolve_tools_by_intent,
            resolve_nurse_tools_by_intent,
            resolve_doctor_tools_by_intent,
            INTENT_TO_GROUP,
            TOOL_GROUPS,
            NURSE_TOOL_GROUPS,
            DOCTOR_TOOL_GROUPS,
        )

    def test_resolve_tools_by_intent(self):
        """resolve_tools_by_intent 应正确路由"""
        from app.core.agno_tools import resolve_tools_by_intent, MEDICAL_TOOLS

        tools, variant = resolve_tools_by_intent(None)
        assert variant == "complex"
        assert tools == MEDICAL_TOOLS

        tools, variant = resolve_tools_by_intent({"intent": "health_data_report"})
        assert variant == "record"

        tools, variant = resolve_tools_by_intent({"intent": "emergency"})
        assert variant == "emergency"

    def test_epds_thresholds_configurable(self):
        """EPDS 阈值应通过配置表而非 if/elif 定义"""
        from app.core.tools.health_data_tools import _EPDS_THRESHOLDS

        assert len(_EPDS_THRESHOLDS) == 4
        assert _EPDS_THRESHOLDS[0][1] == "low"
        assert _EPDS_THRESHOLDS[-1][1] == "severe"


# ==================== 7. ASR/TTS 后端注入测试 ====================


class TestBackendInjection:
    """验证 ASR/TTS 服务支持后端注入"""

    def test_asr_service_accepts_backend(self):
        """ASRService 应接受后端注入"""
        from app.services.asr_service import ASRService
        from app.services.asr_backends import MockASRBackend

        backend = MockASRBackend()
        service = ASRService(backend=backend)
        assert service._backend is backend

    def test_tts_service_accepts_backend(self):
        """TTSService 应接受后端注入"""
        from app.services.tts_service import TTSService
        from app.services.tts_backends import MockTTSBackend

        backend = MockTTSBackend()
        service = TTSService(backend=backend)
        assert service._backend is backend

    @pytest.mark.asyncio
    async def test_asr_service_uses_injected_backend(self):
        """注入后端时应使用后端而非旧逻辑"""
        from app.services.asr_service import ASRService

        class FakeBackend:
            async def transcribe(self, audio_base64, audio_format):
                return "fake transcription"

        service = ASRService(backend=FakeBackend())
        result = await service.transcribe("dGVzdA==", "wav")
        assert result == "fake transcription"

    @pytest.mark.asyncio
    async def test_tts_service_uses_injected_backend(self):
        """注入后端时应使用后端而非旧逻辑"""
        from app.services.tts_service import TTSService

        class FakeBackend:
            async def synthesize(self, text):
                return b"fake_audio"

        service = TTSService(backend=FakeBackend())
        result = await service.synthesize("hello")
        assert result == b"fake_audio"


# ==================== 8. MemoryManager 接口测试 ====================


class TestMemoryManagerRefactored:
    """验证 MemoryManager 支持 KeyValueStore 注入"""

    def test_memory_manager_accepts_store(self):
        """MemoryManager 应接受 KeyValueStore 注入"""
        from app.core.memory_manager import MemoryManager
        from app.services.memory_store import InMemoryKeyValueStore

        store = InMemoryKeyValueStore()
        mm = MemoryManager(store=store)
        mm.set("patient1", "key1", "value1")
        assert mm.get("patient1", "key1") == "value1"

    def test_memory_manager_should_ask_weight(self):
        """should_ask_weight 应正确判断"""
        from app.core.memory_manager import MemoryManager
        from app.services.memory_store import InMemoryKeyValueStore

        mm = MemoryManager(store=InMemoryKeyValueStore())
        # 未记录时应返回 True
        assert mm.should_ask_weight("patient1") is True

    def test_memory_manager_clear(self):
        """clear 应清除所有记忆"""
        from app.core.memory_manager import MemoryManager
        from app.services.memory_store import InMemoryKeyValueStore

        mm = MemoryManager(store=InMemoryKeyValueStore())
        mm.set("patient1", "key1", "value1")
        mm.set("patient1", "key2", "value2")
        mm.clear("patient1")
        assert mm.get("patient1", "key1") is None
        assert mm.get_all("patient1") == {}
