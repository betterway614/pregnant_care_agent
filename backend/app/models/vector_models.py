"""pgvector 向量表模型（仅PostgreSQL环境生效）"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..database import Base
from ..config import settings
from ..utils.timezone import beijing_now


class KnowledgeChunk(Base):
    """知识库文档块（pgvector）"""
    __tablename__ = "knowledge_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_title = Column(String(256), nullable=False, comment="文档标题")
    doc_category = Column(String(64), nullable=False, comment="分类: guideline/drug/education")
    chunk_index = Column(Integer, nullable=False, comment="块序号")
    content = Column(Text, nullable=False, comment="文本内容")
    chunk_metadata = Column("metadata", JSONB, default={}, comment="元数据")

    created_at = Column(DateTime, default=beijing_now)

    __table_args__ = (
        Index("idx_kc_category", "doc_category"),
        {"keep_existing": True},
    )

    def __repr__(self):
        return f"<KnowledgeChunk {self.doc_title}[{self.chunk_index}]>"
