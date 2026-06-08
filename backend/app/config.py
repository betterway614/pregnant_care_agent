"""应用配置管理"""
import os
from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import Literal, Optional

_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


class Settings(BaseSettings):
    # 应用基础
    app_name: str = "AI-Care 孕期智能管理平台"
    app_version: str = "1.0.0"
    debug: bool = True

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_flag(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value

    # LLM配置 - 全局默认（本地部署 Qwen3.6-35B-A3B，开发阶段可切 cloud）
    llm_mode: Literal["cloud", "local", "mock", "mixed"] = "cloud"
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "Qwen3.6-35B-A3B"
    ollama_host: str = "http://localhost:11434"
    local_model: str = "Qwen3.6-35B-A3B"
    # vLLM / SGLang 等 OpenAI 兼容本地推理服务（留空则自动使用 ollama_host）
    local_base_url: str = ""

    # LLM配置 - 角色专属（优先级高于全局配置）
    llm_pregnant_mode: Literal["cloud", "local", "mock", ""] = "cloud"
    llm_nurse_mode: Literal["cloud", "local", "mock", ""] = "cloud"
    llm_doctor_mode: Literal["cloud", "local", "mock", ""] = "cloud"
    # 角色专属模型 ID（空则 fallback llm_model；本地部署后切换）
    llm_pregnant_model: str = ""
    llm_nurse_model: str = ""
    llm_doctor_model: str = ""
    # 角色专属生成参数（空或负值则使用代码内默认值）
    llm_pregnant_temperature: float = 0.7
    llm_nurse_temperature: float = 0.3
    llm_doctor_temperature: float = 0.3
    llm_pregnant_max_tokens: int = 4096
    llm_nurse_max_tokens: int = 8192
    llm_doctor_max_tokens: int = 8192

    # ASR配置 - 全局默认（cloud 使用 DashScope，local 默认调用本地 FunASR HTTP API）
    asr_mode: Literal["cloud", "local"] = "cloud"
    asr_pregnant_mode: Literal["cloud", "local", ""] = ""
    asr_nurse_mode: Literal["cloud", "local", ""] = ""
    asr_doctor_mode: Literal["cloud", "local", ""] = ""
    asr_cloud_api_key: str = ""
    asr_cloud_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    asr_cloud_model: str = "paraformer-v1"
    asr_local_backend: Literal["funasr", "whisper"] = "funasr"
    asr_local_base_url: str = "http://127.0.0.1:10096"
    asr_local_endpoint: str = "/v1/audio/transcriptions"
    asr_local_funasr_model: str = "local-funasr"
    asr_local_api_key: str = ""
    asr_local_hotword: str = ""
    asr_local_timeout: float = 60.0
    asr_local_model: str = "base"

    # TTS配置 - 全局默认
    tts_mode: Literal["browser", "cloud", "local"] = "local"
    tts_pregnant_mode: Literal["browser", "cloud", "local", ""] = ""
    tts_nurse_mode: Literal["browser", "cloud", "local", ""] = ""
    tts_doctor_mode: Literal["browser", "cloud", "local", ""] = ""
    tts_cloud_api_key: str = ""
    tts_cloud_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    tts_cloud_model: str = "cosyvoice-v1"
    tts_cloud_voice: str = "longxiaochun"
    tts_local_voice: str = "zh-CN-XiaoxiaoNeural"
    # TTS本地后端选择
    tts_local_backend: Literal["edge", "cosyvoice"] = "cosyvoice"
    # CosyVoice2 本地服务配置
    tts_local_cosyvoice_url: str = "http://127.0.0.1:9880"
    tts_local_cosyvoice_speaker: str = "中文女"
    tts_local_cosyvoice_timeout: float = 30.0

    # FGR配置
    fgr_mode: bool = True
    # FGR_BACKEND 控制 FGR 分类模型后端；nnU-Net 分割由 segmentation_service 单独调用。
    # - pytorch: 默认旧路径，加载 .pth 权重；torch.cuda 可用时自动走 GPU，否则走 CPU
    # - cuda: pytorch 的显式别名，用于保留现有 CUDA 部署写法
    # - rocm / onnx_igpu: ONNX Runtime + AMD MIGraphX/ROCm，加载 onnx_resnet/*.onnx
    # - onnx_npu: 优先 VitisAI/NPU；不可用时依次回退到 ROCm/MIGraphX、ONNX CPU
    # - onnx_cpu: ONNX Runtime CPU，主要用于本地调试或硬件回退
    # - mock: 不加载模型；API 使用 mock 评估时请同时设置 FGR_MODE=false
    fgr_backend: Literal["pytorch", "cuda", "rocm", "onnx_npu", "onnx_igpu", "onnx_cpu", "mock"] = "pytorch"

    # nnU-Net 分割配置
    nnunet_model_dir: str = "fgr_compete/Dataset001_PlacentaNT"
    nnunet_dataset_id: int = 1
    nnunet_folds: str = "all"

    # NLU配置
    nlu_mode: Literal["cloud", "npu", "hybrid"] = "hybrid"

    # 数据库
    db_type: Literal["sqlite", "postgres"] = "sqlite"
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "ai_care"

    @property
    def database_url(self) -> str:
        if self.db_type == "sqlite":
            db_path = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(__file__)), f"{self.db_name}.db"))
            return f"sqlite:///{db_path}"
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def async_database_url(self) -> Optional[str]:
        if self.db_type == "sqlite":
            return None
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def agno_database_url(self) -> str:
        """Agno PgVector 使用 psycopg3 驱动"""
        if self.db_type == "sqlite":
            return self.database_url
        return f"postgresql+psycopg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # RAG (Agno native)
    rag_enabled: bool = True
    rag_chunk_size: int = 600
    rag_chunk_overlap: int = 120
    rag_search_type: Literal["vector", "hybrid"] = "hybrid"
    rag_max_results: int = 5
    rag_chunking_strategy: Literal["fixed_size", "recursive"] = "fixed_size"

    # Reranker（可选，留空则不启用）
    reranker_provider: Literal["", "cohere", "infinity"] = ""
    reranker_model: str = ""
    reranker_base_url: str = ""

    # Embedding (DashScope / OpenAI-compatible)
    embedding_api_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v3"
    embedding_dimensions: int = 1024

    # Seed
    seed_data: bool = True

    # Agno 配置（生产主路径，默认启用）
    agno_enabled: bool = True
    agno_knowledge_dir: str = "data/knowledge"
    agno_knowledge_table: str = "knowledge_chunks"
    agno_memory_enabled: bool = True
    agno_planning_enabled: bool = True
    persist_chat_messages: bool = True

    model_config = {"env_file": _env_path, "env_file_encoding": "utf-8"}


settings = Settings()


def get_asr_mode(role: str) -> str:
    """解析ASR模式：角色专属 > 全局 > 默认'cloud'"""
    role_mode = getattr(settings, f"asr_{role}_mode", "")
    return role_mode if role_mode else settings.asr_mode


def get_tts_mode(role: str) -> str:
    """解析TTS模式：角色专属 > 全局 > 默认'browser'"""
    role_mode = getattr(settings, f"tts_{role}_mode", "")
    return role_mode if role_mode else settings.tts_mode
