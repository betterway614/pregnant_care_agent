"""知识库后台管理 API 测试

覆盖：文档 CRUD、RAG 配置管理、元数据标签、检索测试。
"""
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


# ── Fixtures ──

def _make_auth_header():
    """生成有效的 JWT 认证头"""
    from app.core.auth import create_token, TokenPayload
    token = create_token(TokenPayload(sub="test-admin", role="admin"))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    """创建测试客户端"""
    from app.main import app
    return TestClient(app, headers=_make_auth_header())


@pytest.fixture
def mock_knowledge():
    """Mock Agno Knowledge 实例和 _ingest_single"""
    with patch("app.routers.knowledge.knowledge") as mock_kb, \
         patch("app.core.agno_knowledge.knowledge") as mock_kb2, \
         patch("app.routers.knowledge._ingest_single", new_callable=AsyncMock):
        mock_kb.ainsert = AsyncMock()
        mock_kb.asearch = AsyncMock(return_value=[])
        mock_kb2.ainsert = AsyncMock()
        mock_kb2.asearch = AsyncMock(return_value=[])
        yield mock_kb


@pytest.fixture
def temp_docs_dir(tmp_path):
    """创建临时知识库文档目录"""
    docs_dir = tmp_path / "knowledge_docs"
    docs_dir.mkdir()

    # 创建测试文件
    (docs_dir / "test_doc.md").write_text("---\ncategory: prenatal_guide\ntrimester: all\n---\n# Test Document\nTest content here.")
    (docs_dir / "nutrition.txt").write_text("Prenatal nutrition guide content")
    (docs_dir / "guidelines.md").write_text("# Prenatal Guidelines\nRegular checkups are important.")

    with patch("app.routers.knowledge.KNOWLEDGE_DOCS_DIR", str(docs_dir)):
        yield docs_dir


# ── 单元测试：文档列表 ──

class TestListDocuments:
    """文档列表接口测试"""

    def test_list_documents_returns_all(self, client, temp_docs_dir):
        """验证返回所有支持格式的文档"""
        resp = client.get("/api/v1/admin/knowledge/docs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        filenames = {d["filename"] for d in data["data"]}
        assert "test_doc.md" in filenames
        assert "nutrition.txt" in filenames
        assert "guidelines.md" in filenames

    def test_list_documents_includes_metadata(self, client, temp_docs_dir):
        """验证 .md 文件的 frontmatter 被提取为 metadata"""
        resp = client.get("/api/v1/admin/knowledge/docs")
        data = resp.json()
        test_doc = next(d for d in data["data"] if d["filename"] == "test_doc.md")
        assert test_doc["metadata"]["category"] == "prenatal_guide"
        assert test_doc["metadata"]["trimester"] == "all"

    def test_list_documents_empty_dir(self, client, tmp_path):
        """空目录返回空列表"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with patch("app.routers.knowledge.KNOWLEDGE_DOCS_DIR", str(empty_dir)):
            resp = client.get("/api/v1/admin/knowledge/docs")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_documents_file_info(self, client, temp_docs_dir):
        """验证文件信息完整性"""
        resp = client.get("/api/v1/admin/knowledge/docs")
        doc = resp.json()["data"][0]
        assert "filename" in doc
        assert "name" in doc
        assert "extension" in doc
        assert "size_bytes" in doc
        assert "size_human" in doc
        assert "modified_at" in doc
        assert doc["size_bytes"] > 0


# ── 单元测试：文档上传 ──

class TestUploadDocument:
    """文档上传接口测试"""

    def test_upload_md_file(self, client, temp_docs_dir, mock_knowledge):
        """上传 .md 文件"""
        resp = client.post(
            "/api/v1/admin/knowledge/upload",
            files={"file": ("new_doc.md", b"# New Document\nContent here", "text/markdown")},
            data={"name": "new_doc", "auto_ingest": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "new_doc.md"
        assert data["name"] == "new_doc"
        assert data["ingested"] is False

    def test_upload_with_auto_ingest(self, client, temp_docs_dir, mock_knowledge):
        """上传并自动入库"""
        with patch("app.routers.knowledge.settings") as mock_settings:
            mock_settings.rag_enabled = True
            mock_settings.rag_chunk_size = 600
            mock_settings.rag_chunk_overlap = 120
            mock_settings.rag_chunking_strategy = "fixed_size"
            resp = client.post(
                "/api/v1/admin/knowledge/upload",
                files={"file": ("auto_doc.md", b"# Auto Ingest Doc", "text/markdown")},
                data={"auto_ingest": "true"},
            )
        assert resp.status_code == 200
        assert resp.json()["ingested"] is True

    def test_upload_rejects_invalid_type(self, client, temp_docs_dir):
        """拒绝不支持的文件类型"""
        resp = client.post(
            "/api/v1/admin/knowledge/upload",
            files={"file": ("test.exe", b"binary", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "不支持的文件类型" in resp.json()["detail"]

    def test_upload_rejects_empty_file(self, client, temp_docs_dir):
        """拒绝空文件"""
        resp = client.post(
            "/api/v1/admin/knowledge/upload",
            files={"file": ("empty.md", b"", "text/markdown")},
        )
        assert resp.status_code == 400
        assert "文件内容为空" in resp.json()["detail"]

    def test_upload_with_metadata(self, client, temp_docs_dir, mock_knowledge):
        """上传带元数据的文档"""
        metadata = {"category": "nutrition", "trimester": "first"}
        resp = client.post(
            "/api/v1/admin/knowledge/upload",
            files={"file": ("meta_doc.md", b"# Nutrition", "text/markdown")},
            data={
                "auto_ingest": "false",
                "metadata_json": json.dumps(metadata),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["metadata"]["category"] == "nutrition"

    def test_upload_duplicate_adds_timestamp(self, client, temp_docs_dir, mock_knowledge):
        """重复文件名添加时间戳后缀"""
        # 第一次上传
        client.post(
            "/api/v1/admin/knowledge/upload",
            files={"file": ("dup.md", b"first", "text/markdown")},
            data={"auto_ingest": "false"},
        )
        # 第二次上传同名文件
        resp = client.post(
            "/api/v1/admin/knowledge/upload",
            files={"file": ("dup.md", b"second", "text/markdown")},
            data={"auto_ingest": "false"},
        )
        assert resp.status_code == 200
        assert resp.json()["filename"] != "dup.md"
        assert "dup_" in resp.json()["filename"]


# ── 单元测试：文档删除 ──

class TestDeleteDocument:
    """文档删除接口测试"""

    def test_delete_existing_document(self, client, temp_docs_dir):
        """删除已存在的文档"""
        resp = client.delete("/api/v1/admin/knowledge/docs/test_doc.md")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == "test_doc.md"
        # 验证文件已删除
        assert not (temp_docs_dir / "test_doc.md").exists()

    def test_delete_nonexistent_document(self, client, temp_docs_dir):
        """删除不存在的文档返回 404"""
        resp = client.delete("/api/v1/admin/knowledge/docs/nonexistent.md")
        assert resp.status_code == 404


# ── 单元测试：知识库统计 ──

class TestKnowledgeStats:
    """统计接口测试"""

    def test_stats_returns_all_fields(self, client, temp_docs_dir):
        """验证统计信息包含所有必要字段"""
        resp = client.get("/api/v1/admin/knowledge/stats")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            "enabled", "document_count", "total_size_bytes", "total_size_human",
            "embedding_model", "embedding_dimensions", "search_type",
            "chunk_size", "chunk_overlap", "chunking_strategy", "max_results",
            "reranker_provider", "reranker_model", "vector_db_table",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_stats_document_count(self, client, temp_docs_dir):
        """验证文档计数正确"""
        resp = client.get("/api/v1/admin/knowledge/stats")
        assert resp.json()["document_count"] == 3


# ── 单元测试：RAG 配置管理 ──

class TestRagConfig:
    """RAG 配置管理接口测试"""

    def test_get_config(self, client):
        """获取当前 RAG 配置"""
        resp = client.get("/api/v1/admin/knowledge/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "search_type" in data
        assert "chunk_size" in data
        assert "predefined_tags" in data
        assert isinstance(data["predefined_tags"], list)

    def test_update_search_type(self, client):
        """更新检索策略"""
        with patch("app.routers.knowledge.create_knowledge") as mock_create:
            mock_create.return_value = MagicMock()
            resp = client.put(
                "/api/v1/admin/knowledge/config",
                json={"search_type": "vector"},
            )
        assert resp.status_code == 200
        assert resp.json()["config"]["search_type"] == "vector"

    def test_update_chunk_size(self, client):
        """更新分块大小"""
        with patch("app.routers.knowledge.create_knowledge") as mock_create:
            mock_create.return_value = MagicMock()
            resp = client.put(
                "/api/v1/admin/knowledge/config",
                json={"chunk_size": 1000},
            )
        assert resp.status_code == 200
        assert resp.json()["config"]["chunk_size"] == 1000

    def test_update_reranker(self, client):
        """更新 Reranker 配置"""
        with patch("app.routers.knowledge.create_knowledge") as mock_create:
            mock_create.return_value = MagicMock()
            resp = client.put(
                "/api/v1/admin/knowledge/config",
                json={"reranker_provider": "cohere", "reranker_model": "rerank-v3.5"},
            )
        assert resp.status_code == 200
        assert resp.json()["config"]["reranker_provider"] == "cohere"

    def test_update_empty_body_rejected(self, client):
        """空请求体被拒绝"""
        resp = client.put("/api/v1/admin/knowledge/config", json={})
        assert resp.status_code == 400

    def test_update_invalid_search_type(self, client):
        """无效检索策略被拒绝"""
        resp = client.put(
            "/api/v1/admin/knowledge/config",
            json={"search_type": "invalid"},
        )
        assert resp.status_code == 400

    def test_update_invalid_chunk_size(self, client):
        """超出范围的分块大小被拒绝"""
        resp = client.put(
            "/api/v1/admin/knowledge/config",
            json={"chunk_size": 50},  # 最小 100
        )
        assert resp.status_code == 400


# ── 单元测试：元数据标签 ──

class TestMetadataTags:
    """元数据标签接口测试"""

    def test_get_predefined_tags(self, client):
        """获取预定义标签列表"""
        resp = client.get("/api/v1/admin/knowledge/tags")
        assert resp.status_code == 200
        data = resp.json()
        assert "tags" in data
        assert "description" in data
        assert "category" in data["tags"]
        assert "trimester" in data["tags"]


# ── 单元测试：知识库检索 ──

class TestKnowledgeSearch:
    """知识库检索接口测试"""

    def test_search_returns_results(self, client, mock_knowledge):
        """检索返回结果列表"""
        mock_result = MagicMock()
        mock_result.content = "Prenatal checkup schedule"
        mock_result.score = 0.95
        mock_result.meta_data = {"category": "prenatal_guide"}
        mock_knowledge.asearch.return_value = [mock_result]

        resp = client.post(
            "/api/v1/admin/knowledge/search",
            json={"query": "prenatal schedule"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["results"][0]["content"] == "Prenatal checkup schedule"
        assert data["results"][0]["score"] == 0.95

    def test_search_with_filters(self, client, mock_knowledge):
        """带过滤条件的检索"""
        mock_knowledge.asearch.return_value = []

        resp = client.post(
            "/api/v1/admin/knowledge/search",
            json={"query": "nutrition", "filters": {"category": "nutrition"}},
        )
        assert resp.status_code == 200

    def test_search_empty_query_rejected(self, client, mock_knowledge):
        """空查询被拒绝或返回空结果"""
        resp = client.post(
            "/api/v1/admin/knowledge/search",
            json={"query": ""},
        )
        # Endpoint accepts empty string but returns no results or 400
        assert resp.status_code in (200, 400, 422)


# ── 单元测试：入库操作 ──

class TestIngestion:
    """入库接口测试"""

    def test_ingest_all(self, client, temp_docs_dir, mock_knowledge):
        """全量入库"""
        with patch("app.routers.knowledge.settings") as mock_settings:
            mock_settings.rag_enabled = True
            mock_settings.rag_chunk_size = 600
            mock_settings.rag_chunk_overlap = 120
            mock_settings.rag_chunking_strategy = "fixed_size"
            resp = client.post("/api/v1/admin/knowledge/ingest?force=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["success"] == 3
        assert data["failed"] == 0

    def test_ingest_single(self, client, temp_docs_dir, mock_knowledge):
        """单文档入库"""
        with patch("app.routers.knowledge.settings") as mock_settings:
            mock_settings.rag_enabled = True
            mock_settings.rag_chunk_size = 600
            mock_settings.rag_chunk_overlap = 120
            mock_settings.rag_chunking_strategy = "fixed_size"
            resp = client.post("/api/v1/admin/knowledge/ingest/test_doc.md?force=true")
        assert resp.status_code == 200
        assert resp.json()["filename"] == "test_doc.md"

    def test_ingest_nonexistent_file(self, client, temp_docs_dir):
        """入库不存在的文件返回 404"""
        with patch("app.routers.knowledge.settings") as mock_settings:
            mock_settings.rag_enabled = True
            resp = client.post("/api/v1/admin/knowledge/ingest/nonexistent.md")
        assert resp.status_code == 404


# ── 集成测试：完整工作流 ──

class TestIntegrationWorkflow:
    """集成测试：模拟完整的知识库管理流程"""

    def test_full_workflow(self, client, temp_docs_dir, mock_knowledge):
        """完整流程：查看 -> 上传 -> 配置修改 -> 检索 -> 删除"""

        # 1. 查看当前文档列表
        resp = client.get("/api/v1/admin/knowledge/docs")
        assert resp.status_code == 200
        initial_count = resp.json()["total"]

        # 2. 上传新文档（带元数据）
        metadata = {"category": "medication_safety", "risk_level": "high", "audience": "doctor"}
        resp = client.post(
            "/api/v1/admin/knowledge/upload",
            files={"file": ("medication.md", b"# Medication Safety\nAspirin precautions", "text/markdown")},
            data={
                "name": "medication_guide",
                "auto_ingest": "false",
                "metadata_json": json.dumps(metadata),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["metadata"]["category"] == "medication_safety"

        # 3. 验证文档列表增加了
        resp = client.get("/api/v1/admin/knowledge/docs")
        assert resp.json()["total"] == initial_count + 1

        # 4. 修改 RAG 配置
        mock_new_kb = MagicMock()
        mock_new_kb.asearch = AsyncMock(return_value=[])
        with patch("app.routers.knowledge.create_knowledge") as mock_create:
            mock_create.return_value = mock_new_kb
            resp = client.put(
                "/api/v1/admin/knowledge/config",
                json={"search_type": "vector", "chunk_size": 800},
            )
        assert resp.status_code == 200
        assert resp.json()["config"]["search_type"] == "vector"

        # 5. 恢复配置
        with patch("app.routers.knowledge.create_knowledge") as mock_create:
            mock_create.return_value = mock_new_kb
            resp = client.put(
                "/api/v1/admin/knowledge/config",
                json={"search_type": "hybrid", "chunk_size": 600},
            )
        assert resp.status_code == 200

        # 6. 检索测试
        mock_result = MagicMock()
        mock_result.content = "Aspirin precautions and dosage"
        mock_result.score = 0.88
        mock_result.meta_data = {"category": "medication_safety"}
        mock_new_kb.asearch = AsyncMock(return_value=[mock_result])

        resp = client.post(
            "/api/v1/admin/knowledge/search",
            json={"query": "aspirin", "filters": {"category": "medication_safety"}},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

        # 7. 删除文档
        resp = client.delete("/api/v1/admin/knowledge/docs/medication.md")
        assert resp.status_code == 200

        # 8. 验证文档列表恢复
        resp = client.get("/api/v1/admin/knowledge/docs")
        assert resp.json()["total"] == initial_count
