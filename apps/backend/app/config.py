from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://novel:novel@localhost:5432/novel_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # AI — 本地模型 / 自定义端点（OpenAI 兼容协议）
    LLM_BASE_URL: str = "http://localhost:11434/v1"   # Ollama 默认地址
    LLM_API_KEY: str = "ollama"                       # 本地模型随便填，远程服务填真实 key
    AI_MODEL: str = "qwen3:8b"
    # Gemini / 远程兼容网关（可选；亦可只在管理后台持久化配置）
    GEMINI_BASE_URL: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: Optional[str] = None

    EMBEDDING_MODEL: str = "nomic-embed-text"         # Ollama 本地 embedding 模型

    # App
    SECRET_KEY: str = "change-me-in-production"
    DEBUG: bool = True
    CORS_ORIGINS: list[str] = [
        "http://localhost:3173",
        "http://127.0.0.1:3173",
        "http://localhost:3174",
        "http://127.0.0.1:3174",
        "http://localhost:19173",
        "http://127.0.0.1:19173",
        "http://localhost:19174",
        "http://127.0.0.1:19174",
        "http://localhost:3000",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
