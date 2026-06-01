# RAG 增强设计文档

> 状态: 待审核 | 日期: 2026-05-31

## 1. 背景与目标

AI-Care 孕期智能管理平台已有完整的 RAG 基础设施，但存在以下问题：

- RAG 默认关闭（`rag_enabled: bool = False`）
- Agent 非 Agentic RAG 模式（`search_knowledge=False`）
- Embedding 为 Mock 模式，无法验证真实语义检索
- 自定义 RAG 实现（`agno_rag.py`）未使用 Agno 原生 Knowledge/PgVector
- 分块策略粗糙（仅按 `##` 分割）
- 知识文档仅 6 篇，覆盖面有限

**目标：** 将 RAG 层迁移到 Agno 原生实现，启用 Agentic RAG，提升检索质量，扩充知识库至 15-16 篇。

## 2. 架构设计

### 2.1 迁移后架构

```
Agent Layer (不变)
  小安 / 小护 / 智医 ── agno.agent.Agent
  knowledge=knowledge, search_knowledge=True
        │
        ▼
Agno Knowledge (替换自定义适配器)
  agno.knowledge.Knowledge
  ├── vector_db = PgVector (替换自定义 SQL 查询)
  ├── embedder = OpenAIEmbedder (替换自定义 Embedding)
  └── chunking_strategy = TextChunkingStrategy
        │
        ▼
PostgreSQL pgvector (不变)
  knowledge_chunks 表 + HNSW 索引
```

### 2.2 组件映射

| 自定义组件 | Agno 原生替代 | 说明 |
|-----------|-------------|------|
| `agno_rag.py` (RAGEngine) | `agno.vectordb.pgvector.PgVector` | 原生向量 + 混合检索 |
| `embedding.py` | `agno.knowledge.embedder.openai.OpenAIEmbedder` | 支持 base_url 对接 DashScope |
| `agno_knowledge.py` | `agno.knowledge.knowledge.Knowledge` | 原生 Knowledge 类 |
| `ingest_knowledge.py` | `Knowledge.insert()` + `TextChunkingStrategy` | 原生文档导入 |
| `vector_models.py` | PgVector 自动管理 | 不再需要手动 ORM |

### 2.3 向量数据库

使用 Docker 启动 pgvector（与生产环境一致）：

```bash
docker compose up -d postgres redis
```

- 镜像：`pgvector/pgvector:pg16`
- 端口：`127.0.0.1:5432`
- 初始化：`init_pgvector.sql` 挂载到 `/docker-entrypoint-initdb.d/`

**表结构管理：** Agno 的 `PgVector` 类会自动创建和管理表结构。现有 `knowledge_chunks` 表将被 Agno 自动重建（包含 `embedding` 列、元数据列等）。`init_pgvector.sql` 仅负责创建 pgvector 扩展，表结构由 Agno 管理。

### 2.4 工具与 Knowledge 的关系

- `search_knowledge=True`：Agno Agent 原生能力，Agent 自动在需要时检索知识库，无需手动定义工具
- `agno_search_knowledge` 工具：保留作为显式调用入口，供 Agent 在特定场景（如用户明确要求查资料）时使用
- 两者不冲突：原生检索由 Agno 框架控制，工具调用由 Agent 自主决定

## 3. 文件级变更

### 3.1 删除（功能被 Agno 原生覆盖）

- `backend/app/core/agno_rag.py`
- `backend/app/core/embedding.py`
- `backend/app/models/vector_models.py`

### 3.2 重写

**`backend/app/core/agno_knowledge.py`** — 从自定义适配器改为 Agno Knowledge 工厂：

```python
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.pgvector import PgVector, SearchType
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.knowledge.chunking.text import TextChunkingStrategy
from ..config import settings

def create_knowledge() -> Knowledge:
    return Knowledge(
        name="AI-Care 医学知识库",
        vector_db=PgVector(
            table_name="knowledge_chunks",
            db_url=settings.database_url,
            search_type=SearchType.hybrid,
            embedder=OpenAIEmbedder(
                id=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                api_key=settings.embedding_api_key,
                base_url=settings.embedding_api_url,
            ),
        ),
        chunking_strategy=TextChunkingStrategy(
            chunk_size=settings.rag_chunk_size,
            overlap=settings.rag_chunk_overlap,
        ),
    )

knowledge = create_knowledge()
```

**`backend/scripts/ingest_knowledge.py`** — 从手动分块改为 Agno Knowledge.insert()：

```python
from app.core.agno_knowledge import knowledge
import os

docs_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge_docs")
for fname in os.listdir(docs_dir):
    if fname.endswith(".md"):
        knowledge.insert(path=os.path.join(docs_dir, fname))
```

### 3.3 小改

**`backend/app/core/agno_agent.py`** — `_build_agent()`:
- `search_knowledge=False` → `True`
- `knowledge=agno_knowledge` → `knowledge=knowledge`（导入新模块）

**`backend/app/core/agno_medical_agents.py`** — 护士/医生 Agent 构造器:
- 同上，`search_knowledge=True`，导入原生 Knowledge

**`backend/app/core/agno_tools.py`** — `agno_search_knowledge`:
- 改为调用 `knowledge.search(query)` 替代 `rag_engine.search()`

**`backend/app/routers/chat.py`** — `/rag/ask` 和 `/rag/status`:
- 适配新 Knowledge 接口

**`backend/app/config.py`** — 新增配置项：

```python
# Embedding
embedding_api_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
embedding_api_key: str = ""
embedding_model: str = "text-embedding-v3"
embedding_dimensions: int = 1024

# RAG
rag_enabled: bool = True
rag_chunk_size: int = 600
rag_chunk_overlap: int = 120
rag_search_type: Literal["vector", "hybrid"] = "hybrid"
rag_max_results: int = 5
```

**`backend/requirements.txt`**:
- 新增 `psycopg[binary]>=3.1.0`（Agno PgVector 依赖）

### 3.4 新增

**知识文档**（`backend/knowledge_docs/` 下新增 10 篇）：

| 文件 | 主题 | 分类 |
|------|------|------|
| prenatal_diagnosis.md | 产前诊断（唐筛、NT、无创DNA、羊穿） | guideline |
| labor_delivery.md | 分娩指导（临产征兆、产程、分娩方式） | guideline |
| postpartum_recovery.md | 产后恢复（恶露、盆底、母乳喂养） | education |
| newborn_care.md | 新生儿护理（黄疸、脐带、喂养） | education |
| common_lab_values.md | 常见检查指标解读 | guideline |
| nutrition_diet.md | 孕期营养与饮食 | education |
| exercise_activity.md | 孕期运动与休息 | education |
| mental_health_expanded.md | 孕期心理健康（扩充版） | education |
| vaccination.md | 孕期疫苗接种指南 | drug |
| travel_safety.md | 孕期出行与安全 | education |

## 4. 配置变更

### .env 新增

```env
# Embedding (阿里云 DashScope)
EMBEDDING_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-v3

# RAG
RAG_ENABLED=true
RAG_SEARCH_TYPE=hybrid
DB_TYPE=postgres
```

### docker-compose.yml

无需修改，已有 pgvector 和 redis 配置。

## 5. 实施步骤

### Phase 1: 环境准备
1. 启动 Docker 容器：`docker compose up -d postgres redis`
2. 配置 `.env`（DB_TYPE=postgres, RAG_ENABLED=true, Embedding API Key）

### Phase 2: 代码迁移
1. 修改 `config.py` — 新增配置项
2. 重写 `agno_knowledge.py` — Agno Knowledge 工厂
3. 修改 `agno_agent.py` — search_knowledge=True
4. 修改 `agno_medical_agents.py` — 同上
5. 修改 `agno_tools.py` — 适配新接口
6. 修改 `routers/chat.py` — 适配新接口
7. 更新 `requirements.txt`

### Phase 3: 知识库
1. 编写 10 篇新知识文档
2. 重写 `ingest_knowledge.py`
3. 运行入库脚本

### Phase 4: 清理
1. 删除 `agno_rag.py`、`embedding.py`、`vector_models.py`
2. 简化 `init_pgvector.sql` — 仅保留 `CREATE EXTENSION IF NOT EXISTS vector`，表结构由 Agno PgVector 管理

### Phase 5: 验证
1. `/rag/status` 端点返回正确状态
2. `/rag/ask` 端点返回基于知识库的回答
3. Agent 对话中可自主检索知识库

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| DashScope Embedding API 不可用 | 保留 Mock 降级逻辑 |
| Agno PgVector 表结构与现有不兼容 | 入库前清空旧表，使用 Agno 管理的表结构 |
| Agent 检索过于频繁导致 token 爆炸 | tool_call_limit 已有限制，可调 max_results |
| 删除旧文件后有隐藏依赖 | 全局搜索 import 引用，确保无遗漏 |

## 7. 验收标准

- [ ] `docker compose up -d postgres redis` 启动成功
- [ ] `python scripts/ingest_knowledge.py` 入库 15+ 篇文档
- [ ] `GET /api/v1/chat/rag/status` 返回 rag_enabled=true, chunk_count > 0
- [ ] `POST /api/v1/chat/rag/ask` 返回知识库支撑的回答 + 来源引用
- [ ] Agent 对话中可自主调用知识检索（search_knowledge=True 生效）
- [ ] 三角色（小安/小护/智医）均可访问知识库
