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

    # FGR配置
    fgr_mode: bool = True

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
