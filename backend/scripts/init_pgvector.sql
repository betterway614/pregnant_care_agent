-- pgvector 扩展初始化
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 知识库文档块表
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_title VARCHAR(256) NOT NULL,
    doc_category VARCHAR(64) NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- 向量索引 (IVFFlat)
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding
    ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 分类索引
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_category
    ON knowledge_chunks(doc_category);
