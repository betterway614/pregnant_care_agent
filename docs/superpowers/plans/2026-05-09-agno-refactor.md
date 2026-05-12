# Agno 框架渐进式重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AI-Care 孕期智能管理平台的 LLM 客户端层、RAG 引擎、工具调用层逐步迁移到 Agno 框架，同时保留自定义 NLU/情绪分析/紧急检测等确定性医疗逻辑。

**Architecture:** 渐进式替换——先替换 LLM 客户端（收益最大、风险最低），再替换 RAG 引擎，最后重写随访工具层。NLU、情绪分析、紧急检测保留原有规则引擎不变。

**Tech Stack:** Agno (Agent Framework), FastAPI, SQLAlchemy, pgvector, OpenAI-compatible API

---

## 文件结构变更

| 操作 | 文件路径 | 职责 |
|------|----------|------|
| **创建** | `backend/app/core/agno_client.py` | Agno 模型适配器，封装 Agno 模型为兼容接口 |
| **创建** | `backend/app/core/agno_rag.py` | 基于 Agno Knowledge 的 RAG 引擎 |
| **创建** | `backend/app/core/agno_tools.py` | 基于 Agno @tool 的随访工具定义 |
| **创建** | `backend/app/core/agno_agent.py` | 主 Agent 定义，整合模型+知识+工具 |
| **修改** | `backend/requirements.txt` | 添加 agno 依赖 |
| **修改** | `backend/app/config.py` | 添加 Agno 相关配置项 |
| **修改** | `backend/app/core/__init__.py` | 导出新模块 |
| **修改** | `backend/app/core/llm_client.py` | 添加 AgnoLLMClient 适配器 |
| **修改** | `backend/app/routers/chat.py` | 集成 Agno Agent |
| **保留** | `backend/app/core/nlu_engine.py` | 不修改 |
| **保留** | `backend/app/core/memory_manager.py` | 不修改 |
| **保留** | `backend/app/core/rule_engine.py` | 不修改 |
| **保留** | `backend/app/core/embedding.py` | 不修改 |
| **删除(后续)** | `backend/app/core/rag_engine.py` | 被 agno_rag.py 替代后移除 |
| **删除(后续)** | `backend/app/core/followup_tools.py` | 被 agno_tools.py 替代后移除 |

---

### Task 1: 安装 Agno 并验证环境

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 添加 agno 依赖**

在 `backend/requirements.txt` 末尾添加：

```
agno>=1.0.0
```

- [ ] **Step 2: 安装依赖**

Run: `cd backend && pip install agno`
Expected: 安装成功，无报错

- [ ] **Step 3: 验证 agno 可导入**

Run: `python -c "from agno.agent import Agent; from agno.models.openai import OpenAIChat; print('agno OK')"`
Expected: 输出 `agno OK`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add agno dependency"
```

---

### Task 2: 添加 Agno 配置项

**Files:**
- Modify: `backend/app/config.py:6-20`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_config.py`：

```python
"""测试 Agno 配置项"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Settings


def test_agno_config_defaults():
    """验证默认配置值"""
    s = Settings()
    assert s.agno_enabled is False
    assert s.agno_model_id == "gpt-4o"
    assert s.agno_knowledge_dir == "data/knowledge"


def test_agno_config_from_env(monkeypatch):
    """验证环境变量覆盖"""
    monkeypatch.setenv("AGNO_ENABLED", "true")
    monkeypatch.setenv("AGNO_MODEL_ID", "deepseek-chat")
    s = Settings()
    assert s.agno_enabled is True
    assert s.agno_model_id == "deepseek-chat"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: FAIL — `Settings` 没有 `agno_enabled` 属性

- [ ] **Step 3: 添加配置项**

在 `backend/app/config.py` 的 `Settings` 类中，`seed_data` 字段之后添加：

```python
    # Agno 配置
    agno_enabled: bool = False
    agno_model_id: str = "gpt-4o"
    agno_knowledge_dir: str = "data/knowledge"
    agno_knowledge_table: str = "knowledge_chunks"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat: add agno configuration options"
```

---

### Task 3: 创建 Agno 模型适配器

**Files:**
- Create: `backend/app/core/agno_client.py`
- Modify: `backend/app/core/__init__.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_agno_client.py`：

```python
"""测试 Agno 模型适配器"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_get_agno_model_cloud():
    """验证云端模式返回 OpenAIChat 模型"""
    from app.core.agno_client import get_agno_model
    from app.config import Settings

    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "cloud"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_base_url = "https://api.test.com/v1"
        mock_settings.llm_model = "deepseek-chat"
        model = get_agno_model()
        assert model is not None


def test_get_agno_model_local():
    """验证本地模式返回 Ollama 模型"""
    from app.core.agno_client import get_agno_model

    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "local"
        mock_settings.ollama_host = "http://localhost:11434"
        mock_settings.local_model = "qwen2.5:7b"
        model = get_agno_model()
        assert model is not None


def test_get_agno_model_mock():
    """验证 mock 模式返回 DummyModel"""
    from app.core.agno_client import get_agno_model

    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "mock"
        model = get_agno_model()
        assert model is not None


@pytest.mark.asyncio
async def test_agno_client_chat():
    """验证 AgnoClient.chat 返回字符串"""
    from app.core.agno_client import AgnoClient

    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(content="测试回复")
    client = AgnoClient(agent=mock_agent)
    result = await client.chat([{"role": "user", "content": "你好"}])
    assert isinstance(result, str)
    assert result == "测试回复"


@pytest.mark.asyncio
async def test_agno_client_chat_stream():
    """验证 AgnoClient.chat_stream 异步生成"""
    from app.core.agno_client import AgnoClient

    mock_agent = MagicMock()

    async def mock_response_stream(*args, **kwargs):
        yield MagicMock(content="你")
        yield MagicMock(content="好")

    mock_agent.arun_stream = mock_response_stream
    client = AgnoClient(agent=mock_agent)
    chunks = []
    async for chunk in client.chat_stream([{"role": "user", "content": "你好"}]):
        chunks.append(chunk)
    assert chunks == ["你", "好"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_agno_client.py -v`
Expected: FAIL — `agno_client` 模块不存在

- [ ] **Step 3: 实现 agno_client.py**

创建 `backend/app/core/agno_client.py`：

```python
"""Agno 模型适配器 - 封装 Agno 模型为兼容 LLMClient 接口"""
from typing import AsyncGenerator, Optional
from ..config import settings


def get_agno_model():
    """根据配置返回 Agno 模型实例"""
    from agno.models.openai import OpenAIChat
    from agno.models.ollama import OllamaChat

    mode = settings.llm_mode

    if mode == "cloud":
        return OpenAIChat(
            id=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
    elif mode == "local":
        return OllamaChat(
            id=settings.local_model,
            host=settings.ollama_host,
        )
    else:
        # Mock 模式：使用 OpenAIChat 指向一个假地址（不会真正调用）
        return OpenAIChat(
            id="mock-model",
            api_key="mock-key",
            base_url="http://localhost:1/v1",
        )


class AgnoClient:
    """兼容 LLMClient 接口的 Agno 适配器"""

    def __init__(self, agent=None):
        from agno.agent import Agent
        self._agent = agent or Agent(
            model=get_agno_model(),
            markdown=True,
        )

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """同步对话接口"""
        user_msg = messages[-1]["content"] if messages else ""
        system_msg = ""
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
                break

        # Agno Agent 用 instructions 做 system prompt
        if system_msg:
            self._agent.instructions = [system_msg]

        response = self._agent.run(user_msg)
        return response.content or ""

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        """流式对话接口"""
        user_msg = messages[-1]["content"] if messages else ""
        system_msg = ""
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
                break

        if system_msg:
            self._agent.instructions = [system_msg]

        async for event in await self._agent.arun_stream(user_msg):
            if hasattr(event, "content") and event.content:
                yield event.content

    async def chat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """支持工具调用的对话 - 使用 Agno Agent 的工具循环"""
        # 当前阶段：回退到简单对话（工具集成在 Task 6）
        user_msg = messages[-1]["content"] if messages else ""
        system_msg = ""
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
                break

        if system_msg:
            self._agent.instructions = [system_msg]

        response = self._agent.run(user_msg)
        return {
            "role": "assistant",
            "content": response.content or "",
            "tool_calls": None,
        }


# 全局缓存
_agno_client_instance: Optional[AgnoClient] = None


def get_agno_client() -> AgnoClient:
    """获取 Agno 客户端单例"""
    global _agno_client_instance
    if _agno_client_instance is None:
        _agno_client_instance = AgnoClient()
    return _agno_client_instance


def reset_agno_client():
    """重置 Agno 客户端"""
    global _agno_client_instance
    _agno_client_instance = None
```

- [ ] **Step 4: 更新 `__init__.py` 导出**

在 `backend/app/core/__init__.py` 末尾的 `__all__` 列表中添加：

```python
from .agno_client import get_agno_client, AgnoClient, get_agno_model, reset_agno_client
```

并在 `__all__` 中追加：

```python
    "get_agno_client", "AgnoClient", "get_agno_model", "reset_agno_client",
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_agno_client.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/agno_client.py backend/app/core/__init__.py backend/tests/test_agno_client.py
git commit -m "feat: add Agno model adapter with LLMClient-compatible interface"
```

---

### Task 4: 创建基于 Agno 的 RAG 引擎

**Files:**
- Create: `backend/app/core/agno_rag.py`
- Modify: `backend/app/core/__init__.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_agno_rag.py`：

```python
"""测试 Agno RAG 引擎"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def test_agno_rag_search_returns_list():
    """验证 search 返回列表格式"""
    from app.core.agno_rag import AgnoRAGEngine

    mock_db = MagicMock()
    mock_rows = [
        MagicMock(
            id=1, doc_title="测试文档", doc_category="guideline",
            content="测试内容", chunk_index=0,
        )
    ]
    mock_db.execute.return_value.fetchall.return_value = mock_rows

    with patch("app.core.agno_rag.SessionLocal", return_value=mock_db):
        with patch("app.core.agno_rag.settings") as mock_settings:
            mock_settings.db_type = "postgres"
            engine = AgnoRAGEngine()
            engine._embedding = MagicMock()
            engine._embedding.embed.return_value = [[0.1] * 1024]
            results = engine.search("测试查询", top_k=1)
            assert isinstance(results, list)
            assert len(results) == 1
            assert results[0]["doc_title"] == "测试文档"


@pytest.mark.asyncio
async def test_agno_rag_ask_returns_dict():
    """验证 ask 返回标准字典格式"""
    from app.core.agno_rag import AgnoRAGEngine

    engine = AgnoRAGEngine()
    engine._embedding = MagicMock()
    engine._embedding.embed.return_value = [[0.1] * 1024]
    engine._llm = AsyncMock()
    engine._llm.chat = AsyncMock(return_value="测试回答")

    with patch.object(engine, "search") as mock_search:
        mock_search.return_value = [
            {"doc_title": "指南", "doc_category": "guideline",
             "content": "知识内容", "similarity": 0.9, "chunk_index": 0}
        ]
        result = await engine.ask("测试问题", patient_context="孕30周")
        assert "answer" in result
        assert "sources" in result
        assert "chunks" in result
        assert result["rag_used"] is True


@pytest.mark.asyncio
async def test_agno_rag_ask_no_results():
    """验证无结果时返回兜底回答"""
    from app.core.agno_rag import AgnoRAGEngine

    engine = AgnoRAGEngine()
    engine._embedding = MagicMock()
    engine._embedding.embed.return_value = [[0.1] * 1024]

    with patch.object(engine, "search") as mock_search:
        mock_search.return_value = []
        result = await engine.ask("不存在的问题")
        assert result["rag_used"] is False
        assert "抱歉" in result["answer"] or "咨询" in result["answer"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_agno_rag.py -v`
Expected: FAIL — `agno_rag` 模块不存在

- [ ] **Step 3: 实现 agno_rag.py**

创建 `backend/app/core/agno_rag.py`：

```python
"""RAG 检索增强生成引擎 - 基于 Agno 框架"""
from typing import Optional
from sqlalchemy import text


class AgnoRAGEngine:
    """Agno RAG 引擎 - 向量检索 + LLM 生成

    保持与原 RAGEngine 相同的接口签名，内部实现替换为 Agno 兼容方式。
    核心流程:
    1. 将用户问题向量化
    2. 在知识库中检索最相关的文档块
    3. 将检索结果作为上下文注入 LLM prompt
    4. LLM 基于知识库生成回答
    """

    def __init__(self, embedding_client=None, llm_client=None):
        self._embedding = embedding_client
        self._llm = llm_client

    @property
    def embedding(self):
        if self._embedding is None:
            from .embedding import get_embedding_client
            self._embedding = get_embedding_client()
        return self._embedding

    @property
    def llm(self):
        if self._llm is None:
            from .llm_client import get_llm_client
            self._llm = get_llm_client()
        return self._llm

    def search(self, query: str, top_k: int = 5,
               category: Optional[str] = None) -> list[dict]:
        """向量检索相关文档块（与原 RAGEngine.search 接口一致）"""
        from ..database import SessionLocal
        from ..config import settings

        db = SessionLocal()
        try:
            query_vec = self.embedding.embed([query])[0]
            vector_str = "[" + ",".join(str(v) for v in query_vec) + "]"

            if settings.db_type == "postgres":
                sql = text("""
                    SELECT id, doc_title, doc_category, content, chunk_index,
                           1 - (embedding <=> :vec) AS similarity
                    FROM knowledge_chunks
                    WHERE (:cat IS NULL OR doc_category = :cat)
                    ORDER BY embedding <=> :vec
                    LIMIT :k
                """)
                rows = db.execute(sql, {
                    "vec": vector_str,
                    "cat": category,
                    "k": top_k
                }).fetchall()

                return [
                    {
                        "doc_title": r.doc_title,
                        "doc_category": r.doc_category,
                        "content": r.content,
                        "similarity": round(float(r.similarity), 4),
                        "chunk_index": r.chunk_index,
                    }
                    for r in rows
                ]
            else:
                return self._keyword_search(db, query, top_k, category)
        except Exception as e:
            print(f"Warning: vector search failed: {e}")
            return []
        finally:
            db.close()

    def _keyword_search(self, db, query: str, top_k: int,
                        category: Optional[str]) -> list[dict]:
        """SQLite 关键词回退检索"""
        from ..models.vector_models import KnowledgeChunk

        keywords = query.split()
        q = db.query(KnowledgeChunk)
        if category:
            q = q.filter(KnowledgeChunk.doc_category == category)

        chunks = q.all()
        scored = []
        for chunk in chunks:
            score = sum(1 for kw in keywords if kw in chunk.content)
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda x: -x[0])
        top = scored[:top_k]

        return [
            {
                "doc_title": chunk.doc_title,
                "doc_category": chunk.doc_category,
                "content": chunk.content,
                "similarity": round(score / max(len(keywords), 1), 4),
                "chunk_index": chunk.chunk_index,
            }
            for score, chunk in top
        ]

    async def ask(self, question: str, patient_context: str = "",
                  top_k: int = 5) -> dict:
        """RAG 问答 - 检索 + 生成（与原接口一致）"""
        chunks = self.search(question, top_k=top_k)

        if not chunks:
            return {
                "answer": "抱歉，我暂时没有找到相关的医学知识来回答您的问题。建议您咨询产检医生获取更准确的指导。",
                "sources": [],
                "chunks": [],
                "rag_used": False,
            }

        knowledge = "\n\n".join([
            f"【参考来源: {c['doc_title']}】(相关度: {c['similarity']})\n{c['content']}"
            for c in chunks
        ])

        system_prompt = {
            "role": "system",
            "content": (
                "你是'小安'，一位温暖、专业的孕期智能助手。请基于以下产科医学知识库内容回答用户问题。\n\n"
                "要求：\n"
                "1. 优先使用知识库中的信息回答\n"
                "2. 用温暖亲切的语气，面向孕妇可理解的语言\n"
                "3. 绝不出具诊断结论或用药建议\n"
                "4. 回答末尾标注知识来源：『知识来源：《xxx》』\n"
                "5. 加兜底话术：'若不适持续，请务必联系医生哦'\n\n"
                f"孕妇上下文：{patient_context}\n\n"
                f"=== 知识库参考 ===\n{knowledge}\n=== 结束 ==="
            )
        }

        user_msg = {"role": "user", "content": question}

        try:
            answer = await self.llm.chat(
                [system_prompt, user_msg], max_tokens=1024
            )
        except Exception as e:
            print(f"Warning: LLM call failed, using fallback answer: {e}")
            answer = self._fallback_answer(chunks)

        sources = list(dict.fromkeys(
            (c["doc_title"], c["doc_category"]) for c in chunks
        ))

        return {
            "answer": answer,
            "sources": [{"title": s[0], "category": s[1]} for s in sources],
            "chunks": [
                {"content": c["content"][:200], "similarity": c["similarity"]}
                for c in chunks
            ],
            "rag_used": True,
        }

    def _fallback_answer(self, chunks: list[dict]) -> str:
        """LLM 不可用时的兜底回答"""
        top = chunks[0] if chunks else None
        if top:
            return (
                f"根据《{top['doc_title']}》中的信息：\n"
                f"{top['content'][:300]}\n\n"
                "以上为知识库参考信息，如需更详细的解答，请咨询您的产检医生。"
            )
        return "建议您咨询产检医生获取更准确的指导。"


# 全局单例
agno_rag_engine = AgnoRAGEngine()
```

- [ ] **Step 4: 更新 `__init__.py`**

在 `backend/app/core/__init__.py` 中添加导入：

```python
from .agno_rag import AgnoRAGEngine, agno_rag_engine
```

并在 `__all__` 中追加：

```python
    "AgnoRAGEngine", "agno_rag_engine",
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_agno_rag.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/agno_rag.py backend/app/core/__init__.py backend/tests/test_agno_rag.py
git commit -m "feat: add Agno-compatible RAG engine"
```

---

### Task 5: 创建基于 Agno @tool 的随访工具

**Files:**
- Create: `backend/app/core/agno_tools.py`
- Modify: `backend/app/core/__init__.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_agno_tools.py`：

```python
"""测试 Agno 随访工具"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4


@pytest.mark.asyncio
async def test_agno_get_followup_context():
    """验证 get_followup_context 工具返回正确格式"""
    from app.core.agno_tools import agno_get_followup_context

    mock_db = MagicMock()
    mock_record = MagicMock()
    mock_record.id = uuid4()
    mock_record.pregnant_id = "test-pid"
    mock_record.gestational_week = "30+2"
    mock_record.status = "in_progress"
    mock_record.self_reported_data = {}
    mock_record.health_education = []

    mock_pregnant = MagicMock()
    mock_pregnant.nickname = "小明"
    mock_pregnant.display_name = "张小明"
    mock_pregnant.risk_tags = ["GDM"]

    mock_db.query.return_value.filter.return_value.first.return_value = mock_record
    # 需要两次 query：一次 for record, 一次 for pregnant
    mock_db.query.side_effect = lambda model: MagicMock(
        filter=MagicMock(return_value=MagicMock(
            first=MagicMock(return_value=mock_record if model.__name__ == "FollowUpRecord" else mock_pregnant)
        ))
    )

    with patch("app.core.agno_tools.SessionLocal", return_value=mock_db):
        with patch("app.core.agno_tools.followup_service") as mock_svc:
            mock_svc.get_template.return_value = {
                "questions": [{"key": "feeling", "question": "感觉如何？"}]
            }
            mock_svc.get_template_from_questions.return_value = {
                "questions": [{"key": "feeling", "question": "感觉如何？"}]
            }
            result = await agno_get_followup_context(str(uuid4()))
            assert "record_id" in result
            assert "pending_questions" in result


@pytest.mark.asyncio
async def test_agno_record_answer():
    """验证 record_answer 工具保存数据"""
    from app.core.agno_tools import agno_record_answer

    mock_db = MagicMock()
    mock_record = MagicMock()
    mock_record.id = uuid4()
    mock_record.pregnant_id = "test-pid"
    mock_record.status = "in_progress"
    mock_record.self_reported_data = {}
    mock_record.chief_complaint = None

    mock_db.query.return_value.filter.return_value.first.return_value = mock_record

    with patch("app.core.agno_tools.SessionLocal", return_value=mock_db):
        with patch("app.core.agno_tools.followup_service") as mock_svc:
            mock_svc.get_template_from_questions.return_value = {
                "questions": [
                    {"key": "feeling", "question": "感觉如何？"},
                    {"key": "weight", "question": "体重多少？"},
                ]
            }
            mock_svc.extract_health_value.return_value = None
            result = await agno_record_answer(str(uuid4()), "feeling", "很好")
            assert result["success"] is True
            assert result["answered_count"] == 1
            assert result["all_questions_answered"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_agno_tools.py -v`
Expected: FAIL — `agno_tools` 模块不存在

- [ ] **Step 3: 实现 agno_tools.py**

创建 `backend/app/core/agno_tools.py`：

```python
"""随访智能体工具 - 基于 Agno @tool 装饰器

为 Agno Agent 提供三个可调用的工具函数，完成结构化随访问询：
1. agno_get_followup_context — 获取当前随访进度
2. agno_record_answer — 记录孕妇回答 + 保存健康数据
3. agno_complete_followup — 归档随访记录
"""
import json
from uuid import UUID
from datetime import datetime
from agno.tools import tool
from ..models import FollowUpRecord, Pregnant, HealthDataPoint
from ..services import followup_service


@tool
async def agno_get_followup_context(record_id: str) -> dict:
    """获取当前随访的上下文信息，包括模板问题列表、已记录的答案、孕妇基本信息。

    Args:
        record_id: 随访记录ID

    Returns:
        包含 record_id, patient_name, pending_questions, answered_count 等字段的字典
    """
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        record = db.query(FollowUpRecord).filter(
            FollowUpRecord.id == UUID(record_id)
        ).first()
        if not record:
            return {"error": "随访记录不存在"}

        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == record.pregnant_id
        ).first()

        current_data = record.self_reported_data or {}
        template = followup_service.get_template_from_questions(current_data)
        all_questions = template["questions"]

        answered_keys = set(current_data.keys())
        pending_questions = [q for q in all_questions if q["key"] not in answered_keys]

        return {
            "record_id": str(record.id),
            "patient_name": pregnant.nickname or pregnant.display_name if pregnant else "未知",
            "gestational_week": record.gestational_week or "?",
            "risk_tags": pregnant.risk_tags if pregnant else [],
            "pending_questions": [
                {"key": q["key"], "question": q["question"]} for q in pending_questions
            ],
            "answered_count": len(answered_keys),
            "total_count": len(all_questions),
            "status": record.status,
        }
    finally:
        db.close()


@tool
async def agno_record_answer(record_id: str, question_key: str, answer_text: str) -> dict:
    """记录孕妇对随访问题的回答。该工具会自动将可量化的健康数据保存到健康档案。

    Args:
        record_id: 随访记录ID
        question_key: 问题标识符，如 feeling/weight/bp/fetal_movement/diet/medication/wound
        answer_text: 孕妇的原始回答文本

    Returns:
        包含 success, answered_count, total_count, remaining_questions 等字段的字典
    """
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        record = db.query(FollowUpRecord).filter(
            FollowUpRecord.id == UUID(record_id)
        ).first()
        if not record:
            return {"error": "随访记录不存在"}
        if record.status == "confirmed":
            return {"error": "该随访已归档，无法继续记录"}

        current_data = dict(record.self_reported_data) if record.self_reported_data else {}
        current_data[question_key] = answer_text
        record.self_reported_data = current_data

        if question_key == "feeling" and not record.chief_complaint:
            record.chief_complaint = answer_text

        _try_save_health_data(record.pregnant_id, question_key, answer_text, db)

        db.commit()

        template = followup_service.get_template_from_questions(current_data)
        all_keys = [q["key"] for q in template["questions"]]
        remaining = [k for k in all_keys if k not in current_data]
        answered_count = len(current_data)
        total = len(all_keys)

        return {
            "success": True,
            "record_id": record_id,
            "question_key": question_key,
            "answered_count": answered_count,
            "total_count": total,
            "remaining_questions": remaining,
            "all_questions_answered": answered_count >= total,
        }
    finally:
        db.close()


@tool
async def agno_complete_followup(record_id: str, summary: str) -> dict:
    """完成随访并归档记录。当所有随访问题都回答完毕后调用此函数。

    Args:
        record_id: 随访记录ID
        summary: 本次随访的简要总结

    Returns:
        包含 success, summary, status 等字段的字典
    """
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        record = db.query(FollowUpRecord).filter(
            FollowUpRecord.id == UUID(record_id)
        ).first()
        if not record:
            return {"error": "随访记录不存在"}
        if record.status == "confirmed":
            return {"error": "该随访已归档", "record_id": record_id, "status": "confirmed"}

        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == record.pregnant_id
        ).first()

        final_summary = followup_service.generate_record_summary(
            patient_name=pregnant.display_name if pregnant else "未知",
            gest_week=record.gestational_week or "?",
            answers=record.self_reported_data or {},
        )
        if summary:
            final_summary = f"{final_summary} | 小结：{summary}"

        record.summary = final_summary
        record.status = "confirmed"
        db.commit()

        return {
            "success": True,
            "record_id": str(record.id),
            "summary": final_summary,
            "status": "confirmed",
            "health_education": record.health_education or [],
        }
    finally:
        db.close()


def _try_save_health_data(pregnant_id: str, question_key: str, text: str, db):
    """尝试从回答文本中提取可量化的健康数据并保存"""
    parsed = followup_service.extract_health_value(question_key, text)
    if not parsed:
        return

    source = "FOLLOWUP"

    if question_key == "bp":
        if "sbp" in parsed and "dbp" in parsed:
            _insert_health_point(db, pregnant_id, "sbp", parsed["sbp"], "mmHg", source)
            _insert_health_point(db, pregnant_id, "dbp", parsed["dbp"], "mmHg", source)
            return

    if "metric_code" in parsed:
        _insert_health_point(
            db, pregnant_id, parsed["metric_code"], parsed["value"],
            parsed.get("unit", ""), source
        )


def _insert_health_point(db, pregnant_id: str, metric_code: str,
                         value: float, unit: str, source: str):
    """插入一条健康数据点"""
    point = HealthDataPoint(
        pregnant_id=pregnant_id,
        metric_code=metric_code,
        value=float(value),
        unit=unit,
        recorded_at=datetime.utcnow(),
        source=source,
    )
    db.add(point)


# 工具列表，供 Agent 初始化时使用
AGNO_FOLLOWUP_TOOLS = [agno_get_followup_context, agno_record_answer, agno_complete_followup]
```

- [ ] **Step 4: 更新 `__init__.py`**

在 `backend/app/core/__init__.py` 中添加导入：

```python
from .agno_tools import AGNO_FOLLOWUP_TOOLS, agno_get_followup_context, agno_record_answer, agno_complete_followup
```

并在 `__all__` 中追加：

```python
    "AGNO_FOLLOWUP_TOOLS", "agno_get_followup_context", "agno_record_answer", "agno_complete_followup",
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_agno_tools.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/agno_tools.py backend/app/core/__init__.py backend/tests/test_agno_tools.py
git commit -m "feat: add Agno @tool based followup tools"
```

---

### Task 6: 创建主 Agent 定义

**Files:**
- Create: `backend/app/core/agno_agent.py`
- Modify: `backend/app/core/__init__.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_agno_agent.py`：

```python
"""测试 Agno 主 Agent"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


def test_create_main_agent():
    """验证主 Agent 创建成功"""
    from app.core.agno_agent import create_main_agent

    with patch("app.core.agno_agent.get_agno_model") as mock_model:
        mock_model.return_value = MagicMock()
        agent = create_main_agent()
        assert agent is not None
        assert agent.name == "小安"


def test_create_followup_agent():
    """验证随访 Agent 创建成功"""
    from app.core.agno_agent import create_followup_agent

    with patch("app.core.agno_agent.get_agno_model") as mock_model:
        mock_model.return_value = MagicMock()
        agent = create_followup_agent(patient_name="小明", gest_week="30+2")
        assert agent is not None
        assert "小明" in str(agent.instructions)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_agno_agent.py -v`
Expected: FAIL — `agno_agent` 模块不存在

- [ ] **Step 3: 实现 agno_agent.py**

创建 `backend/app/core/agno_agent.py`：

```python
"""Agno Agent 定义 - 主 Agent 和随访 Agent"""
from agno.agent import Agent
from .agno_client import get_agno_model


def create_main_agent() -> Agent:
    """创建主对话 Agent（小安）"""
    return Agent(
        name="小安",
        model=get_agno_model(),
        instructions=[
            "你是'小安'，一位温暖、专业的孕期智能助手。你的职责是：",
            "1. 用温暖亲切的语气回答孕期相关问题",
            "2. 帮助记录孕妇的健康数据（体重、血压、胎动等）",
            "3. 提供情绪安抚和支持",
            "4. 回答孕期基础生理知识",
            "5. 绝不出具诊断结论或用药建议",
            "6. 所有知识性回答末尾必须标注'知识来源'标签，格式为：『知识来源：<具体指南/文献名称>』",
            "7. 若识别到紧急情况，引导就医",
            "8. 若孕妇询问的问题超出你的知识范围，请回复：'这个问题建议您咨询产检医生，小安暂时无法提供确切答案。'",
            "记住：你是辅助工具，不能替代医生的专业判断。",
        ],
        markdown=True,
    )


def create_followup_agent(patient_name: str = "准妈妈",
                          gest_week: str = "?",
                          risk_tags: list[str] | None = None,
                          record_id: str = "",
                          template_name: str = "standard",
                          health_education: list[str] | None = None) -> Agent:
    """创建随访模式 Agent"""
    from .agno_tools import AGNO_FOLLOWUP_TOOLS

    risk_text = "、".join(risk_tags) if risk_tags else "无"
    edu_text = "\n".join(f"- {item}" for item in (health_education or []))

    instructions = [
        f"你是'小安'，一位温暖、贴心的孕期智能助手。当前处于【随访模式】。",
        "",
        "【孕妇信息】",
        f"- 称呼: {patient_name}",
        f"- 孕周: {gest_week}周",
        f"- 风险标签: {risk_text}",
        "",
        "【随访信息】",
        f"- 随访记录ID: {record_id}",
        f"- template_name: {template_name}",
        "",
        "【核心人设要求——务必遵守】",
        "你必须用以下风格与孕妇交流：",
        "",
        f"1. 【称呼方式】直接称呼孕妇昵称\"{patient_name}\"",
        "2. 【语气风格】温暖亲切，像闺蜜或姐姐一样聊天。多用语气词（呀、呢、哦、嘛、啦）",
        "3. 【提问方式】每次只问一个问题，用自然的过渡引出",
        "4. 【回答反馈】每次孕妇回答后，先给予温暖的认可和简单反馈，再问下一题",
        "5. 【情绪价值】主动关心孕妇感受，提供简短温馨的健康提示",
        "6. 【规则】绝不出具诊断结论或用药建议。如果孕妇表现出紧急症状，引导就医。",
        "",
        "【工具使用流程】",
        "1. 首先调用 agno_get_followup_context 获取随访模板和当前进度",
        "2. 根据模板逐一提问，每次用 agno_record_answer 记录孕妇回答",
        "3. 所有问题完成后，调用 agno_complete_followup 归档记录",
        "",
        f"【健康教育内容】\n{edu_text if edu_text else '无'}",
    ]

    return Agent(
        name="小安-随访",
        model=get_agno_model(),
        instructions=instructions,
        tools=AGNO_FOLLOWUP_TOOLS,
        markdown=True,
    )
```

- [ ] **Step 4: 更新 `__init__.py`**

在 `backend/app/core/__init__.py` 中添加导入：

```python
from .agno_agent import create_main_agent, create_followup_agent
```

并在 `__all__` 中追加：

```python
    "create_main_agent", "create_followup_agent",
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_agno_agent.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/agno_agent.py backend/app/core/__init__.py backend/tests/test_agno_agent.py
git commit -m "feat: add Agno main agent and followup agent definitions"
```

---

### Task 7: 集成到 Chat Router（渐进切换）

**Files:**
- Modify: `backend/app/routers/chat.py:1-20`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_chat_agno_integration.py`：

```python
"""测试 Chat Router Agno 集成"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_send_message_uses_agno_when_enabled():
    """验证 agno_enabled=True 时使用 Agno Agent"""
    from app.routers.chat import send_message
    from app.schemas import ChatSendRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = True
        with patch("app.routers.chat.get_agno_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock(return_value="Agno回复")
            mock_get_client.return_value = mock_client
            with patch("app.routers.chat.nlu_engine") as mock_nlu:
                mock_nlu.parse.return_value = MagicMock(
                    intent="GREETING", entities={}, is_emergency=False,
                    emotion={"level": "neutral", "score": 0}
                )
                with patch("app.routers.chat.SessionLocal") as mock_db:
                    mock_db.return_value.query.return_value.filter.return_value.first.return_value = None
                    req = ChatSendRequest(
                        pregnant_id="test-pid",
                        message="你好",
                    )
                    resp = await send_message(req)
                    assert resp.content == "Agno回复"
                    mock_client.chat.assert_called_once()


@pytest.mark.asyncio
async def test_send_message_uses_original_when_disabled():
    """验证 agno_enabled=False 时使用原始 LLM"""
    from app.routers.chat import send_message
    from app.schemas import ChatSendRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = False
        with patch("app.routers.chat.llm") as mock_llm:
            mock_llm.chat = AsyncMock(return_value="原始回复")
            with patch("app.routers.chat.nlu_engine") as mock_nlu:
                mock_nlu.parse.return_value = MagicMock(
                    intent="GREETING", entities={}, is_emergency=False,
                    emotion={"level": "neutral", "score": 0}
                )
                with patch("app.routers.chat.SessionLocal") as mock_db:
                    mock_db.return_value.query.return_value.filter.return_value.first.return_value = None
                    req = ChatSendRequest(
                        pregnant_id="test-pid",
                        message="你好",
                    )
                    resp = await send_message(req)
                    assert resp.content == "原始回复"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_chat_agno_integration.py -v`
Expected: FAIL — `settings` 无 `agno_enabled` 或导入错误

- [ ] **Step 3: 修改 chat.py 集成 Agno**

在 `backend/app/routers/chat.py` 顶部导入区域添加：

```python
from ..config import settings
```

在 `send_message` 函数中，`# 5. 调用LLM获取回复` 之前，添加 Agno 分支逻辑。将原来的：

```python
    # 5. 调用LLM获取回复
    try:
        response = await llm.chat([system_prompt, user_msg], max_tokens=1024)
    except Exception as e:
        # LLM调用失败时回退到mock
        from ..core import MockLLMClient
        mock = MockLLMClient()
        response = await mock.chat([system_prompt, user_msg])
```

替换为：

```python
    # 5. 调用LLM获取回复（支持 Agno 模式切换）
    try:
        if settings.agno_enabled:
            from ..core.agno_client import get_agno_client
            agno = get_agno_client()
            response = await agno.chat([system_prompt, user_msg])
        else:
            response = await llm.chat([system_prompt, user_msg], max_tokens=1024)
    except Exception as e:
        from ..core import MockLLMClient
        mock = MockLLMClient()
        response = await mock.chat([system_prompt, user_msg])
```

在 `_build_chat_context` 函数中同样添加 Agno 分支，在 LLM 调用处保持一致的切换逻辑。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_chat_agno_integration.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/chat.py backend/tests/test_chat_agno_integration.py
git commit -m "feat: integrate Agno agent into chat router with feature toggle"
```

---

### Task 8: 集成到护士/医生 AI Router

**Files:**
- Modify: `backend/app/routers/nurse_ai.py:107-112`
- Modify: `backend/app/routers/doctor_ai.py:131-158`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_nurse_doctor_agno.py`：

```python
"""测试护士/医生 AI Router Agno 集成"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_nurse_analyze_uses_agno():
    """验证护士分析使用 Agno"""
    from app.routers.nurse_ai import _try_llm_nurse_analyze
    from app.models import Pregnant

    mock_pregnant = MagicMock(spec=Pregnant)
    mock_pregnant.pregnant_id = "test-pid"
    mock_pregnant.display_name = "测试"
    mock_pregnant.nickname = "小明"

    with patch("app.routers.nurse_ai.settings") as mock_settings:
        mock_settings.agno_enabled = True
        with patch("app.routers.nurse_ai.get_agno_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock(return_value='{"summary":"测试概述","risk_assessment":"低风险","nursing_suggestions":"建议休息","followup_focus":["饮食"]}')
            mock_get.return_value = mock_client
            result = await _try_llm_nurse_analyze(mock_pregnant, 30, 2, [], {})
            assert result is not None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_nurse_doctor_agno.py -v`
Expected: FAIL

- [ ] **Step 3: 修改 nurse_ai.py**

在 `backend/app/routers/nurse_ai.py` 中 `_try_llm_nurse_analyze` 函数里，将：

```python
        client = get_llm_client()
```

替换为：

```python
        from ..config import settings
        if settings.agno_enabled:
            from ..core.agno_client import get_agno_client
            client = get_agno_client()
        else:
            client = get_llm_client()
```

- [ ] **Step 4: 修改 doctor_ai.py**

同样在 `backend/app/routers/doctor_ai.py` 的 `_try_llm_doctor_analyze` 函数中：

```python
        from ..config import settings
        if settings.agno_enabled:
            from ..core.agno_client import get_agno_client
            client = get_agno_client()
        else:
            client = get_llm_client()
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_nurse_doctor_agno.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/nurse_ai.py backend/app/routers/doctor_ai.py backend/tests/test_nurse_doctor_agno.py
git commit -m "feat: add Agno toggle to nurse and doctor AI routers"
```

---

### Task 9: 集成到 RAG Router

**Files:**
- Modify: `backend/app/routers/chat.py:553-620`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_rag_agno.py`：

```python
"""测试 RAG Router Agno 集成"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_rag_ask_uses_agno_engine():
    """验证 RAG 问答在 agno_enabled=True 时使用 AgnoRAGEngine"""
    from app.routers.chat import rag_ask
    from app.routers.chat import RAGAskRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = True
        mock_settings.rag_enabled = True
        with patch("app.routers.chat.agno_rag_engine") as mock_engine:
            mock_engine.ask = AsyncMock(return_value={
                "answer": "Agno回答",
                "sources": [],
                "chunks": [],
                "rag_used": True,
            })
            with patch("app.routers.chat.SessionLocal") as mock_db:
                mock_db.return_value.query.return_value.filter.return_value.first.return_value = None
                req = RAGAskRequest(question="测试", pregnant_id="test-pid")
                result = await rag_ask(req)
                assert result.answer == "Agno回答"
                mock_engine.ask.assert_called_once()


@pytest.mark.asyncio
async def test_rag_ask_uses_original_engine():
    """验证 RAG 问答在 agno_enabled=False 时使用原始引擎"""
    from app.routers.chat import rag_ask
    from app.routers.chat import RAGAskRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = False
        mock_settings.rag_enabled = True
        with patch("app.routers.chat.rag_engine") as mock_engine:
            mock_engine.ask = AsyncMock(return_value={
                "answer": "原始回答",
                "sources": [],
                "chunks": [],
                "rag_used": True,
            })
            with patch("app.routers.chat.SessionLocal") as mock_db:
                mock_db.return_value.query.return_value.filter.return_value.first.return_value = None
                req = RAGAskRequest(question="测试", pregnant_id="test-pid")
                result = await rag_ask(req)
                assert result.answer == "原始回答"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_rag_agno.py -v`
Expected: FAIL

- [ ] **Step 3: 修改 chat.py 的 rag_ask 端点**

在 `backend/app/routers/chat.py` 顶部导入区域添加：

```python
from ..core.agno_rag import agno_rag_engine
```

在 `rag_ask` 端点函数中，将：

```python
    result = await rag_engine.ask(
        question=req.question,
        patient_context=patient_context,
        top_k=req.top_k,
    )
```

替换为：

```python
    if settings.agno_enabled:
        result = await agno_rag_engine.ask(
            question=req.question,
            patient_context=patient_context,
            top_k=req.top_k,
        )
    else:
        result = await rag_engine.ask(
            question=req.question,
            patient_context=patient_context,
            top_k=req.top_k,
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_rag_agno.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/chat.py backend/tests/test_rag_agno.py
git commit -m "feat: add Agno RAG engine toggle to RAG router"
```

---

### Task 10: 运行全部测试并验证

**Files:** 无新增

- [ ] **Step 1: 运行全部测试**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: 所有测试通过

- [ ] **Step 2: 验证原有功能不受影响**

Run: `cd backend && python -c "from app.main import app; print('App loads OK')"`
Expected: `App loads OK`

- [ ] **Step 3: 验证 Agno 可用性**

Run: `cd backend && python -c "from app.core.agno_agent import create_main_agent; a = create_main_agent(); print(f'Agent: {a.name}')"`
Expected: `Agent: 小安`

- [ ] **Step 4: Commit（如有遗漏的测试修复）**

```bash
git add -A
git commit -m "test: verify all tests pass with Agno integration"
```

---

## 使用方式

重构完成后，通过环境变量控制 Agno 切换：

```bash
# 启用 Agno 模式
AGNO_ENABLED=true

# 禁用 Agno（使用原始实现，向后兼容）
AGNO_ENABLED=false  # 或不设置，默认 false
```

所有 API 端点保持不变，前端无需任何修改。

---

## 迁移路径总结

| 阶段 | 内容 | 风险 |
|------|------|------|
| **Phase 1 (Task 1-3)** | 安装 Agno + 模型适配器 | 低 — 只是新代码，不影响现有功能 |
| **Phase 2 (Task 4-6)** | RAG 引擎 + 工具 + Agent | 低 — 新模块独立测试 |
| **Phase 3 (Task 7-9)** | 集成到 Router + Feature Toggle | 中 — 需要测试切换逻辑 |
| **Phase 4 (Task 10)** | 全量测试验证 | 低 — 确认无回归 |
| **后续** | 移除旧 rag_engine / followup_tools | 待 Agno 模式稳定后 |
