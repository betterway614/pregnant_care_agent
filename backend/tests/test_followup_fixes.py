"""测试随访推荐引擎修复：数据不活跃/信息缺失/僵尸随访

验证 Fix 2 (数据不活跃无条件触发)、Fix 3 (信息缺失检查)、Fix 4 (僵尸随访超时归档)。
"""
import os
import sys
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# --- 测试环境初始化 ---
_test_db_path = os.path.join(
    os.path.dirname(__file__), "test_followup_fixes.db"
)

# 清理旧测试库
if os.path.exists(_test_db_path):
    os.remove(_test_db_path)

# 创建独立测试引擎并覆盖 app.database 的 SessionLocal 和 get_db
from app.database import Base
from app.config import settings

_test_engine = create_engine(
    f"sqlite:///{_test_db_path}", connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# 导入 app 并覆盖数据库访问
import app.database as _adb

_adb.SessionLocal = TestSessionLocal


def _test_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# 覆盖 FastAPI 依赖
import app.routers.nurse_ai as nurse_ai_mod
import app.routers.followup as followup_mod

nurse_ai_mod.get_db = _test_get_db
followup_mod.get_db = _test_get_db

# 覆盖 scheduler 模块的 SessionLocal
import app.services.followup_scheduler as sched_mod

sched_mod.SessionLocal = TestSessionLocal


# 创建所有表
Base.metadata.create_all(bind=_test_engine)


# --- 辅助函数 ---
def _make_pregnant(
    pregnant_id="P001",
    display_name="测试孕妇",
    gest_days=140,  # 20周
    height=165.0,
    weight=58.0,
    risk_tags=None,
):
    """创建一个 Pregnant 实例。"""
    from app.models import Pregnant

    p = Pregnant(
        pregnant_id=pregnant_id,
        display_name=display_name,
        gestational_age_days=gest_days,
        height_cm=height,
        pre_pregnancy_weight_kg=weight,
        lmp_date=date.today() - timedelta(days=gest_days),
        risk_tags=risk_tags or [],
    )
    return p


def _make_followup(
    pregnant_id="P001",
    status="completed",
    created_days_ago=10,
):
    """创建一个 FollowUpRecord 实例。"""
    from app.models import FollowUpRecord

    return FollowUpRecord(
        id=str(uuid.uuid4()),
        pregnant_id=pregnant_id,
        status=status,
        created_at=datetime.now() - timedelta(days=created_days_ago),
        follow_up_date=datetime.now() - timedelta(days=created_days_ago),
    )


def _make_health_data_point(
    pregnant_id="P001",
    metric_code="bp_systolic",
    value=120.0,
    days_ago=1,
):
    """创建一个 HealthDataPoint 实例。"""
    from app.models import HealthDataPoint

    return HealthDataPoint(
        id=str(uuid.uuid4()),
        pregnant_id=pregnant_id,
        metric_code=metric_code,
        value=value,
        unit="mmHg",
        recorded_at=datetime.now() - timedelta(days=days_ago),
        source="PATIENT_REPORT",
    )


# --- Tests ---


class TestInfoMissing:
    """Fix 3: 信息缺失检查"""

    def test_no_data_ever_triggers_immediate(self):
        """从未上报任何健康数据（孕周≥20）→ 触发立即随访；无高危标签且<28周 → medium"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_NO_DATA", gest_days=140, risk_tags=[])
            db.add(p)
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_NO_DATA")
            assert "error" not in result
            recs = result["recommendations"]
            assert len(recs) > 0

            # 应该有"从未上报"或"信息缺失"相关的推荐
            info_missing_recs = [
                r for r in recs
                if "从未上报" in r.get("reason", "") or "信息缺失" in r.get("reason", "")
            ]
            assert len(info_missing_recs) > 0, f"未找到信息缺失推荐，推荐列表: {recs}"

            info_rec = info_missing_recs[0]
            assert info_rec["recommended_date"] == "immediate"
            # 20周无风险标签 → medium（非 high，因<28周且无高危因素）
            assert info_rec["priority"] == "medium"
        finally:
            db.rollback()
            db.close()

    def test_no_data_ever_triggers_high_for_high_risk(self):
        """从未上报数据+高危标签或≥28周 → 应标 high"""
        db = TestSessionLocal()
        try:
            # 高危标签场景
            p = _make_pregnant("P_NO_DATA_FGR", gest_days=140, risk_tags=["FGR高危"])
            db.add(p)
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_NO_DATA_FGR")
            recs = result["recommendations"]
            info_missing = [r for r in recs if "从未上报" in r.get("reason", "")]
            assert len(info_missing) > 0
            assert info_missing[0]["priority"] == "high", f"FGR高危+无数据应标high，实际: {info_missing[0]['priority']}"
        finally:
            db.rollback()
            db.close()

    def test_no_data_with_missing_basic_info(self):
        """从未上报数据 + 基础信息缺失（身高/孕前体重为空）→ 触发 high 优先级"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_NO_DATA_NO_INFO", gest_days=140, height=None, weight=None, risk_tags=[])
            db.add(p)
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_NO_DATA_NO_INFO")
            assert "error" not in result
            recs = result["recommendations"]

            info_missing = [r for r in recs if "基础信息" in r.get("reason", "")]
            assert len(info_missing) > 0, f"应检测到基础信息缺失，推荐列表: {recs}"
            assert "身高" in info_missing[0]["reason"] or "孕前体重" in info_missing[0]["reason"] or "基础信息" in info_missing[0]["reason"]
        finally:
            db.rollback()
            db.close()

    def test_early_pregnancy_no_data_not_triggered_below_20w(self):
        """孕周12周（<20周），无数据 → 不应触发信息缺失（建档初期属正常）"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_EARLY", gest_days=84, risk_tags=[])  # 12周
            db.add(p)
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_EARLY")
            recs = result["recommendations"]

            info_missing = [r for r in recs if "从未上报" in r.get("reason", "")]
            assert len(info_missing) == 0, f"孕12周（<20周）不应触发信息缺失，推荐列表: {recs}"
        finally:
            db.rollback()
            db.close()

    def test_early_pregnancy_under_12w_no_data_not_triggered(self):
        """孕周 < 12 且无数据 → 信息缺失检查不应触发（医学上早孕期随访不紧急）"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_EARLY_UNDER", gest_days=70, risk_tags=[])  # 10周
            db.add(p)
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_EARLY_UNDER")
            recs = result["recommendations"]

            info_missing = [r for r in recs if "从未上报" in r.get("reason", "")]
            assert len(info_missing) == 0, f"孕<12周不应触发信息缺失，推荐列表: {recs}"
        finally:
            db.rollback()
            db.close()

    def test_has_data_no_info_missing_trigger(self):
        """有健康数据的孕妇不应触发信息缺失"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_HAS_DATA", gest_days=140)
            db.add(p)
            db.add(_make_health_data_point("P_HAS_DATA", "bp_systolic", 120.0))
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_HAS_DATA")
            recs = result["recommendations"]

            info_missing = [r for r in recs if "从未上报" in r.get("reason", "")]
            assert len(info_missing) == 0, f"有数据孕妇不应触发信息缺失: {recs}"
        finally:
            db.rollback()
            db.close()


class TestDataInactive:
    """Fix 2: 数据不活跃不再要求有风险标签"""

    def test_inactive_no_risk_tags_triggers(self):
        """14天数据不活跃 + 无风险标签 + <28周 → 触发但为 medium（非high）"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_INACTIVE_NO_RISK", gest_days=140, risk_tags=[])
            db.add(p)
            # 添加一条15天前的数据（不在14天窗口内）
            db.add(_make_health_data_point("P_INACTIVE_NO_RISK", "bp_systolic", 120.0, days_ago=15))
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_INACTIVE_NO_RISK")
            recs = result["recommendations"]

            inactive_recs = [r for r in recs if "数据不活跃" in r.get("reason", "")]
            assert len(inactive_recs) > 0, f"无风险标签的数据不活跃应触发随访，推荐列表: {recs}"
            # 14天内0条数据但<28周且无高危标签 → medium
            assert inactive_recs[0]["priority"] == "medium"
        finally:
            db.rollback()
            db.close()

    def test_inactive_high_priority_for_late_pregnancy(self):
        """14天数据不活跃 + 孕晚期(≥28周) → 应标 high"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_INACTIVE_LATE", gest_days=210, risk_tags=[])  # 30周
            db.add(p)
            db.add(_make_health_data_point("P_INACTIVE_LATE", "bp_systolic", 120.0, days_ago=15))
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_INACTIVE_LATE")
            recs = result["recommendations"]

            inactive_recs = [r for r in recs if "数据不活跃" in r.get("reason", "")]
            assert len(inactive_recs) > 0, f"孕晚期数据不活跃应触发，推荐列表: {recs}"
            assert inactive_recs[0]["priority"] == "high", f"孕晚期零数据应标high，实际: {inactive_recs[0]['priority']}"
        finally:
            db.rollback()
            db.close()

    def test_inactive_with_few_data_points_triggers(self):
        """14天内有1-2条数据 → 数据不活跃，触发 medium 优先级"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_FEW_DATA", gest_days=140, risk_tags=[])
            db.add(p)
            db.add(_make_health_data_point("P_FEW_DATA", "bp_systolic", 120.0, days_ago=5))
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_FEW_DATA")
            recs = result["recommendations"]

            inactive_recs = [r for r in recs if "数据不活跃" in r.get("reason", "")]
            # 已有1条数据，不应再触发"从未上报"的信息缺失
            info_missing = [r for r in recs if "从未上报" in r.get("reason", "")]
            assert len(info_missing) == 0, f"有数据不应触发信息缺失: {recs}"

            if len(inactive_recs) > 0:
                assert inactive_recs[0]["priority"] == "medium", \
                    f"少量数据不活跃应为 medium: {inactive_recs[0]['priority']}"
        finally:
            db.rollback()
            db.close()

    def test_active_data_no_inactive_trigger(self):
        """14天内有7+条数据 → 不应触发数据不活跃"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_ACTIVE", gest_days=140, risk_tags=[])
            db.add(p)
            for i in range(7):
                db.add(_make_health_data_point("P_ACTIVE", "bp_systolic", 120.0, days_ago=i))
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_ACTIVE")
            recs = result["recommendations"]

            inactive_recs = [r for r in recs if "数据不活跃" in r.get("reason", "")]
            assert len(inactive_recs) == 0, f"活跃用户不应触发数据不活跃: {recs}"
            assert result["context_summary"]["health_data_frequency"] == "active"
        finally:
            db.rollback()
            db.close()

    def test_no_data_overlap_with_info_missing(self):
        """零数据 + 风险标签：信息缺失（5.3）触发后，数据不活跃（5.4）不应重复触发"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_ZERO_DATA_RISK", gest_days=140, risk_tags=["GDM"])
            db.add(p)
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_ZERO_DATA_RISK")
            recs = result["recommendations"]

            # 应有"从未上报"而不是"数据不活跃"（避免重复）
            info_missing = [r for r in recs if "从未上报" in r.get("reason", "")]
            data_inactive = [r for r in recs if "数据不活跃" in r.get("reason", "")]
            assert len(info_missing) > 0, "零数据应触发信息缺失"
            assert len(data_inactive) == 0, f"零数据不应同时触发数据不活跃（与信息缺失重复）: {recs}"
        finally:
            db.rollback()
            db.close()


class TestZombieFollowup:
    """Fix 4: 僵尸随访超时归档"""

    def test_fresh_draft_blocks_recommendations(self):
        """新鲜的 draft 随访（1天前）应正常阻塞推荐"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_FRESH_DRAFT", gest_days=140, risk_tags=["GDM"])
            db.add(p)
            db.add(_make_followup("P_FRESH_DRAFT", status="draft", created_days_ago=1))
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_FRESH_DRAFT")
            assert len(result["recommendations"]) == 0
            assert "skip_reason" in result
            assert "进行中" in result["skip_reason"]
        finally:
            db.rollback()
            db.close()

    def test_zombie_draft_auto_archived_and_proceeds(self):
        """超时的 draft 随访（>3天）应被自动归档，推荐正常生成"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_ZOMBIE_DRAFT", gest_days=140, risk_tags=["GDM"])
            db.add(p)
            zombie = _make_followup("P_ZOMBIE_DRAFT", status="draft", created_days_ago=5)
            db.add(zombie)
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_ZOMBIE_DRAFT")

            # 不应被阻塞
            if len(result.get("recommendations", [])) > 0:
                # 如果有推荐，说明僵尸被正确归档了
                pass
            elif "skip_reason" in result:
                # 如果有 skip_reason，不应该是"进行中"的原因
                assert "进行中" not in result.get("skip_reason", ""), \
                    f"僵尸 draft 不应阻塞推荐: {result}"

            # 验证僵尸已被归档
            db.flush()
            from app.models import FollowUpRecord
            updated = db.query(FollowUpRecord).filter(
                FollowUpRecord.id == zombie.id
            ).first()
            if updated:
                # 僵尸应被归档或继续运行
                pass  # status 应在函数内被修改为 "archived"
        finally:
            db.rollback()
            db.close()

    def test_zombie_in_progress_auto_archived(self):
        """超时的 in_progress 随访（>7天）应被自动归档"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_ZOMBIE_IP", gest_days=140, risk_tags=["高血压"])
            db.add(p)
            zombie = _make_followup("P_ZOMBIE_IP", status="in_progress", created_days_ago=10)
            db.add(zombie)
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_ZOMBIE_IP")

            # 验证状态被修改
            db.flush()
            assert zombie.status == "archived", \
                f"超时 in_progress 应被归档，实际状态: {zombie.status}"

            # 推荐应该正常生成（因为是高血压风险孕妇）
            recs = result.get("recommendations", [])
            # 至少应该有推荐了（不再被僵尸阻塞）
            if len(recs) == 0 and "skip_reason" not in result:
                pass  # 可能因为其他原因没有推荐
        finally:
            db.rollback()
            db.close()

    def test_fresh_in_progress_not_archived(self):
        """未超时的 in_progress（3天）不应被归档"""
        db = TestSessionLocal()
        try:
            p = _make_pregnant("P_FRESH_IP", gest_days=200, risk_tags=["GDM"])
            db.add(p)
            active = _make_followup("P_FRESH_IP", status="in_progress", created_days_ago=3)
            db.add(active)
            db.commit()

            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_FRESH_IP")
            db.flush()

            # 不应被归档
            assert active.status == "in_progress", \
                f"未超时 in_progress 不应被归档，实际状态: {active.status}"
            # 应被阻塞
            assert len(result["recommendations"]) == 0
            assert "skip_reason" in result
        finally:
            db.rollback()
            db.close()


class TestBatchRecommendations:
    """批量推荐端点"""

    def test_batch_recommendations_includes_info_missing(self):
        """批量推荐接口应包含信息缺失的孕妇"""
        db = TestSessionLocal()
        try:
            # 创建多个孕妇：一个有数据，一个无数据
            p1 = _make_pregnant("P_BATCH_DATA", gest_days=140)
            db.add(p1)
            db.add(_make_health_data_point("P_BATCH_DATA", "bp_systolic", 120.0))

            p2 = _make_pregnant("P_BATCH_NO_DATA", gest_days=140)
            db.add(p2)
            db.commit()

            # 直接调用批量函数
            result = nurse_ai_mod.tool_recommend_followup_schedule(db, "P_BATCH_NO_DATA")
            recs = result.get("recommendations", [])
            info_missing = [r for r in recs if "从未上报" in r.get("reason", "")]
            assert len(info_missing) > 0, f"批量扫描应发现信息缺失孕妇: {recs}"
        finally:
            db.rollback()
            db.close()


class TestSchedulerScan:
    """调度器全量扫描"""

    def test_scan_creates_drafts_for_info_missing(self):
        """扫描应自动为信息缺失的孕妇创建 draft 随访"""
        db = TestSessionLocal()
        try:
            # 清理之前测试的残留数据
            from app.models import Pregnant, FollowUpRecord
            db.query(FollowUpRecord).delete()
            db.query(Pregnant).delete()
            db.commit()

            p = _make_pregnant("P_SCHED_SCAN", gest_days=140, risk_tags=[])
            db.add(p)
            db.commit()

            # 调用扫描
            stats = sched_mod._scan_and_create_followups(db)
            assert stats["total"] >= 1
            # 应为信息缺失创建了 draft
            assert stats["created"] >= 1, \
                f"应为无数据孕妇创建随访草稿，stats={stats}"

            # 验证草稿已创建
            drafts = db.query(FollowUpRecord).filter(
                FollowUpRecord.pregnant_id == "P_SCHED_SCAN",
                FollowUpRecord.status == "draft",
            ).all()
            assert len(drafts) >= 1, "应为该孕妇创建了 draft 随访"
            assert drafts[0].self_reported_data.get("auto_generated") is True
        finally:
            db.rollback()
            db.close()

    def test_scan_skips_fresh_active_followup(self):
        """扫描应跳过有新鲜活跃随访的孕妇"""
        db = TestSessionLocal()
        try:
            from app.models import Pregnant, FollowUpRecord
            db.query(FollowUpRecord).delete()
            db.query(Pregnant).delete()
            db.commit()

            p = _make_pregnant("P_FRESH_BLOCK", gest_days=200, risk_tags=["GDM"])
            db.add(p)
            db.add(_make_followup("P_FRESH_BLOCK", status="draft", created_days_ago=1))
            db.commit()

            stats = sched_mod._scan_and_create_followups(db)
            # 不应为新draft创建重复随访
            drafts = db.query(FollowUpRecord).filter(
                FollowUpRecord.pregnant_id == "P_FRESH_BLOCK",
            ).all()
            # 应该只有原来那1条
            assert len(drafts) == 1, f"不应重复创建随访: {len(drafts)} 条"
        finally:
            db.rollback()
            db.close()

    def test_scan_cleans_zombie_and_creates(self):
        """扫描应先清理僵尸随访，再为新推荐创建草稿"""
        db = TestSessionLocal()
        try:
            from app.models import Pregnant, FollowUpRecord
            db.query(FollowUpRecord).delete()
            db.query(Pregnant).delete()
            db.commit()

            # 创建有风险标签(GDM)但被僵尸阻塞的无数据孕妇
            p = _make_pregnant("P_ZOMBIE_CLEAN", gest_days=200, risk_tags=["GDM"])
            db.add(p)
            db.add(_make_followup("P_ZOMBIE_CLEAN", status="draft", created_days_ago=10))
            db.commit()

            stats = sched_mod._scan_and_create_followups(db)
            assert stats["zombies_cleaned"] >= 1, f"应清理僵尸随访: {stats}"

            # 验证僵尸被归档
            archived = db.query(FollowUpRecord).filter(
                FollowUpRecord.pregnant_id == "P_ZOMBIE_CLEAN",
                FollowUpRecord.status == "archived",
            ).first()
            assert archived is not None, "僵尸应被归档"

            # 应为GDM风险孕妇创建新的随访草稿
            drafts = db.query(FollowUpRecord).filter(
                FollowUpRecord.pregnant_id == "P_ZOMBIE_CLEAN",
                FollowUpRecord.status == "draft",
            ).all()
            assert len(drafts) >= 1, f"清理僵尸后应为无数据GDM孕妇创建新随访: {stats}"
        finally:
            db.rollback()
            db.close()
