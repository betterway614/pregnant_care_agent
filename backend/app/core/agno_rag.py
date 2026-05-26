"""RAG 检索增强生成引擎（Agno 生产路径唯一实现）"""
import logging
from typing import Optional
from sqlalchemy import text

logger = logging.getLogger(__name__)

class RAGEngine:
    """RAG引擎 - 向量检索 + LLM生成"""

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
            return self._keyword_search(db, query, top_k, category)
        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            return []
        finally:
            db.close()

    def _keyword_search(self, db, query: str, top_k: int,
                        category: Optional[str]) -> list[dict]:
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
        top = chunks[0] if chunks else None
        if top:
            return (
                f"根据《{top['doc_title']}》中的信息：\n"
                f"{top['content'][:300]}\n\n"
                "以上为知识库参考信息，如需更详细的解答，请咨询您的产检医生。"
            )
        return "建议您咨询产检医生获取更准确的指导。"


rag_engine = RAGEngine()
agno_rag_engine = rag_engine
AgnoRAGEngine = RAGEngine
