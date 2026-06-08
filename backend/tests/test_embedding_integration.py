"""BGE-M3 嵌入服务集成测试

验证后端应用能通过 HTTP 实际调用本地 BGE-M3 嵌入服务 (localhost:8081)。

注意：这些测试需要 BGE-M3 embedding server 正在运行。
启动方式: python embedding_server/server.py
跳过方式: pytest -m "not integration" 或 设置环境变量 SKIP_INTEGRATION=1
"""
import os
import sys
import pytest
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── 配置 ──
EMBED_BASE_URL = os.getenv("EMBEDDING_API_URL", "http://localhost:8081/v1")
EMBED_HEALTH_URL = EMBED_BASE_URL.rsplit("/v1", 1)[0] + "/health"
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBED_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))

# 检查是否跳过集成测试
SKIP_REASON = ""
if os.getenv("SKIP_INTEGRATION", "").lower() in ("1", "true", "yes"):
    SKIP_REASON = "SKIP_INTEGRATION 环境变量已设置"


def _server_reachable() -> bool:
    """检查 embedding server 是否可达"""
    try:
        resp = httpx.get(EMBED_HEALTH_URL, timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


# 如果没有设置跳过，但服务不可达，也跳过
if not SKIP_REASON and not _server_reachable():
    SKIP_REASON = f"Embedding server 不可达: {EMBED_HEALTH_URL}"


skip_integration = pytest.mark.skipif(
    bool(SKIP_REASON),
    reason=SKIP_REASON or "集成测试",
)


# ── 健康检查 ──


@skip_integration
class TestEmbeddingServiceHealth:
    """测试 BGE-M3 服务健康状态"""

    def test_health_endpoint_reachable(self):
        """验证 /health 端点可达"""
        resp = httpx.get(EMBED_HEALTH_URL, timeout=5)
        assert resp.status_code == 200

    def test_health_returns_ok(self):
        """验证服务状态为 ok"""
        resp = httpx.get(EMBED_HEALTH_URL, timeout=5)
        data = resp.json()
        assert data["status"] == "ok"
        assert data["model_loaded"] is True

    def test_health_model_name(self):
        """验证模型名称正确"""
        resp = httpx.get(EMBED_HEALTH_URL, timeout=5)
        data = resp.json()
        assert "bge-m3" in data["model_name"].lower()


# ── 模型列表 ──


@skip_integration
class TestEmbeddingModelsEndpoint:
    """测试 /v1/models 端点"""

    def test_list_models(self):
        """验证模型列表返回正确"""
        resp = httpx.get(f"{EMBED_BASE_URL}/models", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) >= 1
        assert data["data"][0]["id"] == EMBED_MODEL


# ── 嵌入生成（核心集成测试） ──


@skip_integration
class TestEmbeddingGeneration:
    """测试实际嵌入生成 — 验证后端能调用 BGE-M3 服务"""

    def test_single_text_embedding(self):
        """验证单文本嵌入生成"""
        resp = httpx.post(
            f"{EMBED_BASE_URL}/embeddings",
            json={
                "input": "孕期饮食注意事项",
                "model": EMBED_MODEL,
            },
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()

        # 响应格式
        assert data["object"] == "list"
        assert len(data["data"]) == 1

        # 嵌入对象
        emb = data["data"][0]
        assert emb["object"] == "embedding"
        assert emb["index"] == 0
        assert len(emb["embedding"]) == EMBED_DIMENSIONS

    def test_batch_embedding(self):
        """验证批量嵌入生成"""
        texts = [
            "孕期饮食注意事项",
            "产后恢复指南",
            "新生儿护理要点",
        ]
        resp = httpx.post(
            f"{EMBED_BASE_URL}/embeddings",
            json={
                "input": texts,
                "model": EMBED_MODEL,
            },
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 3

        for i, emb in enumerate(data["data"]):
            assert emb["index"] == i
            assert len(emb["embedding"]) == EMBED_DIMENSIONS

    def test_embedding_values_are_floats(self):
        """验证嵌入值为浮点数"""
        resp = httpx.post(
            f"{EMBED_BASE_URL}/embeddings",
            json={"input": "测试", "model": EMBED_MODEL},
            timeout=30,
        )
        assert resp.status_code == 200
        embedding = resp.json()["data"][0]["embedding"]
        assert all(isinstance(v, float) for v in embedding)

    def test_embedding_not_all_zeros(self):
        """验证嵌入向量不是全零"""
        resp = httpx.post(
            f"{EMBED_BASE_URL}/embeddings",
            json={"input": "孕期营养补充", "model": EMBED_MODEL},
            timeout=30,
        )
        assert resp.status_code == 200
        embedding = resp.json()["data"][0]["embedding"]
        assert any(v != 0.0 for v in embedding), "嵌入向量不应全为零"

    def test_embedding_dimensions_truncation(self):
        """验证 dimensions 参数可以截断向量"""
        resp = httpx.post(
            f"{EMBED_BASE_URL}/embeddings",
            json={
                "input": "测试截断",
                "model": EMBED_MODEL,
                "dimensions": 256,
            },
            timeout=30,
        )
        assert resp.status_code == 200
        embedding = resp.json()["data"][0]["embedding"]
        assert len(embedding) == 256

    def test_embedding_response_has_usage(self):
        """验证响应包含 usage 统计"""
        resp = httpx.post(
            f"{EMBED_BASE_URL}/embeddings",
            json={"input": "用量统计", "model": EMBED_MODEL},
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "usage" in data
        assert "prompt_tokens" in data["usage"]
        assert "total_tokens" in data["usage"]


# ── 语义相似度验证 ──


@skip_integration
class TestEmbeddingSemanticQuality:
    """测试嵌入质量 — 验证语义相似度"""

    def _get_embedding(self, text: str) -> list[float]:
        """获取单个文本的嵌入向量"""
        resp = httpx.post(
            f"{EMBED_BASE_URL}/embeddings",
            json={"input": text, "model": EMBED_MODEL},
            timeout=30,
        )
        assert resp.status_code == 200
        return resp.json()["data"][0]["embedding"]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """计算余弦相似度"""
        import math
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def test_similar_texts_high_similarity(self):
        """验证相似文本的嵌入向量余弦相似度较高"""
        emb1 = self._get_embedding("孕期应该补充叶酸")
        emb2 = self._get_embedding("怀孕期间需要服用叶酸")
        sim = self._cosine_similarity(emb1, emb2)
        assert sim > 0.7, f"相似文本的余弦相似度应 > 0.7, 实际为 {sim:.4f}"

    def test_different_texts_lower_similarity(self):
        """验证不同主题文本的嵌入向量余弦相似度较低"""
        emb1 = self._get_embedding("孕期应该补充叶酸")
        emb2 = self._get_embedding("今天天气真好适合出去玩")
        sim = self._cosine_similarity(emb1, emb2)
        assert sim < 0.7, f"不同主题文本的余弦相似度应 < 0.7, 实际为 {sim:.4f}"


# ── OpenAI 兼容性验证 ──


@skip_integration
class TestOpenAICompatibilityReal:
    """验证与 OpenAI Embedding API 的实际兼容性"""

    def test_accepts_string_input(self):
        """OpenAI API 允许 input 为字符串"""
        resp = httpx.post(
            f"{EMBED_BASE_URL}/embeddings",
            json={"input": "单字符串", "model": EMBED_MODEL},
            timeout=30,
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_accepts_list_input(self):
        """OpenAI API 允许 input 为数组"""
        resp = httpx.post(
            f"{EMBED_BASE_URL}/embeddings",
            json={"input": ["文本1", "文本2"], "model": EMBED_MODEL},
            timeout=30,
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_response_has_required_fields(self):
        """验证响应包含 OpenAI 规范要求的所有字段"""
        resp = httpx.post(
            f"{EMBED_BASE_URL}/embeddings",
            json={"input": "规范测试", "model": EMBED_MODEL},
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()

        # 顶层字段
        assert "object" in data
        assert "data" in data
        assert "model" in data
        assert "usage" in data

        # embedding 对象字段
        emb = data["data"][0]
        assert "object" in emb
        assert "embedding" in emb
        assert "index" in emb


# ── Agno OpenAIEmbedder 集成验证 ──


@skip_integration
class TestAgnoEmbedderIntegration:
    """验证 Agno OpenAIEmbedder 能实际调用本地 BGE-M3"""

    def test_agno_openai_embedder_works(self):
        """验证 Agno OpenAIEmbedder 可以调用本地服务生成嵌入"""
        from agno.knowledge.embedder.openai import OpenAIEmbedder

        embedder = OpenAIEmbedder(
            id=EMBED_MODEL,
            dimensions=EMBED_DIMENSIONS,
            api_key="not-needed",
            base_url=EMBED_BASE_URL,
        )

        # Agno embedder 使用 get_embedding 方法
        result = embedder.get_embedding("孕期饮食注意事项")
        assert isinstance(result, list)
        assert len(result) == EMBED_DIMENSIONS
        assert all(isinstance(v, float) for v in result)
        assert any(v != 0.0 for v in result)

    def test_agno_openai_embedder_batch(self):
        """验证 Agno OpenAIEmbedder 批量嵌入"""
        from agno.knowledge.embedder.openai import OpenAIEmbedder

        embedder = OpenAIEmbedder(
            id=EMBED_MODEL,
            dimensions=EMBED_DIMENSIONS,
            api_key="not-needed",
            base_url=EMBED_BASE_URL,
        )

        texts = ["孕期饮食", "产后恢复", "新生儿护理"]
        result = embedder.get_embedding(texts)
        assert isinstance(result, list)
        # 批量返回可能是 list of lists
        if result and isinstance(result[0], list):
            assert len(result) == 3
            for emb in result:
                assert len(emb) == EMBED_DIMENSIONS
