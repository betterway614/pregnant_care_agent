"""知识库后台管理 API

提供文档列表、上传、删除、重新入库、统计、RAG 配置管理、元数据过滤等功能，
与 Agno Knowledge + PgVector RAG 系统集成。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from pydantic import BaseModel
from ..config import settings
from ..core.agno_knowledge import knowledge, get_rag_config, create_knowledge

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/knowledge", tags=["知识库管理"])

# 知识库文档目录（与 ingest_knowledge.py 保持一致）
KNOWLEDGE_DOCS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_docs")
)

# 支持的文件类型
ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

# 医学知识库预定义元数据标签
PREDEFINED_TAGS = [
    "category",       # 分类：产检指南、用药安全、孕期疾病、营养饮食、心理健康 等
    "trimester",      # 孕期阶段：first / second / third / all
    "risk_level",     # 风险等级：low / medium / high
    "audience",       # 面向角色：patient / nurse / doctor / all
    "source",         # 来源：guideline / textbook / expert_opinion / research
    "language",       # 语言：zh / en
]


# ── 请求模型 ──

class RagConfigUpdate(BaseModel):
    """RAG 配置更新请求"""
    search_type: Optional[str] = None          # "vector" | "hybrid"
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    chunking_strategy: Optional[str] = None    # "fixed_size" | "recursive"
    max_results: Optional[int] = None
    reranker_provider: Optional[str] = None    # "" | "cohere" | "infinity"
    reranker_model: Optional[str] = None
    reranker_base_url: Optional[str] = None


class SearchRequest(BaseModel):
    """知识库检索请求"""
    query: str
    filters: Optional[dict[str, str]] = None   # 元数据过滤条件
    max_results: Optional[int] = None


# ── 工具函数 ──

def _get_docs_dir() -> str:
    """确保知识库目录存在并返回路径"""
    os.makedirs(KNOWLEDGE_DOCS_DIR, exist_ok=True)
    return KNOWLEDGE_DOCS_DIR


def _scan_documents() -> list[dict]:
    """扫描知识库目录，返回文档元信息列表"""
    docs_dir = _get_docs_dir()
    documents = []

    for fname in sorted(os.listdir(docs_dir)):
        fpath = os.path.join(docs_dir, fname)
        if not os.path.isfile(fpath):
            continue

        ext = os.path.splitext(fname)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue

        stat = os.stat(fpath)

        # 读取文档头部元数据（如果有 YAML frontmatter）
        metadata = _extract_frontmatter(fpath, ext)

        documents.append({
            "filename": fname,
            "name": os.path.splitext(fname)[0],
            "extension": ext,
            "size_bytes": stat.st_size,
            "size_human": _human_size(stat.st_size),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "metadata": metadata,
        })

    return documents


def _extract_frontmatter(fpath: str, ext: str) -> dict[str, str]:
    """从 Markdown 文件提取 YAML frontmatter 中的元数据"""
    if ext != ".md":
        return {}
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read(2000)  # 只读前 2KB
        if not content.startswith("---"):
            return {}
        end = content.find("---", 3)
        if end == -1:
            return {}
        fm_text = content[3:end].strip()
        # 简单 key: value 解析（不依赖 PyYAML）
        result = {}
        for line in fm_text.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                result[key.strip()] = val.strip()
        return result
    except Exception:
        return {}


def _human_size(size_bytes: int) -> str:
    """将字节数转换为人类可读格式"""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ── RAG 配置管理 ──

@router.get("/config")
def get_rag_config_endpoint():
    """获取当前 RAG 配置"""
    config = get_rag_config()
    config["predefined_tags"] = PREDEFINED_TAGS
    config["docs_directory"] = KNOWLEDGE_DOCS_DIR
    return config


@router.put("/config")
def update_rag_config(body: RagConfigUpdate):
    """动态更新 RAG 配置（运行时生效，重启后恢复 .env 默认值）

    更新会重建全局 Knowledge 单例，后续入库和检索使用新配置。
    """
    global knowledge
    import app.core.agno_knowledge as kb_module

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="未提供任何配置更新")

    # 验证枚举值
    if "search_type" in updates and updates["search_type"] not in ("vector", "hybrid"):
        raise HTTPException(status_code=400, detail="search_type 必须为 'vector' 或 'hybrid'")
    if "chunking_strategy" in updates and updates["chunking_strategy"] not in ("fixed_size", "recursive"):
        raise HTTPException(status_code=400, detail="chunking_strategy 必须为 'fixed_size' 或 'recursive'")
    if "reranker_provider" in updates and updates["reranker_provider"] not in ("", "cohere", "infinity"):
        raise HTTPException(status_code=400, detail="reranker_provider 必须为 ''、'cohere' 或 'infinity'")
    if "chunk_size" in updates and (updates["chunk_size"] < 100 or updates["chunk_size"] > 10000):
        raise HTTPException(status_code=400, detail="chunk_size 范围: 100-10000")
    if "max_results" in updates and (updates["max_results"] < 1 or updates["max_results"] > 50):
        raise HTTPException(status_code=400, detail="max_results 范围: 1-50")

    # 应用到 settings（运行时修改）
    # API 字段名 -> settings 属性名映射
    _settings_key_map = {
        "search_type": "rag_search_type",
        "chunk_size": "rag_chunk_size",
        "chunk_overlap": "rag_chunk_overlap",
        "chunking_strategy": "rag_chunking_strategy",
        "max_results": "rag_max_results",
    }
    for key, val in updates.items():
        settings_key = _settings_key_map.get(key, key)
        if hasattr(settings, settings_key):
            setattr(settings, settings_key, val)

    # 重建 Knowledge 实例
    new_knowledge = create_knowledge(updates)
    kb_module.knowledge = new_knowledge
    knowledge = new_knowledge

    logger.info("RAG 配置已更新: %s", updates)
    return {"message": "RAG 配置已更新", "config": get_rag_config()}


# ── 统计与文档管理 ──

@router.get("/stats")
def get_knowledge_stats():
    """获取知识库统计信息"""
    docs = _scan_documents()
    total_size = sum(d["size_bytes"] for d in docs)

    return {
        "enabled": settings.rag_enabled,
        "document_count": len(docs),
        "total_size_bytes": total_size,
        "total_size_human": _human_size(total_size),
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "search_type": settings.rag_search_type,
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "chunking_strategy": settings.rag_chunking_strategy,
        "max_results": settings.rag_max_results,
        "reranker_provider": settings.reranker_provider,
        "reranker_model": settings.reranker_model,
        "vector_db_table": settings.agno_knowledge_table,
        "docs_directory": KNOWLEDGE_DOCS_DIR,
    }


@router.get("/docs")
def list_documents():
    """列出所有知识库文档"""
    docs = _scan_documents()
    return {
        "total": len(docs),
        "data": docs,
    }


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    auto_ingest: bool = Form(True),
    auto_tag: bool = Form(True),
    metadata_json: Optional[str] = Form(None),
):
    """上传新文档到知识库

    Args:
        file: 上传的文件（支持 .md / .txt / .pdf）
        name: 文档显示名称（可选，默认使用文件名）
        auto_ingest: 是否自动入库（默认 True）
        auto_tag: 是否自动 AI 打标签（默认 True）
        metadata_json: 元数据 JSON 字符串，如 '{"category":"产检指南","trimester":"all"}'
    """
    # 校验文件类型
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}，仅支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 读取文件内容
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制 ({_human_size(MAX_FILE_SIZE)})",
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件内容为空")

    # 解析元数据
    metadata: dict[str, Any] = {}
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="metadata_json 格式无效")

    # 保存文件
    docs_dir = _get_docs_dir()
    save_path = os.path.join(docs_dir, filename)

    # 如果文件已存在，添加时间戳后缀
    if os.path.exists(save_path):
        base, ext_part = os.path.splitext(filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{base}_{timestamp}{ext_part}"
        save_path = os.path.join(docs_dir, filename)

    with open(save_path, "wb") as f:
        f.write(content)

    doc_name = name or os.path.splitext(filename)[0]

    # AI 自动打标签
    if auto_tag and not metadata:
        try:
            text_content = content.decode("utf-8", errors="ignore")[:4000]
            auto_meta = await _auto_tag_content(text_content, doc_name)
            if auto_meta:
                metadata = auto_meta
                logger.info("AI 自动标签生成成功: %s -> %s", filename, list(auto_meta.keys()))
        except Exception as e:
            logger.warning("AI 自动标签生成失败（继续入库）: %s", e)

    result = {
        "filename": filename,
        "name": doc_name,
        "size_bytes": len(content),
        "size_human": _human_size(len(content)),
        "auto_ingest": auto_ingest,
        "auto_tag": auto_tag,
        "ingested": False,
        "metadata": metadata,
    }

    # 自动入库
    if auto_ingest and settings.rag_enabled:
        try:
            await _ingest_single(save_path, doc_name, filename, metadata=metadata)
            result["ingested"] = True
        except Exception as e:
            logger.error("文档入库失败: %s - %s", filename, e)
            result["ingest_error"] = str(e)

    return result


@router.delete("/docs/{filename}")
def delete_document(filename: str):
    """删除指定知识库文档"""
    docs_dir = _get_docs_dir()
    fpath = os.path.join(docs_dir, filename)

    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail=f"文档不存在: {filename}")

    os.remove(fpath)
    logger.info("已删除知识库文档: %s", filename)

    return {"deleted": filename, "message": f"文档 {filename} 已删除"}


@router.post("/ingest")
async def ingest_all(force: bool = Query(False, description="是否强制重新入库（upsert）")):
    """触发全部文档入库"""
    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG 未启用")

    docs = _scan_documents()
    if not docs:
        return {"message": "无文档可入库", "success": 0, "failed": 0, "total": 0}

    success = 0
    failed = 0
    errors = []

    for doc in docs:
        fpath = os.path.join(_get_docs_dir(), doc["filename"])
        try:
            await _ingest_single(
                fpath, doc["name"], doc["filename"],
                metadata=doc.get("metadata", {}), force=force,
            )
            success += 1
        except Exception as e:
            failed += 1
            errors.append({"filename": doc["filename"], "error": str(e)})
            logger.error("入库失败: %s - %s", doc["filename"], e)

    return {
        "message": f"入库完成: {success}/{len(docs)} 成功",
        "success": success,
        "failed": failed,
        "total": len(docs),
        "errors": errors,
    }


@router.post("/ingest/{filename}")
async def ingest_single_doc(
    filename: str,
    force: bool = Query(False, description="是否强制重新入库"),
):
    """触发单个文档入库"""
    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG 未启用")

    docs_dir = _get_docs_dir()
    fpath = os.path.join(docs_dir, filename)

    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail=f"文档不存在: {filename}")

    try:
        doc_name = os.path.splitext(filename)[0]
        metadata = _extract_frontmatter(fpath, os.path.splitext(filename)[1].lower())
        await _ingest_single(fpath, doc_name, filename, metadata=metadata, force=force)
        return {
            "message": f"文档 {filename} 入库成功",
            "filename": filename,
            "name": doc_name,
        }
    except Exception as e:
        logger.error("单文档入库失败: %s - %s", filename, e)
        raise HTTPException(status_code=500, detail=f"入库失败: {e}")


# ── 知识库检索（带元数据过滤） ──

@router.post("/search")
async def search_knowledge(body: SearchRequest):
    """在知识库中检索（支持元数据过滤）

    使用 Agno Knowledge 的原生检索能力，支持：
    - 向量检索 (vector)：纯语义相似度
    - 混合检索 (hybrid)：语义 + 关键词
    - 元数据过滤：按 category、trimester、risk_level 等标签过滤
    """
    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG 未启用")

    try:
        # Agno Knowledge.search 支持 filters 参数
        search_kwargs: dict[str, Any] = {
            "query": body.query,
        }
        if body.filters:
            search_kwargs["filters"] = body.filters
        if body.max_results:
            search_kwargs["limit"] = body.max_results

        results = await knowledge.asearch(**search_kwargs)

        return {
            "query": body.query,
            "filters": body.filters or {},
            "results": [
                {
                    "content": r.content if hasattr(r, "content") else str(r),
                    "score": getattr(r, "score", None),
                    "metadata": getattr(r, "meta_data", None) or getattr(r, "metadata", {}),
                }
                for r in results
            ],
            "total": len(results),
        }
    except Exception as e:
        logger.error("知识库检索失败: %s", e)
        raise HTTPException(status_code=500, detail=f"检索失败: {e}")


# ── 嵌入文本块浏览 ──

def _resolve_knowledge_table(db) -> str:
    """解析 knowledge_chunks 表的实际 schema 限定名"""
    from sqlalchemy import text
    table_name = settings.agno_knowledge_table
    # 如果已经包含 schema 前缀，直接返回
    if "." in table_name:
        return table_name
    # 检查 public schema
    exists = db.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=:t"),
        {"t": table_name},
    ).fetchone()
    if exists:
        return table_name
    # 检查 ai schema（PgVector 默认）
    exists = db.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_schema='ai' AND table_name=:t"),
        {"t": table_name},
    ).fetchone()
    if exists:
        return f"ai.{table_name}"
    return table_name


@router.get("/chunks")
def list_chunks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    name: Optional[str] = Query(None, description="按文档名称筛选"),
):
    """浏览向量数据库中已入库的嵌入文本块"""
    from sqlalchemy import text
    from ..database import SessionLocal

    db = SessionLocal()
    table = _resolve_knowledge_table(db)
    try:
        count_sql = text(f"SELECT COUNT(*) FROM {table}")
        if name:
            count_sql = text(f"SELECT COUNT(*) FROM {table} WHERE name = :name")
            total = db.execute(count_sql, {"name": name}).scalar() or 0
        else:
            total = db.execute(count_sql).scalar() or 0

        offset = (page - 1) * page_size
        if name:
            query_sql = text(
                f"SELECT id, name, content, meta_data, filters, content_hash, content_id, created_at, updated_at "
                f"FROM {table} WHERE name = :name ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            )
            rows = db.execute(query_sql, {"name": name, "limit": page_size, "offset": offset}).fetchall()
        else:
            query_sql = text(
                f"SELECT id, name, content, meta_data, filters, content_hash, content_id, created_at, updated_at "
                f"FROM {table} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            )
            rows = db.execute(query_sql, {"limit": page_size, "offset": offset}).fetchall()

        chunks = []
        for row in rows:
            chunks.append({
                "id": row[0],
                "name": row[1],
                "content": row[2],
                "meta_data": row[3],
                "filters": row[4],
                "content_hash": row[5],
                "content_id": row[6],
                "created_at": row[7].isoformat() if row[7] else None,
                "updated_at": row[8].isoformat() if row[8] else None,
            })

        return {"total": total, "page": page, "page_size": page_size, "data": chunks}
    except Exception as e:
        logger.error("查询嵌入文本块失败: %s", e)
        return {"total": 0, "page": page, "page_size": page_size, "data": [], "error": str(e)}
    finally:
        db.close()


@router.get("/chunks/stats")
def get_chunk_stats():
    """获取嵌入文本块统计（按文档分组）"""
    from sqlalchemy import text
    from ..database import SessionLocal

    db = SessionLocal()
    table = _resolve_knowledge_table(db)
    try:
        group_sql = text(
            f"SELECT name, COUNT(*) as chunk_count, "
            f"MIN(LENGTH(content)) as min_len, MAX(LENGTH(content)) as max_len, "
            f"AVG(LENGTH(content))::int as avg_len "
            f"FROM {table} GROUP BY name ORDER BY name"
        )
        rows = db.execute(group_sql).fetchall()
        total_sql = text(f"SELECT COUNT(*) FROM {table}")
        total = db.execute(total_sql).scalar() or 0

        return {
            "total_chunks": total,
            "documents": [
                {
                    "name": row[0], "chunk_count": row[1],
                    "min_content_length": row[2], "max_content_length": row[3],
                    "avg_content_length": row[4],
                }
                for row in rows
            ],
        }
    except Exception as e:
        logger.error("查询嵌入统计失败: %s", e)
        return {"total_chunks": 0, "documents": [], "error": str(e)}
    finally:
        db.close()


# ── 元数据标签管理 ──

@router.get("/tags")
def get_predefined_tags():
    """获取预定义的元数据标签列表"""
    return {
        "tags": PREDEFINED_TAGS,
        "description": {
            "category": "文档分类：产检指南、用药安全、孕期疾病、营养饮食、心理健康等",
            "trimester": "孕期阶段：first(早期) / second(中期) / third(晚期) / all(全期)",
            "risk_level": "风险等级：low(低) / medium(中) / high(高)",
            "audience": "面向角色：patient(孕妇) / nurse(护士) / doctor(医生) / all(全部)",
            "source": "来源类型：guideline(指南) / textbook(教材) / expert_opinion(专家意见) / research(研究)",
            "language": "语言：zh(中文) / en(英文)",
        },
    }


# ── AI 自动打标签 ──

@router.post("/auto-tag")
async def auto_tag_document(filename: str = Query(..., description="文档文件名")):
    """对已存在的文档执行 AI 自动标签生成

    读取文档内容，调用 LLM 分析并返回推荐的元数据标签。
    """
    docs_dir = _get_docs_dir()
    fpath = os.path.join(docs_dir, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail=f"文档不存在: {filename}")

    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(4000)
        doc_name = os.path.splitext(filename)[0]
        tags = await _auto_tag_content(content, doc_name)
        return {"filename": filename, "tags": tags, "message": "AI 标签生成成功"}
    except Exception as e:
        logger.error("AI 标签生成失败: %s - %s", filename, e)
        raise HTTPException(status_code=500, detail=f"标签生成失败: {e}")


async def _auto_tag_content(content: str, doc_name: str) -> dict[str, str]:
    """调用 LLM 分析文档内容，自动生成元数据标签

    返回格式: {"category": "...", "trimester": "...", "risk_level": "...", "audience": "...", "summary": "..."}
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.llm_api_key or "sk-placeholder",
        base_url=settings.llm_base_url,
    )

    prompt = f"""你是一个医学文档分类专家。请分析以下孕期管理平台的文档内容，生成元数据标签。

文档名称：{doc_name}

文档内容（前4000字符）：
{content}

请严格按照以下 JSON 格式返回标签，不要返回其他内容：
{{
  "category": "从以下选择：产检指南、用药安全、孕期疾病、营养饮食、心理健康、运动安全、分娩准备、产后恢复、新生儿护理、实验室检查",
  "trimester": "从以下选择：first（孕早期1-12周）、second（孕中期13-27周）、third（孕晚期28-40周）、all（全孕期）",
  "risk_level": "从以下选择：low（低风险，一般科普）、medium（中风险，需关注）、high（高风险，需专业指导）",
  "audience": "从以下选择：patient（孕妇本人）、nurse（护士）、doctor（医生）、all（所有角色）",
  "language": "zh 或 en",
  "summary": "文档摘要，50字以内"
}}"""

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        result_text = response.choices[0].message.content.strip()

        # 提取 JSON（兼容 markdown code block）
        if "```" in result_text:
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            if start >= 0 and end > start:
                result_text = result_text[start:end]

        tags = json.loads(result_text)

        # 只保留允许的标签键
        valid_keys = {"category", "trimester", "risk_level", "audience", "language", "summary"}
        return {k: v for k, v in tags.items() if k in valid_keys and v}
    except json.JSONDecodeError:
        logger.warning("LLM 返回的标签不是有效 JSON: %s", result_text[:200])
        return {}
    except Exception as e:
        logger.warning("LLM 调用失败: %s", e)
        return {}


async def _ingest_single(
    fpath: str,
    doc_name: str,
    filename: str,
    metadata: dict | None = None,
    force: bool = False,
):
    """调用 Agno Knowledge 入库单个文档，支持元数据和分词策略"""
    from agno.knowledge.reader.pdf_reader import PDFReader
    from agno.knowledge.chunking.fixed_size_chunking import FixedSizeChunking

    ext = os.path.splitext(filename)[1].lower()

    # 构建分词策略
    chunking_strategy = None
    if settings.rag_chunking_strategy == "fixed_size":
        chunking_strategy = FixedSizeChunking(
            chunk_size=settings.rag_chunk_size,
            overlap=settings.rag_chunk_overlap,
        )

    reader = None
    if ext == ".pdf":
        reader = PDFReader(
            chunk_size=settings.rag_chunk_size,
            chunking_strategy=chunking_strategy,
        )
    elif ext in (".md", ".txt"):
        # Markdown/Text 也支持自定义分词
        if chunking_strategy:
            from agno.knowledge.reader.text_reader import TextReader
            reader = TextReader(chunking_strategy=chunking_strategy)

    # 合并元数据
    doc_metadata: dict[str, Any] = {
        "source": "admin_upload",
        "filename": filename,
        "uploaded_at": datetime.now().isoformat(),
    }
    if metadata:
        doc_metadata.update(metadata)

    kwargs: dict[str, Any] = {
        "path": fpath,
        "name": doc_name,
        "metadata": doc_metadata,
    }

    if reader:
        kwargs["reader"] = reader

    if force:
        kwargs["upsert"] = True

    await knowledge.ainsert(**kwargs)
    logger.info("文档入库完成: %s (%s) metadata=%s", doc_name, filename, doc_metadata)
