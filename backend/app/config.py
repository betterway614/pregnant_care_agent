"""应用配置管理"""
import os
from pydantic_settings import BaseSettings
from typing import Literal, Optional

# .env 文件路径相对于 config.py 所在目录（backend/），而非 CWD
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


class Settings(BaseSettings):
    # 应用基础
    app_name: str = "AI-Care 孕期智能管理平台"
    app_version: str = "1.0.0"
    debug: bool = True

    # LLM配置 - 全局默认（护士/医生端使用）
    llm_mode: Literal["cloud", "local", "mock", "mixed"] = "cloud"
    llm_api_key: str = "sk-54b8481fe3a648ccb3bb8d20126420c2"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen3.5-35b-a3b"
    ollama_host: str = "http://localhost:11434"
    local_model: str = "qwen2.5:7b"

    # LLM配置 - 角色专属（优先级高于全局配置）
    # 孕妇端：使用云模型
    llm_pregnant_mode: Literal["cloud", "local", "mock", ""] = "cloud"
    # 护士端：使用本地模型
    llm_nurse_mode: Literal["cloud", "local", "mock", ""] = "cloud"
    # 医生端：使用本地模型
    llm_doctor_mode: Literal["cloud", "local", "mock", ""] = "cloud"

    # ASR配置 - 全局默认
    # llm = 多模态LLM直接处理音频（当前行为，零额外依赖）
    # cloud = DashScope Paraformer ASR
    # local = Whisper 本地推理
    asr_mode: Literal["cloud", "local", "llm"] = "llm"
    # ASR配置 - 角色专属（优先级高于全局配置）
    asr_pregnant_mode: Literal["cloud", "local", "llm", ""] = ""
    asr_nurse_mode: Literal["cloud", "local", "llm", ""] = ""
    asr_doctor_mode: Literal["cloud", "local", "llm", ""] = ""
    # ASR云配置 (DashScope Paraformer)
    asr_cloud_api_key: str = ""  # 不填则复用 llm_api_key
    asr_cloud_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    asr_cloud_model: str = "fun-asr-2025-11-07"
    # ASR本地配置 (Whisper)
    asr_local_model: str = "base"  # tiny/base/small/medium/large

    # TTS配置 - 全局默认
    # browser = 前端 SpeechSynthesis（零后端依赖）
    # cloud = DashScope CosyVoice
    # local = edge-tts（微软 Edge TTS，免费高质量中文）
    tts_mode: Literal["browser", "cloud", "local"] = "browser"
    # TTS配置 - 角色专属
    tts_pregnant_mode: Literal["browser", "cloud", "local", ""] = ""
    tts_nurse_mode: Literal["browser", "cloud", "local", ""] = ""
    tts_doctor_mode: Literal["browser", "cloud", "local", ""] = ""
    # TTS云配置 (DashScope CosyVoice)
    tts_cloud_api_key: str = ""
    tts_cloud_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    tts_cloud_model: str = "cosyvoice-v1"
    tts_cloud_voice: str = "longxiaochun"
    # TTS本地配置 (edge-tts)
    tts_local_voice: str = "zh-CN-XiaoxiaoNeural"

    # FGR配置
    fgr_mode: bool = True

    # nnU-Net 分割配置
    nnunet_model_dir: str = "backend/fgr_compete/Dataset001_PlacentaNT"
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

    # Agno 配置
    agno_enabled: bool = False
    agno_model_id: str = "gpt-4o"
    agno_knowledge_dir: str = "data/knowledge"
    agno_knowledge_table: str = "knowledge_chunks"
    agno_memory_enabled: bool = True
    agno_planning_enabled: bool = True
    persist_chat_messages: bool = True

    model_config = {"env_file": _env_path, "env_file_encoding": "utf-8"}


settings = Settings()


def get_asr_mode(role: str) -> str:
    """解析ASR模式：角色专属 > 全局 > 默认'llm'"""
    role_mode = getattr(settings, f"asr_{role}_mode", "")
    return role_mode if role_mode else settings.asr_mode


def get_tts_mode(role: str) -> str:
    """解析TTS模式：角色专属 > 全局 > 默认'browser'"""
    role_mode = getattr(settings, f"tts_{role}_mode", "")
    return role_mode if role_mode else settings.tts_mode
