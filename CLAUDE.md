# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

**AI-Care 孕期智能管理平台** — 基于 AMD 锐龙 AI MAX+ 平台的多角色智能医疗辅助系统，集成 LLM、ASR、TTS、RAG 和 FGR 专病评估模型。

## 核心架构

**后端 (FastAPI + Agno SDK)**
- 分层: Router → Service → Core (AI Engine) → Model (ORM)
- 依赖注入: `backend/app/container.py` 管理服务实例
- 配置: pydantic-settings，支持 `.env` 文件
- **医嘱生成双路径**: REST API (`POST /orders/generate`) 直接调 LLM+模板+RAG 快速生成草稿；Agent 对话路径 (`doctor/chat/stream`) 经 NLU 意图路由+工具链生成，支持多轮推理和知识检索。两条路径均集成了 RAG 临床知识检索，RAG 不可用时静默降级。

**多智能体系统 (Agno v2.6.9)**
- 三角色 Agent: 小安(孕妇) / 小护(护士) / Dr.智(医生)
- NLU 意图驱动动态工具注入: `Agent.tools` 可变属性，Router 层根据 NLU 结果选择工具子集
- 流式输出: chat 变体无 `output_schema`，保持 SSE 逐 chunk 推送；结构化输出用 `arun(output_schema=...)` 运行时覆盖
- Agent 工厂全部 `@lru_cache(maxsize=1)` 单例复用，session_state 按 session_id 隔离
- **安全护栏 (全角色)**: 所有 Agent 均注入 `pre_hooks=[EmergencyGuardrail()]` (紧急检测)，孕妇/护士 `post_hooks=[MedicalSafetyGuardrail/NurseSafetyGuardrail]` (输出拦截)，医生 `post_hooks=[DoctorDraftGuardrail]` (草稿安全)
- 会话持久化: PostgreSQL 优先，回退 SQLite
- SSE 前端自动重连: 最多重试 2 次，指数退避

**智能体工具系统** (`backend/app/core/tools/`)
- 子包拆分: `nlu_tools` / `health_data_tools` / `vital_rules_tools` / `nurse_tools` / `doctor_tools` / `routing` / `common`
- 当前 **16 个 @tool** 函数，按角色硬隔离: `MEDICAL_TOOLS`(8) / `NURSE_TOOLS`(6) / `DOCTOR_TOOLS`(8)，共享 2 个通用工具 (`analyze_health_trends`, `evaluate_vital_rules`)
- 工具路由: `routing.py` — NLU 意图 → 工具子集 + variant 名称，运行时 `agent.tools = subset` 动态注入
- 知识检索 (RAG) 条件化: analyze/chat 变体开启 `search_knowledge=True`，followup/report/order/issue 变体关闭以减少 token 浪费
- chat-full 变体 (NLU 兜底): nurse `tool_call_limit=5` (6 tools)，doctor `tool_call_limit=6` (8 tools)
- **工具可观测性**: `common.py` → `ToolMetrics` 全局单例 `tool_metrics`；每个 @tool 函数入口 `_t0 = time.perf_counter()` + 出口 `record(name, duration_ms)`；per-session 增量通过 `start_session()`/`end_session()` → `AuditService.save_log(tool_metrics_session=…)` 持久化到 `AgentAuditLog.tool_metrics_json` + `ToolCallDetail.latency_ms`
- **工作流**: 孕妇端 `prenatal_workflow` (症状/检查) + 孕期日记 API `GET /{pid}/diary`；护士端 `nurse_workflow` (分析→评估上报)；医生端 `doctor_workflow` (分析→指南→医嘱)

**前端 (Vue 3 + TypeScript + Element Plus)**
- 四角色端: 孕妇端、护士端、医生端、管理端
- 状态管理: Pinia
- 语音交互: useAudioRecorder + useTTS 组合式函数

**认证 (JWT)**
- 全局 `AuthMiddleware` (`main.py`): 所有请求必须携带 `Authorization: Bearer <token>`
- 白名单路径 (`_PUBLIC_PATHS`): `/`, `/health`, `/docs`, `/openapi.json`, `/redoc`, `/api/v1/auth/login`
- 白名单前缀 (`_PUBLIC_PREFIXES`): `/api/v1/fgr/image/` (图片无 auth 访问), `/ws/` (WebSocket 自行校验 token)
- 前端 axios 拦截器自动附加 token; SSE 使用 `fetchEventSource` 手动附加; WebSocket 通过 query param `?token=` 传递
- 踩坑: `<img src>` 无法携带 header，二进制端点必须加 `_PUBLIC_PREFIXES`; WebSocket 不支持 header，token 走 query param

**硬件加速策略**
- GPU (ROCm): LLM 推理 (Qwen3.6-35B)、BGE-M3、TTS
- NPU (XDNA): ASR 语音识别 (FunASR + VitisAI EP)
- CPU: 调度、前后处理、逻辑控制

## 常用命令

**一键启动 (推荐)**
```bash
cd pregnent_care_agent/pregnant_care_agent
bash start.sh                    # 启动所有服务
bash start.sh --no-ai            # 跳过 AI 服务
bash start.sh stop               # 停止所有服务
bash start.sh status             # 查看服务状态
bash start.sh reload             # 仅重启前后端
```

**AI 服务启动 (工作区根目录)**
```bash
bash start_services_safe.sh              # 安全启动所有 AI 服务
bash start_services_safe.sh --npu        # ASR 使用 NPU 加速
bash start_services_safe.sh --cpu        # ASR 使用 CPU
```

**后端开发**
```bash
cd pregnent_care_agent/pregnant_care_agent/backend
python run.py                    # 启动开发服务器 (端口 9999)
RELOAD=1 python run.py           # 热重载模式
pytest                           # 运行后端测试
pytest tests/test_agno_agent.py  # 运行单个测试文件
pytest -k "test_name"            # 运行匹配的测试
```

**前端开发**
```bash
cd pregnent_care_agent/pregnant_care_agent/frontend
npm install                      # 安装依赖
npm run dev                      # 启动开发服务器 (端口 3000)
npm run build                    # 生产构建
npm run test                     # 运行测试
npm run test:watch               # 监听模式测试
```

**资源管理**
```bash
python3 dynamic_resource_manager.py --policy balanced    # 平衡策略
python3 dynamic_resource_manager.py --policy performance # 性能优先
bash resource_monitor.sh                                 # 实时资源监控
```

## 端口分配

| 服务 | 端口 |
|------|------|
| PostgreSQL | 5432 |
| Redis | 6379 |
| LLM (llama-server) | 8080 |
| BGE-M3 Embedding | 8081 |
| TTS (CosyVoice2) | 9880 |
| ASR (FunASR) | 10096 |
| Backend (FastAPI) | 9999 |
| Frontend (Vite) | 3000 |

## 关键目录结构

```
pregnent_care_agent/pregnant_care_agent/
├── backend/
│   ├── app/
│   │   ├── core/           # AI 引擎 (Agent/RAG/NLU/LLM)
│   │   │   ├── tools/       # 16 个 @tool 函数 (nlu/health/nurse/doctor/routing/common)
│   │   ├── data/           # 结构化参考数据 (40周孕期知识库等)
│   │   ├── models/         # SQLAlchemy ORM 模型
│   │   ├── routers/        # 22个 API 路由模块
│   │   ├── schemas/        # Pydantic 数据校验
│   │   ├── services/       # 28个业务逻辑服务
│   │   └── main.py         # FastAPI 应用入口
│   ├── fgr_compete/        # FGR 专病评估 (nnU-Net + ONNX)
│   ├── alembic/            # 数据库迁移
│   └── tests/              # 后端测试 (46个测试文件)
├── frontend/
│   └── src/
│       ├── api/            # API 请求层
│       ├── views/          # 页面组件 (4个角色端)
│       ├── components/     # 通用 UI 组件
│       ├── composables/    # Vue 组合式函数
│       └── stores/         # Pinia 状态管理
├── embedding_server/       # BGE-M3 向量嵌入服务
└── tts_server/             # CosyVoice2 TTS 服务
```

## LLM 配置

支持四种模式，每个角色可独立配置:
- `cloud`: DashScope/DeepSeek API
- `local`: Ollama 本地模型或 llama-server
- `mixed`: cloud → local → mock 自动降级
- `mock`: 模拟响应 (开发测试)

配置位置: `backend/app/config.py`

## 测试结构

**后端测试** (pytest): `backend/tests/`
- Agent 测试: test_agno_agent, test_agno_tools (含工具路由+计数), test_agno_team, test_agent_optimization (动态注入+NLU路由)
- 工具测试: test_refactored_components (工具拆分验证), test_agno_medical_agents (护士/医生 Agent)
- 审计测试: test_audit_log, test_audit_integration (含 tool_metrics 持久化验证)
- 业务逻辑: test_followup_fixes, test_alert_service, test_order_service
- API 测试: test_bugfix_routes, test_orders_router (含 RAG 辅助生成测试)

**前端测试** (Vitest): 各组件目录的 `__tests__/` 子目录

**运行测试**
```bash
# 后端
cd pregnent_care_agent/pregnant_care_agent/backend
pytest tests/test_agno_agent.py -v

# 前端
cd pregnent_care_agent/pregnant_care_agent/frontend
npm run test
```

## 数据库

- 开发: SQLite (自动创建)
- 生产: PostgreSQL 16 + pgvector
- 迁移: Alembic (`backend/alembic/`)
- 双模式兼容: `main.py` 中的 `_ensure_*()` 函数处理已有数据库的表/列增量迁移
- 孕期日记缓存: `pregnancy_diary_entries` 表，每人每周一条，LLM 叙事 + 模板兜底

## 环境变量

主要配置通过 `.env` 文件或环境变量设置，详见 `backend/app/config.py`:
- `DATABASE_URL`: 数据库连接字符串
- `LLM_MODE`: cloud/local/mixed/mock
- `DASHSCOPE_API_KEY`: 阿里云 DashScope API 密钥
- `JWT_SECRET_KEY`: JWT 认证密钥 (多 worker 部署必须统一设置)
