# RAG Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the custom RAG layer to Agno native Knowledge/PgVector/OpenAIEmbedder, enable Agentic RAG, and expand the knowledge base from 6 to 16 documents.

**Architecture:** Replace custom `agno_rag.py` (SQL vector queries) + `embedding.py` (custom clients) + `agno_knowledge.py` (adapter) with Agno's `Knowledge` + `PgVector` + `OpenAIEmbedder`. Agent gets `search_knowledge=True` for autonomous retrieval. Knowledge docs ingested via `Knowledge.insert(path=...)`.

**Tech Stack:** Agno v2.6.9, PostgreSQL 16 + pgvector (Docker), DashScope Embedding API (OpenAI-compatible), FastAPI

---

## File Structure

### Files to Create
- `backend/app/core/agno_knowledge.py` — Agno Knowledge factory (replaces current adapter)
- `backend/knowledge_docs/prenatal_diagnosis.md` — New knowledge doc
- `backend/knowledge_docs/labor_delivery.md` — New knowledge doc
- `backend/knowledge_docs/postpartum_recovery.md` — New knowledge doc
- `backend/knowledge_docs/newborn_care.md` — New knowledge doc
- `backend/knowledge_docs/common_lab_values.md` — New knowledge doc
- `backend/knowledge_docs/nutrition_diet.md` — New knowledge doc
- `backend/knowledge_docs/exercise_activity.md` — New knowledge doc
- `backend/knowledge_docs/mental_health_expanded.md` — New knowledge doc
- `backend/knowledge_docs/vaccination.md` — New knowledge doc
- `backend/knowledge_docs/travel_safety.md` — New knowledge doc

### Files to Modify
- `backend/app/config.py` — New embedding/RAG config fields
- `backend/requirements.txt` — Add psycopg, pgvector deps
- `backend/app/core/__init__.py` — Update exports (remove old RAG exports)
- `backend/app/core/agno_agent.py` — search_knowledge=True
- `backend/app/core/agno_medical_agents.py` — search_knowledge=True
- `backend/app/core/agno_tools.py` — Adapt agno_search_knowledge to new Knowledge API
- `backend/app/routers/chat.py` — Adapt /rag/ask and /rag/status to new API
- `backend/scripts/ingest_knowledge.py` — Rewrite to use Knowledge.insert()
- `backend/scripts/init_pgvector.sql` — Simplify (only CREATE EXTENSION)
- `backend/.env.example` — Add new config vars

### Files to Delete
- `backend/app/core/agno_rag.py` — Replaced by Agno PgVector
- `backend/app/core/embedding.py` — Replaced by Agno OpenAIEmbedder
- `backend/app/models/vector_models.py` — Replaced by Agno PgVector auto-managed tables

---

## Task 1: Install Dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add psycopg dependency**

Current `requirements.txt` has `psycopg2-binary==2.9.10`. Agno PgVector needs `psycopg[binary]>=3.1.0` (psycopg3).

Add after the existing `psycopg2-binary` line:

```
psycopg[binary]>=3.1.0
```

Keep `psycopg2-binary` for now (other code may use it). Keep `pgvector==0.3.6`.

- [ ] **Step 2: Install the new dependency**

Run: `pip install 'psycopg[binary]>=3.1.0'`
Expected: Successfully installed psycopg-3.x.x

- [ ] **Step 3: Verify Agno imports work**

Run:
```bash
python -c "
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.pgvector import PgVector, SearchType
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.knowledge.chunking.fixed import FixedSizeChunking
print('All Agno RAG imports OK')
"
```
Expected: `All Agno RAG imports OK`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "deps: add psycopg[binary] for Agno PgVector"
```

---

## Task 2: Update Configuration

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add new config fields to config.py**

In `backend/app/config.py`, add these fields after the existing `embedding_model` field (line ~134):

```python
    # Embedding (Agno native)
    embedding_api_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v3"
    embedding_dimensions: int = 1024

    # RAG (Agno native)
    rag_chunk_size: int = 600
    rag_chunk_overlap: int = 120
    rag_search_type: Literal["vector", "hybrid"] = "hybrid"
    rag_max_results: int = 5
```

Remove the old fields that are no longer needed:
- `embedding_mode: Literal["mock", "local", "api"] = "mock"` — replaced by Agno embedder
- `embedding_api_url: str = ""` — replaced by new field above
- `embedding_api_key: str = ""` — replaced by new field above
- `embedding_model: str = "BAAI/bge-m3"` — replaced by new field above

Note: Keep `rag_enabled: bool = False` as-is (we'll change it in .env, not in code defaults).

- [ ] **Step 2: Update .env.example**

Add to `backend/.env.example`:

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

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py backend/.env.example
git commit -m "config: add Agno RAG and DashScope embedding config fields"
```

---

## Task 3: Rewrite agno_knowledge.py

**Files:**
- Modify: `backend/app/core/agno_knowledge.py`

This is the core migration — replace the custom `AgnoKnowledgeAdapter` with an Agno native `Knowledge` instance.

- [ ] **Step 1: Rewrite agno_knowledge.py**

Replace the entire contents of `backend/app/core/agno_knowledge.py` with:

```python
"""Agno Knowledge — 医学知识库

使用 Agno 原生 Knowledge + PgVector + OpenAIEmbedder。
提供全局 knowledge 单例，供所有 Agent 使用。
"""
from __future__ import annotations

from agno.knowledge.knowledge import Knowledge
from agno.vectordb.pgvector import PgVector, SearchType
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.knowledge.chunking.fixed import FixedSizeChunking
from ..config import settings


def create_knowledge() -> Knowledge:
    """创建 Agno Knowledge 实例（全局单例）"""
    search_type = (
        SearchType.hybrid
        if settings.rag_search_type == "hybrid"
        else SearchType.vector
    )

    return Knowledge(
        name="AI-Care 医学知识库",
        description="孕期智能管理平台医学知识库，覆盖产检指南、用药安全、孕期疾病管理等",
        vector_db=PgVector(
            table_name="knowledge_chunks",
            db_url=settings.database_url,
            search_type=search_type,
            embedder=OpenAIEmbedder(
                id=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                api_key=settings.embedding_api_key,
                base_url=settings.embedding_api_url,
            ),
        ),
        max_results=settings.rag_max_results,
    )


# 全局单例 — 供 Agent 和 API 使用
knowledge = create_knowledge()
```

Note: `FixedSizeChunking` is the default, so we don't need to explicitly set it. Agno's `Knowledge` handles chunking internally.

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/agno_knowledge.py
git commit -m "feat(rag): rewrite agno_knowledge.py with Agno native Knowledge"
```

---

## Task 4: Update Agent Definitions

**Files:**
- Modify: `backend/app/core/agno_agent.py`
- Modify: `backend/app/core/agno_medical_agents.py`

- [ ] **Step 1: Update agno_agent.py**

In `backend/app/core/agno_agent.py`, change the import and Agent construction:

Change line 17:
```python
from .agno_knowledge import agno_knowledge
```
to:
```python
from .agno_knowledge import knowledge
```

In `_build_agent()` (line 35-54), change two parameters:

```python
        knowledge=knowledge,           # was: knowledge=agno_knowledge
        search_knowledge=True,         # was: search_knowledge=False
```

- [ ] **Step 2: Update agno_medical_agents.py**

In `backend/app/core/agno_medical_agents.py`, add import at the top (after line 22):

```python
from .agno_knowledge import knowledge as medical_knowledge
```

In `_build_nurse_agent_variant()` (line 219-237), add to the kwargs dict:

```python
        knowledge=medical_knowledge,
        search_knowledge=True,
```

In `_build_doctor_agent_variant()` (line 240-258), add to the kwargs dict:

```python
        knowledge=medical_knowledge,
        search_knowledge=True,
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/agno_agent.py backend/app/core/agno_medical_agents.py
git commit -m "feat(rag): enable Agentic RAG on all agents (search_knowledge=True)"
```

---

## Task 5: Update RAG Tool

**Files:**
- Modify: `backend/app/core/agno_tools.py`

- [ ] **Step 1: Rewrite agno_search_knowledge tool**

In `backend/app/core/agno_tools.py`, find the `agno_search_knowledge` function (around line 330) and replace it:

```python
@tool(
    name="search_knowledge",
    description="检索医学知识库，获取与问题相关的医学知识和指南。用于回答孕期健康、用药安全、产检指标等问题。",
    show_result=True,
    stop_after_tool_call=False,
)
async def agno_search_knowledge(query: str, top_k: int = 3) -> dict:
    """检索医学知识库"""
    if not settings.rag_enabled:
        return {"error": "RAG功能未启用", "results": []}

    try:
        from .agno_knowledge import knowledge
        results = knowledge.search(query=query, max_results=top_k)
        if not results:
            return {"message": "未找到相关知识", "results": []}

        formatted = []
        for doc in results:
            formatted.append({
                "content": doc.content[:500] if hasattr(doc, "content") else str(doc)[:500],
                "source": getattr(doc, "name", "unknown"),
                "score": getattr(doc, "score", 0),
            })
        return {"results": formatted}
    except Exception as e:
        return {"error": f"知识检索失败: {str(e)}", "results": []}
```

- [ ] **Step 2: Remove old RAG imports**

In `backend/app/core/agno_tools.py`, find and remove or update any imports of `agno_rag`:

Line 338: `from ..core.agno_rag import agno_rag_engine` — this is inside the old tool function, already replaced above.

Line 777: `from .agno_rag import search_knowledge_base` — find this reference and update it to use the new knowledge search.

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/agno_tools.py
git commit -m "feat(rag): adapt agno_search_knowledge tool to Agno native Knowledge"
```

---

## Task 6: Update Chat Router

**Files:**
- Modify: `backend/app/routers/chat.py`

- [ ] **Step 1: Update imports**

In `backend/app/routers/chat.py`, line 12 changes from:

```python
from ..core import memory_manager, rag_engine
```

to:

```python
from ..core import memory_manager
from ..core.agno_knowledge import knowledge
```

- [ ] **Step 2: Rewrite /rag/ask endpoint**

Replace the `rag_ask` function (around line 196-220):

```python
@router.post("/rag/ask", response_model=RAGAskResponse)
async def rag_ask(req: RAGAskRequest):
    if not settings.rag_enabled:
        raise HTTPException(400, "RAG功能未启用，请设置 RAG_ENABLED=true")

    try:
        results = knowledge.search(query=req.question, max_results=req.top_k)

        if not results:
            return RAGAskResponse(
                answer="抱歉，未找到相关医学知识。建议咨询产检医生。",
                sources=[],
                chunks=[],
                rag_used=False,
            )

        # Format chunks for response
        chunks = []
        sources = []
        for doc in results:
            content = doc.content[:200] if hasattr(doc, "content") else str(doc)[:200]
            source_name = getattr(doc, "name", "unknown")
            chunks.append({"content": content, "similarity": getattr(doc, "score", 0)})
            sources.append({"title": source_name, "category": "knowledge"})

        # Build answer from chunks
        knowledge_text = "\n\n".join([
            f"【来源: {getattr(doc, 'name', '未知')}】\n{doc.content[:300]}"
            for doc in results
        ])
        answer = f"根据知识库信息：\n{knowledge_text}\n\n以上为参考信息，如需更详细解答，请咨询产检医生。"

        return RAGAskResponse(
            answer=answer,
            sources=sources,
            chunks=chunks,
            rag_used=True,
        )
    except Exception as e:
        raise HTTPException(500, f"知识检索失败: {str(e)}")
```

- [ ] **Step 3: Rewrite /rag/status endpoint**

Replace the `rag_status` function (around line 223):

```python
@router.get("/rag/status")
def rag_status():
    try:
        # Try to get chunk count from knowledge base
        results = knowledge.search(query="test", max_results=1)
        chunk_count = "available" if results else "empty"
    except Exception:
        chunk_count = "unavailable"

    return {
        "enabled": settings.rag_enabled,
        "search_type": settings.rag_search_type,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "max_results": settings.rag_max_results,
        "knowledge_status": chunk_count,
        "vector_db": "pgvector",
    }
```

- [ ] **Step 4: Remove vector_models import**

Line 227: `from ..models.vector_models import KnowledgeChunk` — remove this import (no longer needed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/chat.py
git commit -m "feat(rag): adapt /rag/ask and /rag/status to Agno native Knowledge"
```

---

## Task 7: Update Core __init__.py

**Files:**
- Modify: `backend/app/core/__init__.py`

- [ ] **Step 1: Update exports**

Replace the old RAG/embedding exports with new ones. In `backend/app/core/__init__.py`:

Change lines 17-18:
```python
from .embedding import get_embedding_client, EmbeddingClient, MockEmbedding, HuggingFaceEmbedding, APIEmbedding
from .agno_rag import RAGEngine, rag_engine, agno_rag_engine, AgnoRAGEngine
```

to:
```python
from .agno_knowledge import knowledge
```

Update the `__all__` list — remove:
- `"get_embedding_client"`, `"EmbeddingClient"`, `"MockEmbedding"`, `"HuggingFaceEmbedding"`, `"APIEmbedding"`
- `"RAGEngine"`, `"rag_engine"`, `"agno_rag_engine"`, `"AgnoRAGEngine"`

Add:
- `"knowledge"`

Also update the agno_knowledge import (line 15):
```python
from .agno_knowledge import AgnoKnowledgeAdapter, agno_knowledge
```
to:
```python
from .agno_knowledge import knowledge
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/__init__.py
git commit -m "refactor: update core exports for Agno native RAG"
```

---

## Task 8: Rewrite ingest_knowledge.py

**Files:**
- Modify: `backend/scripts/ingest_knowledge.py`

- [ ] **Step 1: Rewrite ingestion script**

Replace the entire contents of `backend/scripts/ingest_knowledge.py`:

```python
"""知识库文档入库脚本（Agno 原生 Knowledge）

用法: python scripts/ingest_knowledge.py [--force]

流程:
1. 读取 knowledge_docs/ 下所有 .md 文件
2. 通过 Agno Knowledge.insert() 自动分块、embedding、入库
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def ingest(force: bool = False):
    """主入库流程"""
    from app.core.agno_knowledge import knowledge
    from app.config import settings

    if not settings.rag_enabled:
        print("RAG 未启用 (RAG_ENABLED=false)，跳过入库")
        return

    docs_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge_docs")
    if not os.path.isdir(docs_dir):
        print(f"知识库目录不存在: {docs_dir}")
        return

    md_files = sorted([f for f in os.listdir(docs_dir) if f.endswith(".md")])
    if not md_files:
        print("未找到 Markdown 文件")
        return

    print(f"找到 {len(md_files)} 个文档文件")
    print(f"Embedding: {settings.embedding_model} @ {settings.embedding_api_url}")
    print(f"Vector DB: pgvector ({settings.database_url})")
    print(f"Search type: {settings.rag_search_type}")
    print()

    success = 0
    for fname in md_files:
        fpath = os.path.join(docs_dir, fname)
        print(f"  导入: {fname} ... ", end="", flush=True)
        try:
            knowledge.insert(
                path=fpath,
                name=fname.replace(".md", ""),
                metadata={"source": "knowledge_docs", "filename": fname},
                upsert=force,
            )
            print("OK")
            success += 1
        except Exception as e:
            print(f"FAILED: {e}")

    print(f"\n入库完成: {success}/{len(md_files)} 个文档成功")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="知识库文档入库 (Agno Native)")
    parser.add_argument("--force", action="store_true", help="强制重新入库 (upsert)")
    args = parser.parse_args()

    ingest(force=args.force)
```

- [ ] **Step 2: Commit**

```bash
git add backend/scripts/ingest_knowledge.py
git commit -m "feat(rag): rewrite ingest script using Agno Knowledge.insert()"
```

---

## Task 9: Update init_pgvector.sql

**Files:**
- Modify: `backend/scripts/init_pgvector.sql`

- [ ] **Step 1: Simplify to extension-only**

Replace `backend/scripts/init_pgvector.sql`:

```sql
-- pgvector 扩展初始化
-- 表结构由 Agno PgVector 类自动管理
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

This removes the manual `knowledge_chunks` table creation and IVFFlat index. Agno's `PgVector` class manages table creation, columns, and indexes automatically.

- [ ] **Step 2: Commit**

```bash
git add backend/scripts/init_pgvector.sql
git commit -m "refactor: simplify init_pgvector.sql, table managed by Agno"
```

---

## Task 10: Delete Old RAG Files

**Files:**
- Delete: `backend/app/core/agno_rag.py`
- Delete: `backend/app/core/embedding.py`
- Delete: `backend/app/models/vector_models.py`

- [ ] **Step 1: Verify no remaining imports**

Run:
```bash
grep -rn "agno_rag\|from.*embedding import\|vector_models" backend/app/ --include="*.py" | grep -v "__pycache__"
```

Expected: Only the new `agno_knowledge.py` import should remain. If other files still reference old modules, fix them first.

- [ ] **Step 2: Delete the files**

```bash
rm backend/app/core/agno_rag.py
rm backend/app/core/embedding.py
rm backend/app/models/vector_models.py
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: remove custom RAG/Embedding/VectorModel files (replaced by Agno native)"
```

---

## Task 11: Write Knowledge Documents (Part 1 — 5 docs)

**Files:**
- Create: `backend/knowledge_docs/prenatal_diagnosis.md`
- Create: `backend/knowledge_docs/labor_delivery.md`
- Create: `backend/knowledge_docs/postpartum_recovery.md`
- Create: `backend/knowledge_docs/newborn_care.md`
- Create: `backend/knowledge_docs/common_lab_values.md`

- [ ] **Step 1: Create prenatal_diagnosis.md**

```markdown
# 产前诊断指南

## 产前筛查概述

产前筛查是孕期保健的重要组成部分，旨在评估胎儿是否存在某些先天性疾病或染色体异常的风险。筛查不等于诊断，高风险结果需要进一步确诊检查。

## 唐氏综合征筛查

### 早期唐筛（11-13+6周）
- 检测指标：PAPP-A + β-hCG + NT（颈项透明层厚度）
- NT正常值：<2.5mm（不同标准略有差异）
- 检出率约85-90%

### 中期唐筛（15-20周）
- 检测指标：AFP + β-hCG + uE3（游离雌三醇）
- 三联筛查检出率约60-70%
- 四联筛查（增加Inhibin A）检出率约75-80%

### 无创DNA检测（NIPT，12-22周）
- 检测母体外周血中的胎儿游离DNA
- 21三体检出率>99%，18三体>97%，13三体>95%
- 适用人群：唐筛高风险、高龄孕妇（≥35岁）、超声软指标异常
- 局限性：对结构异常和单基因病不敏感

## NT检查（11-13+6周）

NT（Nuchal Translucency）即颈项透明层，是胎儿颈椎水平皮肤与皮下软组织之间的无回声区。

- 正常值：一般<2.5mm
- NT增厚（≥3.5mm）与染色体异常、先天性心脏病、遗传综合征等相关
- NT检查需要胎儿特定体位，可能需要多次检查

## 系统超声筛查（大排畸，20-24周）

主要检查内容：
- 胎儿头颅、面部、脊柱、心脏、腹部、四肢结构
- 胎盘位置、羊水量、脐带
- 建议在有资质的产前诊断中心进行

## 羊膜腔穿刺（16-22周）

- 适应证：NIPT高风险、高龄、超声异常、家族遗传病史
- 抽取羊水进行染色体核型分析或基因芯片检测
- 流产风险约1/500-1/1000
- 术后需观察30分钟，24小时内避免剧烈活动

## 脐血穿刺（通常18周后）

- 适应证：需快速核型分析、胎儿贫血评估、宫内感染诊断
- 超声引导下经腹穿刺脐带
- 风险高于羊穿，需严格掌握适应证

## 注意事项

- 产前筛查≠产前诊断，筛查高风险不等于胎儿一定有问题
- 所有侵入性检查前需充分知情同意
- 高龄孕妇（≥35岁）建议直接进行NIPT或介入性产前诊断
- 若不适持续或有疑虑，请务必咨询产科医生
```

- [ ] **Step 2: Create labor_delivery.md**

```markdown
# 分娩指导

## 临产征兆

### 见红
- 阴道少量血性分泌物（粉红色或褐色）
- 通常在分娩前24-48小时出现
- 若出血量多（如月经量），需立即就医

### 规律宫缩
- 真宫缩特征：规律性、逐渐增强、间隔缩短
- 初产妇宫缩间隔5-10分钟，持续30秒以上时应就医
- 经产妇宫缩间隔10-15分钟时即可就医
- 假宫缩（Braxton Hicks）：不规则、无痛或轻微、休息可缓解

### 破水
- 阴道突然流出清亮液体（可能混有少量白色胎脂）
- 破水后应立即平卧，垫高臀部
- 记录破水时间、液体颜色和量
- 破水后需尽快就医（脐带脱垂风险）

## 产程概述

### 第一产程（宫颈扩张期）
- 潜伏期：宫口开至3cm，约8-16小时（初产妇）
- 活跃期：宫口3cm至10cm，约4-8小时（初产妇）
- 建议：适当活动、变换体位、呼吸放松

### 第二产程（胎儿娩出期）
- 宫口开全至胎儿娩出，约1-2小时（初产妇）
- 配合宫缩用力：深吸气→屏气用力→呼气
- 听从助产士指导

### 第三产程（胎盘娩出期）
- 胎儿娩出后胎盘排出，约5-30分钟
- 胎盘完整娩出后检查软产道

## 分娩方式选择

### 顺产（阴道分娩）
- 优势：恢复快、并发症少、有利于新生儿肺液排出
- 适合：胎位正常、骨盆条件好、无严重并发症

### 剖宫产
- 适应证：胎位异常、前置胎盘、胎儿窘迫、头盆不称、瘢痕子宫等
- 风险：出血量多、感染、术后粘连、再次妊娠风险

## 无痛分娩

- 硬膜外麻醉镇痛，可有效减轻产痛
- 通常在宫口开至2-3cm时实施
- 不影响产程进展和新生儿评分
- 可能的副作用：低血压、头痛、发热

## 待产包清单

- 证件：身份证、医保卡、母子健康手册、所有产检资料
- 产妇用品：产褥垫、一次性内裤、卫生巾、哺乳内衣、吸管杯
- 新生儿用品：包被、纸尿裤、婴儿服、湿巾
```

- [ ] **Step 3: Create postpartum_recovery.md**

```markdown
# 产后恢复指南

## 产褥期（产后42天）

产褥期是产妇身体恢复的关键时期，需注意休息、营养和卫生。

## 恶露观察

- 血性恶露（产后1-3天）：鲜红色，量较多
- 浆液性恶露（产后4-10天）：淡红色，量渐少
- 白色恶露（产后10天后）：白色或淡黄色
- 异常信号：恶露量突然增多、有臭味、持续鲜红色超过2周

## 伤口护理

### 顺产侧切/撕裂
- 保持会阴清洁干燥
- 每次如厕后用温水冲洗，从前向后擦
- 避免久坐压迫伤口

### 剖宫产切口
- 保持切口干燥，避免沾水
- 观察切口有无红肿、渗液、发热
- 术后6周内避免提重物

## 母乳喂养

### 开奶时机
- 产后30分钟内尽早开奶
- 初乳富含免疫球蛋白，对新生儿极为珍贵

### 正确衔乳姿势
- 婴儿嘴巴张大，含住大部分乳晕
- 下唇外翻，下巴贴紧乳房
- 吸吮时有节奏的吞咽声

### 常见问题
- 乳房胀痛：频繁哺乳、冷敷缓解
- 乳头皲裂：调整衔乳姿势，涂抹乳汁保护
- 奶量不足：增加哺乳次数，保证充足水分和营养

## 产后心理

- 产后情绪低落（Baby Blues）：约50-80%产妇经历，产后2周内自行缓解
- 产后抑郁：持续2周以上的情绪低落、兴趣丧失、失眠，需专业干预
- 心理援助热线：400-161-9995

## 产后复查

- 产后42天复查：子宫复旧、伤口愈合、血压、血糖
- 盆底功能评估：产后42天后进行
- 避孕指导：产后恢复性生活前需确认避孕方案

## 产后运动

- 产后1-2天：床上翻身、抬腿
- 产后1周：凯格尔运动（盆底肌训练）
- 产后6周后：逐步恢复中等强度运动
- 剖宫产：术后6-8周后开始运动
```

- [ ] **Step 4: Create newborn_care.md**

```markdown
# 新生儿护理指南

## 新生儿特点

足月新生儿：胎龄37-42周，出生体重2500-4000g。皮肤红润、哭声响亮、四肢活动自如。

## 喂养

### 母乳喂养
- 按需哺乳，不限时间和次数
- 新生儿每天哺乳8-12次
- 判断奶量充足：每天6+片湿尿布，体重增长正常

### 配方奶喂养
- 选择适龄配方奶，严格按比例冲调
- 奶瓶奶嘴需消毒
- 喂奶后拍嗝，右侧卧位防溢奶

## 黄疸

### 生理性黄疸
- 出生后2-3天出现，4-5天达高峰，7-10天消退
- 足月儿血清胆红素<12.9mg/dl
- 多喂奶促进排泄

### 病理性黄疸
- 出生24小时内出现
- 黄疸进展快、程度重、持续时间长
- 需及时就医，可能需要蓝光治疗

## 脐带护理

- 保持脐带残端清洁干燥
- 每天用75%酒精或碘伏消毒脐带根部
- 脐带通常在出生后1-2周自然脱落
- 异常信号：脐周红肿、有脓性分泌物、出血不止

## 洗澡

- 脐带脱落前建议擦浴
- 脐带脱落后可盆浴，水温37-38℃
- 每周2-3次，使用婴儿专用沐浴露
- 洗后立即擦干，注意皮肤皱褶处

## 睡眠

- 新生儿每天睡16-20小时
- 仰卧位睡眠，降低SIDS风险
- 床铺平整，不放枕头、毛绒玩具
- 室温22-26℃，湿度50-60%

## 预防接种

- 出生后24小时内：卡介苗、乙肝疫苗第1针
- 满月：乙肝疫苗第2针
- 按照国家免疫规划程序接种

## 就医信号

- 体温异常（<36℃或>37.5℃）
- 持续哭闹不止、拒奶
- 呼吸急促、鼻翼扇动
- 皮肤发紫、黄疸加重
- 呕吐、腹泻、血便
```

- [ ] **Step 5: Create common_lab_values.md**

```markdown
# 常见产检指标解读

## 血常规

### 血红蛋白（Hb）
- 孕期正常值：≥110g/L
- 轻度贫血：90-109g/L
- 中度贫血：60-89g/L
- 重度贫血：<60g/L
- 孕期贫血需补充铁剂+维生素C

### 白细胞（WBC）
- 孕期正常值：(5-12)×10^9/L（孕期可生理性升高）
- 升高：可能感染、炎症
- 降低：病毒感染、免疫异常

### 血小板（PLT）
- 正常值：(100-300)×10^9/L
- 降低：血小板减少症、HELLP综合征、DIC
- 妊娠期血小板<50×10^9/L需警惕

## 肝肾功能

### 谷丙转氨酶（ALT）
- 正常值：0-40U/L
- 升高：肝功能损害、HELLP综合征、妊娠期急性脂肪肝

### 肌酐（Cr）
- 孕期正常值：44-97μmol/L
- 升高：肾功能异常

### 尿酸（UA）
- 孕期正常值：178-387μmol/L
- 升高：子痫前期、痛风

## 血糖

### 空腹血糖（FPG）
- 孕期正常值：<5.1mmol/L
- 5.1-6.9mmol/L：妊娠期糖尿病（GDM）
- ≥7.0mmol/L：孕前糖尿病

### 口服葡萄糖耐量试验（OGTT，24-28周）
- 空腹<5.1mmol/L
- 1小时<10.0mmol/L
- 2小时<8.5mmol/L
- 任一项异常即诊断GDM

## 尿常规

### 尿蛋白
- 正常：阴性或微量
- 阳性：子痫前期、泌尿系感染、肾脏疾病
- 24小时尿蛋白定量>300mg有意义

### 尿糖
- 孕期可出现生理性糖尿
- 持续阳性需排查GDM

## 甲状腺功能

### TSH（促甲状腺激素）
- 孕早期：0.1-2.5mIU/L
- 孕中期：0.2-3.0mIU/L
- 孕晚期：0.3-3.0mIU/L
- 升高：甲状腺功能减退，需补充左甲状腺素

## 感染筛查

### 乙肝（HBsAg）
- 阳性：乙肝携带者，新生儿需注射乙肝免疫球蛋白+疫苗

### 梅毒（RPR/TPHA）
- 阳性需治疗（青霉素），可预防母婴传播

### HIV
- 阳性需抗病毒治疗，可显著降低母婴传播率

### 弓形虫、风疹、巨细胞病毒、单纯疱疹（TORCH）
- IgM阳性：近期感染，需评估胎儿影响
- IgG阳性：既往感染，有免疫力

## 凝血功能

### D-二聚体
- 孕期可生理性升高
- 显著升高：DIC、深静脉血栓、胎盘早剥

## 注意事项

- 检查结果需结合临床综合判断
- 不同医院参考范围可能略有差异
- 单项指标异常不一定代表疾病
- 若有疑虑，请务必咨询产科医生
```

- [ ] **Step 6: Commit**

```bash
git add backend/knowledge_docs/prenatal_diagnosis.md backend/knowledge_docs/labor_delivery.md backend/knowledge_docs/postpartum_recovery.md backend/knowledge_docs/newborn_care.md backend/knowledge_docs/common_lab_values.md
git commit -m "docs: add 5 knowledge docs (diagnosis, delivery, postpartum, newborn, lab values)"
```

---

## Task 12: Write Knowledge Documents (Part 2 — 5 docs)

**Files:**
- Create: `backend/knowledge_docs/nutrition_diet.md`
- Create: `backend/knowledge_docs/exercise_activity.md`
- Create: `backend/knowledge_docs/mental_health_expanded.md`
- Create: `backend/knowledge_docs/vaccination.md`
- Create: `backend/knowledge_docs/travel_safety.md`

- [ ] **Step 1: Create nutrition_diet.md**

```markdown
# 孕期营养与饮食指南

## 孕期营养原则

孕期营养直接影响胎儿发育和孕妇健康。均衡饮食、适量增加、避免禁忌是核心原则。

## 各孕期营养需求

### 孕早期（1-12周）
- 热量：无需额外增加
- 叶酸：0.4-0.8mg/天，预防神经管畸形
- 维生素B6：缓解孕吐
- 少食多餐，选择易消化食物

### 孕中期（13-28周）
- 热量：每天增加300kcal
- 蛋白质：每天增加15g（鱼、肉、蛋、奶）
- 钙：1000mg/天（牛奶、豆制品、绿叶蔬菜）
- 铁：30mg/天（红肉、动物肝脏、菠菜）
- DHA：200mg/天（深海鱼、藻油）

### 孕晚期（29-40周）
- 热量：每天增加450kcal
- 继续高蛋白、高钙、高铁饮食
- 控制盐摄入（<6g/天），预防水肿和高血压

## 推荐食物

- 优质蛋白：鸡蛋、鱼肉、鸡胸肉、豆腐、牛奶
- 补铁：猪肝（适量）、红肉、菠菜、黑木耳
- 补钙：牛奶（每天300-500ml）、酸奶、虾皮、芝麻
- 补DHA：三文鱼、沙丁鱼、核桃、亚麻籽
- 膳食纤维：全谷物、蔬菜、水果（预防便秘）

## 饮食禁忌

### 绝对禁止
- 酒精：任何剂量均不安全
- 生食：生鱼片、半熟蛋、未熟肉类（寄生虫/细菌风险）
- 高汞鱼：鲨鱼、剑鱼、方头鱼、金枪鱼（大型）

### 限制摄入
- 咖啡因：<200mg/天（约1杯咖啡）
- 腌制食品：高盐，增加妊娠高血压风险
- 甜食/含糖饮料：增加GDM风险
- 动物肝脏：每周不超过1次（维生素A过量风险）

### 慎用
- 薏米、山楂：传统认为可能促进子宫收缩
- 人参、鹿茸等大补之品：需咨询医生

## 体重管理

- BMI正常（18.5-24.9）：孕期增重11.5-16kg
- BMI偏低（<18.5）：孕期增重12.5-18kg
- BMI超重（25-29.9）：孕期增重7-11.5kg
- BMI肥胖（≥30）：孕期增重5-9kg
- 每周固定时间称重，孕中晚期每周增重0.3-0.5kg

## 常见营养问题

### 贫血
- 补铁：铁剂+维生素C（促进吸收）
- 避免与茶、咖啡同服（抑制铁吸收）

### 腿抽筋
- 常见原因：缺钙
- 补钙：牛奶、钙片、晒太阳（促进维生素D合成）

### 便秘
- 增加膳食纤维和水分摄入
- 适量运动促进肠蠕动
- 必要时使用乳果糖等安全通便药
```

- [ ] **Step 2: Create exercise_activity.md**

```markdown
# 孕期运动与休息指南

## 运动原则

孕期适当运动有助于控制体重、缓解不适、促进分娩、改善情绪。

## 推荐运动

### 散步
- 最安全、最简单的孕期运动
- 每天30分钟，可分次进行
- 选择平坦路面，穿舒适运动鞋

### 孕妇瑜伽
- 增强柔韧性和平衡感
- 缓解腰背疼痛
- 避免过度拉伸和仰卧位动作（孕中晚期）

### 游泳
- 减轻关节负担
- 全身运动，增强心肺功能
- 水温不宜过热（<32℃）

### 凯格尔运动
- 锻炼盆底肌
- 每天3组，每组10-15次
- 有助于分娩和产后恢复

## 运动注意事项

- 运动前热身5-10分钟
- 心率不超过140次/分
- 避免跳跃、快速转身、仰卧起坐
- 避免高温环境运动（热瑜伽、桑拿）
- 运动中出现头晕、出血、宫缩应立即停止

## 高危孕妇运动限制

以下情况需减少或避免运动：
- 前置胎盘
- 宫颈机能不全
- 先兆早产
- 严重贫血
- 心肺疾病
- 多胎妊娠

## 休息与睡眠

### 睡眠姿势
- 孕中晚期建议左侧卧位
- 促进子宫胎盘血液循环
- 可使用孕妇枕支撑腰腹

### 睡眠时间
- 每天7-9小时
- 午休30-60分钟
- 失眠时可尝试：温水泡脚、听轻音乐、减少晚间饮水

### 工作休息
- 每工作1小时起身活动5-10分钟
- 避免久站久坐
- 孕晚期可申请调换轻体力岗位

## 旅行建议

- 孕中期（14-28周）是旅行最佳时期
- 飞机：孕36周前可乘机，需航空公司确认
- 长途汽车：每2小时停车休息
- 避免高海拔地区（>2500米）
```

- [ ] **Step 3: Create mental_health_expanded.md**

```markdown
# 孕期心理健康指南

## 孕期心理变化

孕期激素水平变化、身体不适、角色转换等因素均可影响心理健康。

## 常见心理问题

### 孕期焦虑
- 表现：过度担心胎儿健康、分娩恐惧、经济压力
- 发生率：约15-20%
- 应对：获取正确信息、参加孕妇学校、与家人沟通

### 孕期抑郁
- 表现：持续情绪低落、兴趣丧失、失眠或嗜睡、食欲改变
- 发生率：约10-15%
- 风险因素：既往抑郁史、缺乏社会支持、意外妊娠

### 分娩恐惧（分娩焦虑症）
- 表现：对分娩过程极度恐惧、要求剖宫产
- 应对：了解分娩知识、参观产房、制定分娩计划

## 自我调节方法

### 认知行为技巧（CBT）
- 识别自动负性思维（如"我一定会难产"）
- 用证据反驳：查看统计数据、咨询医生
- 用理性替代：如"大多数分娩是安全的"

### 正念呼吸
- 深吸气4秒→屏息4秒→慢呼气4秒
- 每天练习3-5分钟
- 可配合冥想APP引导

### 情绪日记
- 记录每天的情绪变化和触发事件
- 帮助识别情绪模式
- 可作为就医时的参考

### 社会支持
- 与伴侣、家人、朋友分享感受
- 参加孕妇交流群或线下活动
- 接受他人的帮助

## 需要专业帮助的信号

- 情绪低落持续超过2周
- 影响日常生活和工作
- 出现自杀或自伤想法
- 严重的睡眠障碍
- 无法正常进食

## 心理援助资源

- 心理援助热线：400-161-9995
- 北京心理危机研究与干预中心：010-82951332
- 产后抑郁专线：400-685-9680
- 就医：精神科/心理科/妇产科心理门诊

## 家人支持指南

- 伴侣：多陪伴、多倾听、分担家务
- 避免说"你想多了""别人怀孕都没事"
- 陪同产检、参加孕妇学校
- 关注产妇情绪变化，及时就医
```

- [ ] **Step 4: Create vaccination.md**

```markdown
# 孕期疫苗接种指南

## 孕期可接种的疫苗

### 流感疫苗（灭活）
- 推荐：孕中期或孕晚期接种
- 降低孕期流感并发症风险
- 保护新生儿（母传抗体）
- 注意：仅限灭活疫苗，不建议减毒活疫苗

### 百白破疫苗（Tdap）
- 推荐：孕27-36周接种
- 预防新生儿百日咳
- 每次妊娠均建议接种

### 新冠疫苗
- 灭活疫苗或重组蛋白疫苗可在孕期接种
- mRNA疫苗：根据当地指南
- 感染后可降低重症风险

## 孕期禁止接种的疫苗

- 麻疹-腮腺炎-风疹（MMR）：减毒活疫苗
- 水痘疫苗：减毒活疫苗
- 黄热病疫苗：减毒活疫苗
- 卡介苗：减毒活疫苗

## 接种建议

- 备孕前：完成MMR、水痘等活疫苗接种，接种后1-3个月再怀孕
- 孕期：仅接种灭活疫苗
- 哺乳期：可接种大部分疫苗
- 接种后观察30分钟，注意不良反应

## 注意事项

- 接种前告知医生怀孕状态
- 接种部位疼痛、低热为正常反应
- 严重过敏反应需立即就医
- 疫苗接种不能替代其他防护措施
```

- [ ] **Step 5: Create travel_safety.md**

```markdown
# 孕期出行与安全指南

## 最佳出行时间

- 孕中期（14-28周）最适宜出行
- 孕早期（前12周）孕吐、流产风险较高
- 孕晚期（28周后）早产风险增加

## 交通工具

### 自驾/乘车
- 系安全带：腰带放在腹部下方，肩带放在胸部之间
- 每2小时停车活动
- 避免长时间驾驶（疲劳）

### 飞机
- 孕36周前可乘机（需航空公司确认）
- 选择靠走道座位，方便活动
- 飞行中多饮水、定时起身活动
- 携带产检资料

### 火车
- 相对舒适，空间较大
- 选择下铺，方便休息
- 注意防寒保暖

## 安全注意事项

### 防跌倒
- 穿平底防滑鞋
- 避免湿滑地面
- 上下楼梯扶好扶手
- 孕晚期避免登高

### 防碰撞
- 避免拥挤场所
- 乘车时注意急刹车
- 远离危险区域（建筑工地等）

### 饮食安全
- 外出饮食注意食品卫生
- 避免生食和不洁食物
- 携带零食应对饥饿

## 禁忌出行情况

- 先兆流产/早产
- 前置胎盘
- 宫颈机能不全
- 多胎妊娠（孕晚期）
- 严重妊娠并发症
- 医生明确建议不宜出行

## 紧急情况处理

- 出现规律宫缩、破水、大量出血：立即就医
- 记录宫缩间隔和持续时间
- 保持冷静，拨打120或就近就医
- 携带产检资料和身份证件
```

- [ ] **Step 6: Commit**

```bash
git add backend/knowledge_docs/nutrition_diet.md backend/knowledge_docs/exercise_activity.md backend/knowledge_docs/mental_health_expanded.md backend/knowledge_docs/vaccination.md backend/knowledge_docs/travel_safety.md
git commit -m "docs: add 5 knowledge docs (nutrition, exercise, mental health, vaccination, travel)"
```

---

## Task 13: Verify and Test

- [ ] **Step 1: Verify no broken imports**

Run:
```bash
cd /media/amd-22oilkp/workspace/pregnent_care_agent/pregnent_care_agent/backend
python -c "from app.core.agno_knowledge import knowledge; print('Knowledge import OK')"
python -c "from app.core import knowledge; print('Core import OK')"
```

- [ ] **Step 2: Start Docker containers**

```bash
docker compose up -d postgres redis
```

Wait for healthy status:
```bash
docker compose ps
```

Expected: postgres and redis both "Up" or "healthy".

- [ ] **Step 3: Update .env for testing**

Ensure `.env` has:
```
DB_TYPE=postgres
RAG_ENABLED=true
EMBEDDING_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=<your-key>
EMBEDDING_MODEL=text-embedding-v3
```

- [ ] **Step 4: Run knowledge ingestion**

```bash
cd backend && python scripts/ingest_knowledge.py --force
```

Expected output for each of the 16 documents: `导入: xxx.md ... OK`

- [ ] **Step 5: Test RAG status endpoint**

```bash
curl http://localhost:8000/api/v1/chat/rag/status
```

Expected: JSON with `"enabled": true`, `"vector_db": "pgvector"`.

- [ ] **Step 6: Test RAG ask endpoint**

```bash
curl -X POST http://localhost:8000/api/v1/chat/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "孕期可以吃感冒药吗？", "top_k": 3}'
```

Expected: JSON with `"rag_used": true`, non-empty `answer` and `sources`.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat(rag): complete RAG migration to Agno native + 16 knowledge docs"
```
