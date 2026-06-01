# AI-Care RAG 增强方案

> 版本: v1.0 | 日期: 2026-05-31 | 状态: 待评审

---

## 一、现状分析

### 1.1 已有能力

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| RAG 引擎 | `agno_rag.py` | 已实现 | 向量检索 + LLM 生成，支持 pgvector 和 SQLite 降级 |
| Embedding | `embedding.py` | 已实现 | 三种模式：HuggingFace(bge-m3) / API / Mock |
| 向量存储 | `vector_models.py` | 已实现 | KnowledgeChunk ORM，pgvector vector(1024) |
| 知识入库 | `ingest_knowledge.py` | 已实现 | Markdown 按 `##` 分割，分类入库 |
| 知识文档 | `knowledge_docs/` | 已有 6 篇 | 产检指南、用药安全、妊高症、GDM、胎动监测、健康教育 |
| Agno 适配 | `agno_knowledge.py` | 已实现 | 包装 RAG 引擎为 Agno Knowledge 接口 |
| RAG Tool | `agno_tools.py` | 已实现 | `agno_search_knowledge` 工具 |
| API | `routers/chat.py` | 已实现 | `/rag/ask` 和 `/rag/status` 端点 |

### 1.2 当前问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | **RAG 默认关闭** (`rag_enabled: bool = False`) | Agent 不会主动检索知识库 |
| 2 | **非 Agentic RAG** — `search_knowledge=False` | Agent 无法自主决定何时检索 |
| 3 | **Embedding 为 Mock 模式** | 开发环境无法验证真实语义检索质量 |
| 4 | **无 Reranking** | 检索结果未经精排，相关性可能不准 |
| 5 | **分块策略单一** — 仅按 `##` 分割 | 长章节可能包含多个主题，短章节可能信息不足 |
| 6 | **无混合检索** — 仅向量检索或关键词降级 | 缺少 BM25 + 向量的混合召回 |
| 7 | **知识文档仅 6 篇** | 覆盖面有限，缺少产前诊断、分娩、产后等主题 |
| 8 | **无文档管理能力** — 仅支持全量重灌 | 无法增量更新、版本管理、文档增删 |
| 9 | **未使用 Agno 原生 Knowledge 类** | 自定义适配器未利用 Agno 的 Chunking/Reader 能力 |
| 10 | **无检索可观测性** | 无法追踪检索命中率、延迟、相关性 |

---

## 二、方案设计

### 2.1 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Layer (Agno)                    │
│  小安 / 小护 / 智医  ── search_knowledge=True (Agentic)  │
└──────────────┬──────────────────────────┬───────────────┘
               │ Tool Call                │ Knowledge 注入
               ▼                          ▼
┌──────────────────────┐  ┌───────────────────────────────┐
│   agno_search_       │  │   Agno Knowledge Adapter      │
│   knowledge (Tool)   │  │   (agno_knowledge.py)         │
└──────────┬───────────┘  └──────────┬────────────────────┘
           │                         │
           ▼                         ▼
┌─────────────────────────────────────────────────────────┐
│              RAG Engine (agno_rag.py)                    │
│  search() ──► Hybrid Retrieval ──► Reranker ──► Top-K   │
│  ask()    ──► search() + LLM Generation + Citations     │
└──────────────┬──────────────────────────────────────────┘
               │
       ┌───────┴───────┐
       ▼               ▼
┌─────────────┐  ┌──────────────┐
│ Embedding   │  │ Vector Store │
│ bge-m3      │  │ pgvector     │
│ (1024-dim)  │  │ (PostgreSQL) │
└─────────────┘  └──────────────┘
```

### 2.2 向量数据库选型决策

**决策：Docker 启动 pgvector**（与生产环境一致）

本地环境现状：
- Docker v29.1.3 + Docker Compose v5.1.1 已就绪
- `docker-compose.yml` 已配置 `pgvector/pgvector:pg16`，含健康检查和初始化脚本
- 当前 `.env` 使用 SQLite + Mock Embedding，RAG 未启用

启动方式：`docker compose up -d postgres redis` 即可获得完整的 pgvector 环境

**增强措施：**
- 升级 IVFFlat 索引为 HNSW（`m=16, ef_construction=64`）
- 添加 `tsvector` 全文检索列 + GIN 索引
- 实现 `vector_similarity * 0.7 + text_rank * 0.3` 混合排序

### 2.3 分块策略升级

| 策略 | 现状 | 增强方案 |
|------|------|----------|
| 分割方式 | 按 `##` 章节 | 递归字符分割（RecursiveCharacterTextSplitter 模式） |
| 块大小 | 不控制（整个章节） | 目标 500-800 tokens，硬上限 1000 |
| 重叠 | 无 | 100-150 tokens overlap |
| 元数据 | doc_title, doc_category | 增加 section_title, chunk_hash, source_file, created_at |
| 去重 | 无 | 基于 content hash 去重 |

**实现方案：** 新增 `core/chunking.py`，实现两种分块策略：
- `FixedSizeChunker` — 递归字符分割，适配中文长文本
- `SemanticChunker` — 基于语义相似度的智能分割（可选，需额外 embedding 开销）

### 2.4 混合检索 + Reranking

**检索流水线：**

```
Query ──► Embedding ──► 向量检索 (Top-20)  ──┐
                                            ├──► 合并去重 ──► Reranker ──► Top-5
Query ──► 分词 ──► 全文检索 (Top-20)  ───────┘
```

**实现细节：**

1. **向量检索**（已有）：pgvector cosine similarity
2. **全文检索**（新增）：PostgreSQL `tsvector` + `plainto_tsquery`
3. **混合排序**：RRF (Reciprocal Rank Fusion) 或加权融合
4. **Reranking**（新增）：使用 `BAAI/bge-reranker-v2-m3` 本地模型，或 Cohere API

**Reranker 选型：**

| 方案 | 模型 | 优势 | 劣势 |
|------|------|------|------|
| 本地 Reranker | `BAAI/bge-reranker-v2-m3` | 无 API 成本、隐私安全 | 需 GPU，增加推理延迟 |
| API Reranker | Cohere `rerank-multilingual-v3.0` | 质量高、无需本地资源 | API 成本、网络依赖 |
| 无 Reranker | — | 零开销 | 检索质量次优 |

**推荐：** 开发阶段先不启用 Reranker，生产环境按需启用。在 `config.py` 中增加 `reranker_mode: Literal["off", "local", "api"]`。

---

## 三、功能模块增强清单

### 3.1 核心增强（P0 — 必须完成）

| # | 模块 | 增强内容 | 涉及文件 |
|---|------|----------|----------|
| 1 | **Agentic RAG 开关** | `search_knowledge=True`，Agent 自主决定何时检索 | `agno_agent.py`, `agno_medical_agents.py` |
| 2 | **启用 RAG** | `.env` 中 `rag_enabled=true`，开发环境也默认开启 | `.env.example`, `config.py` |
| 3 | **Embedding 真实化** | 开发环境默认 `api` 模式（SiliconFlow 免费额度） | `.env.example`, `config.py` |
| 4 | **分块策略升级** | 实现递归字符分割，控制块大小和重叠 | 新增 `core/chunking.py`，修改 `ingest_knowledge.py` |
| 5 | **全文检索** | PostgreSQL tsvector 列 + GIN 索引 | `init_pgvector.sql`, `vector_models.py`, `agno_rag.py` |
| 6 | **混合检索** | 向量 + 全文 RRF 融合排序 | `agno_rag.py` |
| 7 | **知识入库脚本增强** | 增量更新、hash 去重、元数据丰富 | `ingest_knowledge.py` |

### 3.2 质量增强（P1 — 重要）

| # | 模块 | 增强内容 | 涉及文件 |
|---|------|----------|----------|
| 8 | **Reranking** | 本地 bge-reranker 或 Cohere API 精排 | 新增 `core/reranker.py`，`agno_rag.py` |
| 9 | **知识文档扩充** | 增加产前诊断、分娩指导、产后恢复、新生儿护理等文档 | `knowledge_docs/` |
| 10 | **多语言 Embedding** | 切换为 `text-embedding-3-small` 或保持 bge-m3 | `embedding.py`, `config.py` |
| 11 | **检索结果引用增强** | 返回精确来源（文档名+章节+页码），前端展示可溯源 | `agno_rag.py`, 前端组件 |

### 3.3 运维增强（P2 — 可选）

| # | 模块 | 增强内容 | 涉及文件 |
|---|------|----------|----------|
| 12 | **文档管理 API** | 增删改查知识文档，支持热更新 | 新增 `routers/knowledge.py` |
| 13 | **检索可观测性** | 记录检索日志（query, latency, hit_count, relevance） | `agno_rag.py` + 日志模块 |
| 14 | **Agno 原生 Knowledge 集成** | 使用 `agno.knowledge` 的 Reader/Chunker 替代自定义实现 | `agno_knowledge.py` |
| 15 | **Web UI 知识管理** | 前端知识库管理页面（文档上传、预览、搜索测试） | 前端新增页面 |

---

## 四、实施路线图

### Phase 1: 核心 RAG 激活（1-2 天）

```
目标：让 RAG 在开发环境真正跑起来

Step 1.1 — 配置激活
  - config.py: rag_enabled 默认改为 True
  - .env.example: embedding_mode 默认改为 "api"
  - 添加 SiliconFlow 免费 embedding 配置示例

Step 1.2 — Agentic RAG
  - agno_agent.py: search_knowledge=False → True
  - agno_medical_agents.py: 同上
  - 验证 Agent 能自主调用 agno_search_knowledge

Step 1.3 — 知识入库验证
  - 启动 PostgreSQL (docker-compose up postgres)
  - 运行 ingest_knowledge.py --force
  - 通过 /rag/status 和 /rag/ask 验证
```

### Phase 2: 检索质量提升（2-3 天）

```
目标：提升检索准确性和结果质量

Step 2.1 — 分块策略升级
  - 新建 core/chunking.py
  - 实现 RecursiveChunker (500-800 tokens, 100 overlap)
  - 修改 ingest_knowledge.py 使用新分块器

Step 2.2 — 全文检索
  - vector_models.py: 添加 content_tsv (tsvector) 列
  - init_pgvector.sql: 添加 GIN 索引
  - agno_rag.py: 实现 hybrid_search()

Step 2.3 — 混合排序
  - agno_rag.py: 实现 RRF 融合
  - config.py: 添加 hybrid_search_alpha 配置

Step 2.4 — Reranking (可选)
  - 新建 core/reranker.py
  - 实现 BGEReranker (本地) 和 CohereReranker (API)
  - 集成到 agno_rag.py 检索流水线
```

### Phase 3: 知识库扩充 + 文档管理（2-3 天）

```
目标：扩展知识覆盖面，支持文档管理

Step 3.1 — 知识文档扩充
  - 新增: 产前诊断指南、分娩指导、产后恢复、新生儿护理
  - 新增: 常见检查指标解读（唐筛、NT、糖耐等）
  - 目标: 从 6 篇扩展到 15-20 篇

Step 3.2 — 增量入库
  - ingest_knowledge.py: 支持 --增量模式
  - 基于 content hash 判断是否需要重新 embedding
  - 支持 --delete 删除指定文档

Step 3.3 — 文档管理 API
  - 新增 routers/knowledge.py
  - POST /knowledge/documents — 上传文档
  - GET /knowledge/documents — 列表
  - DELETE /knowledge/documents/{id} — 删除
  - POST /knowledge/reindex — 重建索引
```

### Phase 4: 可观测性 + 前端（1-2 天）

```
目标：可观测 + 用户友好

Step 4.1 — 检索日志
  - agno_rag.py: 记录每次检索的 query, latency, results
  - 暴露 /rag/metrics 端点

Step 4.2 — 前端知识管理
  - 知识库状态面板
  - 文档上传/删除
  - 搜索测试（输入问题，查看检索结果）
```

---

## 五、配置变更汇总

### config.py 新增配置项

```python
# RAG 增强配置
rag_enabled: bool = True                                    # 默认启用
embedding_mode: Literal["mock", "local", "api"] = "api"    # 默认 API 模式
embedding_api_url: str = "https://api.siliconflow.cn/v1/embeddings"
embedding_api_key: str = ""                                  # 需配置
embedding_model: str = "BAAI/bge-m3"
embedding_dim: int = 1024

# 混合检索
hybrid_search_enabled: bool = True
hybrid_search_alpha: float = 0.7    # 向量权重 (1-alpha 为全文权重)

# Reranking
reranker_mode: Literal["off", "local", "api"] = "off"
reranker_model: str = "BAAI/bge-reranker-v2-m3"
reranker_api_key: str = ""

# 分块
chunk_size: int = 600          # 目标 tokens
chunk_overlap: int = 120       # 重叠 tokens
```

### .env.example 新增

```env
# RAG Configuration
RAG_ENABLED=true
EMBEDDING_MODE=api
EMBEDDING_API_URL=https://api.siliconflow.cn/v1/embeddings
EMBEDDING_API_KEY=sk-xxx    # SiliconFlow 免费额度
EMBEDDING_MODEL=BAAI/bge-m3

# Hybrid Search
HYBRID_SEARCH_ENABLED=true
HYBRID_SEARCH_ALPHA=0.7

# Reranker (optional)
RERANKER_MODE=off
```

---

## 六、Agno 原生集成对比

| 维度 | 当前自定义方案 | Agno 原生方案 |
|------|----------------|---------------|
| Knowledge 类 | `AgnoKnowledgeAdapter` (自定义) | `agno.knowledge.Knowledge` |
| 分块 | 手动 `##` 分割 | `FixedSizeChunking` / `SemanticChunking` |
| Embedding | 自定义 `EmbeddingClient` | `agno.embeddings.OpenAIEmbedder` |
| Vector DB | 自定义 SQL 查询 | `agno.vectordb.PgVector` |
| Reader | 手动读取 markdown | `agno.document.reader.PDFReader` / `WebsiteReader` |
| Reranker | 无 | `agno.reranker.CohereReranker` |

**建议：Phase 1-3 保持自定义方案（最小改动），Phase 4 考虑迁移到 Agno 原生。**

理由：
1. 自定义方案已深度集成业务逻辑（分类、Guardrail、三角色隔离）
2. Agno 原生 Knowledge 类在 v1.0+ 才趋于稳定
3. 迁移收益主要是代码简化，但需要重写入库流程和测试

---

## 七、依赖变更

### requirements.txt 新增

```
# RAG 增强
sentence-transformers>=2.2.0    # 本地 Reranker (bge-reranker)
jieba>=0.42.1                   # 中文分词（全文检索）
rank-bm25>=0.2.2                # BM25 检索（可选）
```

---

## 八、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Embedding API 不可用 | RAG 完全失效 | 保留 Mock 降级 + 本地 HuggingFace 备选 |
| 混合检索引入延迟 | 用户体验下降 | 异步并行检索，设置超时（500ms） |
| 知识文档质量参差 | 检索结果噪声大 | 文档审核流程 + Reranker 过滤 |
| Agno 版本升级 breaking | 适配器失效 | 锁定 agno 版本，集成测试覆盖 |
| pgvector 索引重建耗时 | 入库阻塞 | CONCURRENTLY 建索引，后台任务执行 |

---

## 九、验收标准

### Phase 1 验收
- [ ] 开发环境 `rag_enabled=true` 正常启动
- [ ] Agent 可自主调用 `agno_search_knowledge` 检索知识
- [ ] `/rag/ask` 端点返回基于知识库的回答 + 来源引用
- [ ] `/rag/status` 显示正确的 chunk 数量和分类

### Phase 2 验收
- [ ] 新分块器产生的 chunk 数量 > 旧方案（更细粒度）
- [ ] 混合检索返回结果优于纯向量检索（人工评估 10 个 query）
- [ ] Reranker（如启用）Top-5 结果相关性 > 80%

### Phase 3 验收
- [ ] 知识文档 ≥ 15 篇
- [ ] 增量入库支持单文档增删
- [ ] 文档管理 API 可用

### Phase 4 验收
- [ ] 检索日志可查询
- [ ] 前端知识管理页面可用
