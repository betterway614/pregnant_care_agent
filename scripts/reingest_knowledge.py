#!/usr/bin/env python3
"""
知识库重新向量化脚本
清空现有向量数据，使用本地 bge-m3 重新嵌入所有文档
"""
import asyncio
import os
import sys

# 切换到 backend 目录
BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from sqlalchemy import create_engine, text
from app.config import settings
from app.core.agno_knowledge import knowledge, create_knowledge
from agno.knowledge.chunking.fixed import FixedSizeChunking

# 知识库文档目录
KNOWLEDGE_DOCS_DIR = os.path.normpath(
    os.path.join(BACKEND_DIR, "knowledge_docs")
)


def clear_vectors():
    """清空向量数据库中的现有嵌入数据"""
    print(f"\n[1/3] 清空向量数据库表: {settings.agno_knowledge_table}")
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        # 检查表是否存在
        exists = conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=:t"
        ), {"t": settings.agno_knowledge_table}).fetchone()
        if not exists:
            print(f"  表不存在，跳过清空（首次入库）")
            engine.dispose()
            return
        # 删除所有记录
        result = conn.execute(text(f"DELETE FROM {settings.agno_knowledge_table}"))
        conn.commit()
        print(f"  已删除 {result.rowcount} 条旧向量记录")
    engine.dispose()


def scan_documents():
    """扫描知识库目录"""
    print(f"\n[2/3] 扫描知识库目录: {KNOWLEDGE_DOCS_DIR}")
    docs = []
    for fname in sorted(os.listdir(KNOWLEDGE_DOCS_DIR)):
        fpath = os.path.join(KNOWLEDGE_DOCS_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext in (".md", ".txt", ".pdf"):
            docs.append((fpath, fname))
    print(f"  发现 {len(docs)} 个文档")
    return docs


async def reingest_all(docs):
    """重新嵌入所有文档"""
    print(f"\n[3/3] 重新向量化 (使用 {settings.embedding_model} @ {settings.embedding_api_url})")
    print(f"  Embedding 维度: {settings.embedding_dimensions}")
    print(f"  分词策略: {settings.rag_chunking_strategy} (size={settings.rag_chunk_size}, overlap={settings.rag_chunk_overlap})")
    print()

    success = 0
    failed = 0

    for i, (fpath, fname) in enumerate(docs, 1):
        doc_name = os.path.splitext(fname)[0]
        ext = os.path.splitext(fname)[1].lower()
        print(f"  [{i}/{len(docs)}] {fname} ...", end=" ", flush=True)

        try:
            chunking_strategy = None
            if settings.rag_chunking_strategy == "fixed_size":
                chunking_strategy = FixedSizeChunking(
                    chunk_size=settings.rag_chunk_size,
                    overlap=settings.rag_chunk_overlap,
                )

            reader = None
            if ext == ".pdf":
                from agno.knowledge.reader.pdf_reader import PDFReader
                reader = PDFReader(
                    chunk_size=settings.rag_chunk_size,
                    chunking_strategy=chunking_strategy,
                )
            elif ext in (".md", ".txt"):
                if chunking_strategy:
                    from agno.knowledge.reader.text_reader import TextReader
                    reader = TextReader(chunking_strategy=chunking_strategy)

            doc_metadata = {
                "source": "admin_upload",
                "filename": fname,
            }

            kwargs = {
                "path": fpath,
                "name": doc_name,
                "metadata": doc_metadata,
                "upsert": True,
            }

            if reader:
                kwargs["reader"] = reader

            await knowledge.ainsert(**kwargs)
            print("OK")
            success += 1
        except Exception as e:
            print(f"FAILED: {e}")
            failed += 1

    print(f"\n完成: {success} 成功, {failed} 失败")
    return success, failed


def verify():
    """验证重新入库后的数据"""
    print(f"\n[验证] 检查向量数据库...")
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM {settings.agno_knowledge_table}")).scalar()
        print(f"  总向量记录数: {total}")

        # 按文档分组统计
        rows = conn.execute(text(
            f"SELECT name, COUNT(*) FROM {settings.agno_knowledge_table} GROUP BY name ORDER BY name"
        )).fetchall()
        print(f"  文档分布:")
        for row in rows:
            print(f"    - {row[0]}: {row[1]} chunks")
    engine.dispose()


async def main():
    print("=" * 60)
    print("  知识库重新向量化")
    print("=" * 60)

    # 1. 清空旧向量
    clear_vectors()

    # 2. 扫描文档
    docs = scan_documents()
    if not docs:
        print("无文档可处理")
        return

    # 3. 重新嵌入
    success, failed = await reingest_all(docs)

    # 4. 验证
    verify()

    print("\n" + "=" * 60)
    print(f"  完成！使用 bge-m3 (1024维) 重新向量化 {success} 个文档")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
