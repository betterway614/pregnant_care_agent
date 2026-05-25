# 预警推送机制完善 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从根源消除同领域重复报警，建立完整的级别流转、分级推送、护士分诊机制。

**Architecture:** 规则引擎按 3 个临床领域（vital/fetal/mental）分组互斥评估；WebSocket 按级别+来源角色路由推送；护士端获得升级/复议/确认等完整操作权限；预警内嵌时间线追踪流转历史。

**Tech Stack:** Python FastAPI + SQLAlchemy + Vue 3 Composition API + TypeScript + WebSocket

---

## 文件结构

| 文件 | 职责 | 变更类型 |
|------|------|----------|
| `backend/app/core/rule_engine.py` | Rule 增加 domain/priority；evaluate_all 按领域取最高 | 修改 |
| `backend/app/models/models.py` | Alert 增加 domain 字段；status 增加 AUTO_DISMISSED | 修改 |
| `backend/app/services/alert_service.py` | 去重简化为 domain-based；create_alerts_from_hits 适配新结构 | 修改 |
| `backend/app/core/websocket_manager.py` | broadcast_alert → route_alert；新增定向推送方法 | 修改 |
| `backend/app/schemas/schemas.py` | AlertReviewRequest 扩展 action + target_level | 修改 |
| `backend/app/routers/alerts.py` | review_alert 增加护士操作+角色校验+source_role；auto-dismiss 端点 | 修改 |
| `backend/app/services/auto_dismiss_service.py` | 定时清理超时 PENDING 预警 | **新建** |
| `frontend/src/views/nurse/AlertList.vue` | 护士升级/复议/确认/解除操作；WebSocket 接入；预警折叠 | 修改 |
| `frontend/src/views/nurse/NurseDashboard.vue` | WebSocket 实时推送接入 | 修改 |
| `frontend/src/views/doctor/ReviewWorkbench.vue` | 预警列表折叠；时间线展示；推送路由对齐 | 修改 |
| `frontend/src/components/common/RiskBadge.vue` | 降级/复议状态标识 | 修改 |
| `backend/tests/test_rule_engine.py` | 领域分组 + 优先级互斥测试 | **新建** |
| `backend/tests/test_alert_service.py` | 简化去重 + 护士操作测试 | 修改 |

---

### Task 1: 编写规则引擎领域分组测试

**Files:**
- Create: `backend/tests/test_rule_engine.py`

- [ ] **Step 1: 创建测试文件，编写领域分组单领域互斥测试**

```python
"""规则引擎领域分组测试"""
import pytest
from app.core.rule_engine import RuleEngine, Rule, rule_engine


class TestDomainGrouping:
    """领域分组 + 优先级互斥"""

    def test_single_domain_returns_highest_priority_only(self):
        """同领域多条规则命中时，只返回优先级最高的"""
        engine = RuleEngine()
        context = {
            "sbp": 145, "dbp": 95, "weight": 65,
            "fetal_movement": 10, "fetal_movement_avg": 10,
            "weight_gain_weekly": 0.5, "emotion_score_avg_7d": 4,
            "blood_sugar_fasting": 4.5, "blood_sugar_postprandial": 6.0,
            "sleep_hours": 7, "gest_week": 20,
        }
        hits = engine.evaluate_all(context)
        vital_hits = [h for h in hits if h["domain"] == "vital"]
        assert len(vital_hits) == 1
        assert vital_hits[0]["level"] == "RED"
        assert vital_hits[0]["rule_id"] == "RULE_BP_HIGH"

    def test_domain_merges_same_priority_rules(self):
        """同领域同优先级规则合并 triggered_rules"""
        engine = RuleEngine()
        context = {
            "sbp": 132, "dbp": 86, "weight": 65,
            "fetal_movement": 10, "fetal_movement_avg": 10,
            "weight_gain_weekly": 0.5, "emotion_score_avg_7d": 4,
            "blood_sugar_fasting": 4.5, "blood_sugar_postprandial": 6.0,
            "sleep_hours": 7, "gest_week": 32,
        }
        hits = engine.evaluate_all(context)
        vital_hits = [h for h in hits if h["domain"] == "vital"]
        assert len(vital_hits) == 1
        assert vital_hits[0]["level"] == "ORANGE"
        assert "RULE_LATE_PREGNANCY_BP" in vital_hits[0]["triggered_rules"]
        assert "RULE_BP_HIGH_ORANGE" in vital_hits[0]["triggered_rules"]

    def test_multi_domain_returns_one_per_domain(self):
        """多领域同时触发时，每个领域最多一条"""
        engine = RuleEngine()
        context = {
            "sbp": 150, "dbp": 100, "weight": 65,
            "fetal_movement": 2, "fetal_movement_avg": 10,
            "weight_gain_weekly": 0.5, "emotion_score_avg_7d": 9,
            "blood_sugar_fasting": 4.5, "blood_sugar_postprandial": 6.0,
            "sleep_hours": 7, "gest_week": 25,
        }
        hits = engine.evaluate_all(context)
        domains = set(h["domain"] for h in hits)
        assert len(hits) == len(domains)  # 每个领域一条
        domain_map = {h["domain"]: h for h in hits}
        assert domain_map["vital"]["level"] == "RED"    # 血压150
        assert domain_map["fetal"]["level"] == "RED"    # 胎动2
        assert domain_map["mental"]["level"] == "ORANGE" # 情绪9

    def test_no_hits_returns_empty(self):
        """所有指标正常时不产生预警"""
        engine = RuleEngine()
        context = {
            "sbp": 120, "dbp": 80, "weight": 65,
            "fetal_movement": 10, "fetal_movement_avg": 10,
            "weight_gain_weekly": 0.5, "emotion_score_avg_7d": 4,
            "blood_sugar_fasting": 4.5, "blood_sugar_postprandial": 6.0,
            "sleep_hours": 8, "gest_week": 20,
        }
        hits = engine.evaluate_all(context)
        assert len(hits) == 0

    def test_each_rule_has_domain_and_priority(self):
        """所有规则都有 domain 和 priority 属性"""
        engine = RuleEngine()
        for rule in engine.rules:
            assert hasattr(rule, "domain"), f"{rule.id} missing domain"
            assert hasattr(rule, "priority"), f"{rule.id} missing priority"
            assert rule.domain in ("vital", "fetal", "mental")
            assert isinstance(rule.priority, int)

    def test_lower_priority_not_returned_when_higher_exists(self):
        """低优先级规则被高优先级覆盖"""
        engine = RuleEngine()
        context = {"sbp": 138, "dbp": 88, "gest_week": 20, "weight": 65,
                   "fetal_movement": 10, "fetal_movement_avg": 10,
                   "weight_gain_weekly": 0.5, "emotion_score_avg_7d": 4,
                   "blood_sugar_fasting": 4.5, "blood_sugar_postprandial": 6.0,
                   "sleep_hours": 7}
        hits = engine.evaluate_all(context)
        vital_hits = [h for h in hits if h["domain"] == "vital"]
        assert len(vital_hits) == 1
        # priority 2 (RULE_BP_HIGH_ORANGE) 覆盖 priority 1 (RULE_BP_LOW)
        assert vital_hits[0]["rule_id"] == "RULE_BP_HIGH_ORANGE"
        assert vital_hits[0]["level"] == "ORANGE"
```

- [ ] **Step 2: 运行测试确认全部失败**

```bash
cd backend && python -m pytest tests/test_rule_engine.py -v
```

Expected: 所有测试 FAIL（Rule 还没有 domain/priority 属性）

---

### Task 2: 重构 Rule 模型和规则定义

**Files:**
- Modify: `backend/app/core/rule_engine.py:1-148`

- [ ] **Step 1: 修改 Rule 类，增加 domain 和 priority 参数**

```python
class Rule:
    """规则定义"""
    def __init__(self, rule_id: str, domain: str, priority: int,
                 expression: str, level: str,
                 message: str, action: str = "ALERT_NURSE"):
        self.id = rule_id
        self.domain = domain      # vital / fetal / mental
        self.priority = priority  # 组内优先级, 数字越大越高
        self.expression = expression
        self.level = level
        self.message = message
        self.action = action

    def evaluate(self, context: dict) -> bool:
        """评估规则是否命中（安全版本，不使用eval）"""
        try:
            variables = {
                "sbp": context.get("sbp", 0) or 0,
                "dbp": context.get("dbp", 0) or 0,
                "weight": context.get("weight", 0) or 0,
                "fetal_movement": context.get("fetal_movement", 0) or 0,
                "fetal_movement_avg": context.get("fetal_movement_avg", context.get("fetal_movement", 0)) or context.get("fetal_movement", 0),
                "weight_gain_weekly": context.get("weight_gain_weekly", 0) or 0,
                "emotion_score": context.get("emotion_score_avg_7d", 0) or 0,
                "emotion_score_avg_7d": context.get("emotion_score_avg_7d", 0) or 0,
                "blood_sugar_fasting": context.get("blood_sugar_fasting", 0) or 0,
                "blood_sugar_postprandial": context.get("blood_sugar_postprandial", 0) or 0,
                "sleep_hours": context.get("sleep_hours", 8) or 8,
                "gest_week": context.get("gest_week", 0) or 0,
            }
            return _safe_eval_condition(self.expression, variables)
        except Exception:
            return False
```

- [ ] **Step 2: 替换规则定义列表**

```python
RULES = [
    # === 生命体征 (vital) ===
    Rule("RULE_BP_HIGH", "vital", 3, "sbp >= 140 or dbp >= 90", "RED",
         "血压异常升高（≥140/90mmHg）", "ALERT_NURSE_AND_DOCTOR"),
    Rule("RULE_BP_HIGH_ORANGE", "vital", 2, "sbp >= 135 or dbp >= 85", "ORANGE",
         "血压偏高（≥135/85mmHg），需要关注", "ALERT_NURSE"),
    Rule("RULE_BP_LOW", "vital", 1, "sbp < 90 or dbp < 60", "YELLOW",
         "血压偏低，需关注", "NOTE_NURSE"),
    Rule("RULE_LATE_PREGNANCY_BP", "vital", 2, "sbp >= 130 and gest_week >= 32", "ORANGE",
         "孕晚期血压偏高，子痫前期风险", "ALERT_NURSE_AND_DOCTOR"),
    Rule("RULE_BS_POSTPRANDIAL_HIGH", "vital", 3, "blood_sugar_postprandial > 7.0", "RED",
         "餐后血糖异常（>7.0mmol/L）", "ALERT_NURSE_AND_DOCTOR"),
    Rule("RULE_BS_FASTING_HIGH", "vital", 2, "blood_sugar_fasting > 5.3", "ORANGE",
         "空腹血糖偏高（>5.3mmol/L），建议复查", "ALERT_NURSE"),
    Rule("RULE_WEIGHT_GAIN_FAST", "vital", 2, "weight_gain_weekly > 2.0", "ORANGE",
         "体重周增长过快（>2kg/周）", "ALERT_NURSE"),
    Rule("RULE_WEIGHT_GAIN_SLOW", "vital", 1, "weight_gain_weekly < 0.1 and gest_week > 12", "YELLOW",
         "体重增长过慢，需关注营养摄入", "NOTE_NURSE"),

    # === 胎儿 (fetal) ===
    Rule("RULE_FETAL_DROP", "fetal", 3, "fetal_movement < fetal_movement_avg * 0.5", "RED",
         "胎动显著减少（低于平均50%）", "ALERT_NURSE_AND_DOCTOR"),
    Rule("RULE_FETAL_VERY_LOW", "fetal", 3, "fetal_movement < 3", "RED",
         "胎动极少（<3次/小时），请立即就医", "ALERT_NURSE_AND_DOCTOR"),

    # === 心理行为 (mental) ===
    Rule("RULE_EMOTION_CRITICAL", "mental", 2, "emotion_score_avg_7d >= 9", "ORANGE",
         "情绪评分严重偏高，建议心理干预", "ALERT_NURSE"),
    Rule("RULE_EMOTION_HIGH", "mental", 1, "emotion_score_avg_7d >= 7", "YELLOW",
         "近7日情绪评分偏高，需关注心理状态", "NOTE_NURSE"),
    Rule("RULE_SLEEP_SHORT", "mental", 1, "sleep_hours < 5", "YELLOW",
         "睡眠不足5小时，建议改善睡眠", "NOTE_NURSE"),
]
```

- [ ] **Step 3: 运行现有测试确认无回归**

```bash
cd backend && python -m pytest tests/test_alert_service.py tests/test_websocket_manager.py -v
```

Expected: 所有现有测试 PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/rule_engine.py
git commit -m "refactor: add domain and priority to Rule model for clinical domain grouping"
```

---

### Task 3: 重构 evaluate_all 为按领域取最高

**Files:**
- Modify: `backend/app/core/rule_engine.py:150-168`

- [ ] **Step 1: 替换 evaluate_all 方法**

```python
def evaluate_all(self, context: dict) -> list[dict]:
    """每个领域只返回优先级最高的命中。同领域同优先级合并 triggered_rules。"""
    domain_hits: dict[str, dict] = {}
    for rule in self.rules:
        if rule.evaluate(context):
            current = domain_hits.get(rule.domain)
            if not current or rule.priority > current["priority"]:
                domain_hits[rule.domain] = {
                    "rule_id": rule.id,
                    "domain": rule.domain,
                    "priority": rule.priority,
                    "level": rule.level,
                    "message": rule.message,
                    "action": rule.action,
                    "triggered_rules": [rule.id],
                }
            elif rule.priority == current["priority"]:
                current["triggered_rules"].append(rule.id)
    return list(domain_hits.values())
```

- [ ] **Step 2: 运行领域分组测试**

```bash
cd backend && python -m pytest tests/test_rule_engine.py -v
```

Expected: 7 tests PASS

- [ ] **Step 3: 运行全部后端测试确认无回归**

```bash
cd backend && python -m pytest -v
```

Expected: ALL tests PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/rule_engine.py backend/tests/test_rule_engine.py
git commit -m "feat: evaluate_all returns only highest-priority hit per clinical domain"
```

---

### Task 4: Alert 模型增加 domain 和 AUTO_DISMISSED

**Files:**
- Modify: `backend/app/models/models.py:152-167`

- [ ] **Step 1: 在 Alert 模型中添加 domain 字段，更新 status 注释**

```python
class Alert(Base):
    """预警记录"""
    __tablename__ = "alerts"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    trigger_source = Column(String(32), default="RULE_ENGINE", comment="RULE_ENGINE/FGR_ALGORITHM/MANUAL")
    rule_id = Column(String(32), nullable=True)
    domain = Column(String(32), nullable=True, comment="vital/fetal/mental")
    level = Column(String(16), default="YELLOW", comment="RED/ORANGE/YELLOW")
    message = Column(Text, nullable=False)
    details = Column(JSON, default=dict, comment="触发详情/历史时间线")
    status = Column(String(16), default="PENDING", comment="PENDING/CONFIRMED/DISMISSED/AUTO_DISMISSED")
    reviewed_by = Column(String(64), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=beijing_now)
```

- [ ] **Step 2: 创建数据库迁移脚本生成新列**

由于使用 SQLite + SQLAlchemy，执行以下命令验证 Alert 模型可正常导入：

```bash
cd backend && python -c "from app.models import Alert; a = Alert(); print(a.domain, a.status)"
```

Expected: `None PENDING`（无错误）

- [ ] **Step 3: 提交**

```bash
git add backend/app/models/models.py
git commit -m "feat: add domain field and AUTO_DISMISSED status to Alert model"
```

---

### Task 5: 简化 alert_service 去重 + 适配领域结构

**Files:**
- Modify: `backend/app/services/alert_service.py:1-93`

- [ ] **Step 1: 替换去重逻辑和创建逻辑**

```python
"""预警服务 - 创建和管理预警记录"""
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import and_
from loguru import logger
from ..utils.timezone import beijing_now
from ..models import Alert


class AlertService:
    """预警服务"""

    @staticmethod
    def _find_duplicate(db: Session, pregnant_id: str, domain: str) -> Alert | None:
        """同一孕妇同一领域已有 PENDING 预警时视为重复"""
        if not domain:
            return None
        return db.query(Alert).filter(
            and_(
                Alert.pregnant_id == pregnant_id,
                Alert.domain == domain,
                Alert.status == "PENDING",
            )
        ).first()

    @staticmethod
    def create_alert(
        db: Session,
        pregnant_id: str,
        rule_id: str,
        domain: str,
        level: str,
        message: str,
        trigger_source: str = "RULE_ENGINE",
        details: dict = None,
    ) -> Alert:
        """创建预警记录（领域级去重）"""
        existing = AlertService._find_duplicate(db, pregnant_id, domain)
        if existing:
            logger.info(f"预警去重: domain={domain} for {pregnant_id} 已有 PENDING 预警, 跳过创建")
            return existing

        base_details = details or {}
        base_details["history"] = [{
            "seq": 1,
            "action": "created",
            "source_role": "system",
            "level": level,
            "operator": None,
            "reason": None,
            "timestamp": beijing_now().isoformat(),
        }]
        base_details["source_role"] = "system"

        alert = Alert(
            id=uuid4(),
            pregnant_id=pregnant_id,
            trigger_source=trigger_source,
            rule_id=rule_id,
            domain=domain,
            level=level,
            message=message,
            status="PENDING",
            details=base_details,
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def create_alerts_from_hits(
        db: Session,
        pregnant_id: str,
        hits: list[dict],
        trigger_source: str = "RULE_ENGINE",
    ) -> list[Alert]:
        """从领域分组命中列表批量创建预警（领域级去重）"""
        alerts = []
        for hit in hits:
            alert = AlertService.create_alert(
                db=db,
                pregnant_id=pregnant_id,
                rule_id=hit.get("rule_id", "UNKNOWN"),
                domain=hit.get("domain", ""),
                level=hit.get("level", "YELLOW"),
                message=hit.get("message", ""),
                trigger_source=trigger_source,
                details={
                    "action": hit.get("action", "ALERT_NURSE"),
                    "triggered_rules": hit.get("triggered_rules", []),
                    "created_at": beijing_now().isoformat(),
                },
            )
            alerts.append(alert)
        return alerts

    @staticmethod
    async def enrich_alert_with_llm(db: Session, alert: Alert, pregnant):
        """使用护士 Agno Agent 为预警生成分析摘要"""
        from .alert_analysis_service import alert_analysis_service

        nurse_result = await alert_analysis_service.run_nurse_analysis(db, alert, pregnant)
        if not nurse_result:
            return

        details = alert.details or {}
        details["llm_analysis"] = {
            "risk_interpretation": nurse_result.get("risk_assessment") or nurse_result.get("summary", ""),
            "recommended_actions": [nurse_result.get("nursing_suggestions", "")],
            "severity_assessment": nurse_result.get("summary", ""),
            "analyzed_at": nurse_result.get("analyzed_at", beijing_now().isoformat()),
            "source": "agno_nurse_agent",
        }
        alert.details = details
        db.commit()
        logger.info("Agno预警分析完成: alert_id={}", alert.id)


alert_service = AlertService()
```

- [ ] **Step 2: 运行现有测试确认兼容**

```bash
cd backend && python -m pytest tests/test_alert_service.py -v
```

Expected: FAIL — 现有测试使用旧的 `_find_duplicate(pregnant_id, rule_id, level)` 签名

- [ ] **Step 3: 提交**

```bash
git add backend/app/services/alert_service.py
git commit -m "refactor: simplify dedup to domain-based, remove time-window dedup"
```

---

### Task 6: 更新 alert_service 测试

**Files:**
- Modify: `backend/tests/test_alert_service.py:1-95`

- [ ] **Step 1: 重写去重测试适配新接口**

将 `test_alert_service.py` 中 `TestAlertDeduplication` 类替换为：

```python
class TestAlertDeduplication:
    """测试预警去重逻辑 — domain-based"""

    def _make_alert(self, **kwargs):
        alert = MagicMock()
        alert.id = kwargs.get("id", uuid4())
        alert.pregnant_id = kwargs.get("pregnant_id", "P001")
        alert.rule_id = kwargs.get("rule_id", "RULE_BP_HIGH")
        alert.domain = kwargs.get("domain", "vital")
        alert.level = kwargs.get("level", "RED")
        alert.message = kwargs.get("message", "血压异常升高")
        alert.status = kwargs.get("status", "PENDING")
        alert.trigger_source = kwargs.get("trigger_source", "RULE_ENGINE")
        alert.details = kwargs.get("details", {})
        alert.created_at = kwargs.get("created_at", datetime.utcnow())
        return alert

    def test_find_duplicate_by_domain_returns_existing(self):
        from app.services.alert_service import AlertService
        existing_alert = self._make_alert()
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.first.return_value = existing_alert
        result = AlertService._find_duplicate(db, "P001", "vital")
        assert result == existing_alert

    def test_find_duplicate_different_domain_returns_none(self):
        from app.services.alert_service import AlertService
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.first.return_value = None
        result = AlertService._find_duplicate(db, "P001", "fetal")
        assert result is None

    def test_find_duplicate_returns_none_for_no_domain(self):
        from app.services.alert_service import AlertService
        db = MagicMock()
        result = AlertService._find_duplicate(db, "P001", None)
        assert result is None
        db.query.assert_not_called()

    def test_create_alert_skips_domain_duplicate(self):
        from app.services.alert_service import AlertService
        existing_alert = self._make_alert(id=uuid4())
        db = MagicMock()
        with patch.object(AlertService, '_find_duplicate', return_value=existing_alert):
            result = AlertService.create_alert(
                db=db, pregnant_id="P001", rule_id="RULE_BP_HIGH",
                domain="vital", level="RED", message="血压异常升高",
            )
            assert result == existing_alert
            db.add.assert_not_called()

    def test_create_alert_creates_new_when_no_duplicate(self):
        from app.services.alert_service import AlertService
        db = MagicMock()
        with patch.object(AlertService, '_find_duplicate', return_value=None):
            result = AlertService.create_alert(
                db=db, pregnant_id="P001", rule_id="RULE_BP_HIGH",
                domain="vital", level="RED", message="血压异常升高",
            )
            db.add.assert_called_once()
            db.commit.assert_called_once()
            assert result.pregnant_id == "P001"
            assert result.level == "RED"

    def test_create_alert_initializes_history(self):
        """创建预警时初始化 history 时间线"""
        from app.services.alert_service import AlertService
        db = MagicMock()
        with patch.object(AlertService, '_find_duplicate', return_value=None):
            result = AlertService.create_alert(
                db=db, pregnant_id="P001", rule_id="RULE_BP_HIGH",
                domain="vital", level="RED", message="血压异常升高",
            )
            assert "history" in result.details
            assert result.details["history"][0]["action"] == "created"
            assert result.details["history"][0]["source_role"] == "system"
            assert result.details["source_role"] == "system"

    def test_create_alerts_from_hits_uses_domain(self):
        from app.services.alert_service import AlertService
        hits = [
            {"rule_id": "RULE_BP_HIGH", "domain": "vital", "level": "RED",
             "message": "血压异常", "action": "ALERT_NURSE_AND_DOCTOR",
             "triggered_rules": ["RULE_BP_HIGH"], "priority": 3},
            {"rule_id": "RULE_FETAL_DROP", "domain": "fetal", "level": "RED",
             "message": "胎动减少", "action": "ALERT_NURSE_AND_DOCTOR",
             "triggered_rules": ["RULE_FETAL_DROP"], "priority": 3},
        ]
        db = MagicMock()
        existing = self._make_alert()

        def mock_find_dup(db, pid, domain):
            return existing if domain == "vital" else None

        with patch.object(AlertService, '_find_duplicate', side_effect=mock_find_dup):
            results = AlertService.create_alerts_from_hits(db, "P001", hits)
            assert len(results) == 2
            assert results[0] == existing
            assert results[1].rule_id == "RULE_FETAL_DROP"
```

- [ ] **Step 2: 运行去重测试确认通过**

```bash
cd backend && python -m pytest tests/test_alert_service.py::TestAlertDeduplication -v
```

Expected: 7 tests PASS

- [ ] **Step 3: 运行全部测试确认无回归**

```bash
cd backend && python -m pytest -v
```

Expected: ALL tests PASS

- [ ] **Step 4: 提交**

```bash
git add backend/tests/test_alert_service.py
git commit -m "test: update dedup tests for domain-based deduplication"
```

---

### Task 7: WebSocket Manager 增加 route_alert + 定向广播

**Files:**
- Modify: `backend/app/core/websocket_manager.py:81-122`

- [ ] **Step 1: 在 broadcast_alert 后面新增 route_alert 和定向广播方法**

```python
    # ==================== 路由推送 ====================

    async def route_alert(self, alert_data: dict):
        """按级别和来源角色路由推送

        alert_data 必须包含: level, source_role
        可选: action, target_doctor_id
        """
        level = alert_data.get("level", "YELLOW")
        source_role = alert_data.get("source_role", "system")
        action = alert_data.get("action", "")

        if source_role == "doctor" and action == "downgrade":
            await self._broadcast_to_nurses_only(alert_data)
        elif source_role == "nurse" and action == "escalate":
            await self._broadcast_all(alert_data)
        elif source_role == "nurse" and action == "appeal":
            target_doctor_id = alert_data.get("target_doctor_id")
            if target_doctor_id:
                await self.send_alert_to_doctor(target_doctor_id, alert_data)
            await self._broadcast_to_nurses_only(alert_data)
        elif level == "RED":
            await self._broadcast_all(alert_data)
        elif level in ("ORANGE", "YELLOW"):
            await self._broadcast_to_nurses_only(alert_data)

    async def _broadcast_all(self, alert_data: dict):
        """广播给所有在线的医生和护士"""
        disconnected_doctors = []
        for doctor_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json({
                    "type": "NEW_ALERT",
                    "data": alert_data
                })
            except Exception:
                disconnected_doctors.append(doctor_id)

        for doctor_id in disconnected_doctors:
            self.disconnect(doctor_id)

        disconnected_nurses = []
        for nurse_id, websocket in self.nurse_connections.items():
            try:
                await websocket.send_json({
                    "type": "NEW_ALERT",
                    "data": alert_data
                })
            except Exception:
                disconnected_nurses.append(nurse_id)

        for nurse_id in disconnected_nurses:
            self.disconnect_nurse(nurse_id)

    async def _broadcast_to_nurses_only(self, alert_data: dict):
        """仅广播给所有在线的护士"""
        disconnected_nurses = []
        for nurse_id, websocket in self.nurse_connections.items():
            try:
                await websocket.send_json({
                    "type": "NEW_ALERT",
                    "data": alert_data
                })
            except Exception:
                disconnected_nurses.append(nurse_id)

        for nurse_id in disconnected_nurses:
            self.disconnect_nurse(nurse_id)

    async def broadcast_to_nurses(self, alert_data: dict):
        """公开的护士广播方法（兼容旧调用）"""
        await self._broadcast_to_nurses_only(alert_data)

    async def broadcast_alert(self, alert_data: dict):
        """广播给所有医生和护士（保留兼容）"""
        await self._broadcast_all(alert_data)
```

- [ ] **Step 2: 编写 WebSocket route_alert 测试**

在 `backend/tests/test_websocket_manager.py` 末尾添加：

```python
class TestRouteAlert:
    """route_alert 分级路由测试"""

    @pytest.fixture
    def ws_manager(self):
        return WebSocketManager()

    @pytest.mark.asyncio
    async def test_red_alert_broadcasts_to_all(self, ws_manager):
        """RED 预警广播给医生和护士"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {"level": "RED", "source_role": "system", "message": "血压异常"}
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_called_once()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_orange_alert_only_nurses(self, ws_manager):
        """ORANGE 预警仅推送给护士"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {"level": "ORANGE", "source_role": "system", "message": "血压偏高"}
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_not_called()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_yellow_alert_only_nurses(self, ws_manager):
        """YELLOW 预警仅推送给护士"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {"level": "YELLOW", "source_role": "system", "message": "体重缓慢"}
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_not_called()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_doctor_downgrade_only_nurses(self, ws_manager):
        """医生降级仅推护士"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "YELLOW", "source_role": "doctor", "action": "downgrade",
            "message": "[医生降级] 血压偏高",
        }
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_not_called()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_nurse_escalate_broadcasts_all(self, ws_manager):
        """护士升级推全部"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "ORANGE", "source_role": "nurse", "action": "escalate",
            "message": "[护士升级] 血压偏高需要医生关注",
        }
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_called_once()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_nurse_appeal_sends_to_target_doctor(self, ws_manager):
        """护士复议推给目标医生"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "YELLOW", "source_role": "nurse", "action": "appeal",
            "target_doctor_id": "doctor-1", "message": "[复议] 请重新评估",
        }
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_called_once()
        nurse_ws.send_json.assert_called_once()
```

- [ ] **Step 3: 运行 WebSocket 测试**

```bash
cd backend && python -m pytest tests/test_websocket_manager.py -v
```

Expected: ALL tests (existing + new) PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/websocket_manager.py backend/tests/test_websocket_manager.py
git commit -m "feat: add route_alert with level/role-based push routing"
```

---

### Task 8: 扩展 AlertReviewRequest Schema

**Files:**
- Modify: `backend/app/schemas/schemas.py:301-304`

- [ ] **Step 1: 扩展 schema**

```python
class AlertReviewRequest(BaseModel):
    action: str = Field(...,
        pattern="^(confirm|dismiss|downgrade|supplement|nurse_confirm|nurse_dismiss|nurse_escalate|nurse_appeal)$")
    reason: Optional[str] = None
    target_level: Optional[str] = Field(None,
        pattern="^(ORANGE|YELLOW|GREEN)$")
```

- [ ] **Step 2: 验证 schema 可导入**

```bash
cd backend && python -c "from app.schemas import AlertReviewRequest; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add backend/app/schemas/schemas.py
git commit -m "feat: extend AlertReviewRequest with nurse actions (escalate/appeal/confirm/dismiss)"
```

---

### Task 9: 重构 review_alert API + auto-dismiss 端点

**Files:**
- Modify: `backend/app/routers/alerts.py:186-273`

- [ ] **Step 1: 添加辅助函数，追加 history 记录**

在 `review_alert` 函数前添加：

```python
def _append_history(alert: Alert, action: str, source_role: str, level: str,
                   operator: str = None, reason: str = None):
    """在 alert.details.history 追加一条操作记录"""
    details = alert.details or {}
    history = details.get("history", [])
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
```

- [ ] **Step 2: 重写 review_alert 函数体**

```python
@router.put("/{alert_id}/review", response_model=AlertResponse)
async def review_alert(alert_id: str, review: AlertReviewRequest,
                  db: Session = Depends(get_db)):
    """审核预警 — 支持医生和护士的全部操作"""
    alert = db.query(Alert).filter(Alert.id == UUID(alert_id)).first()
    if not alert:
        raise HTTPException(404, "预警不存在")

    original_level = alert.level
    operator = None  # 可从 auth token 获取, 当前暂用 reviewed_by 字段
    source_role = "doctor"  # 默认, 通过 action 前缀区分

    if review.action == "confirm":
        alert.status = "CONFIRMED"
        _append_history(alert, "confirm", source_role, alert.level, operator, review.reason)
    elif review.action == "dismiss":
        alert.status = "DISMISSED"
        _append_history(alert, "dismiss", source_role, alert.level, operator, review.reason)
    elif review.action == "downgrade":
        if not review.target_level:
            raise HTTPException(400, "降级操作必须指定 target_level")
        if review.target_level == "GREEN":
            alert.status = "DISMISSED"
            _append_history(alert, "downgrade", source_role, "GREEN", operator, review.reason)
        else:
            alert.level = review.target_level
            alert.status = "PENDING"
            _append_history(alert, "downgrade", source_role, review.target_level, operator, review.reason)
    elif review.action == "supplement":
        _append_history(alert, "supplement", source_role, alert.level, operator, review.reason)
    elif review.action == "nurse_confirm":
        source_role = "nurse"
        alert.status = "CONFIRMED"
        _append_history(alert, "nurse_confirm", source_role, alert.level, operator, review.reason)
    elif review.action == "nurse_dismiss":
        source_role = "nurse"
        alert.status = "DISMISSED"
        _append_history(alert, "nurse_dismiss", source_role, alert.level, operator, review.reason)
    elif review.action == "nurse_escalate":
        source_role = "nurse"
        if alert.level == "YELLOW":
            alert.level = "ORANGE"
        elif alert.level == "ORANGE":
            alert.level = "RED"
        _append_history(alert, "nurse_escalate", source_role, alert.level, operator, review.reason)
    elif review.action == "nurse_appeal":
        source_role = "nurse"
        _append_history(alert, "nurse_appeal", source_role, alert.level, operator, review.reason)

    alert.reviewed_at = beijing_now()
    db.commit()
    db.refresh(alert)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == alert.pregnant_id).first()

    # WebSocket 路由推送
    try:
        alert_data = {
            "id": str(alert.id),
            "pregnant_id": alert.pregnant_id,
            "patient_name": pregnant.display_name if pregnant else "未知",
            "level": alert.level,
            "message": alert.message,
            "trigger_source": alert.trigger_source,
            "status": alert.status,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "gestational_age_days": pregnant.gestational_age_days if pregnant else None,
            "source_role": source_role,
            "action": review.action,
            "review_reason": review.reason,
        }

        if source_role == "nurse" and review.action == "escalate":
            prefix = "[护士升级]" if alert.level == "RED" else ""
            if prefix:
                alert_data["message"] = f"{prefix} {alert.message}"

        if source_role == "doctor" and review.action == "downgrade" and review.target_level != "GREEN":
            alert_data["message"] = f"[医生降级] {alert.message}"

        if source_role == "nurse" and review.action == "appeal":
            alert_data["message"] = f"[护士复议] {alert.message}"
            alert_details = alert.details or {}
            downgrade_entry = next(
                (h for h in reversed(alert_details.get("history", [])) if h["action"] == "downgrade"), None
            )
            if downgrade_entry:
                alert_data["target_doctor_id"] = downgrade_entry.get("operator")

        await ws_manager.route_alert(alert_data)
    except Exception as e:
        logger.warning(f"WebSocket路由推送失败: {e}")

    return AlertResponse(
        **{c.name: getattr(alert, c.name) for c in alert.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
        gestational_age_days=pregnant.gestational_age_days if pregnant else None,
    )
```

- [ ] **Step 3: 添加 auto-dismiss 端点**

在 `review_alert` 后面添加：

```python
@router.post("/auto-dismiss")
def auto_dismiss_alerts(db: Session = Depends(get_db)):
    """定时任务: 自动关闭超时 PENDING 预警"""
    from datetime import timedelta

    now = beijing_now()
    thresholds = {
        "RED": now - timedelta(hours=72),
        "ORANGE": now - timedelta(hours=48),
        "YELLOW": now - timedelta(hours=24),
    }

    dismissed_count = 0
    for level, cutoff in thresholds.items():
        stale = db.query(Alert).filter(
            Alert.status == "PENDING",
            Alert.level == level,
            Alert.created_at < cutoff,
        ).all()

        timeout_hours = {"RED": 72, "ORANGE": 48, "YELLOW": 24}.get(level, 24)
        for alert in stale:
            _append_history(alert, "auto_dismiss", "system", alert.level,
                          reason=f"超时{timeout_hours}小时未处理")
            alert.status = "AUTO_DISMISSED"
            alert.reviewed_at = now
            dismissed_count += 1

    db.commit()
    logger.info(f"自动关闭 {dismissed_count} 条超时预警")
    return {"message": f"自动关闭了 {dismissed_count} 条超时预警", "count": dismissed_count}
```

- [ ] **Step 4: 更新 alerts.py 中创建预警时的推送调用**

将 `POST /api/v1/alerts` (create_alert) 中第 118 行的 `ws_manager.broadcast_alert(alert_data)` 改为：

```python
    # 4. 按级别路由推送
    alert_data["source_role"] = "system"
    alert_data["action"] = "created"
    try:
        await ws_manager.route_alert(alert_data)
    except Exception as e:
        logger.warning(f"WebSocket路由推送失败，预警已创建: {e}")
```

- [ ] **Step 5: 验证 API 可导入**

```bash
cd backend && python -c "from app.routers.alerts import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/alerts.py
git commit -m "feat: refactor review_alert with nurse actions, history tracking, auto-dismiss endpoint"
```

---

### Task 10: 更新前端 alertApi 调用签名

**Files:**
- Modify: `frontend/src/api/endpoints.ts` (alertApi.review 行)

- [ ] **Step 1: 确认 review 方法签名支持新 action**

当前签名：
```typescript
review: (alertId: string, action: string, reason?: string, targetLevel?: string) =>
  client.put(`/alerts/${alertId}/review`, { action, reason, target_level: targetLevel }),
```

此签名已支持所有新 action（`nurse_confirm`, `nurse_dismiss`, `nurse_escalate`, `nurse_appeal`），无需修改。只需确认 TypeScript 编译无错：

```bash
cd frontend && npx vue-tsc --noEmit src/api/endpoints.ts 2>&1 | head -20
```

- [ ] **Step 2: 提交（如有改动）**

如无改动则跳过提交。

---

### Task 11: 护士端 AlertList — 操作按钮 + WebSocket

**Files:**
- Modify: `frontend/src/views/nurse/AlertList.vue`

- [ ] **Step 1: 更新操作按钮模板**

在 `AlertList.vue` 的 `<script setup lang="ts">` 中添加护士操作逻辑。找到 `handleReview` 函数，扩展为：

```typescript
// 替换原有的 handleReview，增加护士专属操作
const nurseActions = computed(() => {
  const status = selectedAlert.value?.status
  if (status !== 'PENDING') return []
  const level = selectedAlert.value?.level
  const details = selectedAlert.value?.details || {}
  const isDowngraded = details.history?.some((h: any) => h.action === 'downgrade')

  const actions = [
    { key: 'nurse_confirm', label: '确认', icon: 'Check', type: 'primary' },
    { key: 'nurse_dismiss', label: '解除', icon: 'Close', type: 'default' },
  ]
  if (level === 'YELLOW' || level === 'ORANGE') {
    actions.push({ key: 'nurse_escalate', label: level === 'YELLOW' ? '升级为橙色' : '升级为红色', icon: 'Top', type: 'warning' })
  }
  if (isDowngraded) {
    actions.push({ key: 'nurse_appeal', label: '申请复议', icon: 'RefreshRight', type: 'danger' })
  }
  return actions
})
```

- [ ] **Step 2: 更新操作处理函数**

```typescript
async function handleReview(row: any, action: string) {
  const actionsNeedReason = ['nurse_dismiss', 'nurse_escalate', 'nurse_appeal']
  let reason = ''
  let targetLevel: string | undefined

  if (actionsNeedReason.includes(action)) {
    try {
      const { value } = await ElMessageBox.prompt(
        action === 'nurse_escalate' ? '请填写升级理由' :
        action === 'nurse_appeal' ? '请填写复议理由' :
        '请填写解除理由',
        '操作确认'
      )
      reason = value
    } catch {
      return // 用户取消
    }
  }

  if (action === 'nurse_escalate') {
    const newLevel = row.level === 'YELLOW' ? 'ORANGE' : 'RED'
    try {
      await ElMessageBox.confirm(
        `确认将预警从 ${row.level} 升级为 ${newLevel}？`,
        '升级确认',
        { confirmButtonText: '确认升级', type: 'warning' }
      )
    } catch {
      return
    }
  }

  submitting.value = true
  try {
    await alertApi.review(row.id, action, reason, targetLevel)
    ElMessage.success('操作成功')
    await fetchAlerts()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}
```

- [ ] **Step 3: 接入 WebSocket 实时推送**

在 `<script setup>` 中添加：

```typescript
import { getNurseWebSocketClient } from '@/utils/websocket'

const nurseId = ref('nurse-default') // TODO: 从登录状态获取
let wsClient: any = null

onMounted(() => {
  wsClient = getNurseWebSocketClient(nurseId.value)
  wsClient.onAlert((data: any) => {
    // 收到新预警时刷新列表
    fetchAlerts()
  })
  wsClient.connect()
})

onUnmounted(() => {
  if (wsClient) {
    wsClient.disconnect()
  }
})
```

- [ ] **Step 4: 更新操作按钮模板**

在 per-row 操作列中，仅 PENDING 状态显示护士操作按钮。替换原有的 `handleReview(row, 'confirm')` 等调用为对应新 action：

```html
<template v-if="isAlertPending(row.status)">
  <el-button size="small" type="primary" @click="handleReview(row, 'nurse_confirm')">
    确认
  </el-button>
  <el-button
    v-if="row.level === 'YELLOW' || row.level === 'ORANGE'"
    size="small" type="warning"
    @click="handleReview(row, 'nurse_escalate')"
  >
    {{ row.level === 'YELLOW' ? '升级' : '升级为红色' }}
  </el-button>
  <el-button
    v-if="hasBeenDowngraded(row)"
    size="small" type="danger"
    @click="handleReview(row, 'nurse_appeal')"
  >
    复议
  </el-button>
  <el-button size="small" @click="handleReview(row, 'nurse_dismiss')">
    解除
  </el-button>
</template>
```

添加辅助函数：

```typescript
function hasBeenDowngraded(row: any): boolean {
  return row.details?.history?.some((h: any) => h.action === 'downgrade') ?? false
}
```

- [ ] **Step 5: 验证前端编译**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | tail -20
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/nurse/AlertList.vue
git commit -m "feat: add nurse escalate/appeal/confirm/dismiss actions and WebSocket to AlertList"
```

---

### Task 12: 护士端 Dashboard WebSocket 接入

**Files:**
- Modify: `frontend/src/views/nurse/NurseDashboard.vue`

- [ ] **Step 1: 添加 WebSocket 连接**

在 `<script setup>` 中添加：

```typescript
import { getNurseWebSocketClient } from '@/utils/websocket'

const nurseId = ref('nurse-default') // TODO: 从登录状态获取

onMounted(() => {
  const wsClient = getNurseWebSocketClient(nurseId.value)
  wsClient.onAlert(() => {
    fetchData()
  })
  wsClient.connect()
})
```

- [ ] **Step 2: 验证前端编译**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | tail -20
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/nurse/NurseDashboard.vue
git commit -m "feat: add WebSocket real-time push to NurseDashboard"
```

---

### Task 13: 医生端 ReviewWorkbench — 推送对齐 + 预警折叠

**Files:**
- Modify: `frontend/src/views/doctor/ReviewWorkbench.vue`

- [ ] **Step 1: 预警列表按孕妇聚合**

在 `loadAlerts` 函数中或通过 computed 聚合预警列表（同孕妇同领域折叠为一组）：

```typescript
// 将预警按 pregnant_id + domain 分组
const groupedAlerts = computed(() => {
  const groups = new Map<string, Alert[]>()
  for (const alert of alertList.value) {
    const key = `${alert.pregnant_id}-${alert.domain || 'unknown'}`
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key)!.push(alert)
  }
  return Array.from(groups.entries()).map(([key, alerts]) => {
    // 取最高级别作为折叠组主显示
    const sorted = [...alerts].sort((a, b) => {
      const order: Record<string, number> = { RED: 3, ORANGE: 2, YELLOW: 1 }
      return (order[b.level] || 0) - (order[a.level] || 0)
    })
    return {
      key,
      pregnant_id: sorted[0].pregnant_id,
      patient_name: sorted[0].patient_name,
      level: sorted[0].level,
      message: sorted[0].message,
      count: alerts.length,
      children: alerts,
      topAlert: sorted[0],
    }
  })
})
```

模板中替换 `alert-list-item` 循环：

```html
<div
  v-for="group in groupedAlerts"
  :key="group.key"
  class="alert-list-item"
  :class="{ selected: selectedGroup?.key === group.key }"
  @click="selectGroup(group)"
>
  <div class="alert-list-header">
    <span class="patient-name">{{ group.patient_name }}</span>
    <RiskBadge :level="group.level" />
    <span v-if="group.count > 1" class="group-count">+{{ group.count - 1 }}</span>
  </div>
  <div class="alert-list-message">{{ group.message }}</div>
</div>
```

- [ ] **Step 2: 实现展开折叠组详情**

点击折叠组后，在预警详情面板中展示时间线和所有关联预警：

```typescript
function selectGroup(group: any) {
  selectedGroup.value = group
  if (group.count === 1) {
    selectedAlert.value = group.topAlert
  }
  // 展开模式：显示所有关联预警 + 时间线
}
```

- [ ] **Step 3: 添加时间线组件到详情面板**

在详情面板中添加历史时间线展示（使用 `el-timeline`）：

```html
<el-timeline v-if="selectedAlert?.details?.history?.length">
  <el-timeline-item
    v-for="entry in selectedAlert.details.history"
    :key="entry.seq"
    :timestamp="entry.timestamp"
    :type="entry.action === 'created' ? 'primary' : entry.action.includes('escalate') ? 'danger' : entry.action.includes('downgrade') ? 'warning' : 'info'"
  >
    <p>
      <el-tag size="small" :type="entry.source_role === 'system' ? '' : entry.source_role === 'doctor' ? 'success' : 'warning'">
        {{ entry.source_role === 'system' ? '系统' : entry.source_role === 'doctor' ? '医生' : '护士' }}
      </el-tag>
      {{ entry.action === 'created' ? '创建预警' :
         entry.action === 'downgrade' ? `降级为 ${entry.level}` :
         entry.action === 'nurse_escalate' ? `升级为 ${entry.level}` :
         entry.action === 'nurse_appeal' ? '申请复议' :
         entry.action === 'confirm' ? '确认' :
         entry.action === 'nurse_confirm' ? '护士确认' :
         entry.action === 'dismiss' ? '解除' :
         entry.action === 'nurse_dismiss' ? '护士解除' :
         entry.action === 'auto_dismiss' ? '自动关闭' : entry.action }}
    </p>
    <p v-if="entry.reason" class="timeline-reason">{{ entry.reason }}</p>
  </el-timeline-item>
</el-timeline>
```

- [ ] **Step 4: 确认 WebSocket 只接收 RED 级别**

ReviewWorkbench 当前 WebSocket `onAlert` 回调中，RED 预警直接显示，ORANGE/YELLOW 不应出现在医生端（由推送路由保证）。添加日志确认：

```typescript
wsClient.onAlert((data: any) => {
  if (data.level === 'RED') {
    pendingNewAlerts.value.push(data)
  }
  // ORANGE/YELLOW 不会推送到医生端，记录异常日志
  if (data.level !== 'RED') {
    console.warn('[ReviewWorkbench] 收到非RED预警:', data.level, data)
  }
})
```

- [ ] **Step 5: 验证前端编译**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | tail -20
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/doctor/ReviewWorkbench.vue
git commit -m "feat: add alert grouping/folding, timeline display, and push routing alignment to ReviewWorkbench"
```

---

### Task 14: RiskBadge 状态增强

**Files:**
- Modify: `frontend/src/components/common/RiskBadge.vue`

- [ ] **Step 1: 增加降级/复议状态标识**

在 `RiskBadge.vue` 中增加 props 支持展示附加状态：

```typescript
interface Props {
  level: string
  sourceRole?: string    // 'doctor' | 'nurse' | 'system'
  action?: string        // 'downgrade' | 'nurse_escalate' | 'nurse_appeal'
  showPrefix?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  sourceRole: undefined,
  action: undefined,
  showPrefix: true,
})

const prefixLabel = computed(() => {
  if (!props.showPrefix) return ''
  if (props.action === 'downgrade') return '[医生降级] '
  if (props.action === 'nurse_escalate') return '[护士升级] '
  if (props.action === 'nurse_appeal') return '[复议中] '
  return ''
})
```

模板更新：

```html
<template>
  <el-tag :type="tagType" size="small">
    {{ prefixLabel }}{{ levelLabel }}
  </el-tag>
</template>
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | tail -20
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/common/RiskBadge.vue
git commit -m "feat: add downgrade/escalate/appeal prefix to RiskBadge"
```

---

### Task 15: 集成测试验证

**Files:**
- 无新文件

- [ ] **Step 1: 运行全部后端测试**

```bash
cd backend && python -m pytest -v
```

Expected: ALL tests PASS

- [ ] **Step 2: 运行前端类型检查**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected: 无类型错误

- [ ] **Step 3: 启动后端验证 API 可访问**

```bash
cd backend && python -c "from app.main import app; print('FastAPI app loaded successfully')"
```

Expected: `FastAPI app loaded successfully`（无 import 错误）

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "chore: final integration verification for alert push mechanism enhancement"
```
