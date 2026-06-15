"""产检排期引擎测试 — TDD 驱动

测试覆盖：
- 标准13次产检生成（附录一）
- 超声里程碑生成（附录二）
- 风险联动（FGR/GDM/高血压/GBS阳性）
- 孕周跳过逻辑
- 动态孕周计算
"""
from datetime import date, timedelta

import pytest


# ============================================================
# 辅助函数
# ============================================================

def _make_date(iso: str) -> date:
    return date.fromisoformat(iso)


# ============================================================
# RED: ScheduleEngine 新版核心测试
# ============================================================


class TestScheduleEngineGeneration:
    """测试新版排期引擎生成逻辑"""

    def test_generates_all_13_standard_visits(self):
        """标准无风险孕妇应生成全部13次产检（附录一）"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        visit_numbers = {n.get("visit_number") for n in nodes if n.get("visit_number")}
        assert len(visit_numbers) == 13, f"应有13次标准产检，生成了{len(visit_numbers)}次"
        assert min(visit_numbers) == 1
        assert max(visit_numbers) == 13

    def test_visit_1_contains_mandatory_items(self):
        """第1次产检（6-10周）必须包含确认妊娠B超和血检"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        v1 = [n for n in nodes if n.get("visit_number") == 1]
        assert len(v1) >= 1, "应有至少1个第1次产检节点"
        mandatory = v1[0].get("mandatory_items", [])
        mandatory_str = " ".join(mandatory)
        assert "B超" in mandatory_str or "妊娠" in mandatory_str
        assert "血" in mandatory_str  # HCG、血常规等

    def test_visit_4_is_anomaly_scan(self):
        """第4次产检（20-24周）大排畸"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        v4_nodes = [n for n in nodes if n.get("visit_number") == 4]
        assert len(v4_nodes) >= 1
        item_text = " ".join(v4_nodes[0].get("mandatory_items", [])) + v4_nodes[0].get("item", "")
        assert "大排畸" in item_text or "系统超声" in item_text

    def test_visit_5_is_ogtt(self):
        """第5次产检（24-28周）OGTT糖耐"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        v5_nodes = [n for n in nodes if n.get("visit_number") == 5]
        assert len(v5_nodes) >= 1
        item_text = " ".join(v5_nodes[0].get("mandatory_items", [])) + v5_nodes[0].get("item", "")
        assert "OGTT" in item_text or "糖耐" in item_text

    def test_visit_8_is_gbs(self):
        """第8次产检（35-37周）GBS筛查"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        v8_nodes = [n for n in nodes if n.get("visit_number") == 8]
        assert len(v8_nodes) >= 1
        item_text = " ".join(v8_nodes[0].get("mandatory_items", [])) + v8_nodes[0].get("item", "")
        assert "GBS" in item_text or "B族" in item_text

    def test_late_visits_9_to_13_weekly(self):
        """孕晚期37-41周每周一次（第9-13次）"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        late_visits = [n for n in nodes if n.get("visit_number") in (9, 10, 11, 12, 13)]
        assert len(late_visits) >= 5, f"晚期应有至少5次产检，实际{len(late_visits)}次"

    def test_nodes_have_gest_week_range(self):
        """新版节点应包含孕周范围字段"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        for n in nodes:
            if n.get("visit_number"):
                assert "gest_week_start" in n, f"缺少 gest_week_start (visit={n.get('visit_number')})"
                assert "gest_week_end" in n, f"缺少 gest_week_end (visit={n.get('visit_number')})"
                assert n["gest_week_start"] <= n["gest_week_end"]

    def test_nodes_have_category(self):
        """节点应有 category 字段区分产检/超声/检验"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        categories = {n.get("category") for n in nodes if n.get("category")}
        assert "checkup" in categories, "应有产检分类"
        # 超声和检验分类至少有一个存在
        assert len(categories) >= 2, f"应有多种分类，实际: {categories}"

    def test_nodes_have_notes(self):
        """节点应包含注意事项"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        nodes_with_notes = [n for n in nodes if n.get("notes")]
        assert len(nodes_with_notes) > 0, "至少部分节点应有注意事项"


class TestUltrasoundMilestones:
    """测试附录二超声关键节点"""

    def test_generates_ultrasound_milestones(self):
        """应生成超声里程碑节点（部分已合并到标准产检visit中）"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        us_nodes = [n for n in nodes if n.get("category") == "ultrasound"]
        # 大排畸(20-24周)已作为visit_number=4的标准产检，故独立超声里程碑为4个
        assert len(us_nodes) >= 3, f"应有至少3个超声节点: {[n.get('item') for n in us_nodes]}"

    def test_nt_ultrasound_at_11_to_13_weeks(self):
        """NT超声应在11-13+6周"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        nt_nodes = [
            n for n in nodes
            if "NT" in (n.get("item", "") + " ".join(n.get("mandatory_items", [])))
        ]
        assert len(nt_nodes) >= 1, f"应有NT超声节点，找到: {len(nt_nodes)}"
        nt = nt_nodes[0]
        assert 11 <= nt.get("gest_week_start", 0) <= 13


class TestRiskBasedAdjustments:
    """测试风险联动"""

    def test_fgr_adds_monitoring(self):
        """FGR高危应增加额外B超监测"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        standard = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)
        fgr = schedule_engine.generate(lmp, risk_tags=["FGR高危"], current_gest_week=None)

        assert len(fgr) > len(standard), f"FGR高风险应有更多节点 (std={len(standard)}, fgr={len(fgr)})"
        fgr_nodes = [n for n in fgr if n.get("node_type") == "fgr_high_risk"]
        assert len(fgr_nodes) >= 1

    def test_gdm_adds_glucose_monitoring(self):
        """GDM应增加血糖监测"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        standard = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)
        gdm = schedule_engine.generate(lmp, risk_tags=["GDM"], current_gest_week=None)

        assert len(gdm) > len(standard)
        gdm_nodes = [n for n in gdm if "血糖" in n.get("item", "")]
        assert len(gdm_nodes) >= 1

    def test_hypertension_adds_bp_monitoring(self):
        """高血压应增加血压监测"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        standard = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)
        htn = schedule_engine.generate(lmp, risk_tags=["高血压"], current_gest_week=None)

        assert len(htn) > len(standard)
        htn_nodes = [n for n in htn if "血压" in n.get("item", "")]
        assert len(htn_nodes) >= 1


class TestWeekSkipping:
    """测试孕周跳过逻辑"""

    def test_skips_past_visits(self):
        """当前孕周已过期的检查应跳过"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        # 假设当前已到孕28周，前4次检查应跳过
        current_week = 28
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=current_week)

        for n in nodes:
            if n.get("gest_week_end"):
                assert n["gest_week_end"] >= current_week, (
                    f"过期节点未跳过: visit={n.get('visit_number')} "
                    f"range={n.get('gest_week_start')}-{n.get('gest_week_end')} "
                    f"current={current_week}"
                )

    def test_no_skip_when_no_current_week(self):
        """不传入 current_gest_week 时应生成全部节点"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        # 应包含第1次检查（最早）
        v1 = [n for n in nodes if n.get("visit_number") == 1]
        assert len(v1) >= 1, "不跳过时应包含孕早期检查"


class TestScheduleDateCalculation:
    """测试排期日期计算"""

    def test_dates_are_sequential(self):
        """生成的排期日期应按时间先后排列"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        dates = [n["scheduled_date"] for n in nodes]
        assert dates == sorted(dates), "排期应按日期排序"

    def test_dates_based_on_lmp(self):
        """排期日期应基于LMP计算"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-03-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        v1 = [n for n in nodes if n.get("visit_number") == 1][0]
        # 第1次检查在6-10周，取中间8周
        expected_approx = lmp + timedelta(weeks=8)
        actual = _make_date(v1["scheduled_date"])
        delta_days = abs((actual - expected_approx).days)
        assert delta_days <= 21, f"日期偏离预期太大: {actual} vs {expected_approx} (delta={delta_days}天)"


class TestNodeOutputStructure:
    """测试输出的数据结构完整性"""

    def test_all_nodes_have_required_fields(self):
        """每个节点必须包含所有必要字段"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        required = {"gest_week", "scheduled_date", "item", "node_type"}
        for n in nodes:
            missing = required - set(n.keys())
            assert not missing, f"节点缺少字段: {missing}, node={n}"

    def test_node_types_are_valid(self):
        """node_type 应该是有效值"""
        from app.services.schedule_engine import schedule_engine

        lmp = _make_date("2026-01-01")
        nodes = schedule_engine.generate(lmp, risk_tags=[], current_gest_week=None)

        valid_types = {
            "routine", "fgr_high_risk", "gdm_monitor", "bp_monitor",
            "ultrasound", "checkup", "lab", "custom",
        }
        for n in nodes:
            assert n["node_type"] in valid_types, (
                f"无效的 node_type: {n['node_type']} (visit={n.get('visit_number')})"
            )
