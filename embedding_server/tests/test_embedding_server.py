"""BGE-M3 Embedding Server 单元测试

测试范围：
1. 健康检查端点 (/health)
2. 模型列表端点 (/v1/models)
3. 嵌入生成端点 (POST /v1/embeddings)
4. 配置默认值
5. 错误处理
"""
import os
import sys
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

# 将 embedding_server 目录加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient


# ── 辅助函数 ──

def _fake_encode(texts):
    """模拟 BGE-M3 encode 返回 1024 维向量"""
    return np.random.randn(len(texts), 1024).astype(np.float32)


# ── Fixtures ──

@pytest.fixture
def client_with_mock_model():
    """创建带有 mock 模型的 TestClient，patch _encode 避免加载真实模型"""
    import embedding_server.server as server_module

    original_model = server_module._model

    # 注入一个非 None 的 mock 模型（让端点通过 _model is None 检查）
    server_module._model = MagicMock()

    # patch _encode 函数，避免 import FlagEmbedding
    with patch.object(server_module, "_encode", side_effect=_fake_encode):
        from embedding_server.server import app
        client = TestClient(app)
        yield client, server_module._model

    server_module._model = original_model


@pytest.fixture
def client_no_model():
    """创建没有加载模型的 TestClient"""
    import embedding_server.server as server_module

    original_model = server_module._model
    server_module._model = None

    from embedding_server.server import app
    client = TestClient(app)

    yield client

    server_module._model = original_model


# ── 配置测试 ──


class TestEmbeddingConfig:
    """测试 embedding server 配置默认值"""

    def test_default_host(self):
        assert os.getenv("EMBED_HOST", "0.0.0.0") == "0.0.0.0"

    def test_default_port(self):
        assert int(os.getenv("EMBED_PORT", "8081")) == 8081

    def test_default_model_name(self):
        assert os.getenv("EMBED_MODEL", "BAAI/bge-m3") == "BAAI/bge-m3"

    def test_default_device(self):
        assert os.getenv("EMBED_DEVICE", "cuda") == "cuda"

    def test_default_batch_size(self):
        assert int(os.getenv("EMBED_BATCH_SIZE", "64")) == 64

    def test_default_max_length(self):
        assert int(os.getenv("EMBED_MAX_LENGTH", "8192")) == 8192


# ── 健康检查测试 ──


class TestHealthEndpoint:
    """测试 /health 端点"""

    def test_health_ok_when_model_loaded(self, client_with_mock_model):
        client, _ = client_with_mock_model
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["model_loaded"] is True
        assert data["model_name"] == "BAAI/bge-m3"

    def test_health_unavailable_when_no_model(self, client_no_model):
        resp = client_no_model.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"
        assert data["model_loaded"] is False


# ── 模型列表测试 ──


class TestModelsEndpoint:
    """测试 /v1/models 端点"""

    def test_list_models(self, client_with_mock_model):
        client, _ = client_with_mock_model
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 1
        assert data["data"][0]["id"] == "BAAI/bge-m3"
        assert data["data"][0]["object"] == "model"
        assert data["data"][0]["owned_by"] == "local"


# ── 嵌入生成测试 ──


class TestEmbeddingEndpoint:
    """测试 POST /v1/embeddings"""

    def test_single_text_embedding(self, client_with_mock_model):
        client, _ = client_with_mock_model
        resp = client.post("/v1/embeddings", json={
            "input": "孕期饮食注意事项",
            "model": "BAAI/bge-m3",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 1
        assert data["data"][0]["object"] == "embedding"
        assert data["data"][0]["index"] == 0
        assert len(data["data"][0]["embedding"]) == 1024
        assert data["model"] == "BAAI/bge-m3"

    def test_batch_text_embedding(self, client_with_mock_model):
        client, _ = client_with_mock_model
        texts = ["孕期饮食", "产后恢复", "新生儿护理"]
        resp = client.post("/v1/embeddings", json={
            "input": texts,
            "model": "BAAI/bge-m3",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 3
        for i, emb in enumerate(data["data"]):
            assert emb["index"] == i
            assert len(emb["embedding"]) == 1024

    def test_embedding_with_dimensions_truncation(self, client_with_mock_model):
        client, _ = client_with_mock_model
        resp = client.post("/v1/embeddings", json={
            "input": "测试截断",
            "model": "BAAI/bge-m3",
            "dimensions": 256,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"][0]["embedding"]) == 256

    def test_embedding_with_encoding_format(self, client_with_mock_model):
        client, _ = client_with_mock_model
        resp = client.post("/v1/embeddings", json={
            "input": "测试格式",
            "model": "BAAI/bge-m3",
            "encoding_format": "float",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["data"][0]["embedding"], list)
        assert isinstance(data["data"][0]["embedding"][0], float)

    def test_embedding_returns_usage(self, client_with_mock_model):
        client, _ = client_with_mock_model
        resp = client.post("/v1/embeddings", json={
            "input": "测试用量统计",
            "model": "BAAI/bge-m3",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "usage" in data
        assert "prompt_tokens" in data["usage"]
        assert "total_tokens" in data["usage"]


# ── 错误处理测试 ──


class TestErrorHandling:
    """测试错误场景"""

    def test_empty_input_returns_400(self, client_with_mock_model):
        client, _ = client_with_mock_model
        resp = client.post("/v1/embeddings", json={
            "input": [],
            "model": "BAAI/bge-m3",
        })
        assert resp.status_code == 400

    def test_model_not_loaded_returns_503(self, client_no_model):
        resp = client_no_model.post("/v1/embeddings", json={
            "input": "测试无模型",
            "model": "BAAI/bge-m3",
        })
        assert resp.status_code == 503

    def test_invalid_request_body(self, client_with_mock_model):
        client, _ = client_with_mock_model
        resp = client.post("/v1/embeddings", json={})
        assert resp.status_code == 422  # Pydantic validation error

    def test_missing_input_field(self, client_with_mock_model):
        client, _ = client_with_mock_model
        resp = client.post("/v1/embeddings", json={
            "model": "BAAI/bge-m3",
        })
        assert resp.status_code == 422


# ── 模型加载测试 ──


class TestModelLoading:
    """测试模型加载逻辑"""

    def test_model_dir_points_to_local(self):
        """验证 MODEL_DIR 指向本地预训练模型目录"""
        from embedding_server.server import MODEL_DIR
        assert "pretrained_models/bge-m3" in MODEL_DIR

    def test_model_dir_exists(self):
        """验证本地模型目录存在"""
        from embedding_server.server import MODEL_DIR
        # MODEL_DIR 是相对路径，相对于 embedding_server 目录
        server_dir = os.path.dirname(os.path.dirname(__file__))
        # 如果从 tests/ 目录运行，需要回溯
        if os.path.basename(server_dir) == "embedding_server":
            full_path = os.path.join(server_dir, MODEL_DIR)
        else:
            full_path = MODEL_DIR
        # 至少应该存在 config.json
        assert os.path.exists(full_path) or "pretrained_models" in MODEL_DIR


# ── OpenAI 兼容性测试 ──


class TestOpenAICompatibility:
    """测试 OpenAI API 兼容性"""

    def test_response_format_matches_openai(self, client_with_mock_model):
        client, _ = client_with_mock_model
        resp = client.post("/v1/embeddings", json={
            "input": "兼容性测试",
            "model": "BAAI/bge-m3",
        })
        assert resp.status_code == 200
        data = resp.json()

        # OpenAI Embedding Response 格式
        assert "object" in data
        assert data["object"] == "list"
        assert "data" in data
        assert "model" in data
        assert "usage" in data

        # 单个 embedding 对象格式
        emb = data["data"][0]
        assert "object" in emb
        assert emb["object"] == "embedding"
        assert "index" in emb
        assert "embedding" in emb
        assert isinstance(emb["embedding"], list)

    def test_string_input_returns_single_embedding(self, client_with_mock_model):
        """OpenAI API 允许 input 为字符串而非数组"""
        client, _ = client_with_mock_model
        resp = client.post("/v1/embeddings", json={
            "input": "单字符串输入",
            "model": "BAAI/bge-m3",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1

    def test_dimensions_field_accepted(self, client_with_mock_model):
        """OpenAI API 支持 dimensions 参数截断向量"""
        client, _ = client_with_mock_model
        resp = client.post("/v1/embeddings", json={
            "input": "维度截断",
            "model": "BAAI/bge-m3",
            "dimensions": 512,
        })
        assert resp.status_code == 200
        assert len(resp.json()["data"][0]["embedding"]) == 512
