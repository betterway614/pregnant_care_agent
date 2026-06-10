"""
BGE-M3 Embedding 服务 — OpenAI 兼容 API
端口 8081，提供 /v1/embeddings 端点
"""
import os
import time
import logging
import numpy as np
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── 配置 ──
HOST = os.getenv("EMBED_HOST", "0.0.0.0")
PORT = int(os.getenv("EMBED_PORT", "8081"))
MODEL_NAME = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
MODEL_DIR = os.getenv("EMBED_MODEL_DIR", "./pretrained_models/bge-m3")
DEVICE = os.getenv("EMBED_DEVICE", "cuda")  # ROCm 下 cuda = HIP
BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "64"))
MAX_LENGTH = int(os.getenv("EMBED_MAX_LENGTH", "8192"))

# 全局模型引用
_model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    logger.info("Loading embedding model: %s (device=%s)", MODEL_NAME, DEVICE)
    try:
        from FlagEmbedding import BGEM3FlagModel

        model_path = MODEL_DIR if os.path.exists(MODEL_DIR) else MODEL_NAME
        _model = BGEM3FlagModel(
            model_path,
            use_fp16=True,
            device=DEVICE if DEVICE != "cpu" else -1,
        )
        logger.info("BGE-M3 model loaded successfully")
    except Exception as e:
        logger.warning("FlagEmbedding failed, falling back to sentence-transformers: %s", e)
        try:
            from sentence_transformers import SentenceTransformer
            model_path = MODEL_DIR if os.path.exists(MODEL_DIR) else MODEL_NAME
            _model = SentenceTransformer(model_path, device=DEVICE)
            logger.info("sentence-transformers model loaded successfully")
        except Exception as e2:
            logger.error("Failed to load embedding model: %s", e2)
            _model = None
    yield
    logger.info("Embedding service shutting down")


app = FastAPI(title="BGE-M3 Embedding API", version="1.0.0", lifespan=lifespan)


# ── 请求/响应模型 (OpenAI 兼容) ──

class EmbeddingRequest(BaseModel):
    input: list[str] | str
    model: str = MODEL_NAME
    encoding_format: str = "float"
    dimensions: Optional[int] = None


class EmbeddingObject(BaseModel):
    object: str = "embedding"
    index: int
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingObject]
    model: str
    usage: dict


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_name: str


class ConfigUpdateRequest(BaseModel):
    batch_size: Optional[int] = Field(None, ge=1, le=512)
    max_length: Optional[int] = Field(None, ge=128, le=16384)
    device: Optional[str] = None  # "cuda", "cpu", "npu"


class ConfigResponse(BaseModel):
    status: str
    batch_size: int
    max_length: int
    device: str


# ── 端点 ──

@app.get("/health")
async def health():
    return HealthResponse(
        status="ok" if _model is not None else "unavailable",
        model_loaded=_model is not None,
        model_name=MODEL_NAME,
    )


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": MODEL_NAME, "object": "model", "owned_by": "local"}],
    }


@app.get("/config")
async def get_config():
    """获取当前配置 (用于动态资源管理)"""
    return ConfigResponse(
        status="ok",
        batch_size=BATCH_SIZE,
        max_length=MAX_LENGTH,
        device=DEVICE,
    )


@app.post("/config")
async def update_config(req: ConfigUpdateRequest):
    """热更新配置 (无需重启服务)"""
    global BATCH_SIZE, MAX_LENGTH, DEVICE

    updated = []

    if req.batch_size is not None:
        old = BATCH_SIZE
        BATCH_SIZE = req.batch_size
        updated.append(f"batch_size: {old} -> {BATCH_SIZE}")
        logger.info("配置更新: batch_size %d -> %d", old, BATCH_SIZE)

    if req.max_length is not None:
        old = MAX_LENGTH
        MAX_LENGTH = req.max_length
        updated.append(f"max_length: {old} -> {MAX_LENGTH}")
        logger.info("配置更新: max_length %d -> %d", old, MAX_LENGTH)

    if req.device is not None and req.device in ("cuda", "cpu", "npu"):
        old = DEVICE
        DEVICE = req.device
        updated.append(f"device: {old} -> {DEVICE}")
        logger.info("配置更新: device %s -> %s (下次加载生效)", old, DEVICE)

    return ConfigResponse(
        status="updated",
        batch_size=BATCH_SIZE,
        max_length=MAX_LENGTH,
        device=DEVICE,
    )


@app.post("/v1/embeddings")
async def create_embeddings(req: EmbeddingRequest):
    if _model is None:
        raise HTTPException(status_code=503, detail="Embedding model not loaded")

    # 标准化输入
    texts = req.input if isinstance(req.input, list) else [req.input]
    if not texts:
        raise HTTPException(status_code=400, detail="Empty input")

    start = time.time()

    # 使用 BGE-M3 的 dense embedding (1024维)
    embeddings = _encode(texts)

    elapsed = time.time() - start
    logger.info("Encoded %d texts in %.3fs", len(texts), elapsed)

    # 构建 OpenAI 兼容响应
    data = []
    total_tokens = 0
    for i, emb in enumerate(embeddings):
        # 截断到指定维度（如果有）
        if req.dimensions and req.dimensions < len(emb):
            emb = emb[:req.dimensions]
        data.append(EmbeddingObject(index=i, embedding=emb.tolist()))
        total_tokens += len(texts[i].split()) * 2  # 粗略估计

    return EmbeddingResponse(
        data=data,
        model=MODEL_NAME,
        usage={"prompt_tokens": total_tokens, "total_tokens": total_tokens},
    )


def _encode(texts: list[str]) -> np.ndarray:
    """调用模型编码，返回 [N, dim] float32 数组"""
    try:
        from FlagEmbedding import BGEM3FlagModel
        if isinstance(_model, BGEM3FlagModel):
            output = _model.encode(
                texts,
                batch_size=BATCH_SIZE,
                max_length=MAX_LENGTH,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            return output["dense_vecs"]
    except ImportError:
        pass

    # sentence-transformers fallback
    return _model.encode(texts, batch_size=BATCH_SIZE, normalize_embeddings=True)


# ── 入口 ──

def main():
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
