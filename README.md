# AI-Care 孕期智能管理平台

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128.0-009688.svg)](https://fastapi.tiangolo.com)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

基于AMD锐龙AI Max+平台的孕期智能管理平台，通过通用大模型（Qwen/DeepSeek）结合医学知识库RAG增强，集成FGR专病风险评估模块，提供孕妇端、护士端、医生端三端协同的智能医疗辅助服务。

> **声明**：本系统仅用于科研教学辅助，不替代临床诊断、不提供治疗决策。

## 核心特性

- **Agno多智能体框架**：基于Agno SDK构建，孕妇端（健康咨询/情绪陪伴）、护士端（随访管理/排期）、医生端（FGR预警/医嘱辅助）三端协同，16个@tool函数按角色硬隔离
- **RAG知识检索**：基于pgvector的混合检索（向量+关键词），结合40周孕期知识库与医学知识库增强LLM回答的专业准确性
- **语音交互**：集成ASR语音识别（FunASR/Whisper/DashScope）与TTS语音合成（CosyVoice），支持全语音对话
- **NLU意图识别**：规则引擎+LLM混合模式，支持紧急情况检测、情绪分析与动态工具路由
- **FGR风险评估**：胎儿生长受限专病评估模块，支持多后端推理（PyTorch/ONNX/ROCm/NPU），集成胎盘分割（nnU-Net）与超声图像分析
- **产检排期引擎**：基于ACOG/中华医学会指南的硬编码规则引擎，覆盖13次标准产检 + 5个超声里程碑 + 8项速查参考，联动风险标签（FGR/GDM/高血压）自动加密监测
- **随访排期推荐**：纯规则引擎五维度优先级判定（告警/逾期/数据活跃度/孕周/风险标签），输出高/中/低三档紧急度
- **医嘱生命周期管理**：AI辅助生成（RAG增强+LLM模板）、签署（手写签名+归档快照）、软删除（保障医疗记录完整性）
- **安全护栏**：全角色紧急检测护栏 + 角色级输出安全拦截 + JWT认证全局中间件
- **端侧部署优先**：支持Ollama本地模型+FunASR本地识别，医疗数据本地处理，保护隐私

## 技术栈

### 后端
- **框架**：FastAPI + SQLAlchemy + Pydantic
- **Agent框架**：Agno SDK（多智能体编排、工具调用、工作流引擎）
- **数据库**：PostgreSQL + pgvector（向量检索）/ SQLite（开发模式）
- **缓存**：Redis
- **LLM**：Qwen3.5-35b（DashScope）/ DeepSeek API / Ollama本地模型（Qwen2.5-7B）
- **向量模型**：BAAI/bge-m3 / DashScope text-embedding-v3
- **ASR**：FunASR（本地）/ Whisper / DashScope（云端）
- **TTS**：CosyVoice（端侧语音合成）

### 前端
- **框架**：Vue 3 + TypeScript + Vite
- **UI**：Element Plus
- **图表**：ECharts
- **状态管理**：Pinia

### 基础设施
- **容器化**：Docker + Docker Compose
- **反向代理**：Nginx

## 项目结构

```
pregnant_care_agent/
│
├── backend/                          # 后端服务（FastAPI）
│   ├── app/
│   │   ├── core/                     # 核心引擎模块（Agent/RAG/NLU/规则引擎等）
│   │   ├── models/                   # 数据模型层（ORM模型）
│   │   ├── routers/                  # API路由层
│   │   ├── schemas/                  # Pydantic数据校验
│   │   ├── services/                 # 业务逻辑层
│   │   ├── scripts/                  # 数据初始化脚本
│   │   ├── config.py                 # 应用配置（环境变量管理）
│   │   ├── database.py               # 数据库连接（SQLAlchemy）
│   │   └── main.py                   # FastAPI应用入口
│   │
│   ├── fgr_compete/                  # FGR专病评估模块
│   ├── knowledge_docs/               # 医学知识库（向量化前的原始文档）
│   ├── tests/                        # 后端测试
│   ├── .env.example                  # 环境变量示例
│   ├── Dockerfile                    # 后端容器镜像
│   ├── run.py                        # 开发服务器启动
│   └── requirements.txt              # Python依赖
│
├── frontend/                         # 前端应用（Vue 3 + TypeScript）
│   ├── src/
│   │   ├── api/                      # API请求层
│   │   ├── views/                    # 页面组件（孕妇/护士/医生端）
│   │   ├── components/               # 通用UI组件
│   │   ├── router/                   # 路由配置
│   │   ├── stores/                   # 状态管理（Pinia）
│   │   └── utils/                    # 工具函数
│   ├── public/                       # 静态资源
│   ├── nginx.conf                    # Nginx配置
│   ├── Dockerfile                    # 前端容器镜像
│   └── package.json                  # Node依赖
│
├── embedding_server/                 # 向量嵌入服务（BGE-M3）
├── tts_server/                       # TTS语音合成服务
│
├── docker-compose.yml                # 容器编排
├── start.sh                          # 一键启动脚本
└── README.md                         # 项目说明
```

### 核心模块说明

| 模块 | 路径 | 说明 |
|------|------|------|
| **Agno智能体** | `backend/app/core/agno_agent.py` | 基于Agno SDK的多Agent编排，支持工具调用、团队协作与工作流 |
| **安全护栏** | `backend/app/core/agno_guardrails.py` | 全角色紧急检测护栏 + 角色级输出安全拦截 |
| **LLM客户端** | `backend/app/core/llm_client.py` | 封装DashScope/DeepSeek/Ollama调用，支持cloud/local/mixed/mock四种模式 |
| **NLU引擎** | `backend/app/core/nlu_engine.py` | 规则+LLM混合意图识别，支持紧急检测、情绪分析与工具路由 |
| **RAG知识库** | `backend/app/core/agno_knowledge.py` | 基于pgvector的混合检索（向量+关键词），医学知识增强生成 |
| **产检排期引擎** | `backend/app/services/schedule_engine.py` | ACOG/中华医学会指南硬编码规则引擎，13次标准产检 + 5个超声里程碑 |
| **随访排期推荐** | `backend/app/routers/nurse_ai.py` | 五维度优先级判定规则引擎（告警/逾期/数据活跃度/孕周/风险标签） |
| **医嘱服务** | `backend/app/services/order_service.py` | 医嘱AI辅助生成（RAG增强）+ 签署（手写签名归档）+ 软删除生命周期管理 |
| **ASR服务** | `backend/app/interfaces/asr_backend.py` | 语音识别接口，支持FunASR/Whisper/DashScope多后端 |
| **TTS服务** | `backend/app/interfaces/tts_backend.py` | 语音合成接口，集成CosyVoice端侧TTS |
| **对话路由** | `backend/app/routers/chat.py` | 孕妇智能问答核心接口，集成NLU/RAG/记忆管理 |
| **FGR评估** | `backend/app/routers/fgr.py` | 胎儿生长受限风险评估，支持PyTorch/ONNX/ROCm多后端 |
| **孕期日记** | `backend/app/services/pregnancy_diary.py` | 每周孕期叙事，LLM生成 + 40周知识库驱动 + 模板兜底 |

## 快速开始

### 环境要求

- Docker & Docker Compose
- Node.js 18+（本地开发）
- Python 3.10+（本地开发）

### Docker部署（推荐）

```bash
# 1. 克隆项目
git clone git@github.com:betterway614/pregnant_care_agent.git
cd pregnant_care_agent

# 2. 配置环境变量（可选）
cp backend/.env.example backend/.env
# 编辑 .env 配置LLM API Key等

# 3. 启动服务
docker-compose up -d

# 4. 访问应用
# 前端：http://localhost:3000
# 后端API：http://localhost:8000
# API文档：http://localhost:8000/docs
```

### 本地开发

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py

# 前端
cd frontend
npm install
npm run dev
```

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_MODE` | LLM模式：cloud/local/mock/mixed | cloud |
| `LLM_API_KEY` | LLM API密钥（DashScope/DeepSeek） | - |
| `LLM_BASE_URL` | LLM API地址 | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| `LLM_MODEL` | LLM模型名称 | qwen3.5-35b-a3b |
| `AGNO_ENABLED` | 启用Agno智能体框架 | true |
| `FGR_MODE` | FGR算法开关：true/false | true |
| `FGR_BACKEND` | FGR推理后端：pytorch/onnx_igpu/onnx_npu/onnx_cpu | pytorch |
| `DB_TYPE` | 数据库类型：sqlite/postgres | sqlite |
| `DB_NAME` | 数据库名称 | ai_care |
| `RAG_ENABLED` | 启用RAG检索 | true |
| `RAG_SEARCH_TYPE` | RAG检索方式：hybrid/vector/keyword | hybrid |
| `EMBEDDING_MODEL` | 向量嵌入模型 | text-embedding-v3 |
| `ASR_MODE` | ASR模式：local/cloud | cloud |
| `JWT_SECRET_KEY` | JWT签名密钥 | - |

### LLM模式说明

- **cloud**：使用云端API（通义千问 DashScope / DeepSeek）
- **local**：使用Ollama本地模型（Qwen2.5-7B等）
- **mixed**：cloud→local→mock 自动降级链，保证服务可用性
- **mock**：模拟响应（开发测试用）

## API接口

### 核心接口

| 模块 | 端点 | 说明 |
|------|------|------|
| 认证 | `POST /api/auth/login` | 用户登录 |
| 聊天 | `POST /api/chat` | 孕妇智能问答（支持语音，SSE流式推送） |
| 随访 | `POST /api/followup` | 随访管理与AI智能排期推荐 |
| 预警 | `GET /api/alerts` | 高危预警列表（角色数据隔离） |
| FGR | `POST /api/fgr/assess` | FGR风险评估（多后端推理） |
| 产检排期 | `GET /api/schedule` | 产检日程管理（护士生成→发布→孕妇同步） |
| 医嘱 | `POST /api/orders/generate` | AI医嘱生成（RAG增强） |
| 医嘱签署 | `PUT /api/orders/{id}/sign` | 医嘱签署（手写签名 + 归档快照） |
| 医嘱删除 | `DELETE /api/orders/{id}` | 医嘱软删除（保障医疗记录完整性） |
| 孕期日记 | `GET /api/{pid}/diary` | 孕期周记（LLM叙事 + 40周知识库驱动） |
| 仪表盘 | `GET /api/dashboard` | 数据统计看板（模块独立加载） |
| 健康趋势 | `GET /api/health-trends` | 健康数据趋势分析 |
| 心理评估 | `POST /api/mental-health` | 心理健康评估 |
| 知识库 | `GET /api/knowledge` | 医学知识库管理 |
| TTS | `POST /api/tts/synthesize` | 语音合成 |
| WebSocket | `WS /ws/chat` | 实时对话推送 |

完整API文档请访问：`http://localhost:8000/docs`

## 功能模块

### 孕妇端
- 智能健康咨询（RAG增强，支持语音输入/输出，全面去预警化温和措辞）
- 产检日程管理与提醒（基于LMP动态推算，已发布排期自动同步）
- 健康数据记录（体重/血压/胎动/健康趋势，NLU自动提取）
- 情绪陪伴与心理评估
- 孕期日记（LLM叙事 + 模板兜底，每周一条，40周知识库驱动每周变化内容）
- 胎动计数工具
- 患者主题页面（背景矢量图 + 视觉升级）

### 护士端
- 随访任务管理与AI智能排期推荐（五维度优先级：告警/逾期/数据活跃度/孕周/风险标签）
- 高危预警处理与升级（角色数据隔离，规则消息源统一）
- 孕妇健康趋势追踪
- 随访记录自动生成（结构化详情展示）
- 产检排期管理（护士生成→发布→孕妇端自动同步）

### 医生端
- FGR风险看板与多维数据分析（胎儿生长受限看板重构，响应速度优化 + 移动端适配）
- AI辅助医嘱生成（RAG增强 + LLM模板 + Markdown渲染）、签署（手写签名 + 归档快照）、软删除
- 病例审核工作台
- 仪表盘数据独立加载（杜绝单一模块故障引发整体连锁崩溃）
- WebSocket实时数据推送

### 管理端
- 审计日志查询（含工具调用会话记录，支持按会话ID查询）
- 系统监控与数据统计

## 模型权重文件说明

### FGR 专病评估模型

FGR 风险评估模块依赖以下预训练模型权重文件，由于文件过大（单个模型文件数百MB）且受 GitHub LFS 限制，**未包含在 Git 仓库中**。`.gitignore` 中已排除以下文件类型：

| 排除规则 | 说明 |
|----------|------|
| `backend/fgr_compete/**/*.pth` | PyTorch 模型权重（ResNet 5折模型 + nnU-Net 胎盘分割模型） |
| `backend/fgr_compete/**/*.pt` | PyTorch 跟踪/脚本模型 |
| `backend/fgr_compete/**/*.ckpt` | PyTorch Lightning 检查点 |
| `backend/fgr_compete/**/*.safetensors` | SafeTensors 格式权重 |
| `backend/fgr_compete/onnx_resnet/*.onnx` | ONNX 导出模型（ROCm NPU 推理） |
| `backend/fgr_compete/cache/` | 推理缓存目录 |
| `backend/fgr_compete/uploads/` | 上传的超声图像 |
| `backend/fgr_compete/diagnostic_reports/` | 生成的诊断报告 |
| `backend/fgr_compete/photo/` | 患者照片 |
| `backend/fgr_compete/_vendor/` | 第三方依赖（ONNX Runtime 等） |

### 获取模型权重

运行项目前需将模型权重文件放入对应目录。目录结构和模型权重获取方式请参考：

```
backend/fgr_compete/
├── 0.701_515pth/                    # PyTorch ResNet 5折模型 (resnet_v9_best_fold{1-5}.pth)
├── onnx_resnet/                       # ONNX 模型 (resnet_v9_best_fold{1-5}.onnx)
└── Dataset001_PlacentaNT/
    └── nnUNetTrainer__nnUNetPlans__2d/
        └── fold_{0-4}/
            └── checkpoint_final.pth   # nnU-Net 胎盘分割 5折模型
```

> **注意**：未放置模型权重文件时，FGR 相关接口将返回错误提示。如需本地开发测试，可将 `FGR_MODE=false` 或 `FGR_BACKEND=mock` 临时禁用 FGR 模块。

## 开发指南

### 添加新路由

```python
# backend/app/routers/xxx.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/xxx", tags=["xxx"])

@router.get("/")
async def list_items():
    return {"items": []}
```

在 `main.py` 中注册：

```python
from .routers import xxx
app.include_router(xxx.router)
```

### 知识库导入

将医学文档放入 `backend/knowledge_docs/` 目录，支持格式：
- PDF
- Word (.docx)
- Markdown (.md)
- 纯文本 (.txt)

## 许可证

MIT License

## 免责声明

本系统输出结果仅供参考，不能替代专业医疗诊断。任何健康问题请咨询正规医疗机构。
