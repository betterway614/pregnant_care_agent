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
