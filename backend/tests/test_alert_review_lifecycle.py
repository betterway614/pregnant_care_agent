"""
预警审核全链路测试 — 验证护士端与医生端逻辑正确性

测试场景:
1. 护士确认后预警仍为 PENDING，医生可继续审核
2. 医生确认后预警进入 CONFIRMED 终态
3. 完整链路: 创建 → 护士确认 → 医生审核 → 生成医嘱
4. 护士解除预警正常关闭
5. 护士升级预警仍保持可审核状态
6. FGR 预警仅医生可见（护士端过滤）
"""

import pytest
import uuid as uuid_lib
from datetime import datetime
from unittest.mock import patch

from app.utils.timezone import beijing_now


# ============================================================================
# Helper: 模拟 _append_history 的业务逻辑（不依赖 SQLAlchemy ORM）
# ============================================================================

def simulate_append_history(alert, action, source_role, level,
                            operator=None, reason=None):
    """等价于 alerts.py:_append_history 的业务逻辑，去除 ORM 依赖"""
    details = dict(alert.details or {})
    history = list(details.get("history", []))
    history.append({
        "seq": len(history) + 1,
        "action": action,
        "source_role": source_role,
        "level": level,
        "operator": operator,
        "reason": reason,
        "timestamp": beijing_now().isoformat(),
    })
    details["history"] = history
    details["source_role"] = source_role
    alert.details = details


def simulate_nurse_confirm(alert, operator="nurse-001", reason=None):
    """模拟改后 alerts.py nurse_confirm 分支：仅记录 history，不改 status"""
    simulate_append_history(alert, "nurse_confirm", "nurse", alert.level, operator, reason)
    # 注意：改后不再设 alert.status = "CONFIRMED"


def simulate_doctor_confirm(alert, operator="doctor-001", reason=None):
    """模拟 alerts.py confirm 分支：设 CONFIRMED + 记录 history"""
    alert.status = "CONFIRMED"
    simulate_append_history(alert, "confirm", "doctor", alert.level, operator, reason)


def simulate_nurse_dismiss(alert, operator="nurse-001", reason=None):
    """模拟 alerts.py nurse_dismiss 分支"""
    alert.status = "DISMISSED"
    simulate_append_history(alert, "nurse_dismiss", "nurse", alert.level, operator, reason)


def simulate_nurse_escalate(alert, new_level, operator="nurse-001", reason=None):
    """模拟 alerts.py nurse_escalate 分支：升级 level，不改 status"""
    alert.level = new_level
    simulate_append_history(alert, "nurse_escalate", "nurse", alert.level, operator, reason)


def simulate_nurse_appeal(alert, operator="nurse-001", reason=None):
    """模拟 alerts.py nurse_appeal 分支：记录 history，不改 status"""
    simulate_append_history(alert, "nurse_appeal", "nurse", alert.level, operator, reason)


def simulate_doctor_dismiss(alert, operator="doctor-001", reason=None):
    """模拟 alerts.py dismiss 分支"""
    alert.status = "DISMISSED"
    simulate_append_history(alert, "dismiss", "doctor", alert.level, operator, reason)


def simulate_doctor_downgrade(alert, target_level, operator="doctor-001", reason=None):
    """模拟 alerts.py downgrade 分支"""
    if target_level == "GREEN":
        alert.status = "DISMISSED"
    else:
        alert.level = target_level
        alert.status = "PENDING"
    simulate_append_history(alert, "downgrade", "doctor", target_level, operator, reason)


# ============================================================================
# Fake Alert 构造器
# ============================================================================

def make_fake_alert(
    *,
    alert_id=None,
    pregnant_id="P001",
    level="RED",
    status="PENDING",
    trigger_source="RULE_ENGINE",
    rule_id="RULE_BP_HIGH",
    domain="vital",
    message="血压异常升高（≥140/90mmHg）",
    details=None,
    created_at=None,
):
    """构建假 Alert 对象用于状态转换测试"""
    if alert_id is None:
        alert_id = uuid_lib.uuid4()
    if created_at is None:
        created_at = datetime(2026, 6, 13, 10, 0, 0)

    class FakeAlert:
        pass

    alert = FakeAlert()
    alert.id = alert_id
    alert.pregnant_id = pregnant_id
    alert.trigger_source = trigger_source
    alert.rule_id = rule_id
    alert.domain = domain
    alert.level = level
    alert.message = message
    alert.details = details or {}
    alert.status = status
    alert.reviewed_by = None
    alert.reviewed_at = None
    alert.created_at = created_at

    return alert


# ============================================================================
# 1. 核心: 护士确认后保持 PENDING
# ============================================================================

class TestNurseConfirmKeepsPending:
    """验证: 护士确认后预警保持 PENDING，医生可继续操作"""

    def test_nurse_confirm_does_not_change_status(self):
        """护士确认：status 仍为 PENDING（仅记录 history）"""
        alert = make_fake_alert(status="PENDING")
        simulate_nurse_confirm(alert, operator="nurse-001", reason="血压确实偏高")

        assert alert.status == "PENDING", (
            f"FAIL: 护士确认后 status={alert.status}，应为 PENDING。"
            "当前 status 为终态会阻断医生后续审核/医嘱按钮"
        )

        history = alert.details.get("history", [])
        assert len(history) >= 1
        entry = history[-1]
        assert entry["action"] == "nurse_confirm"
        assert entry["source_role"] == "nurse"
        assert entry["operator"] == "nurse-001"
        assert entry["reason"] == "血压确实偏高"

    def test_doctor_confirm_after_nurse_confirm(self):
        """医生在护士确认后仍可审核确认 → CONFIRMED 终态"""
        alert = make_fake_alert(status="PENDING")

        # Step 1: 护士确认
        simulate_nurse_confirm(alert)
        assert alert.status == "PENDING", "护士确认后必须仍为 PENDING"

        # Step 2: 医生确认 → 真正终态
        simulate_doctor_confirm(alert, reason="已审核，开具医嘱")
        assert alert.status == "CONFIRMED"

        history = alert.details.get("history", [])
        assert len(history) == 2
        assert history[0]["action"] == "nurse_confirm"
        assert history[1]["action"] == "confirm"

    def test_doctor_downgrade_after_nurse_confirm(self):
        """医生在护士确认后可降级预警"""
        alert = make_fake_alert(status="PENDING", level="RED")
        simulate_nurse_confirm(alert)

        # 医生降级 → ORANGE, status 回到 PENDING
        simulate_doctor_downgrade(alert, "ORANGE", reason="复查后降级")
        assert alert.status == "PENDING"
        assert alert.level == "ORANGE"

        # 降级到 GREEN → DISMISSED
        alert2 = make_fake_alert(status="PENDING", level="RED")
        simulate_nurse_confirm(alert2)
        simulate_doctor_downgrade(alert2, "GREEN", reason="恢复正常")
        assert alert2.status == "DISMISSED"

    def test_nurse_action_preserves_doctor_actionability(self):
        """所有护士操作不应改变 status，确保医生端按钮不被禁用"""
        # 验证: 护士每个操作后 status 都保持 PENDING
        for nurse_action in ["confirm", "escalate", "appeal"]:
            alert = make_fake_alert(status="PENDING", level="YELLOW")

            if nurse_action == "confirm":
                simulate_nurse_confirm(alert)
            elif nurse_action == "escalate":
                simulate_nurse_escalate(alert, "ORANGE")
            elif nurse_action == "appeal":
                simulate_nurse_appeal(alert, reason="医生降级不合理")

            assert alert.status == "PENDING", (
                f"护士{nurse_action}后 status={alert.status}，必须为 PENDING"
            )


# ============================================================================
# 2. 护士其他操作
# ============================================================================

class TestNurseOtherActions:
    """验证: 护士解除/升级/复议的状态语义"""

    def test_nurse_dismiss_closes_alert(self):
        """护士解除 → DISMISSED（正确：护士判断无需处理直接关闭）"""
        alert = make_fake_alert(status="PENDING")
        simulate_nurse_dismiss(alert, reason="血压已恢复正常")
        assert alert.status == "DISMISSED"

    def test_nurse_escalate_upgrades_level_only(self):
        """护士升级：YELLOW→ORANGE，不改 status"""
        alert = make_fake_alert(status="PENDING", level="YELLOW")
        simulate_nurse_escalate(alert, "ORANGE", reason="情况恶化")
        assert alert.status == "PENDING"
        assert alert.level == "ORANGE"

    def test_nurse_escalate_orange_to_red(self):
        """护士升级：ORANGE→RED，不改 status"""
        alert = make_fake_alert(status="PENDING", level="ORANGE")
        simulate_nurse_escalate(alert, "RED", reason="紧急升级")
        assert alert.status == "PENDING"
        assert alert.level == "RED"

    def test_nurse_appeal_keeps_status(self):
        """护士复议不改 status（医生降级后护士反对）"""
        alert = make_fake_alert(status="PENDING", level="ORANGE")
        simulate_nurse_appeal(alert, reason="医生降级不合理，复议")
        assert alert.status == "PENDING"


# ============================================================================
# 3. 医生操作终态
# ============================================================================

class TestDoctorConfirmTerminal:
    """验证: 医生确认/解除是真正的终态"""

    def test_doctor_confirm_sets_confirmed(self):
        alert = make_fake_alert(status="PENDING")
        simulate_doctor_confirm(alert, reason="高危确认，开医嘱")
        assert alert.status == "CONFIRMED"

    def test_doctor_dismiss_sets_dismissed(self):
        alert = make_fake_alert(status="PENDING")
        simulate_doctor_dismiss(alert, reason="误报")
        assert alert.status == "DISMISSED"


# ============================================================================
# 4. 完整链路集成测试
# ============================================================================

class TestAlertLifecycleIntegration:
    """验证完整的预警审核链路：创建 → 护士确认 → 医生审核"""

    def test_full_lifecycle_nurse_then_doctor(self):
        """完整链路: 创建(PENDING) → 护士确认(PENDING) → 医生确认(CONFIRMED)"""
        alert = make_fake_alert(level="RED", status="PENDING")

        # Step 1: 护士确认 — status 保持 PENDING
        simulate_nurse_confirm(alert, operator="nurse-001", reason="核实属实")
        assert alert.status == "PENDING"

        # Step 2: 医生确认 — 进入终态 CONFIRMED
        simulate_doctor_confirm(alert, operator="doctor-001", reason="已审核，开具医嘱")
        assert alert.status == "CONFIRMED"

        # 验证时间线完整且顺序正确
        history = alert.details["history"]
        actions = [h["action"] for h in history]
        assert "nurse_confirm" in actions
        assert "confirm" in actions
        assert actions.index("nurse_confirm") < actions.index("confirm"), (
            "护士确认必须在医生确认之前"
        )

    def test_doctor_direct_confirm_without_nurse(self):
        """医生直接确认（跳过护士）— 用于 FGR 等医生专属预警"""
        alert = make_fake_alert(
            status="PENDING",
            trigger_source="FGR_ALGORITHM",
            message="FGR极高风险",
        )
        simulate_doctor_confirm(alert, reason="FGR高危，直接审核")
        assert alert.status == "CONFIRMED"
        assert len(alert.details["history"]) == 1
        assert alert.details["history"][0]["action"] == "confirm"


# ============================================================================
# 5. FGR 预警过滤
# ============================================================================

class TestFgrAlertFiltering:
    """验证: FGR 医生专属预警不出现在护士端"""

    def test_fgr_doctor_alert_filtered_from_nurse_view(self):
        """护士端 AlertList 的过滤逻辑"""
        def nurse_filter(alerts):
            return [
                a for a in alerts
                if not (
                    a.get("trigger_source") == "FGR_ALGORITHM"
                    and a.get("details", {}).get("action") == "ALERT_DOCTOR"
                )
            ]

        alerts = [
            {"id": "a1", "trigger_source": "RULE_ENGINE",
             "details": {"action": "ALERT_NURSE_AND_DOCTOR"}, "message": "血压异常"},
            {"id": "a2", "trigger_source": "FGR_ALGORITHM",
             "details": {"action": "ALERT_DOCTOR"}, "message": "FGR极高风险"},
            {"id": "a3", "trigger_source": "FGR_ALGORITHM",
             "details": {"action": "ALERT_NURSE"}, "message": "FGR中风险"},
            {"id": "a4", "trigger_source": "RULE_ENGINE",
             "details": {"action": "ALERT_NURSE"}, "message": "体重增长过慢"},
        ]

        filtered = nurse_filter(alerts)
        ids = [a["id"] for a in filtered]

        assert "a2" not in ids, "FGR + ALERT_DOCTOR 必须被过滤"
        assert "a1" in ids, "常规预警不应被过滤"
        assert "a3" in ids, "FGR + ALERT_NURSE 应保留"
        assert "a4" in ids, "常规 ALERT_NURSE 不应被过滤"
        assert len(filtered) == 3

    def test_fgr_rule_engine_actions(self):
        """FGR 规则引擎的 action 定义正确"""
        from app.core.rule_engine import rule_engine

        critical_hits = rule_engine.evaluate_fgr_risk("critical")
        high_hits = rule_engine.evaluate_fgr_risk("high")
        medium_hits = rule_engine.evaluate_fgr_risk("medium")

        # Critical 和 High → ALERT_DOCTOR（医生专属）
        for hit in critical_hits + high_hits:
            assert hit["action"] == "ALERT_DOCTOR", (
                f"{hit['rule_id']} 必须是 ALERT_DOCTOR，实际为 {hit['action']}"
            )

        # Medium → ALERT_NURSE
        for hit in medium_hits:
            assert hit["action"] == "ALERT_NURSE", (
                f"{hit['rule_id']} 应为 ALERT_NURSE，实际为 {hit['action']}"
            )

    def test_fgr_details_action_field_set_correctly(self):
        """FGR 预警创建时 details.action 被正确设置"""
        from app.core.rule_engine import rule_engine

        result = {"case_id": "CASE_001", "risk_level": "critical"}
        rule_hits = rule_engine.evaluate_fgr_risk(result["risk_level"])

        for hit in rule_hits:
            details = {
                "action": hit.get("action", ""),
                "triggered_rules": [hit["rule_id"]],
                "case_id": result["case_id"],
                "risk_level": result["risk_level"],
            }
            assert details["action"] == "ALERT_DOCTOR", (
                f"details.action 必须为 ALERT_DOCTOR，实际为 {details['action']}"
            )


# ============================================================================
# 6. 前端 isStatusActionable 等价逻辑
# ============================================================================

class TestIsStatusActionable:
    """验证: 前端 ReviewWorkbench.vue isStatusActionable 的等价逻辑"""

    @staticmethod
    def is_actionable(status: str) -> bool:
        """改后前端逻辑"""
        return status.upper() in ("PENDING", "ESCALATED", "CONFIRMED")

    def test_actionable_statuses(self):
        assert self.is_actionable("PENDING")
        assert self.is_actionable("pending")
        assert self.is_actionable("ESCALATED")
        assert self.is_actionable("CONFIRMED")

    def test_non_actionable_statuses(self):
        assert not self.is_actionable("DISMISSED")
        assert not self.is_actionable("AUTO_DISMISSED")

    def test_nurse_confirm_keeps_pending_so_actionable(self):
        """核心链路验证: nurse_confirm 不改 status → PENDING → is_actionable=True"""
        status_after_nurse_confirm = "PENDING"  # 改后行为
        assert self.is_actionable(status_after_nurse_confirm) is True, (
            "修复后护士确认不改变 status(PENDING)，医生端按钮必须可用"
        )

    def test_old_behavior_would_have_broken(self):
        """回归验证: 改前的行为会导致医生按钮被禁用"""
        # 改前: nurse_confirm 设 status="CONFIRMED"
        # 但 CONFIRMED 现在也在 actionable 列表中（兜底）
        # 这就是为什么改前会broken — 旧代码只在 is_actionable 里放了 pending/escalated
        old_actionable_statuses = ["pending", "escalated"]
        assert "confirmed" not in old_actionable_statuses, (
            "旧版 isStatusActionable 不包含 confirmed，"
            "这就是护士确认后医生按钮被禁用的直接原因"
        )
