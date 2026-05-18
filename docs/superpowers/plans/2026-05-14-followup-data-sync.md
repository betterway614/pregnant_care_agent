# 随访问卷数据联动修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复护士端随访数据实时同步问题，实现随访完成后自动触发预警

**Architecture:**
- 前端：通过轮询机制（每30秒）自动刷新护士端数据，实时感知孕妇提交的随访
- 后端：在随访完成（completed）时自动调用规则引擎评估，生成预警记录
- 数据流：孕妇提交 → 后端处理 → 自动预警 → 前端轮询获取

**Tech Stack:** Vue3 Composition API, FastAPI, SQLite

---

## 文件结构

```
backend/
├── app/
│   ├── core/
│   │   ├── rule_engine.py          # 修改：增加 create_alert_from_hits 函数
│   │   └── __init__.py             # 修改：导出 create_alert_from_hits
│   ├── routers/
│   │   ├── followup.py              # 修改：完成后自动触发预警
│   │   └── alerts.py               # 新增：预警创建 API
│   ├── models/
│   │   └── models.py               # 新增：AiAnalysisResult 模型
│   └── services/
│       └── alert_service.py        # 新增：预警服务
frontend/
└── src/
    ├── views/
    │   ├── nurse/
    │   │   ├── NurseDashboard.vue  # 修改：增加轮询机制
    │   │   └── FollowUpList.vue    # 修改：增加轮询机制
    │   └── pregnant/
    │       └── FollowUpForm.vue    # 修改：完成后显示提示
    └── api/
        └── endpoints.ts             # 新增：AI分析保存 API
```

---

## Task 1: 护士端 NurseDashboard 增加轮询机制

**Files:**
- Modify: `frontend/src/views/nurse/NurseDashboard.vue:1-350`

- [ ] **Step 1: 在 script 中添加轮询定时器**

在 `NurseDashboard.vue` 的 script 部分，添加轮询相关代码：

```typescript
// 在现有代码之后添加
/** 轮询间隔（毫秒） */
const POLL_INTERVAL = 30000
let pollTimer: ReturnType<typeof setInterval> | null = null

/** 开始轮询 */
function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    fetchData()
  }, POLL_INTERVAL)
}

/** 停止轮询 */
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 修改 onMounted
onMounted(() => {
  fetchData()
  startPolling()
  loadPatientList()
})

// 新增 onUnmounted
onUnmounted(() => {
  stopPolling()
})
```

- [ ] **Step 2: 添加 onUnmounted 导入**

在 script 顶部的 `import { ref, computed, onMounted } from 'vue'` 中添加：

```typescript
import { ref, computed, onMounted, onUnmounted } from 'vue'
```

- [ ] **Step 3: 运行验证**

启动前端开发服务器，访问护士工作台，控制台应每30秒出现一次 `fetchData` 日志。

---

## Task 2: 护士端 FollowUpList 增加轮询机制

**Files:**
- Modify: `frontend/src/views/nurse/FollowUpList.vue:200-340`

- [ ] **Step 1: 添加轮询相关代码**

在 `FollowUpList.vue` 的 script 部分：

```typescript
/** 轮询间隔（毫秒） */
const POLL_INTERVAL = 30000
let pollTimer: ReturnType<typeof setInterval> | null = null

/** 开始轮询 */
function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    fetchRecords()
  }, POLL_INTERVAL)
}

/** 停止轮询 */
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 修改 onMounted
onMounted(() => {
  fetchRecords()
  startPolling()
})

// 新增 onUnmounted
onUnmounted(() => {
  stopPolling()
})
```

- [ ] **Step 2: 添加 onUnmounted 导入**

```typescript
import { ref, computed, onMounted, onUnmounted } from 'vue'
```

- [ ] **Step 3: 运行验证**

访问随访管理页面，模拟数据更新后，30秒内应自动刷新列表。

---

## Task 3: 后端新增预警服务

**Files:**
- Create: `backend/app/services/alert_service.py`

- [ ] **Step 1: 创建预警服务文件**

```python
"""预警服务 - 创建和管理预警记录"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy.orm import Session
from ..models import Alert


class AlertService:
    """预警服务"""

    @staticmethod
    def create_alert(
        db: Session,
        pregnant_id: str,
        rule_id: str,
        level: str,
        message: str,
        trigger_data: dict = None,
    ) -> Alert:
        """创建预警记录"""
        alert = Alert(
            id=uuid4(),
            pregnant_id=pregnant_id,
            rule_id=rule_id,
            level=level,
            description=message,
            status="pending",
            triggered_at=datetime.utcnow(),
        )
        if trigger_data:
            alert.trigger_data = trigger_data

        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def create_alerts_from_hits(
        db: Session,
        pregnant_id: str,
        hits: list[dict],
        source: str = "FOLLOWUP",
    ) -> list[Alert]:
        """从规则命中列表批量创建预警"""
        alerts = []
        for hit in hits:
            alert = AlertService.create_alert(
                db=db,
                pregnant_id=pregnant_id,
                rule_id=hit.get("rule_id", "UNKNOWN"),
                level=hit.get("level", "YELLOW"),
                message=hit.get("message", ""),
                trigger_data={
                    "source": source,
                    "action": hit.get("action", "ALERT_NURSE"),
                    "created_at": datetime.utcnow().isoformat(),
                },
            )
            alerts.append(alert)
        return alerts


alert_service = AlertService()
```

- [ ] **Step 2: 更新 Alert 模型**

在 `backend/app/models/models.py` 中，查找 `class Alert` 并添加缺失字段：

```python
class Alert(Base):
    """预警记录"""
    __tablename__ = "alerts"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    rule_id = Column(String(64), nullable=True, comment="触发规则ID")
    level = Column(String(16), nullable=False, comment="预警级别 RED/ORANGE/YELLOW")
    description = Column(Text, nullable=True, comment="预警描述")
    status = Column(String(16), default="pending", comment="pending/reviewed/dismissed")
    triggered_at = Column(DateTime, nullable=True)
    trigger_data = Column(JSON, nullable=True, comment="触发时的原始数据")
    reviewed_by = Column(String(64), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

## Task 4: 随访完成后自动触发预警

**Files:**
- Modify: `backend/app/routers/followup.py:255-290`

- [ ] **Step 1: 在 respond_to_followup 结束时添加预警触发**

在 `followup.py` 的 `respond_to_followup` 函数中，找到状态变为 completed 的代码块（约第259行），在 `db.commit()` 之前添加：

```python
# 状态机转换后检查是否完成
if all_answered and record.status == FOLLOWUP_STATUS_IN_PROGRESS:
    record.status = FOLLOWUP_STATUS_COMPLETED

    # 新增：自动触发预警评估
    try:
        from ..services.alert_service import alert_service

        # 构建评估上下文
        context = {}
        for key, value in reported_data.items():
            if key == "bp" and "/" in str(value):
                parts = str(value).split("/")
                if len(parts) == 2:
                    context["sbp"] = float(parts[0])
                    context["dbp"] = float(parts[1])
            elif key in ("sbp", "dbp"):
                context[key] = float(value)
            elif key == "weight":
                match = re.search(r"(\d+\.?\d*)", str(value))
                if match:
                    context["weight"] = float(match.group(1))
            elif key == "fetal_movement":
                match = re.search(r"(\d+)", str(value))
                if match:
                    context["fetal_movement"] = float(match.group(1))
            elif key in ("blood_sugar_fasting", "blood_sugar_postprandial"):
                match = re.search(r"(\d+\.?\d*)", str(value))
                if match:
                    context[key] = float(match.group(1))

        # 添加孕周
        if pregnant and pregnant.gestational_age_days:
            context["gest_week"] = pregnant.gestational_age_days // 7

        # 调用规则引擎
        if context:
            from ..core.rule_engine import rule_engine
            hits = rule_engine.evaluate_all(context)
            if hits:
                alert_service.create_alerts_from_hits(db, record.pregnant_id, hits, "FOLLOWUP")
                from loguru import logger
                logger.info(f"FOLLOWUP_AUTO_ALERT: created {len(hits)} alerts for pregnant_id={record.pregnant_id}")

    except Exception as e:
        from loguru import logger
        logger.warning(f"FOLLOWUP_AUTO_ALERT_FAILED: {e}")

    # 生成摘要（保持原有逻辑）
    record.summary = followup_service.generate_record_summary(
        patient_name=patient_name,
        gest_week=record.gestational_week or "?",
        answers=reported_data,
    )
```

- [ ] **Step 2: 添加 re 导入**

在文件顶部（其他 import 附近）确保有：
```python
import re
```

---

## Task 5: 护士端 AI 分析结果持久化

**Files:**
- Modify: `backend/app/routers/nurse.py` 或新建
- Modify: `frontend/src/views/nurse/NurseDashboard.vue:318-340`
- Modify: `frontend/src/api/endpoints.ts`

- [ ] **Step 1: 创建 AI 分析结果存储 API**

在 `backend/app/routers/` 目录创建或修改 `nurse.py`：

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from uuid import uuid4
from ..database import get_db
from ..models import AiAnalysisResult

router = APIRouter(prefix="/api/v1/nurse", tags=["护士AI"])

class SaveAiAnalysisRequest(BaseModel):
    pregnant_id: str
    result_data: dict
    analysis_type: str = "general"  # general / followup_summary / risk_assessment

class AiAnalysisResponse(BaseModel):
    id: str
    pregnant_id: str
    result_data: dict
    analysis_type: str
    created_at: datetime


@router.post("/ai-analysis", response_model=AiAnalysisResponse)
async def save_ai_analysis(req: SaveAiAnalysisRequest, db: Session = Depends(get_db)):
    """保存 AI 分析结果"""
    result = AiAnalysisResult(
        id=uuid4(),
        pregnant_id=req.pregnant_id,
        result_data=req.result_data,
        analysis_type=req.analysis_type,
    )
    db.add(result)
    db.commit()
    db.refresh(result)

    return AiAnalysisResponse(
        id=str(result.id),
        pregnant_id=result.pregnant_id,
        result_data=result.result_data,
        analysis_type=result.analysis_type,
        created_at=result.created_at,
    )


@router.get("/ai-analysis/{pregnant_id}", response_model=list[AiAnalysisResponse])
async def get_ai_analysis_history(pregnant_id: str, db: Session = Depends(get_db)):
    """获取孕妇的 AI 分析历史"""
    results = db.query(AiAnalysisResult).filter(
        AiAnalysisResult.pregnant_id == pregnant_id
    ).order_by(AiAnalysisResult.created_at.desc()).limit(20).all()

    return [
        AiAnalysisResponse(
            id=str(r.id),
            pregnant_id=r.pregnant_id,
            result_data=r.result_data,
            analysis_type=r.analysis_type,
            created_at=r.created_at,
        )
        for r in results
    ]
```

- [ ] **Step 2: 添加 AiAnalysisResult 模型**

在 `backend/app/models/models.py` 末尾添加：

```python
class AiAnalysisResult(Base):
    """AI 分析结果记录"""
    __tablename__ = "ai_analysis_results"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    analysis_type = Column(String(32), nullable=False, comment="分析类型: general/followup_summary/risk_assessment")
    result_data = Column(JSON, nullable=False, comment="分析结果数据")
    created_at = Column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 3: 更新前端 API**

在 `frontend/src/api/endpoints.ts` 中添加：

```typescript
// AI 分析相关
export const aiAnalysisApi = {
  save: (data: { pregnant_id: string; result_data: any; analysis_type: string }) =>
    client.post('/nurse/ai-analysis', data),
  getHistory: (pregnantId: string) =>
    client.get<Array<{ id: string; pregnant_id: string; result_data: any; analysis_type: string; created_at: string }>>(
      `/nurse/ai-analysis/${pregnantId}`
    ),
}
```

- [ ] **Step 4: 更新 NurseDashboard 保存结果**

在 `NurseDashboard.vue` 的 `runAiAnalysis` 函数中，保存结果到后端：

```typescript
async function runAiAnalysis() {
  if (!aiPatientId.value) return
  aiLoading.value = true
  aiResult.value = null
  try {
    const res = await nurseAiApi.analyze(aiPatientId.value)
    aiResult.value = res.data

    // 新增：保存到后端
    await aiAnalysisApi.save({
      pregnant_id: aiPatientId.value,
      result_data: res.data,
      analysis_type: 'general',
    })
  } catch (err: any) {
    ElMessage.error(err.message || 'AI 分析失败')
  } finally {
    aiLoading.value = false
  }
}
```

- [ ] **Step 5: 导入 aiAnalysisApi**

在 `NurseDashboard.vue` 顶部添加：
```typescript
import { followUpApi, dashboardApi, aiAnalysisApi } from '@/api/endpoints'
```

---

## Task 6: 修复血压数据字典格式解析

**Files:**
- Modify: `backend/app/services/health_data_service.py`

- [ ] **Step 1: 添加 bp 字典格式处理**

找到 `save_health_metrics` 函数，在处理参数的地方添加：

```python
# 处理 bp 字典格式（如 {"sbp": 120, "dbp": 80}）
if "bp" in data and isinstance(data["bp"], dict):
    bp_dict = data["bp"]
    if "sbp" in bp_dict:
        metrics["sbp"] = bp_dict["sbp"]
    if "dbp" in bp_dict:
        metrics["dbp"] = bp_dict["dbp"]
```

此代码应添加到 `save_health_metrics` 函数中，遍历 `data` 参数时。

---

## Task 7: 孕妇端随访完成后提示

**Files:**
- Modify: `frontend/src/views/pregnant/tools/FollowUpForm.vue:340-365`

- [ ] **Step 1: 增强提交成功的提示**

在 `handleSubmit` 函数中，当状态变为 `completed` 时，添加更明确的提示：

```typescript
if (data.status === 'completed') {
  completed.value = true
  summary.value = data.summary || ''
  healthEducation.value = pending.value.health_education || []
  // 可选：显示成功提示
  ElMessage.success('随访已完成，护士会尽快审核')
} else {
  ElMessage.success('已保存')
  loading.value = true
  await loadPending()
}
```

---

## 验证清单

- [ ] 护士端 NurseDashboard 每 30 秒自动刷新数据
- [ ] 护士端 FollowUpList 每 30 秒自动刷新数据
- [ ] 孕妇提交随访完成后，后端自动评估并生成预警（如数据异常）
- [ ] 护士端刷新后可看到孕妇提交的随访记录
- [ ] AI 分析结果保存到数据库，刷新页面不丢失
- [ ] 血压数据以字典格式提交时可正常解析

---

**Plan complete.** 保存于 `docs/superpowers/plans/2026-05-14-followup-data-sync.md`