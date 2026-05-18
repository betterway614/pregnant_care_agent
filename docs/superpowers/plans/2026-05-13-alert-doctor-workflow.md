# Alert-Doctor Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现"智能体主动分析→护士确认→医生预分析→医生审核"的完整工作流

**Architecture:** 事件驱动 + 人工确认的协作流程。后台定时任务调用小护Agent批量分析患者数据，发现异常生成Alert；护士确认后可创建MedicalOrder请求医生介入；医生打开页面时，智医Agent已预分析并缓存结果；医生审核修改后签署。

**Tech Stack:** FastAPI, SQLAlchemy, Agno Agent, APScheduler (定时任务), SSE (实时推送)

---

## 现有基础

**已有的表结构：**
- `Alert`表：已有 `PENDING/CONFIRMED/DISMISSED` 状态，支持 `RULE_ENGINE/FGR_ALGORITHM/MANUAL` 触发源
- `MedicalOrder`表：已有 `draft/signed/executed` 状态，支持 `alert_id` 关联

**已有的API：**
- `alerts.py`：`GET /api/v1/alerts`, `PUT /{alert_id}/review` (支持confirm/dismiss/escalate)
- `orders.py`：`POST /generate`, `PUT /{order_id}/sign`, `PUT /{order_id}`
- `nurse_ai.py`：`POST /analyze` (已有 `tool_create_alert` 函数)

**已有的Agent：**
- 小护Agent：配备4个工具（患者上下文、趋势分析、规则评估、知识搜索）
- 智医Agent：配备4个工具（同上）

---

## 文件结构

```
backend/
├── app/
│   ├── services/
│   │   ├── alert_analysis_service.py    # NEW: 后台分析服务
│   │   └── pre_analysis_service.py      # NEW: 预分析缓存服务
│   ├── routers/
│   │   ├── alerts.py                    # MODIFY: 增加批量分析触发
│   │   ├── doctor_ai.py                 # MODIFY: 增加预分析结果读取
│   │   └── nurse_ai.py                  # MODIFY: 增加确认后自动创建Order
│   ├── models/
│   │   └── models.py                    # MODIFY: 增加PreAnalysis表
│   ├── schemas/
│   │   └── __init__.py                  # MODIFY: 增加相关Schema
│   └── core/
│       └── scheduler.py                 # NEW: 定时任务调度器
└── tests/
    └── test_alert_workflow.py           # NEW: 工作流测试
```

---

## Task 1: 增加PreAnalysis表（预分析缓存）

**Files:**
- Modify: `backend/app/models/models.py:220-230`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_models.py
def test_pre_analysis_model_exists():
    from backend.app.models import PreAnalysis
    assert PreAnalysis is not None

def test_pre_analysis_fields():
    from backend.app.models import PreAnalysis
    pa = PreAnalysis(
        pregnant_id="test123",
        analysis_type="nurse",
        content={"summary": "测试"},
        status="pending"
    )
    assert pa.pregnant_id == "test123"
    assert pa.analysis_type == "nurse"
    assert pa.status == "pending"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_models.py::test_pre_analysis_model_exists -v`
Expected: FAIL with "cannot import name 'PreAnalysis'"

- [ ] **Step 3: 写最小实现**

```python
# backend/app/models/models.py 在文件末尾添加

class PreAnalysis(Base):
    """预分析缓存表 - 存储AI预分析结果供医生查看"""
    __tablename__ = "pre_analyses"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    alert_id = Column(UUIDColumn(as_uuid=True), ForeignKey("alerts.id"), nullable=True)
    analysis_type = Column(String(32), nullable=False, comment="nurse/doctor")
    content = Column(JSON, nullable=False, comment="分析结果JSON")
    model_used = Column(String(64), nullable=True, comment="使用的模型")
    processing_time_ms = Column(Integer, nullable=True)
    status = Column(String(16), default="pending", comment="pending/viewed/used")
    created_at = Column(DateTime, default=datetime.utcnow)
    viewed_at = Column(DateTime, nullable=True)
    used_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_pre_analysis_pregnant_type', 'pregnant_id', 'analysis_type'),
    )
```

- [ ] **Step 4: 更新__init__.py导出**

```python
# backend/app/models/__init__.py 添加
from .models import PreAnalysis
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_models.py::test_pre_analysis_model_exists -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/models/models.py backend/app/models/__init__.py backend/tests/test_models.py
git commit -m "feat: add PreAnalysis model for caching AI analysis results"
```

---

## Task 2: 创建alert_analysis_service（后台分析服务）

**Files:**
- Create: `backend/app/services/alert_analysis_service.py`
- Test: `backend/tests/test_alert_analysis_service.py`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_alert_analysis_service.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

def test_analyze_single_patient_returns_result():
    from backend.app.services.alert_analysis_service import analyze_single_patient

    mock_db = MagicMock()
    mock_pregnant = MagicMock()
    mock_pregnant.pregnant_id = "test123"
    mock_pregnant.display_name = "测试孕妇"
    mock_pregnant.gestational_age_days = 200
    mock_pregnant.risk_tags = ["GDM"]

    mock_db.query.return_value.filter.return_value.first.return_value = mock_pregnant

    with patch('backend.app.services.alert_analysis_service.SessionLocal', return_value=mock_db):
        result = analyze_single_patient("test123")

    assert result is not None
    assert "pregnant_id" in result
    assert result["pregnant_id"] == "test123"

def test_batch_analyze_returns_list():
    from backend.app.services.alert_analysis_service import batch_analyze_patients

    mock_db = MagicMock()
    mock_db.query.return_value.all.return_value = [
        MagicMock(pregnant_id="p1"),
        MagicMock(pregnant_id="p2"),
    ]

    with patch('backend.app.services.alert_analysis_service.SessionLocal', return_value=mock_db):
        with patch('backend.app.services.alert_analysis_service.analyze_single_patient', return_value={"pregnant_id": "test"}):
            results = batch_analyze_patients()

    assert isinstance(results, list)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_alert_analysis_service.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 写最小实现**

```python
# backend/app/services/alert_analysis_service.py
"""后台分析服务 - 定时调用小护Agent分析患者数据"""
from __future__ import annotations

import asyncio
from datetime import datetime
from loguru import logger

from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, Alert, PreAnalysis
from ..core.agno_medical_agents import create_nurse_agent


def get_all_active_pregnant_ids() -> list[str]:
    """获取所有活跃孕妇ID（最近30天有数据记录）"""
    from datetime import timedelta
    from sqlalchemy import distinct

    db = SessionLocal()
    try:
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        pregnant_ids = db.query(distinct(HealthDataPoint.pregnant_id)).filter(
            HealthDataPoint.recorded_at >= thirty_days_ago
        ).all()
        return [pid[0] for pid in pregnant_ids]
    finally:
        db.close()


def analyze_single_patient(pregnant_id: str) -> dict | None:
    """分析单个孕妇数据，返回分析结果"""
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == pregnant_id
        ).first()
        if not pregnant:
            return None

        # 收集最近健康数据
        recent_data = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pregnant_id
        ).order_by(HealthDataPoint.recorded_at.desc()).limit(10).all()

        # 收集活跃预警
        active_alerts = db.query(Alert).filter(
            Alert.pregnant_id == pregnant_id,
            Alert.status == "PENDING"
        ).all()

        # 构建分析上下文
        context = {
            "pregnant_id": pregnant_id,
            "display_name": pregnant.display_name,
            "gestational_week": pregnant.gestational_age_days // 7 if pregnant.gestational_age_days else 0,
            "risk_tags": pregnant.risk_tags or [],
            "recent_data": [
                {"metric": d.metric_code, "value": d.value, "unit": d.unit}
                for d in recent_data
            ],
            "active_alert_count": len(active_alerts),
        }

        return context
    finally:
        db.close()


async def run_nurse_analysis_for_patient(pregnant_id: str) -> dict | None:
    """调用小护Agent分析单个孕妇"""
    import time

    context = analyze_single_patient(pregnant_id)
    if not context:
        return None

    start_time = time.time()

    try:
        # 创建小护Agent
        agent = create_nurse_agent()

        # 构建分析请求
        prompt = f"""请分析以下孕妇的健康数据：

孕妇ID: {context['pregnant_id']}
姓名: {context['display_name']}
孕周: {context['gestational_week']}周
风险标签: {', '.join(context['risk_tags']) if context['risk_tags'] else '无'}

最近健康数据:
{chr(10).join(f"- {d['metric']}: {d['value']}{d['unit']}" for d in context['recent_data'][:5]) or '暂无数据'}

当前活跃预警数: {context['active_alert_count']}

请提供：
1. summary: 综合概述
2. risk_assessment: 风险评估
3. nursing_suggestions: 护理建议
4. followup_focus: 随访重点"""

        response = await agent.arun(input=prompt, user_id=pregnant_id)
        processing_time = int((time.time() - start_time) * 1000)

        # 解析Agent返回的结构化输出
        content = response.content if hasattr(response, 'content') else str(response)

        # 尝试解析JSON
        import json
        try:
            if isinstance(content, str):
                analysis_result = json.loads(content)
            else:
                analysis_result = content if isinstance(content, dict) else {"summary": str(content)}
        except json.JSONDecodeError:
            analysis_result = {"summary": content}

        return {
            "pregnant_id": pregnant_id,
            "analysis_type": "nurse",
            "content": analysis_result,
            "model_used": "agno_nurse_agent",
            "processing_time_ms": processing_time,
        }

    except Exception as e:
        logger.error(f"小护分析失败 pregnant_id={pregnant_id}: {e}")
        return None


def save_analysis_result(result: dict) -> str | None:
    """保存分析结果到PreAnalysis表"""
    if not result:
        return None

    db = SessionLocal()
    try:
        pre_analysis = PreAnalysis(
            pregnant_id=result["pregnant_id"],
            analysis_type=result["analysis_type"],
            content=result["content"],
            model_used=result.get("model_used"),
            processing_time_ms=result.get("processing_time_ms"),
            status="pending",
        )
        db.add(pre_analysis)
        db.commit()
        db.refresh(pre_analysis)
        return str(pre_analysis.id)
    except Exception as e:
        db.rollback()
        logger.error(f"保存预分析结果失败: {e}")
        return None
    finally:
        db.close()


def batch_analyze_patients(pregnant_ids: list[str] | None = None) -> list[dict]:
    """批量分析孕妇数据"""
    if pregnant_ids is None:
        pregnant_ids = get_all_active_pregnant_ids()

    results = []
    for pid in pregnant_ids:
        try:
            # 同步调用分析
            context = analyze_single_patient(pid)
            if context:
                results.append(context)
        except Exception as e:
            logger.error(f"分析孕妇 {pid} 失败: {e}")
            continue

    return results


async def run_batch_analysis_async() -> dict:
    """异步批量分析（供定时任务调用）"""
    pregnant_ids = get_all_active_pregnant_ids()
    logger.info(f"开始批量分析，共 {len(pregnant_ids)} 位孕妇")

    success_count = 0
    fail_count = 0
    alert_count = 0

    for pid in pregnant_ids:
        try:
            result = await run_nurse_analysis_for_patient(pid)
            if result:
                # 保存分析结果
                analysis_id = save_analysis_result(result)
                if analysis_id:
                    success_count += 1

                    # 检查是否需要创建Alert
                    content = result.get("content", {})
                    risk_text = content.get("risk_assessment", "")
                    if "高风险" in risk_text or "异常" in risk_text or "紧急" in risk_text:
                        _create_alert_from_analysis(pid, content)
                        alert_count += 1
                else:
                    fail_count += 1
            else:
                fail_count += 1
        except Exception as e:
            logger.error(f"处理孕妇 {pid} 失败: {e}")
            fail_count += 1

    summary = {
        "total": len(pregnant_ids),
        "success": success_count,
        "fail": fail_count,
        "alerts_created": alert_count,
        "timestamp": datetime.utcnow().isoformat(),
    }
    logger.info(f"批量分析完成: {summary}")
    return summary


def _create_alert_from_analysis(pregnant_id: str, analysis_content: dict):
    """根据分析结果创建Alert"""
    db = SessionLocal()
    try:
        risk_text = analysis_content.get("risk_assessment", "")
        summary = analysis_content.get("summary", "")

        # 确定Alert级别
        if "紧急" in risk_text or "立即就医" in risk_text:
            level = "RED"
        elif "高风险" in risk_text or "异常" in risk_text:
            level = "ORANGE"
        else:
            level = "YELLOW"

        alert = Alert(
            pregnant_id=pregnant_id,
            trigger_source="AI_ANALYSIS",
            level=level,
            message=f"小护AI分析提示：{risk_text[:200]}",
            details={
                "analysis_summary": summary,
                "risk_assessment": risk_text,
                "nursing_suggestions": analysis_content.get("nursing_suggestions", ""),
            },
            status="PENDING",
        )
        db.add(alert)
        db.commit()
        logger.info(f"创建Alert: pregnant_id={pregnant_id}, level={level}")
    except Exception as e:
        db.rollback()
        logger.error(f"创建Alert失败: {e}")
    finally:
        db.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_alert_analysis_service.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/alert_analysis_service.py backend/tests/test_alert_analysis_service.py
git commit -m "feat: add alert_analysis_service for batch patient analysis"
```

---

## Task 3: 创建定时任务调度器

**Files:**
- Create: `backend/app/core/scheduler.py`
- Modify: `backend/run.py:20-30`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_scheduler.py
def test_scheduler_exists():
    from backend.app.core.scheduler import scheduler
    assert scheduler is not None

def test_scheduler_has_batch_job():
    from backend.app.core.scheduler import scheduler
    jobs = scheduler.get_jobs()
    job_ids = [j.id for j in jobs]
    assert "batch_analysis" in job_ids
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_scheduler.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 写最小实现**

```python
# backend/app/core/scheduler.py
"""定时任务调度器 - 使用APScheduler"""
from __future__ import annotations

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


scheduler = AsyncIOScheduler()


async def batch_analysis_job():
    """定时批量分析任务"""
    from ..services.alert_analysis_service import run_batch_analysis_async

    logger.info("定时任务：开始批量分析")
    try:
        result = await run_batch_analysis_async()
        logger.info(f"定时任务：批量分析完成 {result}")
    except Exception as e:
        logger.error(f"定时任务：批量分析失败 {e}")


def init_scheduler():
    """初始化调度器"""
    # 每天早上8点执行批量分析
    scheduler.add_job(
        batch_analysis_job,
        trigger=CronTrigger(hour=8, minute=0),
        id="batch_analysis",
        name="每日批量分析",
        replace_existing=True,
    )

    # 每天下午14点执行一次（可选）
    scheduler.add_job(
        batch_analysis_job,
        trigger=CronTrigger(hour=14, minute=0),
        id="batch_analysis_afternoon",
        name="下午批量分析",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("定时任务调度器已启动")


def shutdown_scheduler():
    """关闭调度器"""
    scheduler.shutdown()
    logger.info("定时任务调度器已关闭")


def run_manual_analysis():
    """手动触发分析（供API调用）"""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(batch_analysis_job())
    else:
        loop.run_until_complete(batch_analysis_job())
```

- [ ] **Step 4: 修改run.py启动调度器**

```python
# backend/run.py 在main函数中添加
from app.core.scheduler import init_scheduler, shutdown_scheduler

@app.on_event("startup")
async def startup_event():
    init_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    shutdown_scheduler()
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_scheduler.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/scheduler.py backend/run.py backend/tests/test_scheduler.py
git commit -m "feat: add APScheduler for batch analysis scheduling"
```

---

## Task 4: 修改alerts API增加手动触发分析

**Files:**
- Modify: `backend/app/routers/alerts.py:90-100`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_alerts_api.py
def test_manual_trigger_analysis(client):
    response = client.post("/api/v1/alerts/analyze", json={
        "pregnant_ids": ["test123"],
        "async": False
    })
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_alerts_api.py::test_manual_trigger_analysis -v`
Expected: FAIL with "404 Not Found"

- [ ] **Step 3: 添加API端点**

```python
# backend/app/routers/alerts.py 在文件末尾添加

@router.post("/analyze")
async def trigger_analysis(pregnant_ids: list[str] | None = None, async_mode: bool = True):
    """手动触发批量分析"""
    from ..services.alert_analysis_service import (
        batch_analyze_patients,
        run_batch_analysis_async,
        run_nurse_analysis_for_patient,
        save_analysis_result,
        _create_alert_from_analysis,
    )

    if pregnant_ids:
        # 分析指定孕妇
        results = []
        for pid in pregnant_ids:
            result = await run_nurse_analysis_for_patient(pid)
            if result:
                analysis_id = save_analysis_result(result)
                if analysis_id:
                    results.append({"pregnant_id": pid, "analysis_id": analysis_id})
                    # 检查是否需要创建Alert
                    content = result.get("content", {})
                    risk_text = content.get("risk_assessment", "")
                    if "高风险" in risk_text or "异常" in risk_text:
                        _create_alert_from_analysis(pid, content)
        return {"message": f"分析了 {len(results)} 位孕妇", "results": results}
    else:
        # 分析所有活跃孕妇
        if async_mode:
            import asyncio
            asyncio.create_task(run_batch_analysis_async())
            return {"message": "已启动异步批量分析任务"}
        else:
            result = await run_batch_analysis_async()
            return {"message": "批量分析完成", "result": result}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_alerts_api.py::test_manual_trigger_analysis -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/alerts.py backend/tests/test_alerts_api.py
git commit -m "feat: add manual analysis trigger endpoint to alerts API"
```

---

## Task 5: 修改alerts review支持自动创建MedicalOrder

**Files:**
- Modify: `backend/app/routers/alerts.py:70-95`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_alerts_api.py
def test_review_alert_creates_order(client):
    # 假设已有一个PENDING状态的Alert
    response = client.put("/api/v1/alerts/test-alert-id/review", json={
        "action": "escalate",
        "create_order": True,
        "doctor_id": "doctor123"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CONFIRMED"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_alerts_api.py::test_review_alert_creates_order -v`
Expected: FAIL

- [ ] **Step 3: 修改review_alert函数**

```python
# backend/app/routers/alerts.py 修改review_alert函数

@router.put("/{alert_id}/review", response_model=AlertResponse)
def review_alert(alert_id: str, review: AlertReviewRequest,
                  db: Session = Depends(get_db)):
    """审核预警"""
    alert = db.query(Alert).filter(Alert.id == UUID(alert_id)).first()
    if not alert:
        raise HTTPException(404, "预警不存在")

    if review.action == "confirm":
        alert.status = "CONFIRMED"
    elif review.action == "dismiss":
        alert.status = "DISMISSED"
    elif review.action == "escalate":
        alert.status = "CONFIRMED"
        # escalate时自动创建MedicalOrder草稿
        if review.create_order:
            order = MedicalOrder(
                pregnant_id=alert.pregnant_id,
                alert_id=alert.id,
                content=f"基于预警 [{alert.level}] {alert.message[:100]} 的医嘱建议",
                order_type="standard",
                source="AI_RECOMMENDED",
                status="draft",
            )
            db.add(order)

    alert.reviewed_at = datetime.utcnow()
    if review.doctor_id:
        alert.reviewed_by = review.doctor_id
    db.commit()
    db.refresh(alert)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == alert.pregnant_id).first()
    return AlertResponse(
        **{c.name: getattr(alert, c.name) for c in alert.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
        gestational_age_days=pregnant.gestational_age_days if pregnant else None,
    )
```

- [ ] **Step 4: 更新AlertReviewRequest Schema**

```python
# backend/app/schemas/__init__.py 修改AlertReviewRequest

class AlertReviewRequest(BaseModel):
    action: str  # confirm/dismiss/escalate
    doctor_id: str | None = None
    create_order: bool = False  # escalate时是否自动创建Order
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_alerts_api.py::test_review_alert_creates_order -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/alerts.py backend/app/schemas/__init__.py backend/tests/test_alerts_api.py
git commit -m "feat: auto-create MedicalOrder when escalating alert"
```

---

## Task 6: 创建pre_analysis_service（预分析缓存服务）

**Files:**
- Create: `backend/app/services/pre_analysis_service.py`
- Test: `backend/tests/test_pre_analysis_service.py`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_pre_analysis_service.py
def test_get_latest_pre_analysis():
    from backend.app.services.pre_analysis_service import get_latest_pre_analysis

    # Mock数据库
    mock_db = MagicMock()
    mock_analysis = MagicMock()
    mock_analysis.id = "test-id"
    mock_analysis.content = {"summary": "测试分析"}
    mock_analysis.status = "pending"

    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_analysis

    with patch('backend.app.services.pre_analysis_service.SessionLocal', return_value=mock_db):
        result = get_latest_pre_analysis("test123", "doctor")

    assert result is not None
    assert result["id"] == "test-id"

def test_mark_analysis_as_viewed():
    from backend.app.services.pre_analysis_service import mark_analysis_as_viewed

    mock_db = MagicMock()
    mock_analysis = MagicMock()
    mock_analysis.status = "pending"

    mock_db.query.return_value.filter.return_value.first.return_value = mock_analysis

    with patch('backend.app.services.pre_analysis_service.SessionLocal', return_value=mock_db):
        result = mark_analysis_as_viewed("test-id")

    assert result is True
    assert mock_analysis.status == "viewed"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_pre_analysis_service.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 写最小实现**

```python
# backend/app/services/pre_analysis_service.py
"""预分析缓存服务 - 管理AI预分析结果"""
from __future__ import annotations

from datetime import datetime
from loguru import logger

from ..database import SessionLocal
from ..models import PreAnalysis


def get_latest_pre_analysis(pregnant_id: str, analysis_type: str = "doctor") -> dict | None:
    """获取最新的预分析结果"""
    db = SessionLocal()
    try:
        analysis = db.query(PreAnalysis).filter(
            PreAnalysis.pregnant_id == pregnant_id,
            PreAnalysis.analysis_type == analysis_type,
        ).order_by(PreAnalysis.created_at.desc()).first()

        if not analysis:
            return None

        return {
            "id": str(analysis.id),
            "pregnant_id": analysis.pregnant_id,
            "analysis_type": analysis.analysis_type,
            "content": analysis.content,
            "model_used": analysis.model_used,
            "processing_time_ms": analysis.processing_time_ms,
            "status": analysis.status,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
            "viewed_at": analysis.viewed_at.isoformat() if analysis.viewed_at else None,
        }
    finally:
        db.close()


def get_pre_analysis_by_alert(alert_id: str) -> dict | None:
    """根据Alert获取关联的预分析结果"""
    from uuid import UUID

    db = SessionLocal()
    try:
        analysis = db.query(PreAnalysis).filter(
            PreAnalysis.alert_id == UUID(alert_id),
        ).order_by(PreAnalysis.created_at.desc()).first()

        if not analysis:
            return None

        return {
            "id": str(analysis.id),
            "pregnant_id": analysis.pregnant_id,
            "analysis_type": analysis.analysis_type,
            "content": analysis.content,
            "model_used": analysis.model_used,
            "processing_time_ms": analysis.processing_time_ms,
            "status": analysis.status,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        }
    except Exception as e:
        logger.error(f"获取预分析结果失败: {e}")
        return None
    finally:
        db.close()


def mark_analysis_as_viewed(analysis_id: str) -> bool:
    """标记预分析结果为已查看"""
    from uuid import UUID

    db = SessionLocal()
    try:
        analysis = db.query(PreAnalysis).filter(
            PreAnalysis.id == UUID(analysis_id)
        ).first()

        if not analysis:
            return False

        analysis.status = "viewed"
        analysis.viewed_at = datetime.utcnow()
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"标记预分析已查看失败: {e}")
        return False
    finally:
        db.close()


def mark_analysis_as_used(analysis_id: str) -> bool:
    """标记预分析结果为已使用（医生采纳）"""
    from uuid import UUID

    db = SessionLocal()
    try:
        analysis = db.query(PreAnalysis).filter(
            PreAnalysis.id == UUID(analysis_id)
        ).first()

        if not analysis:
            return False

        analysis.status = "used"
        analysis.used_at = datetime.utcnow()
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"标记预分析已使用失败: {e}")
        return False
    finally:
        db.close()


def get_pending_analysis_count() -> int:
    """获取待处理的预分析数量"""
    db = SessionLocal()
    try:
        count = db.query(PreAnalysis).filter(
            PreAnalysis.status == "pending"
        ).count()
        return count
    finally:
        db.close()


def get_analysis_summary() -> dict:
    """获取预分析统计摘要"""
    db = SessionLocal()
    try:
        total = db.query(PreAnalysis).count()
        pending = db.query(PreAnalysis).filter(PreAnalysis.status == "pending").count()
        viewed = db.query(PreAnalysis).filter(PreAnalysis.status == "viewed").count()
        used = db.query(PreAnalysis).filter(PreAnalysis.status == "used").count()

        return {
            "total": total,
            "pending": pending,
            "viewed": viewed,
            "used": used,
        }
    finally:
        db.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_pre_analysis_service.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/pre_analysis_service.py backend/tests/test_pre_analysis_service.py
git commit -m "feat: add pre_analysis_service for caching AI analysis results"
```

---

## Task 7: 修改doctor_ai API集成预分析结果

**Files:**
- Modify: `backend/app/routers/doctor_ai.py`
- Test: `backend/tests/test_doctor_ai_api.py`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_doctor_ai_api.py
def test_get_patient_with_pre_analysis(client):
    response = client.get("/api/v1/doctor/patient/test123")
    assert response.status_code == 200
    data = response.json()
    assert "pre_analysis" in data
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_doctor_ai_api.py::test_get_patient_with_pre_analysis -v`
Expected: FAIL with "404 Not Found"

- [ ] **Step 3: 添加获取患者详情API**

```python
# backend/app/routers/doctor_ai.py 在文件末尾添加

@router.get("/patient/{pregnant_id}")
async def get_patient_with_analysis(pregnant_id: str):
    """获取患者详情（含预分析结果）"""
    from ..database import SessionLocal
    from ..models import Pregnant, HealthDataPoint, Alert, PreAnalysis
    from ..services.pre_analysis_service import get_latest_pre_analysis, mark_analysis_as_viewed

    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == pregnant_id
        ).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        # 获取最近健康数据
        recent_data = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pregnant_id
        ).order_by(HealthDataPoint.recorded_at.desc()).limit(10).all()

        # 获取活跃预警
        active_alerts = db.query(Alert).filter(
            Alert.pregnant_id == pregnant_id,
            Alert.status == "PENDING"
        ).all()

        # 获取预分析结果
        pre_analysis = get_latest_pre_analysis(pregnant_id, "doctor")
        if pre_analysis and pre_analysis["status"] == "pending":
            # 标记为已查看
            mark_analysis_as_viewed(pre_analysis["id"])

        return {
            "pregnant_id": pregnant_id,
            "display_name": pregnant.display_name,
            "nickname": pregnant.nickname,
            "gestational_age_days": pregnant.gestational_age_days,
            "risk_tags": pregnant.risk_tags or [],
            "recent_data": [
                {
                    "metric": d.metric_code,
                    "value": d.value,
                    "unit": d.unit,
                    "recorded_at": d.recorded_at.isoformat() if d.recorded_at else None
                }
                for d in recent_data
            ],
            "active_alerts": [
                {
                    "id": str(a.id),
                    "level": a.level,
                    "message": a.message,
                    "status": a.status,
                    "created_at": a.created_at.isoformat() if a.created_at else None
                }
                for a in active_alerts
            ],
            "pre_analysis": pre_analysis,
        }
    finally:
        db.close()


@router.post("/analyze-with-pre-analysis")
async def analyze_with_pre_analysis(pregnant_id: str):
    """医生分析（基于预分析结果）"""
    from ..services.pre_analysis_service import get_latest_pre_analysis, mark_analysis_as_used

    pre_analysis = get_latest_pre_analysis(pregnant_id, "doctor")

    if not pre_analysis:
        # 没有预分析结果，实时分析
        from ..core.agno_medical_agents import create_doctor_agent
        agent = create_doctor_agent()

        prompt = f"请分析孕妇 {pregnant_id} 的健康状况"
        response = await agent.arun(input=prompt, user_id=pregnant_id)

        return {
            "source": "realtime",
            "analysis": response.content if hasattr(response, 'content') else str(response)
        }

    # 使用预分析结果
    mark_analysis_as_used(pre_analysis["id"])

    return {
        "source": "pre_analysis",
        "analysis_id": pre_analysis["id"],
        "analysis": pre_analysis["content"],
        "model_used": pre_analysis["model_used"],
        "created_at": pre_analysis["created_at"],
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_doctor_ai_api.py::test_get_patient_with_pre_analysis -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/doctor_ai.py backend/tests/test_doctor_ai_api.py
git commit -m "feat: integrate pre-analysis results into doctor AI API"
```

---

## Task 8: 修改nurse_ai API支持确认后自动创建Order

**Files:**
- Modify: `backend/app/routers/nurse_ai.py:500-530`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_nurse_ai_api.py
def test_confirm_analysis_creates_order(client):
    response = client.post("/api/v1/nurse/confirm-analysis", json={
        "pregnant_id": "test123",
        "analysis_id": "test-analysis-id",
        "create_order": True,
        "order_content": "建议住院观察"
    })
    assert response.status_code == 200
    data = response.json()
    assert "order_id" in data
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_nurse_ai_api.py::test_confirm_analysis_creates_order -v`
Expected: FAIL with "404 Not Found"

- [ ] **Step 3: 添加确认分析API**

```python
# backend/app/routers/nurse_ai.py 在文件末尾添加

@router.post("/confirm-analysis")
async def confirm_analysis(req: dict):
    """护士确认分析结果，可选择创建MedicalOrder"""
    from ..services.pre_analysis_service import mark_analysis_as_used
    from ..models import MedicalOrder, PreAnalysis
    from uuid import UUID

    pregnant_id = req.get("pregnant_id")
    analysis_id = req.get("analysis_id")
    create_order = req.get("create_order", False)
    order_content = req.get("order_content", "")

    if not pregnant_id or not analysis_id:
        raise HTTPException(400, "pregnant_id and analysis_id are required")

    db = SessionLocal()
    try:
        # 标记分析结果为已使用
        mark_analysis_as_used(analysis_id)

        # 获取分析结果
        analysis = db.query(PreAnalysis).filter(
            PreAnalysis.id == UUID(analysis_id)
        ).first()

        if not analysis:
            raise HTTPException(404, "分析结果不存在")

        order_id = None
        if create_order:
            # 创建MedicalOrder草稿
            content = order_content or f"基于小护AI分析的医嘱建议：{analysis.content.get('risk_assessment', '')[:200]}"

            order = MedicalOrder(
                pregnant_id=pregnant_id,
                alert_id=analysis.alert_id,
                content=content,
                order_type="standard",
                source="AI_RECOMMENDED",
                status="draft",
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            order_id = str(order.id)

        return {
            "success": True,
            "analysis_id": analysis_id,
            "order_id": order_id,
            "message": "分析结果已确认" + ("，已创建医嘱草稿" if create_order else "")
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"确认分析失败: {str(e)}")
    finally:
        db.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_nurse_ai_api.py::test_confirm_analysis_creates_order -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/nurse_ai.py backend/tests/test_nurse_ai_api.py
git commit -m "feat: add nurse confirm analysis endpoint with auto-create order"
```

---

## Task 9: 创建前端Alert管理页面

**Files:**
- Create: `frontend/src/views/nurse/AlertManagement.vue`
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: 写失败的测试**

```typescript
// frontend/src/views/__tests__/AlertManagement.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AlertManagement from '../nurse/AlertManagement.vue'

describe('AlertManagement', () => {
  it('renders alert list', () => {
    const wrapper = mount(AlertManagement)
    expect(wrapper.find('.alert-list').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm run test -- AlertManagement`
Expected: FAIL

- [ ] **Step 3: 创建AlertManagement组件**

```vue
<!-- frontend/src/views/nurse/AlertManagement.vue -->
<template>
  <div class="alert-management">
    <div class="page-header">
      <h2>预警管理</h2>
      <div class="actions">
        <button @click="triggerAnalysis" class="btn-primary">
          触发分析
        </button>
      </div>
    </div>

    <div class="filters">
      <select v-model="statusFilter">
        <option value="">全部状态</option>
        <option value="PENDING">待处理</option>
        <option value="CONFIRMED">已确认</option>
        <option value="DISMISSED">已忽略</option>
      </select>
      <select v-model="levelFilter">
        <option value="">全部级别</option>
        <option value="RED">红色</option>
        <option value="ORANGE">橙色</option>
        <option value="YELLOW">黄色</option>
      </select>
    </div>

    <div class="alert-list">
      <div v-for="alert in filteredAlerts" :key="alert.id" class="alert-item" :class="alert.level.toLowerCase()">
        <div class="alert-header">
          <span class="level-badge">{{ alert.level }}</span>
          <span class="patient-name">{{ alert.patient_name }}</span>
          <span class="time">{{ formatTime(alert.created_at) }}</span>
        </div>
        <div class="alert-message">{{ alert.message }}</div>
        <div class="alert-actions" v-if="alert.status === 'PENDING'">
          <button @click="confirmAlert(alert)" class="btn-success">确认</button>
          <button @click="dismissAlert(alert)" class="btn-secondary">忽略</button>
          <button @click="escalateAlert(alert)" class="btn-warning">升级</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

interface Alert {
  id: string
  pregnant_id: string
  patient_name: string
  level: string
  message: string
  status: string
  created_at: string
}

const alerts = ref<Alert[]>([])
const statusFilter = ref('')
const levelFilter = ref('')

const filteredAlerts = computed(() => {
  return alerts.value.filter(a => {
    if (statusFilter.value && a.status !== statusFilter.value) return false
    if (levelFilter.value && a.level !== levelFilter.value) return false
    return true
  })
})

const fetchAlerts = async () => {
  try {
    const response = await axios.get('/api/v1/alerts')
    alerts.value = response.data
  } catch (error) {
    console.error('获取预警列表失败:', error)
  }
}

const confirmAlert = async (alert: Alert) => {
  try {
    await axios.put(`/api/v1/alerts/${alert.id}/review`, {
      action: 'confirm'
    })
    await fetchAlerts()
  } catch (error) {
    console.error('确认预警失败:', error)
  }
}

const dismissAlert = async (alert: Alert) => {
  try {
    await axios.put(`/api/v1/alerts/${alert.id}/review`, {
      action: 'dismiss'
    })
    await fetchAlerts()
  } catch (error) {
    console.error('忽略预警失败:', error)
  }
}

const escalateAlert = async (alert: Alert) => {
  try {
    await axios.put(`/api/v1/alerts/${alert.id}/review`, {
      action: 'escalate',
      create_order: true
    })
    await fetchAlerts()
  } catch (error) {
    console.error('升级预警失败:', error)
  }
}

const triggerAnalysis = async () => {
  try {
    await axios.post('/api/v1/alerts/analyze')
    alert('分析任务已启动')
  } catch (error) {
    console.error('触发分析失败:', error)
  }
}

const formatTime = (time: string) => {
  if (!time) return ''
  return new Date(time).toLocaleString('zh-CN')
}

onMounted(() => {
  fetchAlerts()
})
</script>

<style scoped>
.alert-management {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.alert-item {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 10px;
}

.alert-item.red {
  border-left: 4px solid #ff4444;
}

.alert-item.orange {
  border-left: 4px solid #ff8800;
}

.alert-item.yellow {
  border-left: 4px solid #ffcc00;
}

.alert-header {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.level-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
}

.alert-actions {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.btn-primary {
  background: #007bff;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.btn-success {
  background: #28a745;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}

.btn-secondary {
  background: #6c757d;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}

.btn-warning {
  background: #ffc107;
  color: #212529;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}
</style>
```

- [ ] **Step 4: 添加路由**

```typescript
// frontend/src/router/index.ts 在护士路由下添加
{
  path: 'alerts',
  name: 'AlertManagement',
  component: () => import('../views/nurse/AlertManagement.vue'),
  meta: { title: '预警管理' }
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd frontend && npm run test -- AlertManagement`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/nurse/AlertManagement.vue frontend/src/router/index.ts frontend/src/views/__tests__/AlertManagement.spec.ts
git commit -m "feat: add AlertManagement page for nurse"
```

---

## Task 10: 创建前端医生患者详情页面（含预分析）

**Files:**
- Create: `frontend/src/views/doctor/PatientDetail.vue`
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: 写失败的测试**

```typescript
// frontend/src/views/__tests__/PatientDetail.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PatientDetail from '../doctor/PatientDetail.vue'

describe('PatientDetail', () => {
  it('renders pre-analysis section', () => {
    const wrapper = mount(PatientDetail, {
      props: { pregnantId: 'test123' }
    })
    expect(wrapper.find('.pre-analysis').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm run test -- PatientDetail`
Expected: FAIL

- [ ] **Step 3: 创建PatientDetail组件**

```vue
<!-- frontend/src/views/doctor/PatientDetail.vue -->
<template>
  <div class="patient-detail">
    <div class="page-header">
      <h2>{{ patient.display_name }} - 患者详情</h2>
      <span class="gestational-week">孕{{ patient.gestational_age_days ? Math.floor(patient.gestational_age_days / 7) : '?' }}周</span>
    </div>

    <div class="risk-tags" v-if="patient.risk_tags?.length">
      <span v-for="tag in patient.risk_tags" :key="tag" class="tag">{{ tag }}</span>
    </div>

    <!-- 预分析结果 -->
    <div class="pre-analysis" v-if="patient.pre_analysis">
      <div class="section-header">
        <h3>AI预分析结果</h3>
        <span class="model-info">{{ patient.pre_analysis.model_used }}</span>
        <span class="time-info">{{ formatTime(patient.pre_analysis.created_at) }}</span>
      </div>
      <div class="analysis-content">
        <div class="analysis-item" v-if="patient.pre_analysis.content.summary">
          <label>综合概述</label>
          <p>{{ patient.pre_analysis.content.summary }}</p>
        </div>
        <div class="analysis-item" v-if="patient.pre_analysis.content.risk_assessment">
          <label>风险评估</label>
          <p>{{ patient.pre_analysis.content.risk_assessment }}</p>
        </div>
        <div class="analysis-item" v-if="patient.pre_analysis.content.nursing_suggestions">
          <label>护理建议</label>
          <p>{{ patient.pre_analysis.content.nursing_suggestions }}</p>
        </div>
      </div>
    </div>

    <!-- 最近健康数据 -->
    <div class="recent-data">
      <h3>最近健康数据</h3>
      <div class="data-grid">
        <div v-for="item in patient.recent_data" :key="item.metric" class="data-item">
          <span class="metric">{{ item.metric }}</span>
          <span class="value">{{ item.value }} {{ item.unit }}</span>
        </div>
      </div>
    </div>

    <!-- 活跃预警 -->
    <div class="active-alerts" v-if="patient.active_alerts?.length">
      <h3>活跃预警</h3>
      <div v-for="alert in patient.active_alerts" :key="alert.id" class="alert-item" :class="alert.level.toLowerCase()">
        <span class="level">{{ alert.level }}</span>
        <span class="message">{{ alert.message }}</span>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="actions">
      <button @click="analyzeRealtime" class="btn-secondary">
        实时分析
      </button>
      <button @click="createOrder" class="btn-primary" :disabled="!patient.pre_analysis">
        基于预分析创建医嘱
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

interface Patient {
  pregnant_id: string
  display_name: string
  nickname?: string
  gestational_age_days?: number
  risk_tags?: string[]
  recent_data?: Array<{
    metric: string
    value: number
    unit: string
    recorded_at?: string
  }>
  active_alerts?: Array<{
    id: string
    level: string
    message: string
    status: string
    created_at?: string
  }>
  pre_analysis?: {
    id: string
    content: {
      summary?: string
      risk_assessment?: string
      nursing_suggestions?: string
      followup_focus?: string[]
    }
    model_used?: string
    created_at?: string
  }
}

const props = defineProps<{
  pregnantId: string
}>()

const patient = ref<Partial<Patient>>({})

const fetchPatient = async () => {
  try {
    const response = await axios.get(`/api/v1/doctor/patient/${props.pregnantId}`)
    patient.value = response.data
  } catch (error) {
    console.error('获取患者详情失败:', error)
  }
}

const analyzeRealtime = async () => {
  try {
    const response = await axios.post('/api/v1/doctor/analyze-with-pre-analysis', {
      pregnant_id: props.pregnantId
    })
    // 更新预分析结果
    if (response.data.source === 'pre_analysis') {
      patient.value.pre_analysis = {
        id: response.data.analysis_id,
        content: response.data.analysis,
        model_used: response.data.model_used,
        created_at: response.data.created_at,
      }
    }
  } catch (error) {
    console.error('实时分析失败:', error)
  }
}

const createOrder = async () => {
  if (!patient.value.pre_analysis) return

  try {
    const response = await axios.post('/api/v1/orders/generate', {
      pregnant_id: props.pregnantId,
      risk_level: 'medium',
      gestational_weeks: Math.floor((patient.value.gestational_age_days || 0) / 7),
      alert_id: null,
    })
    alert('医嘱草稿已创建')
  } catch (error) {
    console.error('创建医嘱失败:', error)
  }
}

const formatTime = (time?: string) => {
  if (!time) return ''
  return new Date(time).toLocaleString('zh-CN')
}

onMounted(() => {
  fetchPatient()
})
</script>

<style scoped>
.patient-detail {
  padding: 20px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 20px;
}

.gestational-week {
  background: #e3f2fd;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 14px;
}

.risk-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.tag {
  background: #fff3e0;
  color: #e65100;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
}

.pre-analysis {
  background: #f5f5f5;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
}

.model-info {
  background: #e8f5e9;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.time-info {
  color: #666;
  font-size: 12px;
}

.analysis-content {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.analysis-item label {
  font-weight: bold;
  display: block;
  margin-bottom: 5px;
}

.data-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}

.data-item {
  background: #f9f9f9;
  padding: 10px;
  border-radius: 4px;
}

.metric {
  display: block;
  font-size: 12px;
  color: #666;
}

.value {
  font-size: 18px;
  font-weight: bold;
}

.alert-item {
  padding: 10px;
  border-radius: 4px;
  margin-bottom: 10px;
}

.alert-item.red {
  background: #ffebee;
}

.alert-item.orange {
  background: #fff3e0;
}

.alert-item.yellow {
  background: #fffde7;
}

.actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.btn-primary {
  background: #007bff;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
}

.btn-secondary {
  background: #6c757d;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}
</style>
```

- [ ] **Step 4: 添加路由**

```typescript
// frontend/src/router/index.ts 在医生路由下添加
{
  path: 'patient/:pregnantId',
  name: 'PatientDetail',
  component: () => import('../views/doctor/PatientDetail.vue'),
  meta: { title: '患者详情' },
  props: true
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd frontend && npm run test -- PatientDetail`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/doctor/PatientDetail.vue frontend/src/router/index.ts frontend/src/views/__tests__/PatientDetail.spec.ts
git commit -m "feat: add PatientDetail page with pre-analysis for doctor"
```

---

## 执行顺序建议

1. **Task 1-2**: 基础模型和服务（PreAnalysis表 + alert_analysis_service）
2. **Task 3-4**: 定时任务和API端点
3. **Task 5-6**: Alert升级逻辑和预分析缓存
4. **Task 7-8**: 医生和护士API集成
5. **Task 9-10**: 前端页面

每个Task完成后，运行相关测试确认通过后再继续下一个。
