# AI-Care Mock 数据补全与业务逻辑打通 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补全种子数据覆盖关键场景，打通3条核心业务链路，修复前后端联调gap，为小Hu和Dr.智补充工具，实现混合LLM模式，确保三角色联动走查全流程可跑通。

**Architecture:** 在现有 FastAPI + Vue3 架构上，通过增强 seed_data.py 补全数据，在 followup_tools.py 中串联规则引擎，在 orders.py 和 chat.py 中打通医嘱→孕妇可见链路，为 nurse_ai.py 和 doctor_ai.py 新增工具函数，最后实现混合 LLM 模式配置。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Vue 3, TypeScript, Element Plus, Pinia

---

## Task 1: 补全种子数据

**目标:** 为 seed_data.py 新增 7 个种子函数，覆盖随访记录、医嘱、对话历史、心理健康、胎动、反馈和缺失的健康指标。

**Files:**
- Modify: `backend/app/scripts/seed_data.py`

### Step 1.1: 在 seed_data.py 顶部补充 import

在现有 import 行后新增需要的模型：

```python
# 文件: backend/app/scripts/seed_data.py
# 在现有 import 行后面追加：
from ..models import (
    Pregnant, HealthDataPoint, ScheduleNode, FollowUpRecord,
    FgrAssessment, Alert, MedicalOrder, ConversationMessage,
    MentalHealthScreening, FetalMovementSession, Feedback,
)
```

### Step 1.2: 实现 seed_followup_records 函数

```python
def seed_followup_records(db):
    """为每个孕妇生成2-3条随访记录"""
    pregnant_list = db.query(Pregnant).all()
    count = 0
    statuses = ["draft", "confirmed", "archived"]
    templates = ["standard", "high_risk", "postpartum"]
    health_edu_options = [
        ["按时产检，关注血压变化", "保持均衡饮食", "每日数胎动"],
        ["控制碳水摄入，监测血糖", "适当运动，饭后散步30分钟", "定期复查OGTT"],
        ["每日早晚监测血压", "低盐饮食，避免腌制食品", "注意休息，避免劳累"],
    ]

    for p in pregnant_list:
        gw = (p.gestational_age_days or 168) // 7
        risk_tags = p.risk_tags or []
        record_count = random.randint(2, 3)

        for i in range(record_count):
            past_weeks = random.randint(2, 8)
            record_gw = max(12, gw - past_weeks)
            record_date = datetime.now() - timedelta(days=past_weeks * 7)

            # 根据风险标签选择模板
            if "FGR高危" in risk_tags:
                template_key = "high_risk"
                edu = health_edu_options[1]
            elif "高血压" in risk_tags:
                template_key = "high_risk"
                edu = health_edu_options[2]
            else:
                template_key = "standard"
                edu = health_edu_options[0]

            # 构造自报数据
            self_reported = {
                "feeling": random.choice(["挺好的", "有点累", "没什么不舒服", "腰有点酸"]),
                "weight": f"{55 + (record_gw - 12) * 0.3 + random.uniform(-2, 2):.1f}",
                "bp": f"{random.randint(105, 135)}/{random.randint(65, 85)}",
                "fetal_movement": str(random.randint(3, 8)),
                "_template": template_key,
            }

            status = statuses[i % len(statuses)]
            summary = f"孕{record_gw}周随访：孕妇自述{self_reported['feeling']}，体重{self_reported['weight']}kg，血压{self_reported['bp']}mmHg。" if status != "draft" else None

            record = FollowUpRecord(
                pregnant_id=p.pregnant_id,
                gestational_week=str(record_gw),
                follow_up_date=record_date,
                self_reported_data=self_reported,
                chief_complaint=self_reported["feeling"],
                health_education=edu,
                status=status,
                summary=summary,
                created_at=record_date,
            )
            db.add(record)
            count += 1
    print(f"   [OK] 生成 {count} 条随访记录")
```

### Step 1.3: 实现 seed_medical_orders 函数

```python
def seed_medical_orders(db):
    """为有预警的孕妇生成医嘱"""
    pregnant_list = db.query(Pregnant).all()
    count = 0
    order_templates = {
        "FGR高危": [
            "建议每2周行胎儿B超监测（AC、HC、FL、EFW、脐动脉血流S/D比值）\n每日自数胎动，每小时不少于3-5次\n加强营养，增加优质蛋白摄入",
            "FGR监测：每周胎心监护1次，每2周B超评估胎儿生长\n左侧卧位休息，每日吸氧30分钟\n如有胎动减少立即就诊",
        ],
        "GDM": [
            "每日监测空腹及三餐后2小时血糖，目标空腹<5.3mmol/L，餐后2h<6.7mmol/L\n医学营养治疗，控制碳水化合物摄入\n适当运动，饭后散步30分钟",
        ],
        "高血压": [
            "每日早晚各测血压一次，目标<140/90mmHg\n低盐饮食，每日食盐<6g\n查尿蛋白（尿常规+24小时尿蛋白定量），监测子痫前期",
        ],
        "正常": [
            "常规产检，下次产检时间：孕{gw}周\n保持均衡饮食，适当运动\n每日数胎动，如有异常及时就诊",
        ],
    }

    for p in pregnant_list:
        risk_tags = p.risk_tags or []
        gw = (p.gestational_age_days or 168) // 7
        order_count = random.randint(1, 2)

        # 确定模板
        template_key = "正常"
        for tag in ["FGR高危", "GDM", "高血压"]:
            if tag in risk_tags:
                template_key = tag
                break

        for i in range(order_count):
            content = random.choice(order_templates[template_key]).format(gw=min(gw + 2, 40))
            source = random.choice(["AI_RECOMMENDED", "DOCTOR_WRITTEN"])
            status = random.choice(["draft", "signed", "signed"])

            order = MedicalOrder(
                pregnant_id=p.pregnant_id,
                content=content,
                order_type="standard",
                source=source,
                status=status,
                created_by="doctor_001" if source == "DOCTOR_WRITTEN" else None,
                signed_at=datetime.now() - timedelta(days=random.randint(0, 7)) if status == "signed" else None,
                created_at=datetime.now() - timedelta(days=random.randint(0, 14)),
            )
            db.add(order)
            count += 1
    print(f"   [OK] 生成 {count} 条医嘱")
```

### Step 1.4: 实现 seed_conversation_messages 函数

```python
def seed_conversation_messages(db):
    """为每个孕妇生成对话历史"""
    pregnant_list = db.query(Pregnant).all()
    count = 0

    sample_dialogues = [
        [
            ("user", "你好，小安！"),
            ("assistant", "您好呀！我是小安，您的孕期智能助手。今天感觉怎么样？有什么我可以帮您的吗？🌸"),
        ],
        [
            ("user", "今天体重72kg，血压125/82"),
            ("assistant", "已记录您的体重：72kg，血压：125/82mmHg。数据已同步至您的健康档案。请继续保持定期监测。"),
        ],
        [
            ("user", "最近晚上总是睡不好，翻来覆去的"),
            ("assistant", "我理解您现在的感受。孕期睡眠问题是很常见的，让我给您一些建议：\n\n1. 睡前避免使用手机\n2. 尝试左侧卧位，用孕妇枕支撑\n3. 睡前喝一杯温牛奶\n4. 保持规律的作息时间\n\n如果持续失眠，建议咨询医生。"),
        ],
        [
            ("user", "宝宝今天动得好像比较少"),
            ("assistant", "胎动监测非常重要！请每天固定时间（建议饭后1小时）数胎动。正常每小时3-5次。\n\n如果发现胎动明显减少或消失，请立即就医。您可以现在试着数一下胎动，记录1小时内宝宝动了几次。"),
        ],
        [
            ("user", "我有点紧张，下周要做大排畸了"),
            ("assistant", "理解您的心情~大排畸是孕中期非常重要的检查，可以帮助了解宝宝的发育情况。放松心情，正常饮食就好。检查前可以适当活动一下，让宝宝活跃一些，这样B超看得更清楚。祝一切顺利！💪"),
        ],
    ]

    for p in pregnant_list:
        sid = f"SESS_{p.pregnant_id[:8]}"
        dialogue = random.choice(sample_dialogues)
        base_time = datetime.now() - timedelta(days=random.randint(1, 30))

        for idx, (role, content) in enumerate(dialogue):
            msg = ConversationMessage(
                session_id=sid,
                pregnant_id=p.pregnant_id,
                role=role,
                content=content,
                created_at=base_time + timedelta(minutes=idx * 2),
            )
            db.add(msg)
            count += 1
    print(f"   [OK] 生成 {count} 条对话消息")
```

### Step 1.5: 实现 seed_mental_health_screenings 函数

```python
def seed_mental_health_screenings(db):
    """为5-8个孕妇生成EPDS记录"""
    pregnant_list = db.query(Pregnant).all()
    selected = random.sample(pregnant_list, min(7, len(pregnant_list)))
    count = 0

    for p in selected:
        # 生成10题答案（每题0-3分）
        answers = [random.randint(0, 2) for _ in range(10)]
        # 有一道反向计分题（第9题，index=8）
        answers[8] = 3 - answers[8]
        total_score = sum(answers)

        if total_score <= 9:
            risk_level = "low"
        elif total_score <= 12:
            risk_level = "moderate"
        elif total_score <= 19:
            risk_level = "high"
        else:
            risk_level = "severe"

        screening = MentalHealthScreening(
            pregnant_id=p.pregnant_id,
            screening_type="EPDS",
            answers=answers,
            total_score=total_score,
            risk_level=risk_level,
            created_at=datetime.now() - timedelta(days=random.randint(1, 30)),
        )
        db.add(screening)
        count += 1
    print(f"   [OK] 生成 {count} 条心理健康筛查记录")
```

### Step 1.6: 实现 seed_fetal_movement_sessions 函数

```python
def seed_fetal_movement_sessions(db):
    """为5-8个孕妇生成胎动记录"""
    pregnant_list = db.query(Pregnant).all()
    selected = random.sample(pregnant_list, min(7, len(pregnant_list)))
    count = 0

    for p in selected:
        session_count = random.randint(2, 3)
        for _ in range(session_count):
            start = datetime.now() - timedelta(days=random.randint(1, 14), hours=random.randint(8, 20))
            duration = random.randint(30, 120)
            end = start + timedelta(minutes=duration)
            total = random.randint(10, 40)

            # 生成每次胎动时刻
            kick_times = sorted([
                (start + timedelta(seconds=random.randint(0, duration * 60))).isoformat()
                for _ in range(total)
            ])

            session = FetalMovementSession(
                pregnant_id=p.pregnant_id,
                start_time=start,
                end_time=end,
                duration_minutes=duration,
                total_count=total,
                kick_times=kick_times,
            )
            db.add(session)
            count += 1
    print(f"   [OK] 生成 {count} 条胎动记录")
```

### Step 1.7: 实现 seed_feedback 函数

```python
def seed_feedback(db):
    """为部分对话消息生成反馈"""
    messages = db.query(ConversationMessage).filter(
        ConversationMessage.role == "assistant"
    ).limit(30).all()
    count = 0
    for msg in random.sample(messages, min(15, len(messages))):
        feedback = Feedback(
            pregnant_id=msg.pregnant_id,
            message_id=str(msg.id),
            rating=random.choice(["thumbs_up", "thumbs_up", "thumbs_down"]),
            session_id=msg.session_id,
            created_at=msg.created_at + timedelta(minutes=random.randint(1, 30)),
        )
        db.add(feedback)
        count += 1
    print(f"   [OK] 生成 {count} 条反馈记录")
```

### Step 1.8: 实现 supplement_health_data 函数

```python
def supplement_health_data(db):
    """补充 blood_sugar / emotion_score / sleep_hours"""
    pregnant_list = db.query(Pregnant).all()
    count = 0
    for p in pregnant_list:
        risk_tags = p.risk_tags or []
        gw = (p.gestational_age_days or 168) // 7

        for days_ago in range(0, 56, 2):
            record_date = datetime.now() - timedelta(days=days_ago)

            # 血糖：GDM患者偏高
            if "GDM" in risk_tags:
                fasting = round(random.uniform(4.5, 6.5), 1)
                postprandial = round(random.uniform(6.0, 9.0), 1)
            else:
                fasting = round(random.uniform(3.8, 5.2), 1)
                postprandial = round(random.uniform(5.0, 7.0), 1)

            db.add(HealthDataPoint(
                pregnant_id=p.pregnant_id, metric_code="blood_sugar",
                value=fasting, unit="mmol/L", recorded_at=record_date, source="AUTO_FOLLOWUP",
            ))

            # 情绪评分
            if "高血压" in risk_tags:
                emotion = round(random.uniform(5, 9), 1)
            else:
                emotion = round(random.uniform(2, 6), 1)
            db.add(HealthDataPoint(
                pregnant_id=p.pregnant_id, metric_code="emotion_score",
                value=emotion, unit="分", recorded_at=record_date, source="AUTO_FOLLOWUP",
            ))

            # 睡眠时长
            sleep = round(random.uniform(5, 9), 1)
            db.add(HealthDataPoint(
                pregnant_id=p.pregnant_id, metric_code="sleep_hours",
                value=sleep, unit="小时", recorded_at=record_date, source="AUTO_FOLLOWUP",
            ))
            count += 3
    print(f"   [OK] 补充 {count} 条健康数据（血糖/情绪/睡眠）")
```

### Step 1.9: 更新 seed_all 函数

在 `seed_all()` 中调用新增的函数：

```python
def seed_all():
    """注入全部Mock数据"""
    db = SessionLocal()
    try:
        _seed_patients(db)
        _seed_health_data(db)
        supplement_health_data(db)
        _seed_schedules(db)
        _seed_fgr_assessments(db)
        _seed_alerts(db)
        seed_followup_records(db)
        seed_medical_orders(db)
        seed_conversation_messages(db)
        seed_mental_health_screenings(db)
        seed_fetal_movement_sessions(db)
        seed_feedback(db)
        db.commit()
        print("[OK] Mock数据注入完成")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
```

### Step 1.10: 测试种子数据

```bash
cd backend && python -c "from app.scripts.seed_data import seed_all; seed_all()"
```

验证：
- 数据库中应有 FollowUpRecord、MedicalOrder、ConversationMessage、MentalHealthScreening、FetalMovementSession、Feedback 记录
- HealthDataPoint 中应有 blood_sugar、emotion_score、sleep_hours 指标

### Step 1.11: Commit

```bash
git add backend/app/scripts/seed_data.py
git commit -m "feat: 补全种子数据覆盖随访/医嘱/对话/心理健康/胎动/反馈/血糖情绪睡眠"
```

---

## Task 2: 打通链路1 — 随访→规则引擎→预警

**目标:** 在 followup_tools.record_answer 中，保存 HealthDataPoint 后自动触发规则引擎评估并创建 Alert。

**Files:**
- Modify: `backend/app/core/followup_tools.py`

### Step 2.1: 在 followup_tools.py 顶部补充 import

```python
# 文件: backend/app/core/followup_tools.py
# 在现有 import 后追加：
from ..models import Alert
from .rule_engine import rule_engine
```

### Step 2.2: 在 execute_record_answer 中新增规则引擎调用

在 `execute_record_answer` 函数中，`db.commit()` 之后、计算剩余问题之前，新增规则引擎评估：

```python
    # 在 db.commit() 之后，计算剩余问题之前新增：
    # 触发规则引擎评估
    _evaluate_rules_after_answer(record.pregnant_id, db)
```

### Step 2.3: 实现 _evaluate_rules_after_answer 辅助函数

```python
def _evaluate_rules_after_answer(pregnant_id: str, db: Session):
    """随访回答后触发规则引擎评估，自动创建预警"""
    from sqlalchemy import desc, func
    from datetime import timedelta

    # 收集该孕妇最近的健康数据上下文
    recent_points = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.recorded_at >= datetime.utcnow() - timedelta(days=7),
    ).order_by(desc(HealthDataPoint.recorded_at)).all()

    if not recent_points:
        return

    # 构建规则引擎上下文
    context = {}
    metric_values = {}
    for point in recent_points:
        if point.metric_code not in metric_values:
            metric_values[point.metric_code] = []
        metric_values[point.metric_code].append(point.value)

    # 取最新值
    for metric, values in metric_values.items():
        if metric in ("sbp", "dbp", "weight", "fetal_movement", "blood_sugar",
                       "emotion_score", "sleep_hours"):
            context[metric] = values[0]

    # 获取孕周
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if pregnant and pregnant.gestational_age_days:
        context["gest_week"] = pregnant.gestational_age_days // 7

    # 计算胎动平均值
    fm_values = metric_values.get("fetal_movement", [])
    if len(fm_values) > 1:
        context["fetal_movement_avg"] = sum(fm_values[1:]) / len(fm_values[1:])

    # 评估规则
    hits = rule_engine.evaluate_all(context)
    for hit in hits:
        alert = Alert(
            pregnant_id=pregnant_id,
            trigger_source="RULE_ENGINE",
            rule_id=hit["rule_id"],
            level=hit["level"],
            message=hit["message"],
            details=hit,
            status="PENDING",
        )
        db.add(alert)
    if hits:
        db.commit()
```

### Step 2.4: 测试

启动后端，通过随访对话提交高血压数据（如"血压158/95"），验证 alerts 表中自动生成了 PENDING 状态的预警记录。

### Step 2.5: Commit

```bash
git add backend/app/core/followup_tools.py
git commit -m "feat: 随访回答后自动触发规则引擎评估并创建预警"
```

---

## Task 3: 打通链路3 — 医嘱→孕妇可见

**目标:** 孕妇端能看到医嘱通知，包含后端新端点、proactive greeting 增强、前端通知卡片。

### Step 3.1: 后端 — 新增按 pregnant_id 查询医嘱的端点

**Files:**
- Modify: `backend/app/routers/orders.py`

在 orders.py 中 `get_orders` 端点之后新增：

```python
@router.get("/pregnant/{pregnant_id}", response_model=list[OrderResponse])
def get_pregnant_orders(pregnant_id: str, db: Session = Depends(get_db)):
    """获取孕妇的医嘱列表（用于孕妇端展示）"""
    orders = db.query(MedicalOrder).filter(
        MedicalOrder.pregnant_id == pregnant_id,
    ).order_by(MedicalOrder.created_at.desc()).limit(10).all()

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    return [
        OrderResponse(
            **{c.name: getattr(o, c.name) for c in o.__table__.columns},
            patient_name=pregnant.display_name if pregnant else "未知",
        )
        for o in orders
    ]
```

### Step 3.2: 后端 — proactive greeting 新增医嘱检查

**Files:**
- Modify: `backend/app/routers/chat.py`

在 `get_proactive_greeting` 端点中，在返回 `ProactiveGreeting` 之前新增医嘱检查：

```python
        # 在 return ProactiveGreeting(...) 之前新增：
        from ..models import MedicalOrder
        pending_orders = db.query(MedicalOrder).filter(
            MedicalOrder.pregnant_id == pregnant_id,
            MedicalOrder.status == "signed",
        ).count()
        if pending_orders > 0:
            msg += f"\n\n📋 您有 {pending_orders} 条新医嘱待查看，请在首页查看。"
```

### Step 3.3: 前端 — API 端点新增

**Files:**
- Modify: `frontend/src/api/endpoints.ts`

在 orderApi 对象中新增：

```typescript
getPregnantOrders: (pregnantId: string) =>
  client.get<OrderResponse[]>(`/orders/pregnant/${pregnantId}`),
```

### Step 3.4: 前端 — PregnantHome 新增医嘱通知卡片

**Files:**
- Modify: `frontend/src/views/pregnant/PregnantHome.vue`

在首页的"待办随访"通知卡片附近，新增医嘱通知卡片（复用已有卡片样式）：

```vue
<!-- 在待办随访卡片后面新增 -->
<el-card v-if="pendingOrders.length > 0" shadow="hover" class="notification-card order-card" @click="$router.push('/pregnant/tools')">
  <div class="notification-icon">📋</div>
  <div class="notification-content">
    <div class="notification-title">待查看医嘱</div>
    <div class="notification-desc">您有 {{ pendingOrders.length }} 条医嘱待查看</div>
  </div>
  <el-icon class="notification-arrow"><ArrowRight /></el-icon>
</el-card>
```

在 `<script setup>` 中新增：

```typescript
import { orderApi } from '@/api/endpoints'

const pendingOrders = ref<any[]>([])

onMounted(async () => {
  // ... 现有逻辑
  try {
    const pid = appStore.currentPregnantId
    if (pid) {
      const orders = await orderApi.getPregnantOrders(pid)
      pendingOrders.value = orders.filter((o: any) => o.status === 'signed')
    }
  } catch (e) {
    // 静默处理
  }
})
```

### Step 3.5: 测试

启动前后端，登录孕妇账号，首页应显示医嘱通知卡片（如果该孕妇有 signed 状态的医嘱）。

### Step 3.6: Commit

```bash
git add backend/app/routers/orders.py backend/app/routers/chat.py frontend/src/api/endpoints.ts frontend/src/views/pregnant/PregnantHome.vue
git commit -m "feat: 医嘱→孕妇可见链路：新增查询端点+proactive greeting增强+首页通知卡片"
```

---

## Task 4: 为小Hu（护士AI）补充工具

**目标:** 在 nurse_ai.py 中新增 create_alert、generate_followup_record、update_nursing_note 工具函数，并在 nurse_analyze 端点中自动调用。

**Files:**
- Modify: `backend/app/routers/nurse_ai.py`

### Step 4.1: 在 nurse_ai.py 顶部补充 import

```python
# 在现有 import 后追加：
from ..models import Alert, FollowUpRecord
from datetime import datetime
```

### Step 4.2: 实现工具函数

在文件末尾（`nurse_chat_stream` 端点之后）新增：

```python
# ==================== 小Hu 工具函数 ====================

def tool_create_alert(db, pregnant_id: str, level: str, message: str, trigger_source: str = "MANUAL") -> dict:
    """创建预警记录"""
    alert = Alert(
        pregnant_id=pregnant_id,
        trigger_source=trigger_source,
        level=level,
        message=message,
        status="PENDING",
    )
    db.add(alert)
    db.commit()
    return {"success": True, "alert_id": str(alert.id), "message": f"已创建{level}级预警"}


def tool_generate_followup_record(db, pregnant_id: str, template_id: str, chief_complaint: str) -> dict:
    """生成随访记录（草稿状态）"""
    from ..services import followup_service
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        return {"error": "孕妇不存在"}

    gw = (pregnant.gestational_age_days or 168) // 7
    template = followup_service.get_template(template_id)
    health_edu = followup_service.generate_health_education(gw, pregnant.risk_tags or [])

    record = FollowUpRecord(
        pregnant_id=pregnant_id,
        gestational_week=str(gw),
        chief_complaint=chief_complaint,
        health_education=health_edu,
        status="draft",
    )
    db.add(record)
    db.commit()
    return {"success": True, "record_id": str(record.id), "message": "随访记录已创建（草稿）"}


def tool_update_nursing_note(db, record_id: str, summary: str, health_education: list = None) -> dict:
    """更新护理笔记"""
    from uuid import UUID
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        return {"error": "随访记录不存在"}
    record.summary = summary
    if health_education:
        record.health_education = health_education
    db.commit()
    return {"success": True, "message": "护理笔记已更新"}
```

### Step 4.3: 在 nurse_analyze 端点中自动调用工具

在 `nurse_analyze` 端点中，在返回结果之前新增：

```python
        # 在 return 之前新增：分析完成后自动创建预警（如果检测到高风险）
        if "高风险" in (result.risk_assessment or "") or "异常" in (result.risk_assessment or ""):
            tool_create_alert(
                db, req.pregnant_id, "ORANGE",
                f"护士AI分析提示：{result.risk_assessment[:100]}",
                "MANUAL"
            )
```

注意：需要在 `nurse_analyze` 端点中确保 `db` 变量在返回前可用（当前 `finally: db.close()` 会在 return 后执行，所以可以在 return 前调用）。

### Step 4.4: 测试

调用 `POST /api/v1/nurse/analyze`，如果分析结果包含"高风险"，验证 alerts 表中自动新增了预警记录。

### Step 4.5: Commit

```bash
git add backend/app/routers/nurse_ai.py
git commit -m "feat: 为小Hu补充create_alert/generate_followup_record/update_nursing_note工具"
```

---

## Task 5: 为Dr.智（医生AI）补充工具

**目标:** 在 doctor_ai.py 中新增 generate_medical_order、update_alert_review、record_clinical_note 工具函数，并在 doctor_analyze 端点中自动调用。

**Files:**
- Modify: `backend/app/routers/doctor_ai.py`

### Step 5.1: 在 doctor_ai.py 顶部补充 import

```python
# 在现有 import 后追加：
from ..models import MedicalOrder, Alert, FollowUpRecord
from datetime import datetime
```

### Step 5.2: 实现工具函数

在文件末尾新增：

```python
# ==================== Dr.智 工具函数 ====================

def tool_generate_medical_order(db, pregnant_id: str, content: str, order_type: str = "standard", alert_id: str = None) -> dict:
    """生成医嘱草稿"""
    from uuid import UUID as _UUID
    order = MedicalOrder(
        pregnant_id=pregnant_id,
        alert_id=_UUID(alert_id) if alert_id else None,
        content=content,
        order_type=order_type,
        source="AI_RECOMMENDED",
        status="draft",
    )
    db.add(order)
    db.commit()
    return {"success": True, "order_id": str(order.id), "message": "医嘱草稿已生成"}


def tool_update_alert_review(db, alert_id: str, action: str, reason: str = "") -> dict:
    """更新预警审核状态"""
    from uuid import UUID as _UUID
    alert = db.query(Alert).filter(Alert.id == _UUID(alert_id)).first()
    if not alert:
        return {"error": "预警不存在"}
    if action == "confirm":
        alert.status = "CONFIRMED"
    elif action == "dismiss":
        alert.status = "DISMISSED"
    alert.reviewed_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": f"预警已{('确认' if action == 'confirm' else 'dismiss')}"}


def tool_record_clinical_note(db, pregnant_id: str, content: str) -> dict:
    """记录临床笔记（写入最新随访记录的summary）"""
    record = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == pregnant_id
    ).order_by(FollowUpRecord.created_at.desc()).first()
    if record:
        record.summary = (record.summary or "") + f"\n\n【临床笔记】{content}"
        db.commit()
        return {"success": True, "message": "临床笔记已记录"}
    return {"error": "未找到该孕妇的随访记录"}
```

### Step 5.3: 在 doctor_analyze 端点中自动调用工具

在 `doctor_analyze` 端点中，在返回结果之前新增：

```python
        # 在 return 之前新增：分析完成后自动生成医嘱草稿
        if result.suggested_orders:
            tool_generate_medical_order(
                db, pregnant_id, result.suggested_orders,
                order_type="standard"
            )
```

### Step 5.4: 测试

调用 `POST /api/v1/doctor/analyze/{pregnant_id}`，验证 medical_orders 表中自动新增了 draft 状态的医嘱。

### Step 5.5: Commit

```bash
git add backend/app/routers/doctor_ai.py
git commit -m "feat: 为Dr.智补充generate_medical_order/update_alert_review/record_clinical_note工具"
```

---

## Task 6: 实现混合 LLM 模式

**目标:** 支持孕妇对话用真实 LLM API，护士/医生 AI 用 Mock 模板。

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/core/llm_client.py`

### Step 6.1: 更新 config.py 新增 mixed 模式配置

```python
# 文件: backend/app/config.py
# 修改 llm_mode 类型注解：
llm_mode: Literal["cloud", "local", "mock", "mixed"] = "mock"
# 新增配置项：
llm_pregnant_mode: Literal["cloud", "local", "mock"] = "cloud"
```

### Step 6.2: 在 llm_client.py 新增 get_pregnant_llm_client

```python
# 文件: backend/app/core/llm_client.py
# 在 get_llm_client() 函数之后新增：

_pregnant_llm_client_instance: LLMClient | None = None


def get_pregnant_llm_client() -> LLMClient:
    """获取孕妇对话专用的LLM客户端（mixed模式下使用）"""
    global _pregnant_llm_client_instance
    if _pregnant_llm_client_instance is not None:
        return _pregnant_llm_client_instance

    from ..config import settings

    if settings.llm_mode == "mixed":
        mode = settings.llm_pregnant_mode
    else:
        mode = settings.llm_mode

    if mode == "cloud":
        _pregnant_llm_client_instance = CloudAPIClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    elif mode == "local":
        _pregnant_llm_client_instance = LocalOllamaClient(
            host=settings.ollama_host,
            model=settings.local_model,
        )
    else:
        _pregnant_llm_client_instance = MockLLMClient()
    return _pregnant_llm_client_instance
```

### Step 6.3: 更新 chat.py 使用孕妇专用 LLM

在 `backend/app/routers/chat.py` 中，将 `llm = get_llm_client()` 改为：

```python
# 文件: backend/app/routers/chat.py
# 修改顶部的 llm 初始化：
from ..core.llm_client import get_pregnant_llm_client

# 在文件顶部（router 定义之后）：
def _get_chat_llm():
    from ..config import settings
    if settings.llm_mode == "mixed":
        return get_pregnant_llm_client()
    return get_llm_client()
```

然后在 `send_message` 和 `send_message_stream` 端点中，将 `llm.chat(...)` 和 `llm.chat_stream(...)` 替换为 `_get_chat_llm().chat(...)` 和 `_get_chat_llm().chat_stream(...)`。

### Step 6.4: 测试

设置 `.env` 中 `LLM_MODE=mixed`，启动后端，验证：
- 孕妇对话走真实 LLM API（如果配置了 API key）
- 护士/医生 AI 分析走 Mock 模板

### Step 6.5: Commit

```bash
git add backend/app/config.py backend/app/core/llm_client.py backend/app/routers/chat.py
git commit -m "feat: 实现混合LLM模式，孕妇对话用真实API，护士/医生AI用Mock模板"
```

---

## Task 7: 修复前后端联调问题

**目标:** 修复 PregnantSchedule 硬编码 ID、OrderManage 硬编码 doctor ID。

### Step 7.1: 修复 PregnantSchedule 硬编码 ID

**Files:**
- Modify: `frontend/src/views/pregnant/PregnantSchedule.vue`

在 `<script setup>` 中找到 `PREGNANT_ID` 常量，替换为从 appStore 读取：

```typescript
// 将硬编码的：
// const PREGNANT_ID = 'current-pregnant-id'
// 替换为：
import { useAppStore } from '@/stores/app'
const appStore = useAppStore()
const PREGNANT_ID = computed(() => appStore.currentPregnantId || '')
```

确保所有使用 `PREGNANT_ID` 的地方改为 `.value`（因为是 computed）。

### Step 7.2: 修复 OrderManage 硬编码 doctor ID

**Files:**
- Modify: `frontend/src/views/doctor/OrderManage.vue`

找到 `handleSign` 函数中的 `orderApi.sign(order.id, 'current-doctor')`，替换为：

```typescript
import { useAppStore } from '@/stores/app'
const appStore = useAppStore()

// 在 handleSign 中：
const doctorId = appStore.currentRole === 'doctor' ? 'doctor_001' : 'current-doctor'
await orderApi.sign(order.id, doctorId)
```

### Step 7.3: 测试

登录孕妇账号，打开检查日程页面，验证能正常加载数据（不再显示空白）。登录医生账号，签署医嘱，验证 doctor_id 不再是硬编码字符串。

### Step 7.4: Commit

```bash
git add frontend/src/views/pregnant/PregnantSchedule.vue frontend/src/views/doctor/OrderManage.vue
git commit -m "fix: 修复PregnantSchedule和OrderManage中的硬编码ID"
```

---

## Task 8: 集成测试 — 三角色联动走查

**目标:** 验证完整演示链路可跑通。

### Step 8.1: 重启后端并验证种子数据

```bash
cd backend
rm -f ai_care.db  # 清除旧数据库
python -c "from app.main import app; from app.scripts.seed_data import seed_all; seed_all()"
python -m uvicorn app.main:app --reload --port 9999
```

验证：数据库中应有完整的种子数据。

### Step 8.2: 验证孕妇端

1. 登录孕妇账号（H202501）
2. 首页应显示：健康数据、随访通知、医嘱通知卡片
3. 聊天页面应显示：对话历史
4. 检查日程页面应显示：产检排期

### Step 8.3: 验证护士端

1. 登录护士账号
2. Dashboard 应显示：统计数据、预警列表、随访列表
3. 点击"AI分析"应返回小Hu的分析报告
4. 分析后应自动创建新预警（如果检测到高风险）

### Step 8.4: 验证医生端

1. 登录医生账号
2. Dashboard 应显示：统计数据、高风险预警、待签医嘱
3. ReviewWorkbench 应显示：预警详情
4. 点击"AI分析"应返回 Dr.智 的分析，并自动生成医嘱草稿

### Step 8.5: Commit

```bash
git add -A
git commit -m "test: 集成测试验证三角色联动走查"
```

---

## 文件变更总结

| 文件 | 操作 | 任务 |
|------|------|------|
| `backend/app/scripts/seed_data.py` | 修改 | Task 1 |
| `backend/app/core/followup_tools.py` | 修改 | Task 2 |
| `backend/app/routers/orders.py` | 修改 | Task 3 |
| `backend/app/routers/chat.py` | 修改 | Task 3, 6 |
| `frontend/src/api/endpoints.ts` | 修改 | Task 3 |
| `frontend/src/views/pregnant/PregnantHome.vue` | 修改 | Task 3 |
| `backend/app/routers/nurse_ai.py` | 修改 | Task 4 |
| `backend/app/routers/doctor_ai.py` | 修改 | Task 5 |
| `backend/app/config.py` | 修改 | Task 6 |
| `backend/app/core/llm_client.py` | 修改 | Task 6 |
| `frontend/src/views/pregnant/PregnantSchedule.vue` | 修改 | Task 7 |
| `frontend/src/views/doctor/OrderManage.vue` | 修改 | Task 7 |
