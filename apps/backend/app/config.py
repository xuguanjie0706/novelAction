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
    # 本系统仅使用远程大上下文模型（Gemini / Claude / GPT-4o 等），LOCAL_* 为兼容保留。
    GEMINI_SINGLE_SHOT_MAX_TOKENS: int = 65536
    GEMINI_SETTING_COMPLETION_MAX_TOKENS: int = 32768
    # Bootstrap 串行各步大块 JSON max_tokens
    # 人物（13人×15字段）/ 设定卡 / 势力等单步输出通常 4000-12000 token
    BOOTSTRAP_COMPLETION_MAX_TOKENS: int = 16384
    GEMINI_EXPAND_OUTLINE_MAX_TOKENS: int = 32768
    GEMINI_OUTLINE_QUALITY_MAX_TOKENS: int = 16384
    GEMINI_CHAPTER_QUALITY_MAX_TOKENS: int = 16384
    GEMINI_COHERENCE_CHECK_MAX_TOKENS: int = 16384
    # 连贯性修订：多章一次输出，需最大上限
    GEMINI_COHERENCE_APPLY_MAX_TOKENS: int = 65536
    GEMINI_DRAFT_STREAM_MAX_TOKENS: int = 16384
    GEMINI_PLAN_STRUCTURE_MAX_TOKENS: int = 32768
    GEMINI_SUGGEST_STREAM_MAX_TOKENS: int = 8192
    GEMINI_EXTRACT_MEMORY_MAX_TOKENS: int = 8192
    # 按卷懒展开章纲：30章×15字段的完整 JSON 输出，单批需要 8000-16000 token；
    # 60章分两批但每批同样需要充足空间；可在 .env 中按模型实际上限调高
    VOL_EXPAND_CHAPTERS_MAX_TOKENS: int = 65536

    LOCAL_EXPAND_OUTLINE_MAX_TOKENS: int = 4096
    LOCAL_OUTLINE_QUALITY_MAX_TOKENS: int = 4096
    LOCAL_CHAPTER_QUALITY_MAX_TOKENS: int = 2048
    LOCAL_COHERENCE_CHECK_MAX_TOKENS: int = 2200
    LOCAL_COHERENCE_APPLY_MAX_TOKENS: int = 16384
    LOCAL_DRAFT_STREAM_MAX_TOKENS: int = 4096
    LOCAL_PLAN_STRUCTURE_MAX_TOKENS: int = 2048
    LOCAL_SUGGEST_STREAM_MAX_TOKENS: int = 2048
    LOCAL_EXTRACT_MEMORY_MAX_TOKENS: int = 2048

    # 复盘（auto_debrief）max_tokens — JSON 输出包含六类资产子字段，必须足够大
    # 复盘 JSON 通常 <4k token；thinking 模型在过大 max_tokens 时极易拖至数分钟无响应
    GEMINI_AUTO_DEBRIEF_MAX_TOKENS: int = 8192
    LOCAL_AUTO_DEBRIEF_MAX_TOKENS: int = 4096

    # ── Embedding（pgvector 语义检索）────────────────────────────────────────
    # EMBEDDING_BASE_URL / EMBEDDING_API_KEY 留空时自动跟随 LLM_BASE_URL / LLM_API_KEY，
    # 方便「远程 LLM + 本地 Ollama embedding」解耦部署：
    #   EMBEDDING_BASE_URL=http://localhost:11434/v1
    #   EMBEDDING_API_KEY=ollama
    EMBEDDING_BASE_URL: Optional[str] = None          # None = 跟随 LLM_BASE_URL
    EMBEDDING_API_KEY: Optional[str] = None           # None = 跟随 LLM_API_KEY
    EMBEDDING_MODEL: str = "nomic-embed-text"         # Ollama 本地 embedding 模型（需先 ollama pull nomic-embed-text）
    EMBEDDING_DIM: int = 768                          # nomic-embed-text 输出 768 维；换模型时同步修改并重跑 migration

    # 封面存储后端（默认本地磁盘，改 .env 即可切换，无需改代码）
    #   local / disk / filesystem → data/covers + /api/v1/covers/files/...
    #   cos / bucket / tencent_cos → 腾讯云对象存储（需 COS_*）
    COVER_STORAGE_BACKEND: str = "local"
    # 封面落盘（相对路径相对于进程 cwd；留空则使用后端目录下 data/covers）
    COVER_STORAGE_DIR: str = ""
    # 封面生成失败时的调试包（meta + 原始 b64 等）；留空则使用 data/covers/debug
    COVER_DEBUG_DIR: str = ""
    COVER_MAX_EDGE: int = 1024
    COVER_WEBP_QUALITY: int = 82

    # 腾讯云 COS（COVER_STORAGE_BACKEND=cos 时必填）
    COS_SECRET_ID: Optional[str] = None
    COS_SECRET_KEY: Optional[str] = None
    COS_REGION: str = "ap-guangzhou"
    COS_BUCKET: Optional[str] = None
    COS_PREFIX: str = "novel-covers/"
    COS_SCHEME: str = "https"
    # 可选：自定义 CDN 域名，如 https://cdn.example.com（勿带末尾斜杠）
    COS_PUBLIC_BASE_URL: Optional[str] = None

    # 人物立绘雪碧图落盘（留空则 data/character-portraits）
    CHARACTER_PORTRAIT_STORAGE_DIR: str = ""
    CHARACTER_PORTRAIT_MAX_EDGE: int = 1536
    CHARACTER_PORTRAIT_WEBP_QUALITY: int = 85
    CHARACTER_PORTRAIT_AVATAR_EDGE: int = 256

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

    # ── 积分系统 ─────────────────────────────────────────────
    # CREDIT_ENFORCEMENT 控制积分不足时的行为：
    #   "off"    关闭积分检查，任何用户都可以无限调用 AI（开发 / 内部使用）
    #   "soft"   积分不足时仍允许调用，但在响应头写入 X-Credit-Warning（默认）
    #   "hard"   积分不足时直接返回 402 Payment Required，阻止调用
    CREDIT_ENFORCEMENT: str = "soft"
    # 新用户注册时赠送的积分数（0 = 不赠送）
    CREDIT_NEW_USER_BONUS: int = 10000

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
