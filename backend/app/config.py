"""应用配置管理"""
from pydantic_settings import BaseSettings
from typing import Literal, Optional


class Settings(BaseSettings):
    # 应用基础
    app_name: str = "AI-Care 孕期智能管理平台"
    app_version: str = "1.0.0"
    debug: bool = True

    # LLM配置
    llm_mode: Literal["cloud", "local", "mock"] = "mock"
    llm_api_key: str = "sk-placeholder"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    ollama_host: str = "http://localhost:11434"
    local_model: str = "qwen2.5:7b"

    # FGR配置
    fgr_mode: Literal["mock", "npu"] = "mock"

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
            return f"sqlite:///./{self.db_name}.db"
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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
