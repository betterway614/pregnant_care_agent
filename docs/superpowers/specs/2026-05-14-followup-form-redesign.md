# 随访模式重构：结构化表单 + LLM 汇总

## 背景

当前随访依赖 LLM Agent 逐个提问、识别回答，存在三个顽疾：
1. 重复问同一个问题（Agent 不遵循工具返回的进度）
2. 不知道何时结束（Agent 不调用 complete_followup）
3. 废话太多、语气不当

根本原因：用 LLM 做结构化数据采集是错误的范式。LLM 擅长分析和生成，不擅长精确的流程控制。

## 设计决策

- **随访改为结构化表单**：用户直接填写，数据直接入库
- **LLM 只负责提交后汇总**：生成 1-2 句温馨总结
- **表单为单页模式**：所有问题一屏展示，自由填写后统一提交
- **入口在首页待办卡片**：孕妇首页显示待完成随访
- **提交后替换为汇总卡片**：原地展示 LLM 生成的总结
- **组件复用**：随访表单复用 HealthRecord 的健康数据字段组件

## 小安 Agent 新定位

| 能力 | 说明 |
|------|------|
| 智能问答 | 孕期知识回答（Knowledge RAG） |
| 情绪安抚 | 温暖对话，共情回应 |
| 情绪识别 | 从文本识别情绪倾向 |
| 历史数据汇总分析 | 健康趋势分析 |
| 随访总结 | 表单提交后 LLM 生成汇总（新增） |

随访问答功能从 Agent 中移除。

## 数据流

```
护士触发随访 → 创建 FollowUpRecord (status=draft)
                    ↓
孕妇首页看到待办卡片 → 点击进入 FollowUpForm
                    ↓
GET /followup/pending/{id} → 获取模板问题列表
                    ↓
前端渲染动态表单（按字段类型匹配组件）
                    ↓
孕妇填写 → POST /followup/respond {answers: {...}}
                    ↓
后端保存：
  ├── 量化数据 → HealthDataPoint（体重/血压/血糖/胎动）
  ├── 文本答案 → FollowUpRecord.self_reported_data
  ├── 状态转换 → draft → in_progress → completed
  └── 调用 LLM → 生成温馨汇总
                    ↓
返回 {status: "completed", summary: "..."}
                    ↓
前端替换表单为汇总卡片
```

## 后端 API 改造

### GET /followup/pending/{pregnant_id}

从模板动态获取问题（不再硬编码），根据孕妇 risk_tags 自动选择模板。

返回格式：
```json
{
  "record_id": "uuid",
  "patient_name": "艳芳",
  "template_id": "gdm",
  "template_name": "妊娠期糖尿病随访",
  "questions": [
    {"key": "feeling", "question": "最近感觉怎么样？", "type": "text"},
    {"key": "blood_sugar_fasting", "question": "今早空腹血糖是多少？", "type": "number", "unit": "mmol/L", "target": "≤5.3"},
    {"key": "weight", "question": "今天的体重是多少？", "type": "number", "unit": "kg"}
  ],
  "answered_count": 0,
  "total_count": 5,
  "has_pending": true,
  "health_education": ["GDM管理：控制碳水摄入..."]
}
```

模板选择逻辑：
- 有 "GDM" → gdm 模板
- 有 "高血压" → hypertension 模板
- 有 "FGR" → fgr_high_risk 模板
- 孕周 < 12 → early_pregnancy 模板
- 孕周 >= 36 → late_pregnancy 模板
- 默认 → standard 模板

### POST /followup/respond

支持部分提交 + 完成后自动调 LLM 汇总。

请求：`{"record_id": "uuid", "answers": {"weight": 65.5, "bp": "120/80"}}`

未完成响应：
```json
{"status": "in_progress", "answered_count": 3, "total_count": 5}
```

全部完成响应：
```json
{
  "status": "completed",
  "answered_count": 5,
  "total_count": 5,
  "summary": "艳芳辛苦啦~ 体重控制得不错，血压也很稳定。继续保持好心情~💗"
}
```

数据写入规则：
- 体重/血压/血糖/胎动等量化字段 → 同时写入 HealthDataPoint
- feeling/diet 等文本字段 → 只写入 self_reported_data
- 全部完成后 → 调用 LLM 生成汇总，写入 record.summary

## 前端设计

### FollowUpForm.vue

位置：`frontend/src/views/pregnant/tools/FollowUpForm.vue`

页面结构：
1. 顶部导航（返回 + 标题 + 进度）
2. 孕妇信息卡（姓名 + 孕周 + 模板名）
3. 进度条
4. 动态表单区域（根据 questions 渲染）
5. 提交按钮
6. 提交后 → 替换为汇总卡片 + 健康教育

字段组件映射：

| type | key 匹配 | 组件 |
|------|---------|------|
| number | weight | 体重输入框（复用 HealthRecord 样式） |
| text | bp/bp_morning/bp_evening | 血压双输入框（复用 HealthRecord 样式） |
| number | fetal_movement | 胎动输入框（复用 HealthRecord 样式） |
| number | blood_sugar_* | 血糖输入框 |
| text | feeling/diet | 多行文本框 |
| text | 其他 | 单行文本框 |

number 类型显示 unit，可选显示 target（目标值提示）。

复用策略：复用 HealthRecord 的视觉样式（CSS 类名、输入框样式），不提取公共组件。
两个页面架构不同（HealthRecord 固定字段 vs FollowUpForm 动态模板），共享样式即可。

未完成处理：用户填写部分字段后关闭页面，已填内容丢失。下次进入重新开始。
这是单页表单的预期行为，不实现自动保存（增加复杂度，随访频率低）。

### 路由

`/pregnant/tools/followup/:recordId` → FollowUpForm.vue

### 首页入口

PregnantHome.vue 的 today_tasks 区域，有待完成随访时显示卡片，点击进入 FollowUpForm。

### 类型定义

```typescript
interface FollowUpQuestion {
  key: string
  question: string
  type: 'text' | 'number' | 'select' | 'scale'
  unit?: string
  target?: string
  format?: string
}

interface FollowUpPendingResponse {
  record_id: string
  patient_name: string
  template_id: string
  template_name: string
  questions: FollowUpQuestion[]
  answered_count: number
  total_count: number
  has_pending: boolean
  health_education: string[]
}
```

## Agent 清理

### 删除

| 文件 | 内容 |
|------|------|
| agno_chat_handler.py | handle_followup_chat_with_agno、handle_followup_chat_with_agno_stream、_init_agno_followup_db |
| followup_tools.py | 整个文件删除 |
| agno_tools.py | AGNO_FOLLOWUP_TOOLS |
| agno_agent.py | create_followup_agent、_get_followup_model |
| prompts.py | get_followup_system_prompt、get_followup_agent_instructions |
| chat.py 路由 | 随访分流逻辑（record_id 判断） |

### 保留

| 文件 | 内容 |
|------|------|
| followup_service.py | 模板定义、健康数据提取、摘要生成、健康教育 — 全部保留 |
| followup.py 路由 | trigger、records、confirm、pending、respond — 保留并改造 |
| FollowUpRecord 模型 | 不变 |
| prompts.py | 主对话 prompt、护士/医生 prompt — 保留 |

## 验证方式

1. 后端：调用 GET /followup/pending 确认返回带 type 的问题列表
2. 前端：从首页进入随访表单，确认动态渲染正确
3. 提交：填写并提交，确认 HealthDataPoint 和 self_reported_data 都正确写入
4. 完成：全部提交后确认状态变为 completed，LLM 汇总正确生成
5. 回归：确认主对话（小安）功能不受影响
