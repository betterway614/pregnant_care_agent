# AI-Care Mock 数据补全与业务逻辑打通设计

## 目标

演示驱动，确保三角色联动走查（孕妇→护士→医生）全流程可跑通，所有页面有数据可看。

- **LLM 模式**：混合模式（孕妇对话用真实 LLM API，护士/医生 AI 用 Mock 模板）
- **初始状态**：就绪状态（预置完整数据）

## 演示链路

```
孕妇聊天报告数据 → AI检测异常 → 生成预警
  → 护士看到预警 → AI分析 → 触发随访
  → 孕妇回答随访 → 护士确认
  → 医生审核 → Dr.智分析 → 开具医嘱
  → 孕妇收到医嘱通知
```

---

## 一、种子数据补全

### 1.1 新增数据类型

| 数据类型 | 模型 | 每人数量 | 关键设计 |
|----------|------|----------|----------|
| 随访记录 | FollowUpRecord | 2-3 条 | 覆盖 draft/confirmed/archived 三态，含 self_reported_data JSON 和 summary |
| 医嘱 | MedicalOrder | 1-2 条 | 覆盖 draft/signed/executed 三态，AI 推荐和医生开具双来源 |
| 对话历史 | ConversationMessage | 5-10 条 | user/assistant 交替消息，模拟真实对话 |
| 心理筛查 | MentalHealthScreening | 1 条 | EPDS 评分，覆盖 low/moderate/high |
| 胎动记录 | FetalMovementSession | 2-3 条 | 完整 kick_times JSON |
| 反馈 | Feedback | 若干 | 关联 ConversationMessage 的 message_id |

### 1.2 补充现有数据

在 HealthDataPoint 中新增 metric_code：
- `blood_sugar`：GDM 患者必须有（空腹/餐后值）
- `emotion_score`：情绪评分（0-10），高血压/正常孕妇各分布
- `sleep_hours`：睡眠时长，用于 SHORT_SLEEP 规则触发

### 1.3 场景覆盖矩阵

| 数据类型 | 正常孕妇 | FGR孕妇 | GDM孕妇 | 高血压孕妇 |
|----------|---------|---------|---------|-----------|
| 基础健康数据 | ✅已有 | ✅已有 | ⚠️+血糖 | ✅已有 |
| 随访记录 | ✅新增 | ✅新增 | ✅新增 | ✅新增 |
| 医嘱 | ✅新增 | ✅新增 | ✅新增 | ✅新增 |
| 对话历史 | ✅新增 | ✅新增 | ✅新增 | ✅新增 |
| 心理健康 | ✅新增 | ✅新增 | — | ✅新增 |
| 胎动记录 | ✅新增 | ✅新增 | — | — |
| 反馈 | ✅新增 | ✅新增 | ✅新增 | ✅新增 |

### 1.4 种子数据实现

修改 `backend/app/scripts/seed_data.py`，在 `seed_all()` 中新增以下函数：

- `seed_followup_records(db)`：为每个孕妇生成 2-3 条随访记录
- `seed_medical_orders(db)`：为有预警的孕妇生成 1-2 条医嘱
- `seed_conversation_messages(db)`：为每个孕妇生成 5-10 条对话历史
- `seed_mental_health_screenings(db)`：为 5-8 个孕妇生成 EPDS 记录
- `seed_fetal_movement_sessions(db)`：为 5-8 个孕妇生成胎动记录
- `seed_feedback(db)`：为部分对话消息生成反馈
- `supplement_health_data(db)`：补充 blood_sugar/emotion_score/sleep_hours

---

## 二、业务链路打通

### 2.1 链路 1：随访 → 规则引擎 → 预警

**现状**：`followup_tools.record_answer` 保存 HealthDataPoint 后结束，不触发规则评估。

**改动**：在 `backend/app/core/followup_tools.py` 的 `record_answer` 函数中，保存 HealthDataPoint **之后**，新增以下逻辑：

```python
# record_answer 中，保存 HealthDataPoint 后新增：
from .rule_engine import RuleEngine
rule_engine = RuleEngine()
# evaluate 接收 pregnant_id 和 db session，返回触发的规则列表
triggered_rules = rule_engine.evaluate(pregnant_id, db)
for rule in triggered_rules:
    alert = Alert(
        pregnant_id=pregnant_id,
        trigger_source="RULE_ENGINE",
        rule_id=rule.get("rule_id", ""),
        level=rule.get("level", "YELLOW"),
        message=rule.get("message", ""),
        details=rule.get("details", {}),
        status="PENDING",
    )
    db.add(alert)
db.commit()
```

注意：`RuleEngine.evaluate()` 的具体接口需在实现时确认，上述为预期签名。

**改动文件**：
- `backend/app/core/followup_tools.py`：record_answer 中新增规则引擎调用和 Alert 创建

### 2.2 链路 2：FGR 评估 → 预警自动生成

**现状**：FgrAssessment 和 Alert 完全独立。

**改动**：在 `backend/app/routers/fgr.py` 的 assess 端点中：

```python
# FGR 评估完成后
if result.risk_level in ("high", "critical"):
    alert = Alert(
        pregnant_id=pregnant_id,
        trigger_source="FGR_ALGORITHM",
        level="RED" if result.risk_level == "critical" else "ORANGE",
        message=f"FGR评估：{result.risk_level}风险",
        status="PENDING",
    )
    db.add(alert)
    db.commit()
```

**改动文件**：
- `backend/app/routers/fgr.py`：assess 端点新增 Alert 生成逻辑

### 2.3 链路 3：医嘱 → 孕妇可见

**现状**：MedicalOrder 创建后孕妇端无展示入口。

**改动**：

**后端**：修改 `backend/app/routers/chat.py` 的 proactive greeting 端点，检查是否有新签署的医嘱：

```python
# 在 proactive greeting 端点中，生成 greeting 后新增：
from ..models import MedicalOrder
# 检查是否有状态为 signed 的医嘱（不限时间，因为孕妇可能还没看过）
pending_orders = db.query(MedicalOrder).filter(
    MedicalOrder.pregnant_id == pregnant_id,
    MedicalOrder.status == "signed",
).all()
if pending_orders:
    greeting += f"\n\n📋 您有 {len(pending_orders)} 条新医嘱待查看，请在首页查看。"
```

注：不使用时间过滤，因为孕妇可能多次打开首页但从未查看过医嘱。只要医嘱状态为 signed 且孕妇未查看，就持续提示。

**前端**：修改 `frontend/src/views/pregnant/PregnantHome.vue`，新增"待查看医嘱"通知卡片（复用已有通知卡片样式）。

**新增后端端点**：`GET /api/v1/orders/pregnant/{pregnant_id}` — 返回该孕妇的 signed 状态医嘱列表（复用现有 order 模型，新增查询条件）。

**改动文件**：
- `backend/app/routers/orders.py`：新增按 pregnant_id 查询医嘱的端点
- `backend/app/routers/chat.py`：proactive greeting 新增医嘱检查
- `frontend/src/views/pregnant/PregnantHome.vue`：新增医嘱通知卡片
- `frontend/src/api/endpoints.ts`：在 orderApi 中新增 `getPregnantOrders(pregnantId)` 方法

---

## 三、前后端联调修复

### 3.1 高优先级

| 问题 | 文件 | 修复方案 |
|------|------|----------|
| PregnantSchedule 硬编码 ID | `frontend/src/views/pregnant/PregnantSchedule.vue` | 改为 `appStore.currentPregnantId` |
| Order 签名硬编码 doctor ID | `frontend/src/views/doctor/OrderManage.vue` | 改为从 appStore 读取 |
| 孕妇端无医嘱入口 | `frontend/src/views/pregnant/PregnantHome.vue` | 新增医嘱通知卡片 |

### 3.2 中优先级

| 问题 | 文件 | 修复方案 |
|------|------|----------|
| EPDS 历史未调用 | `frontend/src/views/pregnant/PregnantTools.vue` | 完成后显示历史记录 |
| Feedback stats 未调用 | 可选 | 护士/医生 AI 面板展示反馈统计 |
| Order explain API 未调用 | `frontend/src/views/doctor/OrderManage.vue` | 详情中增加"患者版解读"按钮 |

---

## 四、智能体工具补充

### 4.1 小Hu（护士AI）工具

在 `backend/app/routers/nurse_ai.py` 中新增工具定义：

| 工具名 | 参数 | 功能 | 入库 |
|--------|------|------|------|
| `create_alert` | pregnant_id, level, message, trigger_source | 创建预警 | → Alert 表 |
| `generate_followup_record` | pregnant_id, template_id, chief_complaint | 生成随访记录 | → FollowUpRecord 表 |
| `update_nursing_note` | record_id, summary, health_education | 更新护理笔记 | → FollowUpRecord |

### 4.2 Dr.智（医生AI）工具

在 `backend/app/routers/doctor_ai.py` 中新增工具定义：

| 工具名 | 参数 | 功能 | 入库 |
|--------|------|------|------|
| `generate_medical_order` | pregnant_id, content, order_type, alert_id | 生成医嘱草稿 | → MedicalOrder 表 (draft) |
| `update_alert_review` | alert_id, action, reason | 更新预警审核 | → Alert.status |
| `record_clinical_note` | pregnant_id, content | 记录临床笔记 | → FollowUpRecord |

### 4.3 Mock 模式下的工具行为

**实现方式**：不修改 MockLLMClient 的 chat_with_tools 接口，而是在 analyze 端点中**分析完成后直接调用工具函数**。

具体实现：
- `nurse_ai.py` 的 `nurse_analyze` 端点：分析返回后，如果 risk_assessment 中包含"高风险"关键词，自动调用 `create_alert` 工具函数创建 Alert
- `doctor_ai.py` 的 `doctor_analyze` 端点：分析返回后，自动调用 `generate_medical_order` 工具函数生成医嘱草稿（status=draft）

工具函数作为独立函数定义在 router 文件中，供 analyze 端点和未来的 tool-calling 端点共同调用。

---

## 五、混合 LLM 模式

### 5.1 设计思路

孕妇端所有数据为 Mock 种子数据，但孕妇对话使用真实 LLM API 以保证对话体验自然。护士/医生 AI 使用 Mock 模板以保证输出格式稳定可控。

### 5.2 实现方式

在 `backend/app/config.py` 中新增配置：

```python
# 新增配置项
llm_mode: str = "mixed"  # cloud / local / mock / mixed
llm_pregnant_mode: str = "cloud"   # 孕妇对话的 LLM 模式
```

在 `backend/app/core/llm_client.py` 的工厂函数 `get_llm_client()` 中：
- 如果 `llm_mode == "mixed"`，根据调用方选择不同的 client
- 新增 `get_pregnant_llm_client()` 专用函数，返回孕妇对话专用的 LLM client
- 护士/医生 AI 的 analyze 端点中，优先使用模板兜底（`_fallback_*` 函数），仅在 LLM 可用时尝试调用

### 5.3 各智能体的 LLM 策略

| 智能体 | LLM 模式 | 原因 |
|--------|----------|------|
| 小安（孕妇对话） | 真实 LLM API | 对话体验自然 |
| 小安（随访模式） | 真实 LLM API + Mock 状态机 | 随访工具调用需要 function calling，Mock 状态机作为 fallback |
| 小Hu（护士分析） | Mock 模板优先 | 输出格式固定，前端渲染稳定 |
| Dr.智（医生分析） | Mock 模板优先 | 同上 |

### 5.4 配置文件更新

`.env` 或 `config.py` 中新增：

```
LLM_MODE=mixed
LLM_PREGNANT_MODE=cloud
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

---

## 六、不动的部分

以下功能在本次设计中不修改：
- ASR 语音识别（保持 reserved）
- 头像上传（保持 coming soon）
- Admin 角色（无独立页面）
- 404 页面
- 国际化
- SQLAlchemy relationship() 改造
- JWT 认证体系
- AuditLog 模型

---

## 七、验证标准

演示时以下场景必须能跑通：

1. ✅ 孕妇打开首页，看到健康数据、随访通知、医嘱通知
2. ✅ 孕妇聊天报告"血压158/95"，小安记录数据并提示已通知医护
3. ✅ 护士 Dashboard 显示该预警，点击"AI分析"获得小Hu的分析报告
4. ✅ 护士点击"触发随访"，孕妇端小安进入随访模式并完成问答
5. ✅ 护士确认随访记录，转交医生
6. ✅ 医生 ReviewWorkbench 显示预警详情，点击"AI分析"获得 Dr.智 的分析
7. ✅ 医生确认预警并生成医嘱，医嘱状态为 signed
8. ✅ 孕妇端收到医嘱通知，可查看医嘱内容和患者版解读
9. ✅ 所有页面（护士/医生/孕妇）打开后有数据可看，无空白页
