# AI-Care 孕期智能管理平台 技术架构设计文档 V1.0

| 文档版本 | 修改日期 | 修改人 | 修改内容 |
|:---|:---|:---|:---|
| V1.0 | 2026-04-29 | [你的名字] | 初始版本创建 |
| V1.1 | 2026-04-29 | [你的名字] | 增加分阶段开发策略、云端开发模式、Mock数据方案 |

## 1. 架构概览

### 1.1 设计原则
- **阶段适配**：开发阶段全走云端API快速闭环，竞赛阶段核心能力切回本地端侧推理
- **异构协同**：CPU/GPU/NPU按任务特性分工，统一内存架构消除数据搬运开销
- **隐私默认**：生产环境医疗数据从采集到推理全链路本地闭环，默认不离开设备
- **三端解耦**：孕妇端/护士端/医生端通过统一API网关通信，各端独立迭代
- **合规先行**：架构设计内置科研/教学辅助定位，所有输出均标注非临床决策声明

### 1.2 分阶段开发策略
```
阶段一：业务闭环验证（当前）          阶段二：端侧迁移（竞赛前）
────────────────────────────────────────────────────────────
孕妇端对话    → 云端API             → GPU本地推理(可选)
护士端随访    → 云端API + 模板      → GPU本地推理(可选)
医生端医嘱    → 云端API + 模板      → GPU本地推理(可选)
FGR评估       → Mock数据            → NPU ONNX Runtime
NLU解析       → 云端API             → NPU轻量BERT
规则引擎      → CPU（始终本地）      → CPU（不变）
高危兜底      → CPU（始终本地）      → CPU（不变）
数据存储      → 本地DB + Mock       → 本地DB + 脱敏数据

策略：先跑通业务逻辑和三端协同，模型推理统一抽象为接口，
      阶段二只需切换实现，不改业务代码。
```

### 1.3 网络拓扑（孕妇公网 / 医护内网）
```
                        互联网                          │  医院内网
                                                       │
 孕妇手机(4G/5G/WiFi)                                  │  护士PC ─────┐
      │                                                │      │        │
      │  HTTPS (仅暴露孕妇端API)                         │      │        │
      ▼                                                │      ▼        ▼
┌──────────────┐     ┌─────────────────┐   内网转发     │  ┌──────────────────────┐
│ 孕妇端前端     │     │ 反向代理网关     │─────────────►│  │ AMD端侧服务器          │
│ (微信小程序    │     │ Nginx (DMZ)    │              │  │                      │
│  /H5云托管)   │     │                │              │  │ FastAPI :8000        │
│              │     │ 路径白名单:      │              │  │ FGR-NPU :8002        │
│ 静态资源      │     │ /api/v1/chat/*  │              │  │ Ollama :11434        │
│ CDN分发      │     │ /api/v1/fgr/*   │              │  │ PG :5432 Redis:6379  │
└──────────────┘     │ /api/v1/schedule│              │  │                      │
                     │ /ws (WebSocket) │              │  │ 护士端前端 :3001      │
                     │                │              │  │ 医生端前端 :3002      │
                     │ 安全策略:       │              │  │                      │
                     │ - JWT鉴权      │              │  └──────────────────────┘
                     │ - IP限流       │              │
                     │ - 仅响应白名单  │              │   医护端通过局域网直接访问
                     │ - 非白名单→403 │              │   http://192.168.x.x:3001
                     └─────────────────┘              │   http://192.168.x.x:3002
```

**访问控制矩阵**：

| 客户端 | 所在网络 | 访问方式 | 可访问资源 |
|:---|:---|:---|:---|:---|
| 孕妇端 | 公网 | HTTPS → Nginx → 内网API | 仅孕妇端相关API（chat/提醒/数据上报） + WebSocket |
| 护士端 | 内网 | 局域网直连 | 护士端前端 + 全部API（含审核/排期/预警） |
| 医生端 | 内网 | 局域网直连 | 医生端前端 + 全部API（含FGR看板/审核/医嘱） |
| 全部 | - | - | 不能直接访问 Ollama/FGR-NPU/DB 端口（仅本机监听） |

**Nginx 反向代理关键配置**：
```nginx
server {
    listen 443 ssl;
    server_name api.ai-care.example.com;

    # SSL证书配置 ...

    # 仅暴露孕妇端所需路径
    location /api/v1/chat/     { proxy_pass http://amd-server:8000; }
    location /api/v1/schedule/ { proxy_pass http://amd-server:8000; }
    location /api/v1/ws        { proxy_pass http://amd-server:8000; }

    # 其他路径一律拒绝
    location /api/             { return 403; }
}
```

**开发阶段简化**：开发时所有端都在同一台机器，不需区分网络，Nginx 也不需路径白名单。以上拓扑仅用于演示/生产部署。

### 1.2 四层架构总览
```
┌─────────────────────────────────────────────────────────────────┐
│                      前端接入层 (Presentation)                    │
│  孕妇端(小程序/UniApp) │ 护士端(React Web) │ 医生端(React Web)    │
│   WebSocket实时通道  │  RESTful API       │  管理后台看板        │
├─────────────────────────────────────────────────────────────────┤
│                      应用服务层 (Application)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ 智能体引擎 │ │ 排期服务  │ │ 随访服务  │ │ 预警与规则引擎    │  │
│  │ Agent Mgr │ │ Schedule │ │ FollowUp │ │ Alert & Rule     │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ 对话管理  │ │ 报告生成  │ │ 用户管理  │ │ 数据统计与监控    │  │
│  │ Dialogue  │ │ Report   │ │ User Mgr │ │ Dashboard        │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                     AI推理层 (AI Inference) - AMD 端侧            │
│  ┌─────────────────────┐  ┌──────────────────────────────┐     │
│  │  GPU - Radeon 8060S │  │  NPU - 锐龙AI                │     │
│  │  ┌───────────────┐  │  │  ┌────────────────────────┐  │     │
│  │  │ 通用医疗大模型  │  │  │  │ FGR评估算法(自研)       │  │     │
│  │  │ (Ollama/ROCm) │  │  │  │ ONNX Runtime + ZenDNN  │  │     │
│  │  ├───────────────┤  │  │  ├────────────────────────┤  │     │
│  │  │ Embedding模型  │  │  │  │ NLU意图/实体/情绪识别   │  │     │
│  │  │ BGE-M3        │  │  │  │ ONNX轻量BERT           │  │     │
│  │  ├───────────────┤  │  │  ├────────────────────────┤  │     │
│  │  │ 向量数据库      │  │  │  │ 指标预处理              │  │     │
│  │  │ ChromaDB/Qdrant│  │  │  │ Ryzen AI SDK           │  │     │
│  │  └───────────────┘  │  │  └────────────────────────┘  │     │
│  └─────────────────────┘  └──────────────────────────────┘     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  CPU - AMD 锐龙 AI Max+ 395                              │  │
│  │  任务调度 │ 流程控制 │ 规则引擎 │ 报告生成 │ API网关        │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  统一内存架构 (UMA) - 128GB (最高96GB GPU显存)             │  │
│  └──────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                      数据存储层 (Data)                           │
│  PostgreSQL(业务) │ ChromaDB/Qdrant(向量) │ MinIO/本地FS(文件)   │
│  Redis(会话/队列)  │ 本地Embedding索引     │ DICOM影像归档        │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 智能体架构设计

### 2.1 智能体基类架构
三个智能体共享统一的任务编排框架，基础结构如下：

```
AgentBase
├── core/
│   ├── llm_client.py        # GPU大模型调用客户端 (Ollama API封装)
│   ├── nlu_engine.py        # NPU轻量NLU引擎 (意图/实体/情绪识别)
│   ├── memory_manager.py    # 对话记忆管理 (短期+云端状态键值对)
│   └── tool_registry.py     # 工具注册与调用
├── domain/
│   ├── medical_knowledge.py # 产科知识库 (向量检索+RAG)
│   ├── fgr_client.py        # FGR算法NPU推理客户端
│   ├── schedule_engine.py   # 孕周排期计算引擎
│   └── alert_rules.py       # 高危规则引擎
├── agent/
│   ├── pregnant_agent.py    # 孕妇端"小安"
│   ├── nurse_agent.py       # 护士端"小护"
│   └── doctor_agent.py      # 医生端"Dr.智"
└── api/
    ├── rest_router.py       # RESTful API路由
    └── ws_handler.py        # WebSocket实时通信处理
```

### 2.2 智能体任务路由
```
用户请求 → API网关
              │
              ▼
         智能体路由器 (CPU)
              │
     ┌────────┼────────┐
     ▼        ▼        ▼
  孕妇Agent  护士Agent  医生Agent
     │        │        │
     └────────┼────────┘
              ▼
       任务编排引擎 (CPU)
         ├── 对话理解 → NLU引擎 (NPU)
         ├── 知识检索 → Embedding + 向量搜索 (GPU)
         ├── 推理生成 → 大模型推理 (GPU)
         ├── 图像分析 → FGR算法推理 (NPU)
         ├── 规则判断 → 规则引擎 (CPU)
         └── 结果组装 → 格式化输出 (CPU)
              │
              ▼
        响应返回 → API网关 → 前端
```

### 2.3 三智能体交互协议

三个智能体之间通过内部事件总线通信，消息格式如下：

```json
{
  "eventId": "EVT_20260429_001",
  "eventType": "ALERT_TRIGGERED | SCHEDULE_PUBLISHED | ORDER_ISSUED | FOLLOWUP_COMPLETED",
  "sourceAgent": "nurse_agent",
  "targetAgent": "doctor_agent",
  "patientId": "PT_ANON_HASH_001",
  "payload": { },
  "timestamp": "2026-04-29T10:30:00Z",
  "priority": "HIGH | MEDIUM | LOW"
}
```

交互流程：
- **孕妇→护士**：健康数据上报事件 → 自动记录/预警判断
- **孕妇→医生**：（间接）经护士确认的预警 → 医生审核列表
- **护士→孕妇**：排期发布事件 → 提醒通知
- **护士→医生**：高危初筛确认事件 → 审核工作台
- **医生→护士**：医嘱发布事件 → 执行任务
- **医生→孕妇**：（间接）医嘱执行注意事项 → 孕妇端展示

## 3. 核心模块详细设计

### 3.1 对话管理与记忆系统

```
┌─────────────────────────────────────────────┐
│                对话管理服务                   │
│                                              │
│  孕妇端会话                                    │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐  │
│  │ 短期记忆  │  │ 云端状态   │  │ 用户控制权   │  │
│  │ (本地)   │  │ (键值对)  │  │ (清除按钮)   │  │
│  │ 1h TTL   │  │ Redis    │  │ 物理删除    │  │
│  └─────────┘  └──────────┘  └────────────┘  │
│                                              │
│  护士/医生端会话                               │
│  ┌──────────────────────────────────────┐    │
│  │ 工作上下文 (Session级)                  │    │
│  │ 当前操作患者 │ 当前审核条目 │ 草稿状态   │    │
│  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

**实现要点**：
- 短期记忆存于前端 IndexedDB（Web）或本地存储（小程序），超时自动清除
- 云端状态仅存键值对（如 `last_weight_date: 2026-04-29`），存于Redis，设置30天TTL
- 清除操作使用Redis DEL命令清除该用户全部键值对
- 不存储任何对话原文，NLU结果经哈希脱敏后即刻处理

### 3.2 知识库与RAG架构

```
┌──────────────────────────────────────────────────┐
│              RAG 检索增强生成流水线                  │
│                                                   │
│  离线索引（一次性/增量）                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐  │
│  │ 产科指南  │   │ 药品说明  │   │ 健康教育材料   │  │
│  │ 文档分割  │   │ 文档分割  │   │ 文档分割      │  │
│  └────┬─────┘   └────┬─────┘   └──────┬───────┘  │
│       └──────────────┼────────────────┘           │
│                      ▼                            │
│              ┌──────────────┐                     │
│              │ Embedding模型 │ ← GPU BGE-M3       │
│              │ 向量化        │                     │
│              └──────┬───────┘                     │
│                     ▼                             │
│            ┌────────────────┐                     │
│            │ 向量数据库       │                     │
│            │ ChromaDB/Qdrant│                     │
│            └────────────────┘                     │
│                                                   │
│  在线推理（每次对话）                                 │
│  用户提问 → Embedding(GPU) → 向量检索(GPU)            │
│           → Top-K文档召回 → Prompt拼装               │
│           → 大模型推理(GPU) → 答案+来源标注            │
└──────────────────────────────────────────────────┘
```

### 3.3 规则引擎设计

高危规则以可配置的表达式存储，支持热更新：

```python
# 规则定义示例
RULES = [
    {
        "id": "RULE_BP_HIGH",
        "expression": "sbp >= 140 OR dbp >= 90",
        "level": "RED",
        "message": "血压异常升高",
        "action": "ALERT_NURSE"
    },
    {
        "id": "RULE_FETAL_DROP",
        "expression": "fetal_movement_current < fetal_movement_avg * 0.5",
        "level": "RED",
        "message": "胎动显著减少",
        "action": "ALERT_NURSE_AND_PATIENT"
    },
    {
        "id": "RULE_WEIGHT_GAIN",
        "expression": "weight_gain_weekly > 2.0",
        "level": "ORANGE",
        "message": "体重周增长过快",
        "action": "ALERT_NURSE"
    },
    {
        "id": "RULE_EMOTION_HIGH",
        "expression": "emotion_score_avg_7d >= 7",
        "level": "YELLOW",
        "message": "近7日情绪评分偏高，需关注心理状态",
        "action": "NOTE_NURSE"
    }
]
```

规则引擎在CPU上执行，每次数据写入时触发全量规则匹配，匹配结果写入事件总线。

### 3.4 排期引擎设计

```
输入：
  - 末次月经日期 (LMP)
  - 预产期 (EDD)
  - 当前孕周
  - 风险标签列表

处理流程 (CPU)：
  1. 根据LMP计算标准孕周节点
  2. 查找产科标准检查时间表，生成基础随访节点
     (12w/16w/20w/24w/28w/30w/32w/34w/36w/37w/38w/39w/40w)
  3. 风险联动调整：
     - 高风险(FGR/GDM/高血压) → B超间隔从4周→2周
     - FGR高风险 → 增加每周脐动脉血流监测节点
  4. 冲突检测 & 合并自定义节点
  5. 输出全周期排期JSON

输出：
  {
    "schedule": [
      {"gestWeek": 28, "date": "2026-05-01", "item": "OGTT糖耐量", "type": "routine"},
      {"gestWeek": 30, "date": "2026-05-15", "item": "B超生长监测", "type": "fgr_high_risk"},
      ...
    ]
  }
```

## 4. API设计

### 4.1 接口总览
| 模块 | 方法 | 路径 | 说明 |
|:---|:---|:---|:---|
| 对话 | POST | `/api/v1/chat/send` | 发送对话消息 |
| 对话 | GET | `/api/v1/chat/history` | 获取会话上下文（仅键值对） |
| 对话 | DELETE | `/api/v1/chat/memory` | 清除用户记忆 |
| 排期 | GET | `/api/v1/schedule/{patient_id}` | 获取排期 |
| 排期 | PUT | `/api/v1/schedule/{patient_id}` | 更新排期 |
| 排期 | POST | `/api/v1/schedule/{patient_id}/publish` | 发布排期 |
| 随访 | POST | `/api/v1/followup/trigger` | 触发自动随访 |
| 随访 | GET | `/api/v1/followup/records` | 随访记录列表 |
| 随访 | PUT | `/api/v1/followup/records/{id}/confirm` | 确认归档 |
| 预警 | GET | `/api/v1/alerts` | 预警列表 |
| 预警 | PUT | `/api/v1/alerts/{id}/review` | 审核预警 |
| FGR | POST | `/api/v1/fgr/assess` | FGR风险评估 |
| FGR | GET | `/api/v1/fgr/trend/{patient_id}` | FGR趋势数据 |
| 医嘱 | POST | `/api/v1/orders/generate` | 生成医嘱建议 |
| 医嘱 | PUT | `/api/v1/orders/{id}/sign` | 签署发布医嘱 |
| 统计 | GET | `/api/v1/dashboard` | 统计看板数据 |
| 监控 | GET | `/api/v1/monitor/hardware` | AMD硬件资源实时监控 |

### 4.2 对话接口设计
```
POST /api/v1/chat/send
Request:
{
  "patientId": "PT_ANON_HASH_001",
  "message": "我今天测了体重是65kg",
  "sessionId": "SESS_001",
  "messageType": "TEXT | IMAGE | VOICE"
}

Response (SSE流式):
event: thinking
data: {"agent": "xiao_an", "status": "processing"}

event: nlu_result
data: {"intent": "HEALTH_DATA_REPORT", "entities": {"weight": 65, "unit": "kg"}}

event: response
data: {"content": "收到啦，已帮您记录今天的体重：65kg。相比上周保持稳定，很棒哦！", "source": null}

event: complete
data: {"sessionId": "SESS_001", "memoryUpdated": ["last_weight_date: 2026-04-29"]}
```

### 4.3 FGR评估接口设计
```
POST /api/v1/fgr/assess
Request (multipart/form-data):
  - image: <DICOM_file>
  - gestationalWeeks: 28.5
  - imageType: "AC"  // HC | AC | FL | UA_Doppler

Response:
{
  "caseId": "CASE_001",
  "riskLevel": "high",
  "riskLabel": "高风险",
  "confidenceInterval": {"lowerBound": 0.82, "upperBound": 0.91},
  "explanation": "基于腹围增长滞后及血流阻力指数升高",
  "processingTime": 3200,  // NPU推理耗时(ms)
  "hardware": "NPU"
}
```

## 5. 数据模型设计

### 5.1 核心实体ER关系
```
Patient (匿名哈希ID)
  ├── 1:N → ScheduleNode (排期节点)
  ├── 1:N → FollowUpRecord (随访记录)
  ├── 1:N → HealthDataPoint (健康数据点)
  ├── 1:N → FgrAssessment (FGR评估记录)
  ├── 1:N → Alert (预警记录)
  └── 1:N → MedicalOrder (医嘱)

Patient {
  patient_id: string (匿名哈希, PK)
  gestational_age: int (孕周天数)
  lmp_date: date (末次月经)
  edd: date (预产期)
  risk_tags: string[] (风险标签列表)
  created_at: datetime
}

HealthDataPoint {
  id: uuid (PK)
  patient_id: string (FK)
  metric_code: string (指标代码: weight/sbp/dbp/fetal_movement/...)
  value: float
  unit: string
  recorded_at: datetime
  source: enum (PATIENT_REPORT | NURSE_INPUT | AUTO_FOLLOWUP)
}

FgrAssessment {
  id: uuid (PK)
  patient_id: string (FK)
  image_hash: string (脱敏B超图片哈希)
  image_type: enum (HC|AC|FL|UA_DOPPLER)
  gestational_weeks: float
  risk_level: enum (low|medium|high|critical)
  confidence_lower: float
  confidence_upper: float
  explanation: string
  processing_time_ms: int
  assessed_at: datetime
}

Alert {
  id: uuid (PK)
  patient_id: string (FK)
  trigger_source: enum (RULE_ENGINE | FGR_ALGORITHM | MANUAL)
  rule_id: string (可选)
  level: enum (RED | ORANGE | YELLOW)
  message: string
  status: enum (PENDING | CONFIRMED | DISMISSED)
  reviewed_by: string
  reviewed_at: datetime
}
```

## 6. 安全架构

### 6.1 数据安全分层
```
第一层·网络隔离
  - 核心AI推理仅监听 localhost
  - 前端至后端API强制TLS (内网可配置降级)
  - VPN/内网部署，核心数据不暴露公网

第二层·数据脱敏
  - 患者身份: 单向哈希(HMAC-SHA256, 密钥本地保管)
  - B超影像: DICOM header清洗 + 文件哈希存储
  - 对话内容: NLU解析后立即丢弃原文，仅存结构化结果

第三层·访问控制
  - RBAC: 孕妇/护士/医生/管理员四级权限
  - 孕妇仅能访问自身数据
  - 医护只能访问所辖科室患者数据
  - 跨角色数据访问需二次授权

第四层·审计追溯
  - 所有关键操作记录审计日志
  - 日志包含: 操作人、操作类型、时间戳、操作对象ID
  - 日志本地存储，定期滚动
```

### 6.2 端侧推理安全
```
┌────────────────────────────────────────────┐
│          AMD 端侧平台 (信任边界)              │
│                                            │
│  ┌──────┐  ┌──────┐  ┌──────────────┐     │
│  │ GPU  │  │ NPU  │  │ 业务服务+API  │     │
│  │ 推理  │  │ 推理  │  │              │     │
│  └──┬───┘  └──┬───┘  └──────┬───────┘     │
│     │         │              │             │
│     └─────────┴──────────────┘             │
│               │                            │
│        ┌──────┴──────┐                     │
│        │ 统一内存(UMA)│                     │
│        │ 数据不落盘   │                     │
│        └─────────────┘                     │
│                                            │
│  ★ 所有数据在此边界内处理，不传输至外部        │
└────────────────────────────────────────────┘

数据生命周期:
  输入 → UMA加载 → GPU/NPU推理 → 结构化结果提取 → 原文丢弃 → 结果入本地DB
```

## 7. 部署架构

### 7.1 开发阶段部署（当前）
```
┌─────────────────────────────────────────────────────┐
│          开发环境 - 任意PC/笔记本                      │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │ Docker Compose                              │    │
│  │                                             │    │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────────┐ │    │
│  │  │ 前端(Nginx)│ │ 后端(FastAPI)│ │ PostgreSQL │ │    │
│  │  │ Port:3000 │ │ Port:8000  │ │ Port:5432   │ │    │
│  │  └──────────┘ └──────────┘ └─────────────┘ │    │
│  │  ┌──────────┐                              │    │
│  │  │ Redis    │                              │    │
│  │  │ Port:6379│                              │    │
│  │  └──────────┘                              │    │
│  └─────────────────────────────────────────────┘    │
│                                                      │
│  大模型调用: 云端API (如 DeepSeek/Qwen API)           │
│  FGR算法: Mock服务 (返回预设JSON)                     │
│  NLU: 云端API / 正则规则混合                          │
│  数据: Mock数据 + 种子脚本填充                         │
└─────────────────────────────────────────────────────┘
```

#### 7.1.1 LLM调用抽象层（适配开发/竞赛双模式）
```python
# backend/app/core/llm_client.py
from abc import ABC, abstractmethod

class LLMClient(ABC):
    """大模型调用抽象基类，开发/竞赛模式切换不改业务代码"""
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str: ...
    @abstractmethod
    async def chat_stream(self, messages: list[dict], **kwargs): ...

class CloudAPIClient(LLMClient):
    """开发阶段：云端API"""
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def chat(self, messages, **kwargs):
        resp = await self.client.chat.completions.create(
            model=self.model, messages=messages, **kwargs
        )
        return resp.choices[0].message.content

    async def chat_stream(self, messages, **kwargs):
        stream = await self.client.chat.completions.create(
            model=self.model, messages=messages, stream=True, **kwargs
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

class LocalOllamaClient(LLMClient):
    """竞赛阶段：本地GPU Ollama推理"""
    def __init__(self, host: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.host = host
        self.model = model

    async def chat(self, messages, **kwargs):
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.host}/api/chat", json={
                "model": self.model, "messages": messages,
                "stream": False, "options": kwargs
            })
            return resp.json()["message"]["content"]

    async def chat_stream(self, messages, **kwargs):
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", f"{self.host}/api/chat", json={
                "model": self.model, "messages": messages,
                "stream": True, "options": kwargs
            }) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        data = json.loads(line)
                        if data.get("message", {}).get("content"):
                            yield data["message"]["content"]

# 工厂函数，通过环境变量切换
def get_llm_client() -> LLMClient:
    if os.getenv("LLM_MODE", "cloud") == "local":
        return LocalOllamaClient(model=os.getenv("LOCAL_MODEL", "qwen2.5:7b"))
    return CloudAPIClient(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        model=os.getenv("LLM_MODEL", "deepseek-chat")
    )
```

#### 7.1.2 Mock数据方案
```
Mock数据分层：

孕妇数据 (20条模拟用户)
├── 不同孕周分布: 12w/16w/20w/24w/28w/32w/36w (各2-3人)
├── 不同风险标签: 正常/FGR高危/GDM/高血压
└── 健康数据时间序列: 体重、血压、胎动 (按孕周增长的合理曲线)

排期数据
├── 标准产科检查排期 (根据孕周自动计算)
└── 风险联动排期 (FGR高危用户自动增加B超节点)

FGR评估记录 (Mock)
├── 风险分布: low(40%) / medium(30%) / high(20%) / critical(10%)
├── 置信区间模拟: 正态分布采样
└── 趋势模拟: 随孕周风险逐渐升高的合理趋势

预警数据
├── 规则引擎触发: 血压异常(3条) / 胎动骤降(2条) / 体重异常(2条)
└── FGR算法触发: 中/高/极高 各若干条

医嘱模板数据
├── FGR高风险+孕周<34w → 收治入院模板
├── FGR中风险+孕周≥34w → 复查B超模板
└── 高血压 → 降压监测模板

Mock数据注入方式:
  backend/scripts/
  ├── seed_patients.py      # 生成20条匿名孕妇
  ├── seed_schedules.py     # 生成全孕周排期
  ├── seed_health_data.py   # 生成健康指标时间序列
  ├── seed_fgr_assessments.py  # 生成FGR评估Mock记录
  └── seed_alerts.py        # 生成预警记录
```

#### 7.1.3 开发环境配置
```bash
# .env (开发阶段)
LLM_MODE=cloud
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

FGR_MODE=mock              # mock | npu
NLU_MODE=hybrid            # cloud | npu | hybrid

DB_HOST=localhost
DB_PORT=5432
REDIS_HOST=localhost

# Mock数据开关
SEED_DATA=true             # 首次启动自动填充Mock数据
```

### 7.2 竞赛阶段部署（AMD端侧）
```
┌──────────────────────────────────────────────────────┐
│        AMD 锐龙 AI Max+ 395 - 单机全栈                 │
│                                                       │
│  ┌──────────────────────────────────────────────┐    │
│  │ Docker Compose 容器编排                        │    │
│  │                                               │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │    │
│  │  │ 前端(Nginx)│ │ 后端(FastAPI)│ │ Ollama(GPU) │  │    │
│  │  │ Port:80   │ │ Port:8000  │ │ Port:11434  │  │    │
│  │  └──────────┘ └──────────┘ └──────────────┘  │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │    │
│  │  │ PostgreSQL│ │ Redis    │ │ ChromaDB     │  │    │
│  │  │ Port:5432 │ │ Port:6379│ │ Port:8001    │  │    │
│  │  └──────────┘ └──────────┘ └──────────────┘  │    │
│  │  ┌──────────────────────────────────────┐    │    │
│  │  │ FGR NPU推理服务 (ONNX Runtime)        │    │    │
│  │  │ Port:8002                            │    │    │
│  │  └──────────────────────────────────────┘    │    │
│  └──────────────────────────────────────────────┘    │
│                                                       │
│  ★ 所有服务均绑定 localhost 或内网IP                    │
└──────────────────────────────────────────────────────┘
```

### 7.3 Docker Compose 配置要点
```yaml
# docker-compose.yml 核心服务定义
services:
  backend:
    build: ./backend
    ports: ["127.0.0.1:8000:8000"]
    environment:
      - OLLAMA_HOST=http://ollama:11434
      - NPU_SERVICE_HOST=http://fgr-npu:8002
      - DB_HOST=postgres
      - REDIS_HOST=redis
    depends_on: [postgres, redis, ollama, fgr-npu]
    # GPU设备映射
    devices:
      - /dev/kfd:/dev/kfd  # AMD GPU设备
      - /dev/dri:/dev/dri  # 渲染节点

  ollama:
    image: ollama/ollama:rocm
    ports: ["127.0.0.1:11434:11434"]
    devices:
      - /dev/kfd:/dev/kfd
      - /dev/dri:/dev/dri
    volumes:
      - ./models:/root/.ollama

  fgr-npu:
    build: ./fgr-inference
    ports: ["127.0.0.1:8002:8002"]
    devices:
      - /dev/ipu0:/dev/ipu0  # AMD NPU设备
    volumes:
      - ./fgr-models:/models
```

## 8. 关键技术决策记录

| 决策 | 选项A | 选项B | 选择 | 理由 |
|:---|:---|:---|:---|:---|
| 大模型推理框架 | Ollama | VLLM | Ollama | AMD ROCm原生支持更好，部署简单，竞赛环境够用 |
| 向量数据库 | ChromaDB | Qdrant | ChromaDB | 嵌入式部署，零运维，内存占用小 |
| NPU推理框架 | ONNX Runtime | PyTorch Direct | ONNX Runtime | 跨平台兼容，AMD Ryzen AI SDK原生支持 |
| 量化精度 | INT4 | INT8 | INT4(大模型) / INT8(小模型) | 大模型INT4在128GB UMA下可加载更多模型 |
| 前端框架 |  | Vue3 | | |
| API协议 | REST | gRPC | REST为主 + SSE流式 | 前端兼容性好，调试方便 |
