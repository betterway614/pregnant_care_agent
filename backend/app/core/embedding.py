"""Embedding服务 - 文本向量化"""
from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class EmbeddingClient(ABC):
    """文本向量化抽象基类"""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """将文本列表转换为向量列表"""
        ...


class HuggingFaceEmbedding(EmbeddingClient):
    """本地 HuggingFace embedding 模型"""

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model_name = model_name
        self._model = None
        self._tokenizer = None
        self._lazy_load()

    def _lazy_load(self):
        """延迟加载模型（避免启动时卡顿）"""
        try:
            from transformers import AutoTokenizer, AutoModel
            import torch
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModel.from_pretrained(self.model_name)
            if torch.cuda.is_available():
                self._model = self._model.cuda()
            self._model.eval()
        except ImportError:
            print("Warning: transformers not installed, using zero embedding")
        except Exception as e:
            print(f"Warning: failed to load embedding model '{self.model_name}': {e}")
            self._model = None
            self._tokenizer = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None or self._tokenizer is None:
            return [[0.0] * 1024 for _ in texts]

        import torch
        with torch.no_grad():
            inputs = self._tokenizer(
                texts, padding=True, truncation=True,
                max_length=512, return_tensors="pt"
            )
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            outputs = self._model(**inputs)
            # Mean pooling: 对最后一层hidden states做注意力加权平均
            attention_mask = inputs["attention_mask"]
            embeddings = outputs.last_hidden_state
            mask = attention_mask.unsqueeze(-1).expand(embeddings.size()).float()
            masked = embeddings * mask
            summed = masked.sum(dim=1)
            counts = mask.sum(dim=1)
            pooled = summed / counts.clamp(min=1e-9)
            # L2归一化
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            return pooled.cpu().numpy().tolist()


class APIEmbedding(EmbeddingClient):
    """云端 API Embedding (如 SiliconFlow / OpenAI 兼容接口)"""

    def __init__(self, api_url: str, api_key: str, model: str = "BAAI/bge-m3"):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        try:
            resp = httpx.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if "data" in data:
                return [d["embedding"] for d in data["data"]]
        except Exception as e:
            print(f"Warning: API embedding failed: {e}")
        return [[0.0] * 1024 for _ in texts]


class MockEmbedding(EmbeddingClient):
    """Mock embedding - 开发/测试环境使用

    基于文本 SHA256 哈希生成伪向量，保证相同文本产生相同向量，
    用于在没有真实 embedding 服务时验证 RAG 流程。
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        dim = 1024
        result = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [(int(h[i % len(h)]) / 255.0 * 2 - 1) for i in range(dim)]
            # L2归一化
            norm = np.sqrt(sum(v * v for v in vec))
            vec = [v / max(norm, 1e-9) for v in vec]
            result.append(vec)
        return result


def get_embedding_client() -> EmbeddingClient:
    """工厂函数 - 根据配置返回合适的 Embedding 客户端"""
    from ..config import settings

    mode = getattr(settings, 'embedding_mode', 'mock')

    if mode == "local":
        return HuggingFaceEmbedding(
            model_name=getattr(settings, 'embedding_model', 'BAAI/bge-m3')
        )
    elif mode == "api":
        api_key = getattr(settings, 'embedding_api_key', '')
        if not api_key:
            print("Warning: embedding_api_key not configured, falling back to MockEmbedding")
            return MockEmbedding()
        return APIEmbedding(
            api_url=getattr(settings, 'embedding_api_url', ''),
            api_key=api_key,
            model=getattr(settings, 'embedding_model', 'BAAI/bge-m3'),
        )

    return MockEmbedding()
