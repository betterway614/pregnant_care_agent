"""应用配置管理"""
import os
from pydantic_settings import BaseSettings
from typing import Literal, Optional

_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


class Settings(BaseSettings):
    # 应用基础
    app_name: str = "AI-Care 孕期智能管理平台"
    app_version: str = "1.0.0"
    debug: bool = True

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

    # ASR配置 - 全局默认（cloud 使用 DashScope Paraformer 专用 ASR 服务，local 使用 Whisper）
    asr_mode: Literal["cloud", "local"] = "cloud"
    asr_pregnant_mode: Literal["cloud", "local", ""] = ""
    asr_nurse_mode: Literal["cloud", "local", ""] = ""
    asr_doctor_mode: Literal["cloud", "local", ""] = ""
    asr_cloud_api_key: str = "sk-54b8481fe3a648ccb3bb8d20126420c2"
    asr_cloud_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    asr_cloud_model: str = "paraformer-v1"
    asr_local_model: str = "base"

    # TTS配置 - 全局默认
    tts_mode: Literal["browser", "cloud", "local"] = "browser"
    tts_pregnant_mode: Literal["browser", "cloud", "local", ""] = ""
    tts_nurse_mode: Literal["browser", "cloud", "local", ""] = ""
    tts_doctor_mode: Literal["browser", "cloud", "local", ""] = ""
    tts_cloud_api_key: str = "sk-54b8481fe3a648ccb3bb8d20126420c2"
    tts_cloud_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    tts_cloud_model: str = "cosyvoice-v1"
    tts_cloud_voice: str = "longxiaochun"
    tts_local_voice: str = "zh-CN-XiaoxiaoNeural"

    # FGR配置
    fgr_mode: bool = True

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

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # RAG配置
    rag_enabled: bool = False
    embedding_mode: Literal["mock", "local", "api"] = "mock"
    embedding_api_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "BAAI/bge-m3"

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
