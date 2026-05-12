from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://novel:novel@localhost:5432/novel_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # AI — 默认走远程（管理后台 LlmProvider 或 GEMINI_*）；下列为可选本地 OpenAI 兼容端点（遗留/开发机 Ollama 等）
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_API_KEY: str = "ollama"
    AI_MODEL: Optional[str] = None
    # OpenAI 兼容客户端超时（秒）：连接失败快速报错；读超时避免模型无响应时无限挂起
    LLM_HTTP_CONNECT_TIMEOUT: float = 30.0
    LLM_HTTP_READ_TIMEOUT: float = 900.0
    # Gemini / 远程兼容网关（可选；亦可只在管理后台持久化配置）
    GEMINI_BASE_URL: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: Optional[str] = None

    # chat.completions max_tokens — 勿超过所用模型/网关的实际上限（见各云厂商文档）
    GEMINI_SINGLE_SHOT_MAX_TOKENS: int = 32768
    GEMINI_SETTING_COMPLETION_MAX_TOKENS: int = 16384
    # Bootstrap 串行各步大块 JSON（人物、设定卡、势力/技能等）的 chat.completions max_tokens 统一上限
    # 各步实际输出通常 2000-6000 token；65536 易超出模型/网关硬限导致拒绝并触发重试瀑布
    # 本地模型建议 8192，远程大上下文模型可在 .env 中按需调高（如 16384）
    BOOTSTRAP_COMPLETION_MAX_TOKENS: int = 8192
    GEMINI_EXPAND_OUTLINE_MAX_TOKENS: int = 20000
    GEMINI_OUTLINE_QUALITY_MAX_TOKENS: int = 8192
    GEMINI_CHAPTER_QUALITY_MAX_TOKENS: int = 8192
    GEMINI_COHERENCE_CHECK_MAX_TOKENS: int = 8192
    # 根据连贯性评测结果最小幅度修订正文（多章一次输出，需较大上限）
    GEMINI_COHERENCE_APPLY_MAX_TOKENS: int = 32768
    GEMINI_DRAFT_STREAM_MAX_TOKENS: int = 8192
    GEMINI_PLAN_STRUCTURE_MAX_TOKENS: int = 8192
    GEMINI_SUGGEST_STREAM_MAX_TOKENS: int = 4096
    GEMINI_EXTRACT_MEMORY_MAX_TOKENS: int = 4096

    LOCAL_EXPAND_OUTLINE_MAX_TOKENS: int = 4096
    LOCAL_OUTLINE_QUALITY_MAX_TOKENS: int = 4096
    LOCAL_CHAPTER_QUALITY_MAX_TOKENS: int = 2048
    LOCAL_COHERENCE_CHECK_MAX_TOKENS: int = 2200
    # 本地模型按章顺序修订，单章输出上限
    LOCAL_COHERENCE_APPLY_MAX_TOKENS: int = 16384
    LOCAL_DRAFT_STREAM_MAX_TOKENS: int = 4096
    LOCAL_PLAN_STRUCTURE_MAX_TOKENS: int = 2048
    LOCAL_SUGGEST_STREAM_MAX_TOKENS: int = 2048
    LOCAL_EXTRACT_MEMORY_MAX_TOKENS: int = 2048

    # 复盘（auto_debrief）max_tokens — JSON 输出包含六类资产子字段，必须足够大
    # 旧默认 1500 几乎必然截断，导致 JSON 解析失败、复盘链路静默失效
    GEMINI_AUTO_DEBRIEF_MAX_TOKENS: int = 8192
    LOCAL_AUTO_DEBRIEF_MAX_TOKENS: int = 4096

    EMBEDDING_MODEL: str = "nomic-embed-text"         # Ollama 本地 embedding 模型
    EMBEDDING_DIM: int = 768                          # nomic-embed-text 输出 768 维

    # 封面落盘（相对路径相对于进程 cwd；留空则使用后端目录下 data/covers）
    COVER_STORAGE_DIR: str = ""
    # 封面生成失败时的调试包（meta + 原始 b64 等）；留空则使用 data/covers/debug
    COVER_DEBUG_DIR: str = ""
    COVER_MAX_EDGE: int = 1024
    COVER_WEBP_QUALITY: int = 82

    # App
    SECRET_KEY: str = "change-me-in-production"
    DEBUG: bool = True

    # JWT 认证
    JWT_SECRET_KEY: str = "jwt-secret-change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 默认 7 天

    # 管理后台账号（apps/frontend，端口 3174；与创作端账号体系完全隔离）
    # ADMIN_USERNAME/ADMIN_PASSWORD 任一为空 = 关闭管理后台登录入口（默认关闭，强制部署时显式开启）。
    # 登录成功后签发 role=admin JWT，可跨用户访问所有 /api/v1/projects/*。
    ADMIN_USERNAME: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None
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
