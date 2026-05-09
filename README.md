# AI-Care 孕期智能管理平台

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128.0-009688.svg)](https://fastapi.tiangolo.com)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

基于AMD锐龙AI Max+平台的孕期智能管理平台，集成通用医疗大模型与专科FGR评估算法，提供孕妇端、护士端、医生端三端协同的智能医疗辅助服务。

> **声明**：本系统仅用于科研教学辅助，不替代临床诊断、不提供治疗决策。

## 核心特性

- **三端协同智能体**：孕妇端（健康咨询/情绪陪伴）、护士端（随访管理/排期）、医生端（FGR预警/医嘱辅助）
- **RAG知识检索**：基于pgvector的向量检索，结合医学知识库增强LLM回答准确性
- **NLU意图识别**：规则引擎+LLM混合模式，支持紧急情况检测与情绪分析
- **FGR风险评估**：胎儿生长受限专病算法，支持多模态超声指标分析
- **本地推理优先**：支持Ollama本地模型，保护医疗数据隐私

## 技术栈

### 后端
- **框架**：FastAPI + SQLAlchemy + Pydantic
- **数据库**：PostgreSQL + pgvector（向量检索）/ SQLite（开发模式）
- **缓存**：Redis
- **LLM**：DeepSeek API / Ollama本地模型（Qwen2.5-7B）
- **向量模型**：BAAI/bge-m3

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
medical_agent1/
│
├── backend/                          # 后端服务（FastAPI）
│   ├── app/
│   │   ├── core/                     # 核心引擎模块
│   │   │   ├── llm_client.py         #   LLM客户端（DeepSeek/Ollama/Mock）
│   │   │   ├── nlu_engine.py         #   NLU意图识别引擎（规则+LLM混合）
│   │   │   ├── rag_engine.py         #   RAG检索增强生成引擎
│   │   │   ├── embedding.py          #   向量嵌入服务
│   │   │   ├── memory_manager.py     #   对话记忆管理
│   │   │   ├── rule_engine.py        #   规则引擎（业务逻辑）
│   │   │   └── followup_tools.py     #   随访工具集
│   │   │
│   │   ├── models/                   # 数据模型层
│   │   │   ├── models.py             #   核心业务模型（孕妇/护士/医生/随访等）
│   │   │   └── vector_models.py      #   向量数据库模型（知识库文档块）
│   │   │
│   │   ├── routers/                  # API路由层
│   │   │   ├── auth.py               #   用户认证（JWT登录）
│   │   │   ├── chat.py               #   孕妇智能问答（核心对话接口）
│   │   │   ├── pregnant.py           #   孕妇信息管理
│   │   │   ├── schedule.py           #   产检排期管理
│   │   │   ├── followup.py           #   随访任务管理
│   │   │   ├── alerts.py             #   高危预警管理
│   │   │   ├── fgr.py                #   FGR风险评估
│   │   │   ├── orders.py             #   医嘱管理
│   │   │   ├── dashboard.py          #   数据统计看板
│   │   │   ├── monitor.py            #   健康监测数据
│   │   │   ├── fetal_movement.py     #   胎动记录管理
│   │   │   ├── recommend.py          #   健康建议推荐
│   │   │   ├── nurse_ai.py           #   护士端AI助手
│   │   │   └── doctor_ai.py          #   医生端AI助手
│   │   │
│   │   ├── schemas/                  # Pydantic数据校验
│   │   │   └── schemas.py            #   请求/响应模型定义
│   │   │
│   │   ├── services/                 # 业务逻辑层
│   │   │   ├── followup_service.py   #   随访业务服务
│   │   │   ├── order_service.py      #   医嘱业务服务
│   │   │   └── schedule_engine.py    #   排期引擎
│   │   │
│   │   ├── scripts/                  # 数据初始化
│   │   │   └── seed_data.py          #   Mock数据注入脚本
│   │   │
│   │   ├── config.py                 # 应用配置（环境变量管理）
│   │   ├── database.py               # 数据库连接（SQLAlchemy）
│   │   └── main.py                   # FastAPI应用入口
│   │
│   ├── knowledge_docs/               # 医学知识库（向量化前的原始文档）
│   │   ├── prenatal_guidelines.md    #   产前检查指南
│   │   ├── health_education.md       #   健康教育资料
│   │   └── medication_safety.md      #   孕期用药安全
│   │
│   ├── scripts/                      # 工具脚本
│   │   ├── init_pgvector.sql         #   PostgreSQL向量扩展初始化
│   │   └── ingest_knowledge.py       #   知识库文档向量化导入
│   │
│   ├── .env                          # 环境变量配置
│   ├── Dockerfile                    # 后端容器镜像
│   ├── init_db.py                    # 数据库初始化脚本
│   ├── run.py                        # 开发服务器启动
│   └── requirements.txt              # Python依赖
│
├── frontend/                         # 前端应用（Vue 3）
│   ├── src/
│   │   ├── api/                      # API请求层
│   │   │   ├── client.ts             #   Axios实例配置
│   │   │   └── endpoints.ts          #   后端接口定义
│   │   │
│   │   ├── views/                    # 页面组件
│   │   │   ├── Login.vue             #   登录页
│   │   │   ├── pregnant/             #   孕妇端页面
│   │   │   │   ├── PregnantHome.vue   #     孕妇首页
│   │   │   │   ├── PregnantChat.vue   #     智能问答对话
│   │   │   │   ├── PregnantSchedule.vue #   产检日程
│   │   │   │   ├── PregnantProfile.vue #    个人档案
│   │   │   │   └── PregnantTools.vue  #     健康工具
│   │   │   ├── nurse/                #   护士端页面
│   │   │   │   ├── NurseDashboard.vue #    护士工作台
│   │   │   │   ├── ScheduleManage.vue #    排期管理
│   │   │   │   ├── FollowUpList.vue   #    随访列表
│   │   │   │   └── AlertList.vue     #     预警处理
│   │   │   └── doctor/               #   医生端页面
│   │   │       ├── DoctorDashboard.vue #   医生看板
│   │   │       ├── FGRBoard.vue      #     FGR风险看板
│   │   │       ├── OrderManage.vue   #     医嘱管理
│   │   │       └── ReviewWorkbench.vue #   病例审核
│   │   │
│   │   ├── components/               # 通用组件
│   │   │   ├── layout/               #   布局组件
│   │   │   │   ├── HeaderBar.vue     #     顶部导航
│   │   │   │   ├── Sidebar.vue       #     侧边栏
│   │   │   │   ├── PregnantLayout.vue #    孕妇端布局
│   │   │   │   ├── NurseLayout.vue   #     护士端布局
│   │   │   │   └── DoctorLayout.vue  #     医生端布局
│   │   │   └── common/               #   公共组件
│   │   │       ├── StatCard.vue      #     统计卡片
│   │   │       └── RiskBadge.vue     #     风险等级标签
│   │   │
│   │   ├── router/                   # 路由配置
│   │   │   └── index.ts              #   Vue Router定义
│   │   │
│   │   ├── stores/                   # 状态管理（Pinia）
│   │   │   ├── app.ts                #   全局应用状态
│   │   │   └── chat.ts               #   对话状态管理
│   │   │
│   │   ├── types/                    # TypeScript类型
│   │   │   └── index.ts              #   全局类型定义
│   │   │
│   │   ├── utils/                    # 工具函数
│   │   │   └── markdown.ts           #   Markdown渲染
│   │   │
│   │   ├── App.vue                   # 根组件
│   │   ├── main.ts                   # 应用入口
│   │   └── env.d.ts                  # 环境类型声明
│   │
│   ├── public/                       # 静态资源
│   ├── dist/                         # 构建输出
│   ├── nginx.conf                    # Nginx配置
│   ├── Dockerfile                    # 前端容器镜像
│   ├── index.html                    # HTML入口
│   ├── vite.config.ts                # Vite构建配置
│   ├── tsconfig.json                 # TypeScript配置
│   └── package.json                  # Node依赖
│
├── docs/                             # 项目文档
│   ├── 赛题要求和赛题方向.md           #   竞赛赛题说明
│   ├── chatui.md                     #   聊天UI设计文档
│   └── design/                       #   设计文档
│       ├── 2026-04-28-medical-agent-design.md
│       ├── 2026-04-29-hardware-adaptation.md
│       └── 2026-04-29-technical-architecture.md
│
├── docker-compose.yml                # 容器编排（Backend/Frontend/PostgreSQL/Redis）
├── .gitignore                        # Git忽略配置
└── README.md                         # 项目说明
```

### 核心模块说明

| 模块 | 路径 | 说明 |
|------|------|------|
| **LLM客户端** | `backend/app/core/llm_client.py` | 封装DeepSeek/Ollama调用，支持cloud/local/mock三种模式 |
| **NLU引擎** | `backend/app/core/nlu_engine.py` | 规则+LLM混合意图识别，支持紧急检测与情绪分析 |
| **RAG引擎** | `backend/app/core/rag_engine.py` | 向量检索+LLM生成，基于pgvector的医学知识增强 |
| **对话路由** | `backend/app/routers/chat.py` | 孕妇智能问答核心接口，集成NLU/RAG/记忆管理 |
| **FGR评估** | `backend/app/routers/fgr.py` | 胎儿生长受限风险评估接口 |

## 快速开始

### 环境要求

- Docker & Docker Compose
- Node.js 18+（本地开发）
- Python 3.10+（本地开发）

### Docker部署（推荐）

```bash
# 1. 克隆项目
git clone <repository-url>
cd medical_agent1

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
| `LLM_MODE` | LLM模式：cloud/local/mock | mock |
| `LLM_API_KEY` | LLM API密钥 | - |
| `LLM_BASE_URL` | LLM API地址 | https://api.deepseek.com/v1 |
| `LLM_MODEL` | LLM模型名称 | deepseek-chat |
| `FGR_MODE` | FGR算法模式：mock/npu | mock |
| `DB_TYPE` | 数据库类型：sqlite/postgres | sqlite |
| `RAG_ENABLED` | 启用RAG检索 | false |

### LLM模式说明

- **cloud**：使用云端API（DeepSeek）
- **local**：使用Ollama本地模型
- **mock**：模拟响应（开发测试）

## API接口

### 核心接口

| 模块 | 端点 | 说明 |
|------|------|------|
| 认证 | `POST /api/auth/login` | 用户登录 |
| 聊天 | `POST /api/chat` | 孕妇智能问答 |
| 随访 | `POST /api/followup` | 随访管理 |
| 预警 | `GET /api/alerts` | 高危预警列表 |
| FGR | `POST /api/fgr/assess` | FGR风险评估 |
| 医嘱 | `POST /api/orders/generate` | AI医嘱生成 |
| 仪表盘 | `GET /api/dashboard` | 数据统计看板 |

完整API文档请访问：`http://localhost:8000/docs`

## 功能模块

### 孕妇端
- 智能健康咨询（RAG增强）
- 产检日程管理
- 健康数据记录（体重/血压/胎动）
- 情绪陪伴与心理支持

### 护士端
- 随访任务管理
- 孕妇排期管理
- 高危预警处理
- 随访记录生成

### 医生端
- FGR风险看板
- 辅助医嘱生成
- 病例审核工作台
- 多维度数据分析

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
