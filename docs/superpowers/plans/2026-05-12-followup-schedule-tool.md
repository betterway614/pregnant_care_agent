# 小Hu随访排期推荐工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为护士AI（小Hu）新增随访排期推荐工具，根据孕周/风险/预警/数据频率生成推荐列表，集成到分析响应和独立端点。

**Architecture:** 纯规则引擎，无LLM调用。在 nurse_ai.py 中新增 `tool_recommend_followup_schedule` 函数 + 3个辅助函数，新增 GET 端点，集成到 nurse_analyze 响应。schemas.py 新增3个 Pydantic 模型。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2

---

## 文件变更总览

| 文件 | 操作 | 内容 |
|------|------|------|
| `backend/app/schemas/schemas.py` | 修改 | 新增3个Pydantic模型 + NurseAnalyzeResponse加字段 |
| `backend/app/schemas/__init__.py` | 修改 | 导出新模型 |
| `backend/app/routers/nurse_ai.py` | 修改 | 新增工具函数 + 辅助函数 + GET端点 + nurse_analyze集成 |

---

## Task 1: 新增 Pydantic 排期模型

**Files:**
- Modify: `backend/app/schemas/schemas.py:260-266`
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 1.1: 在 schemas.py 中 NurseAnalyzeResponse 之前插入3个新模型**

在 `backend/app/schemas/schemas.py` 中，找到 `class NurseAnalyzeResponse`（line 260），在它**之前**插入以下代码：

```python
# === 随访排期推荐 ===
class FollowupScheduleRecommendation(BaseModel):
    recommended_date: str                    # ISO日期 "2026-05-15" 或 "immediate"
    gestational_week: str                    # 该日期的孕周 "29+0"
    template_id: str                         # standard / fgr_high_risk / post_discharge
    reason: str                              # 推荐原因（中文）
    priority: str                            # high / medium / low
    is_overdue: bool = False
    suggested_actions: list[str] = []


class FollowupScheduleContext(BaseModel):
    days_since_last_followup: int | None = None
    last_followup_date: str | None = None
    last_followup_status: str | None = None
    health_data_frequency: str = "inactive"  # active / moderate / inactive
    health_data_count_14d: int = 0
    active_alert_count: int = 0
    has_critical_alerts: bool = False
    risk_tags: list[str] = []


class FollowupScheduleResponse(BaseModel):
    pregnant_id: str
    current_gestational_week: str
    recommendations: list[FollowupScheduleRecommendation] = []
    context_summary: FollowupScheduleContext = FollowupScheduleContext()
```

- [ ] **Step 1.2: 在 NurseAnalyzeResponse 中新增 followup_schedule 字段**

找到 `NurseAnalyzeResponse`（现在在插入新模型之后），在 `followup_focus: list[str] = []` 之后添加一行：

```python
    followup_schedule: FollowupScheduleResponse | None = None
```

完整的 NurseAnalyzeResponse 变为：

```python
class NurseAnalyzeResponse(BaseModel):
    pregnant_id: str
    patient_name: str
    summary: str = ""
    risk_assessment: str = ""
    nursing_suggestions: str = ""
    followup_focus: list[str] = []
    followup_schedule: FollowupScheduleResponse | None = None
```

- [ ] **Step 1.3: 在 schemas/__init__.py 中导出新模型**

在 `backend/app/schemas/__init__.py` 的 import 行中添加3个新类：

```python
from .schemas import (
    # ... 现有导入保持不变 ...
    FollowUpGenerateRequest, FollowUpGenerateResponse,
    FollowupScheduleRecommendation, FollowupScheduleContext, FollowupScheduleResponse,  # 新增
    DoctorAnalyzeRequest, DoctorAnalyzeResponse,
    OrderExplainResponse,
)
```

在 `__all__` 列表中也添加：

```python
    "FollowupScheduleRecommendation", "FollowupScheduleContext", "FollowupScheduleResponse",
```

- [ ] **Step 1.4: 验证 import 正确**

Run: `cd backend && python -c "from app.schemas import FollowupScheduleResponse, FollowupScheduleRecommendation, FollowupScheduleContext, NurseAnalyzeResponse; print('Import OK')"`

Expected: `Import OK`

- [ ] **Step 1.5: Commit**

```bash
git add backend/app/schemas/schemas.py backend/app/schemas/__init__.py
git commit -m "feat: 新增随访排期推荐Pydantic模型"
```

---

## Task 2: 实现 tool_recommend_followup_schedule

**Files:**
- Modify: `backend/app/routers/nurse_ai.py:537`（在现有工具函数之后追加）

- [ ] **Step 2.1: 在 nurse_ai.py 顶部补充 import**

找到文件顶部的 import 区域（line 1-10），在现有 import 后追加：

```python
from datetime import datetime, timedelta
from sqlalchemy import desc, func
from ..schemas import FollowupScheduleResponse, FollowupScheduleRecommendation, FollowupScheduleContext
```

- [ ] **Step 2.2: 在 nurse_ai.py 末尾（line 537 之后）追加辅助函数和主函数**

在 `tool_update_nursing_note` 函数之后，追加以下完整代码：

```python
# ==================== 随访排期推荐 ====================

def _determine_base_interval(gest_week: int, risk_tags: list, has_critical: bool) -> int:
    """返回建议随访间隔（天）"""
    if has_critical:
        return 0  # 立即
    if gest_week >= 36:
        return 7
    if any(t in risk_tags for t in ("FGR高危", "高血压")):
        return 10
    if "GDM" in risk_tags:
        return 14
    return 21


def _select_template(risk_tags: list, gest_week: int) -> str:
    """根据风险标签和孕周选择随访模板"""
    if any(t in risk_tags for t in ("FGR高危", "高血压")):
        return "fgr_high_risk"
    if gest_week >= 37:
        return "post_discharge"
    return "standard"


def _build_suggested_actions(gest_week: int, risk_tags: list, data_freq: str) -> list[str]:
    """根据条件生成建议动作列表"""
    actions = ["确认随访时间并通知孕妇"]
    if "FGR高危" in risk_tags:
        actions.append("提醒携带最近B超报告")
    if "高血压" in risk_tags:
        actions.append("提醒携带血压监测记录")
    if "GDM" in risk_tags:
        actions.append("提醒携带血糖监测记录")
    if data_freq == "inactive":
        actions.append("督促孕妇加强健康数据上报")
    if gest_week >= 36:
        actions.append("确认分娩准备情况")
    return actions


def tool_recommend_followup_schedule(db, pregnant_id: str) -> dict:
    """根据历史随访和数据上报情况，生成随访排期推荐列表"""
    # 1. 查询孕妇信息
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        return {"error": "孕妇不存在", "pregnant_id": pregnant_id}

    gest_days = pregnant.gestational_age_days or 0
    gest_week = gest_days // 7
    gest_day = gest_days % 7
    risk_tags = pregnant.risk_tags or []
    current_date = datetime.utcnow().date()

    # 2. 查询最近随访记录
    last_followup = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == pregnant_id
    ).order_by(desc(FollowUpRecord.created_at)).first()

    days_since_last = None
    last_followup_date = None
    last_followup_status = None
    if last_followup and last_followup.created_at:
        last_followup_date = last_followup.created_at.date()
        days_since_last = (current_date - last_followup_date).days
        last_followup_status = last_followup.status

    # 3. 查询活跃预警
    active_alerts = db.query(Alert).filter(
        Alert.pregnant_id == pregnant_id,
        Alert.status == "PENDING"
    ).all()
    has_critical = any(a.level in ("RED", "ORANGE") for a in active_alerts)
    alert_count = len(active_alerts)

    # 4. 查询14天健康数据量
    fourteen_days_ago = datetime.utcnow() - timedelta(days=14)
    data_count_14d = db.query(func.count(HealthDataPoint.id)).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.recorded_at >= fourteen_days_ago
    ).scalar() or 0

    if data_count_14d >= 7:
        data_freq = "active"
    elif data_count_14d >= 3:
        data_freq = "moderate"
    else:
        data_freq = "inactive"

    # 5. 计算排期
    interval = _determine_base_interval(gest_week, risk_tags, has_critical)
    template = _select_template(risk_tags, gest_week)
    recommendations = []

    # 5.1 立即随访：高危预警
    if has_critical:
        critical_alerts = [a for a in active_alerts if a.level in ("RED", "ORANGE")]
        reasons = [f"[{a.level}] {a.message}" for a in critical_alerts[:3]]
        recommendations.append({
            "recommended_date": "immediate",
            "gestational_week": f"{gest_week}+{gest_day}",
            "template_id": _select_template(risk_tags, gest_week),
            "reason": f"存在{len(critical_alerts)}条高级别预警需立即处理：{'；'.join(reasons)}",
            "priority": "high",
            "is_overdue": False,
            "suggested_actions": ["立即联系孕妇进行随访", "确认预警详情并处理"],
        })

    # 5.2 逾期检查
    if interval > 0 and days_since_last is not None and days_since_last > interval * 1.5:
        recommendations.append({
            "recommended_date": "immediate",
            "gestational_week": f"{gest_week}+{gest_day}",
            "template_id": template,
            "reason": f"已超过{days_since_last}天未随访（建议间隔{interval}天），需尽快安排",
            "priority": "high",
            "is_overdue": True,
            "suggested_actions": ["尽快安排随访", "了解未随访原因"],
        })
    elif interval > 0 and days_since_last is None and gest_week >= 12:
        recommendations.append({
            "recommended_date": "immediate",
            "gestational_week": f"{gest_week}+{gest_day}",
            "template_id": template,
            "reason": "该孕妇尚无随访记录，建议尽快安排首次随访",
            "priority": "high",
            "is_overdue": True,
            "suggested_actions": ["安排首次随访", "建立随访档案"],
        })

    # 5.3 数据督促
    if data_freq == "inactive" and risk_tags:
        has_data_engagement = any(r.get("reason", "").startswith("数据不活跃") for r in recommendations)
        if not has_data_engagement:
            recommendations.append({
                "recommended_date": "immediate",
                "gestational_week": f"{gest_week}+{gest_day}",
                "template_id": template,
                "reason": f"数据不活跃：14天内仅上报{data_count_14d}条，有风险标签的孕妇需加强监测",
                "priority": "medium",
                "is_overdue": False,
                "suggested_actions": ["督促孕妇加强健康数据上报", "了解数据未上报原因"],
            })

    # 5.4 未来排期（2-3次）
    for i in range(1, 4):
        future_date = current_date + timedelta(days=interval * i)
        future_days_offset = interval * i
        future_gest_week = gest_week + (future_days_offset // 7)
        future_gest_day = gest_day + (future_days_offset % 7)
        if future_gest_day >= 7:
            future_gest_week += 1
            future_gest_day -= 7

        if future_gest_week > 42:
            break

        # 优先级
        if future_gest_week >= 36:
            priority = "high"
        elif any(t in risk_tags for t in ("FGR高危", "高血压")):
            priority = "medium"
        else:
            priority = "low"

        if data_freq == "inactive" and priority == "low":
            priority = "medium"

        future_template = _select_template(risk_tags, future_gest_week)

        reason_parts = []
        if future_gest_week >= 36:
            reason_parts.append(f"孕{future_gest_week}周已进入晚期，需每周随访")
        if any(t in risk_tags for t in ("FGR高危", "高血压")):
            reason_parts.append("高危孕妇需加密随访")
        if "GDM" in risk_tags:
            reason_parts.append("妊娠期糖尿病需定期监测")
        if not reason_parts:
            reason_parts.append(f"常规随访（建议间隔{interval}天）")

        recommendations.append({
            "recommended_date": future_date.isoformat(),
            "gestational_week": f"{future_gest_week}+{future_gest_day}",
            "template_id": future_template,
            "reason": "；".join(reason_parts),
            "priority": priority,
            "is_overdue": False,
            "suggested_actions": _build_suggested_actions(future_gest_week, risk_tags, data_freq),
        })

    # 6. 排序：immediate优先，然后按priority，最后按日期
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda r: (
        0 if r["recommended_date"] == "immediate" else 1,
        priority_order.get(r["priority"], 2),
        r["recommended_date"] if r["recommended_date"] != "immediate" else "",
    ))

    return {
        "pregnant_id": pregnant_id,
        "current_gestational_week": f"{gest_week}+{gest_day}",
        "recommendations": recommendations[:5],  # 最多5条
        "context_summary": {
            "days_since_last_followup": days_since_last,
            "last_followup_date": last_followup_date.isoformat() if last_followup_date else None,
            "last_followup_status": last_followup_status,
            "health_data_frequency": data_freq,
            "health_data_count_14d": data_count_14d,
            "active_alert_count": alert_count,
            "has_critical_alerts": has_critical,
            "risk_tags": risk_tags,
        },
    }
```

- [ ] **Step 2.3: 验证函数可导入**

Run: `cd backend && python -c "from app.routers.nurse_ai import tool_recommend_followup_schedule; print('Import OK')"`

Expected: `Import OK`

- [ ] **Step 2.4: 验证排期逻辑（手动测试）**

Run:
```bash
cd backend && python -c "
from app.database import SessionLocal
from app.routers.nurse_ai import tool_recommend_followup_schedule
from app.models import Pregnant

db = SessionLocal()
# 取第一个有风险标签的孕妇
p = db.query(Pregnant).filter(Pregnant.risk_tags != '[]').first()
if p:
    result = tool_recommend_followup_schedule(db, p.pregnant_id)
    print(f'Pregnant: {p.nickname} ({p.risk_tags})')
    print(f'Current week: {result[\"current_gestational_week\"]}')
    print(f'Recommendations: {len(result[\"recommendations\"])}')
    for r in result['recommendations']:
        print(f'  [{r[\"priority\"]}] {r[\"recommended_date\"]} - {r[\"reason\"][:60]}')
    print(f'Context: {result[\"context_summary\"]}')
else:
    print('No pregnant with risk tags found')
db.close()
"
```

Expected: 输出排期推荐列表，包含至少1-3条推荐

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/routers/nurse_ai.py
git commit -m "feat: 实现tool_recommend_followup_schedule排期推荐函数"
```

---

## Task 3: 集成到 nurse_analyze + 新增独立端点

**Files:**
- Modify: `backend/app/routers/nurse_ai.py:15-47`（nurse_analyze端点）
- Modify: `backend/app/routers/nurse_ai.py`（新增GET端点）

- [ ] **Step 3.1: 修改 nurse_analyze 端点，集成排期推荐**

找到 `nurse_analyze` 函数中的 `return result`（line 47），在其**之前**插入排期推荐调用：

```python
        # 生成随访排期推荐
        schedule_result = tool_recommend_followup_schedule(db, req.pregnant_id)
        if "error" not in schedule_result:
            result.followup_schedule = FollowupScheduleResponse(**schedule_result)

        return result
```

修改后的 nurse_analyze 函数关键部分（line 40-50）应为：

```python
        # 分析完成后自动创建预警（如果检测到高风险）
        if "高风险" in (result.risk_assessment or "") or "异常" in (result.risk_assessment or ""):
            tool_create_alert(
                db, req.pregnant_id, "ORANGE",
                f"护士AI分析提示：{result.risk_assessment[:100]}",
                "MANUAL"
            )

        # 生成随访排期推荐
        schedule_result = tool_recommend_followup_schedule(db, req.pregnant_id)
        if "error" not in schedule_result:
            result.followup_schedule = FollowupScheduleResponse(**schedule_result)

        return result
```

- [ ] **Step 3.2: 在 nurse_ai.py 中新增独立查询端点**

在 `nurse_analyze` 端点之后（line 49 的 `finally` 之后），追加新的 GET 端点：

```python
@router.get("/schedule-recommend/{pregnant_id}")
def recommend_followup_schedule(pregnant_id: str):
    """获取随访排期推荐列表"""
    db = SessionLocal()
    try:
        result = tool_recommend_followup_schedule(db, pregnant_id)
        if "error" in result:
            raise HTTPException(404, result["error"])
        return result
    finally:
        db.close()
```

- [ ] **Step 3.3: 验证端点注册**

Run: `cd backend && python -c "from app.main import app; routes = [r.path for r in app.routes if hasattr(r, 'path')]; print([r for r in routes if 'nurse' in r])"`

Expected: 列表中包含 `/api/v1/nurse/schedule-recommend/{pregnant_id}`

- [ ] **Step 3.4: 验证 nurse_analyze 响应包含 followup_schedule**

Run:
```bash
cd backend && python -c "
from app.database import SessionLocal
from app.models import Pregnant

db = SessionLocal()
p = db.query(Pregnant).first()
print(f'Test with: {p.pregnant_id}')
db.close()
# 启动后用 curl 测试:
# curl -X POST http://localhost:9999/api/v1/nurse/analyze -H 'Content-Type: application/json' -d '{\"pregnant_id\": \"PT_XXX\"}' | python -m json.tool | grep -A5 followup_schedule
"
```

Expected: 响应中 `followup_schedule` 字段非 null，包含 recommendations 列表

- [ ] **Step 3.5: Commit**

```bash
git add backend/app/routers/nurse_ai.py
git commit -m "feat: nurse_analyze集成排期推荐 + 新增独立查询端点"
```

---

## 文件变更总结

| 文件 | 行数变化 | 说明 |
|------|---------|------|
| `backend/app/schemas/schemas.py` | +25行 | 3个新Pydantic模型 + NurseAnalyzeResponse加字段 |
| `backend/app/schemas/__init__.py` | +4行 | 导出3个新模型 |
| `backend/app/routers/nurse_ai.py` | +130行 | 3个辅助函数 + 主工具函数 + GET端点 + nurse_analyze集成 |
