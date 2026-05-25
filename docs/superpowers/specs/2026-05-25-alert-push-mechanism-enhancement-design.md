# 预警推送机制完善 — 设计方案

**日期**: 2026-05-25
**状态**: 待评审
**关联**: [[2026-05-25-alert-downgrade-independent-order-design]]

---

## 1. 问题分析

### 1.1 现状痛点

同一孕妇同一时刻出现多条不同级别预警，如：

> 孕妇01, 32周:
> - [医生降级] 孕晚期血压偏高，子痫前期风险 — YELLOW
> - 孕晚期血压偏高，子痫前期风险 — ORANGE
> - 体重增长过慢，需关注营养摄入 — YELLOW

### 1.2 根因

三层叠加导致重复报警：

1. **规则重叠** — `RULE_BP_HIGH_ORANGE`(sbp>=135) 和 `RULE_LATE_PREGNANCY_BP`(sbp>=130 and gest_week>=32) 覆盖同一临床问题
2. **评估无分组** — `evaluate_all()` 遍历全部规则，每条独立判断，命中几条产出几条
3. **创建无合并** — `create_alerts_from_hits()` 一个 hit = 一条 alert，不做临床语义聚合

### 1.3 目标

从根源消除同领域重复报警，并建立完整的级别流转、分级推送、护士分诊机制。

---

## 2. 规则引擎重构：领域分组

### 2.1 3 领域划分

| 领域 | domain | 包含规则 | 级别 |
|------|--------|---------|------|
| 生命体征 | `vital` | RULE_BP_HIGH, RULE_BP_HIGH_ORANGE, RULE_BP_LOW, RULE_LATE_PREGNANCY_BP, RULE_BS_POSTPRANDIAL_HIGH, RULE_BS_FASTING_HIGH, RULE_WEIGHT_GAIN_FAST, RULE_WEIGHT_GAIN_SLOW | RED/ORANGE/YELLOW |
| 胎儿 | `fetal` | RULE_FETAL_DROP, RULE_FETAL_VERY_LOW | RED |
| 心理行为 | `mental` | RULE_EMOTION_CRITICAL, RULE_EMOTION_HIGH, RULE_SLEEP_SHORT | ORANGE/YELLOW |

### 2.2 Rule 模型扩展

`backend/app/core/rule_engine.py`

```python
class Rule:
    def __init__(self, rule_id: str, domain: str, priority: int,
                 expression: str, level: str, message: str, action: str = "ALERT_NURSE"):
        self.id = rule_id
        self.domain = domain      # 新增: vital / fetal / mental
        self.priority = priority  # 新增: 组内优先级, 数字越大越高
        self.expression = expression
        self.level = level
        self.message = message
        self.action = action
```

### 2.3 规则定义

```python
RULES = [
    # === 生命体征 ===
    Rule("RULE_BP_HIGH", "vital", 3, "sbp >= 140 or dbp >= 90", "RED",
         "血压异常升高（≥140/90mmHg）", "ALERT_DOCTOR_AND_NURSE"),
    Rule("RULE_BP_HIGH_ORANGE", "vital", 2, "sbp >= 135 or dbp >= 85", "ORANGE",
         "血压偏高（≥135/85mmHg），需要关注", "ALERT_NURSE"),
    Rule("RULE_BP_LOW", "vital", 1, "sbp < 90 or dbp < 60", "YELLOW",
         "血压偏低，需关注", "NOTE_NURSE"),
    Rule("RULE_LATE_PREGNANCY_BP", "vital", 2, "sbp >= 130 and gest_week >= 32", "ORANGE",
         "孕晚期血压偏高，子痫前期风险", "ALERT_NURSE"),
    Rule("RULE_BS_POSTPRANDIAL_HIGH", "vital", 3, "blood_sugar_postprandial > 7.0", "RED",
         "餐后血糖异常（>7.0mmol/L）", "ALERT_DOCTOR_AND_NURSE"),
    Rule("RULE_BS_FASTING_HIGH", "vital", 2, "blood_sugar_fasting > 5.3", "ORANGE",
         "空腹血糖偏高（>5.3mmol/L），建议复查", "ALERT_NURSE"),
    Rule("RULE_WEIGHT_GAIN_FAST", "vital", 2, "weight_gain_weekly > 2.0", "ORANGE",
         "体重周增长过快（>2kg/周）", "ALERT_NURSE"),
    Rule("RULE_WEIGHT_GAIN_SLOW", "vital", 1, "weight_gain_weekly < 0.1 and gest_week > 12", "YELLOW",
         "体重增长过慢，需关注营养摄入", "NOTE_NURSE"),

    # === 胎儿 ===
    Rule("RULE_FETAL_DROP", "fetal", 3, "fetal_movement < fetal_movement_avg * 0.5", "RED",
         "胎动显著减少（低于平均50%）", "ALERT_DOCTOR_AND_NURSE"),
    Rule("RULE_FETAL_VERY_LOW", "fetal", 3, "fetal_movement < 3", "RED",
         "胎动极少（<3次/小时），请立即就医", "ALERT_DOCTOR_AND_NURSE"),

    # === 心理行为 ===
    Rule("RULE_EMOTION_CRITICAL", "mental", 2, "emotion_score_avg_7d >= 9", "ORANGE",
         "情绪评分严重偏高，建议心理干预", "ALERT_NURSE"),
    Rule("RULE_EMOTION_HIGH", "mental", 1, "emotion_score_avg_7d >= 7", "YELLOW",
         "近7日情绪评分偏高，需关注心理状态", "NOTE_NURSE"),
    Rule("RULE_SLEEP_SHORT", "mental", 1, "sleep_hours < 5", "YELLOW",
         "睡眠不足5小时，建议改善睡眠", "NOTE_NURSE"),
]
```

### 2.4 evaluate_all() 按领域取最高优先级

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

### 2.5 效果与跨指标处理

孕妇01 (32周, sbp=132, dbp=86, 体重增长慢)：
- 改造前：3 条预警 (RULE_LATE_PREGNANCY_BP + RULE_BP_HIGH_ORANGE + RULE_WEIGHT_GAIN_SLOW)
- 改造后：1 条预警
  - `vital`: ORANGE "孕晚期血压偏高，子痫前期风险"
  - `triggered_rules` = [RULE_LATE_PREGNANCY_BP, RULE_BP_HIGH_ORANGE, RULE_WEIGHT_GAIN_SLOW]
  - `details.all_hits` 列出所有命中指标及其级别

同一领域 vital 内包含血压、血糖、体重三类临床指标，它们可能独立异常。一次评估中取高优先级作为主预警，`details.all_hits` 记录所有命中。

> **设计决策**：同一领域合并有利有弊。利：大幅减少重复预警；弊：低优先级的异常指标可能被高优先级"掩盖"。依赖 LLM enrich 阶段在 `details` 中补充所有异常指标分析，确保护士/医生不会遗漏。

---

## 3. 推送策略

### 3.1 推送矩阵

```
触发来源          目标级别    推送医生    推送护士    说明
────────────────────────────────────────────────────────
规则引擎           RED         ✅          ✅         直接告警
规则引擎           ORANGE      ❌          ✅         护士先审
规则引擎           YELLOW      ❌          ✅         护士关注
医生降级           ORANGE      ❌          ✅         仅推护士
医生降级           YELLOW      ❌          ✅         仅推护士
护士升级到 ORANGE  ORANGE      ✅          ✅         护士已分诊, 推全部医生
护士升级到 RED     RED         ✅(全部)    ✅
护士复议           —           ✅(目标医生) ✅        回推降级医生
```

**核心理念**：护士承担分诊角色。RED 是唯一直接通知医生的级别，ORANGE/YELLOW 由护士评估后决定是否升级。

### 3.2 WebSocket 改造

`backend/app/core/websocket_manager.py`

当前 `broadcast_alert()` 无差别推送，改为按级别和来源角色路由：

```python
async def route_alert(self, alert_data: dict):
    """按级别和来源角色路由推送"""
    level = alert_data["level"]
    source_role = alert_data.get("source_role", "system")
    action = alert_data.get("action")

    if source_role == "doctor" and action == "downgrade":
        await self.broadcast_to_nurses(alert_data)
    elif source_role == "nurse" and action == "escalate":
        await self.broadcast_all(alert_data)  # 升级后级别已是 RED/ORANGE
    elif source_role == "nurse" and action == "appeal":
        target_doctor_id = alert_data.get("target_doctor_id")
        await self.send_to_doctor(target_doctor_id, alert_data)
        await self.broadcast_to_nurses(alert_data)
    elif level == "RED":
        await self.broadcast_all(alert_data)
    elif level == "ORANGE" or level == "YELLOW":
        await self.broadcast_to_nurses(alert_data)
```

### 3.3 角色来源标记

| 场景 | source_role |
|------|-------------|
| 规则引擎触发 | `system` |
| 医生操作 | `doctor` |
| 护士操作 | `nurse` |

API 层根据 `reviewed_by` 查用户角色，写入 `alert.details.source_role`。

---

## 4. 状态机

### 4.1 状态流转图

```
规则引擎触发
     │
     ▼
  PENDING ──────────────────────────────┐
     │                                   │
     ├── 医生确认 ──→ CONFIRMED (关闭)    │
     │                                   │
     ├── 医生解除 ──→ DISMISSED (关闭)    │
     │                                   │
     ├── 护士确认 ──→ CONFIRMED (关闭)    │
     │                                   │
     ├── 护士解除 ──→ DISMISSED (关闭)    │
     │                                   │
     ├── 医生降级 ──→ PENDING (级别降低)   │
     │                                   │
     ├── 护士升级 ──→ PENDING (级别升高)   │
     │                                   │
     ├── 护士复议 ──→ PENDING (标记"复议")  │
     │                                   │
     └── N小时后无人处理 ──→ AUTO_DISMISSED │
```

### 4.2 状态枚举

保留：`PENDING`, `CONFIRMED`, `DISMISSED`
新增：`AUTO_DISMISSED`
移除独立状态：`ESCALATED`（升级后仍为 PENDING，通过 level 变化 + 历史时间线体现流转）

### 4.3 自动关闭时效

| 级别 | 未处理自动关闭 | 理由 |
|------|---------------|------|
| YELLOW | 24 小时 | 低风险，快速关闭减少积压 |
| ORANGE | 48 小时 | 中等风险 |
| RED | 72 小时 | 高危，给予充足处理时间 |

通过定时任务（`CronCreate` 每小时一次）检查超时 PENDING 预警并自动标记。

### 4.4 操作矩阵

| 操作 | 角色 | 前置状态 | 后置状态 | 级别变化 | 推送 |
|------|------|---------|---------|---------|------|
| `confirm` | doctor | PENDING | CONFIRMED | 不变 | 不推 |
| `dismiss` | doctor | PENDING | DISMISSED | 不变 | 不推 |
| `downgrade` | doctor | PENDING | PENDING | 降为指定级别 | 目标级别为 ORANGE/YELLOW 推护士；GREEN → DISMISSED |
| `nurse_confirm` | nurse | PENDING | CONFIRMED | 不变 | 不推 |
| `nurse_dismiss` | nurse | PENDING | DISMISSED | 不变 | 不推 |
| `nurse_escalate` | nurse | PENDING | PENDING | 升一级(Y→O→R) | 推全部医生+护士 |
| `nurse_appeal` | nurse | PENDING(医生降级) | PENDING | 不变，标记"复议中" | 推回原降级医生 + 护士 |

---

## 5. 流转追踪

### 5.1 预警内时间线

`Alert` 模型 `details` 字段扩展 `history` 数组：

```json
{
  "history": [
    {
      "seq": 1,
      "action": "created",
      "source_role": "system",
      "level": "ORANGE",
      "operator": null,
      "reason": null,
      "timestamp": "2026-05-25T11:54:00"
    },
    {
      "seq": 2,
      "action": "downgrade",
      "source_role": "doctor",
      "level": "YELLOW",
      "operator": "doctor_001",
      "reason": "血压在妊娠期正常范围上限，暂观察",
      "timestamp": "2026-05-25T12:30:00"
    },
    {
      "seq": 3,
      "action": "nurse_appeal",
      "source_role": "nurse",
      "level": "YELLOW",
      "operator": "nurse_002",
      "reason": "孕妇自述有头晕症状，建议重新评估",
      "timestamp": "2026-05-25T14:00:00"
    }
  ]
}
```

### 5.2 列表关联折叠

预警列表中，同一孕妇的关联预警折叠显示（通过 `details.parent_alert_id` 或同一 `pregnant_id + domain` 的活跃预警聚类）。

- 列表展示折叠组的最新/最高级别预警
- 展开后显示该孕妇所有关联预警卡片，按时序排列

---

## 6. 数据模型变更

### 6.1 Alert 模型 (`backend/app/models/models.py`)

| 字段 | 类型 | 变更 |
|------|------|------|
| `domain` | String(32) | **新增** — vital / fetal / mental |
| `status` | String(16) | 枚举增加 `AUTO_DISMISSED`；默认 `ESCALATED` 仍保留但不再新建使用 |

### 6.2 AlertReviewRequest Schema (`backend/app/schemas/schemas.py`)

```python
class AlertReviewRequest(BaseModel):
    action: str  # confirm / dismiss / downgrade / nurse_confirm / nurse_dismiss / nurse_escalate / nurse_appeal
    target_level: Optional[str] = None  # 降级时必填: ORANGE / YELLOW / GREEN
    reason: Optional[str] = None
```

---

## 7. API 变更

### 7.1 操作接口改造

`PUT /api/v1/alerts/{alert_id}/review` — 扩展 action 枚举，增加角色校验。

### 7.2 新增：护士端接口（如需要独立入口）

`PUT /api/v1/alerts/{alert_id}/nurse-review`

### 7.3 新增：定时清理任务

`POST /api/v1/alerts/auto-dismiss` — 内部定时任务调用，关闭超时 PENDING 预警。

### 7.4 改造：WebSocket 路由

`route_alert()` 替代 `broadcast_alert()` 的旧调用点（`alerts.py` 创建预警时 + review 操作后）。

---

## 8. 去重简化

原有的 `_find_duplicate()` 时间窗口去重逻辑（`alert_service.py:11-36`）可以简化为**同一 domain + pregnant_id + status=PENDING 时视为重复**，不再依赖时间窗口。

```python
def _find_duplicate(self, db: Session, pregnant_id: str, domain: str) -> Optional[Alert]:
    """同一孕妇同一领域已有 PENDING 预警时视为重复"""
    return db.query(Alert).filter(
        Alert.pregnant_id == pregnant_id,
        Alert.domain == domain,
        Alert.status == "PENDING",
    ).first()
```

领域分组从根源减少了重复预警数量，新的去重逻辑只需防止同领域并发创建。

---

## 9. 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/core/rule_engine.py` | Rule 模型增加 domain/priority；evaluate_all 改为按领域取最高 |
| `backend/app/services/alert_service.py` | create_alerts_from_hits 适配新结构；简化去重逻辑 |
| `backend/app/routers/alerts.py` | review_alert 增加护士操作 + 角色校验；source_role 写入 |
| `backend/app/schemas/schemas.py` | AlertReviewRequest action 扩展；新增 Alert 字段 |
| `backend/app/models/models.py` | Alert 增加 domain 字段；status 增加 AUTO_DISMISSED |
| `backend/app/core/websocket_manager.py` | broadcast_alert → route_alert |
| `frontend/src/views/doctor/ReviewWorkbench.vue` | 预警列表关联折叠；时间线展示；降级逻辑对齐 |
| `frontend/src/views/nurse/AlertList.vue` | 护士升级/复议/确认操作；预警列表折叠；WebSocket 接入 |
| `frontend/src/views/nurse/NurseDashboard.vue` | WebSocket 实时推送接入 |
| `frontend/src/components/common/RiskBadge.vue` | 如需要，增加降级/复议状态标识 |
| `backend/tests/test_rule_engine.py` | 领域分组 + 优先级互斥测试 |
| `backend/tests/test_alert_service.py` | 简化去重 + 护士操作测试 |

---

## 10. 不变更范围

- FGR 评估逻辑（`evaluate_fgr_risk`）独立于领域分组，本次不改
- LLM enrichment（`enrich_alert_with_llm`）流程不变
- Agno 工作流（nurse → doctor）结构不变
- 独立生成医嘱功能（已有设计文档覆盖）不变
- 签署页交互不变
