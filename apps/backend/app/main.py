from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text


def _server_from_x_forwarded_host(x_forwarded_host: str, scheme: str) -> tuple[str, int] | None:
    """
    解析 X-Forwarded-Host（Vite 代理 xfwd 时传入），用于修正 ASGI scope['server']，
    避免 FastAPI 尾部斜杠 307 的 Location 指向后端直连地址（如 127.0.0.1:9000）导致前端跨域失败。
    """
    raw = x_forwarded_host.strip().split(",")[0].strip()
    if not raw:
        return None
    default_port = 443 if scheme == "https" else 80
    if "]:" in raw:
        bracket_end = raw.index("]")
        host = raw[1:bracket_end]
        rest = raw[bracket_end + 1 :]
        if rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, default_port
    if raw.count(":") == 1:
        host, port_s = raw.split(":", 1)
        if port_s.isdigit():
            return host, int(port_s)
    idx = raw.rfind(":")
    if idx > 0 and raw[idx + 1 :].isdigit():
        return raw[:idx], int(raw[idx + 1 :])
    return raw, default_port


class ForwardedHostASGIMiddleware:
    """信任反向代理传入的 X-Forwarded-Host，修正重定向 URL 的 host/port。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            for key, val in scope.get("headers") or []:
                if key.lower() != b"x-forwarded-host":
                    continue
                parsed = _server_from_x_forwarded_host(
                    val.decode("latin1"), scheme=scope.get("scheme") or "http"
                )
                if parsed:
                    scope["server"] = parsed
                break
        await self.app(scope, receive, send)
from app.config import settings
from app.database import engine, Base
from app.routers import projects, world_settings, characters, outline, chapters, chapter_indexes, ai, generate, admin_llm, llm_public, admin_llm_calls
from app.routers import storylines, power_systems, skills, items, factions
from app.routers import foreshadows, quality_debts
from app.routers import cover as cover_router
from app.services.llm_config import seed_llm_from_env_if_empty
from app.services.cover_storage import ensure_cover_storage_dir, resolved_cover_storage_dir


def _ensure_outline_node_columns() -> None:
    """
    开发环境兼容迁移：为已有 outline_nodes 表补齐新字段，避免旧库因缺列直接 500。
    """
    ddl_statements = [
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS storyline_ids JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS involved_character_ids JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS key_item_ids JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS key_skill_ids JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS emotional_tone VARCHAR(50)",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS pacing VARCHAR(20)",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS power_milestone TEXT",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS foreshadows_laid JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS foreshadows_resolved JSON",
    ]
    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))


def _ensure_character_columns() -> None:
    """
    开发环境兼容迁移：为已有 characters 表补齐新字段，避免旧库缺列导致接口 500。
    """
    ddl_statements = [
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS alias JSON",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS gender VARCHAR(20)",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS age VARCHAR(50)",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500)",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS faction VARCHAR(100)",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS faction_id UUID",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS faction_rank VARCHAR(100)",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS birthplace VARCHAR(200)",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS appearance TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS clothing_style TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS current_realm VARCHAR(100)",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS power_system_id UUID",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS realm_rank INTEGER",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS personality TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS speech_style TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS values TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS background TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS secrets TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS trauma TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS motivation TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS fear TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS arc TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS arc_stages JSON",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS strengths JSON",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS weaknesses JSON",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS special_traits JSON",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS known_skills JSON",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS owned_items JSON",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS current_status VARCHAR(20)",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS current_location VARCHAR(200)",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS author_notes TEXT",
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS character_tier VARCHAR(20) DEFAULT 'core'",
    ]
    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))


def _ensure_character_relationship_columns() -> None:
    """
    开发环境兼容迁移：为已有 character_relationships 表补齐新字段，避免旧库缺列导致接口 500。
    """
    ddl_statements = [
        "ALTER TABLE character_relationships ADD COLUMN IF NOT EXISTS is_dynamic VARCHAR(20)",
        "ALTER TABLE character_relationships ADD COLUMN IF NOT EXISTS evolution_note TEXT",
    ]
    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))
        # 历史数据兜底：旧记录如果为空，统一回填 stable
        conn.execute(text(
            "UPDATE character_relationships SET is_dynamic = 'stable' WHERE is_dynamic IS NULL"
        ))


def _ensure_project_columns() -> None:
    """
    开发环境兼容迁移：为已有 projects 表补齐作品基本面字段。
    """
    ddl_statements = [
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS premise TEXT",
        # target_words 从 VARCHAR(20) 升级为 INTEGER，旧字符串值自动转换
        # USING 子句：把旧字符串强制转为 INTEGER（NULL 时保持 NULL）
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'projects'
                  AND column_name = 'target_words'
                  AND data_type <> 'integer'
            ) THEN
                ALTER TABLE projects
                    ALTER COLUMN target_words TYPE INTEGER
                    USING NULLIF(target_words, '')::INTEGER;
            END IF;
        END $$;
        """,
        # 若列不存在则新建（全新部署）
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS target_words INTEGER DEFAULT 1200000",
    ]
    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))


def _ensure_foreshadow_columns() -> None:
    """
    开发环境兼容迁移：为已有 foreshadows 表补齐计划动作字段。
    """
    ddl_statements = [
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS planned_action VARCHAR(20)",
    ]
    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))
        conn.execute(text(
            "UPDATE foreshadows SET planned_action = 'resolve' WHERE planned_action IS NULL"
        ))


def _ensure_memory_embedding_column() -> None:
    """
    开发环境兼容迁移：
    1. 启用 pgvector 扩展（若未安装则跳过，不影响启动）
    2. 若 embedding 列维度与当前配置不一致（旧库 1536 → 新 768），删列重建
    3. 无 embedding 列时以正确维度新建

    修改列类型是破坏性操作（历史向量全部清空），但首次迁移时本就无有效向量，
    后续服务启动如果维度已匹配则直接跳过，安全幂等。
    """
    from app.config import settings as app_settings

    target_dim = app_settings.EMBEDDING_DIM

    with engine.begin() as conn:
        # ── 启用 pgvector 扩展 ──────────────────────────────────────────────
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:  # noqa: BLE001
            # 数据库用户无权限或 pgvector 未安装 → 跳过，语义检索会自动降级
            return

        # ── 查当前 embedding 列是否存在及维度 ─────────────────────────────
        row = conn.execute(text("""
            SELECT atttypmod
            FROM pg_attribute
            WHERE attrelid = 'memory_chunks'::regclass
              AND attname  = 'embedding'
              AND attnum   > 0
              AND NOT attisdropped
        """)).fetchone()

        if row is None:
            # 列不存在 → 新建
            conn.execute(text(
                f"ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS embedding vector({target_dim})"
            ))
        else:
            # atttypmod 对 vector 类型：维度存在 typmod 里，具体值 = dim + 某固定偏移
            # 最可靠的方式是读 column_type 字符串
            type_row = conn.execute(text("""
                SELECT pg_catalog.format_type(atttypid, atttypmod)
                FROM pg_attribute
                WHERE attrelid = 'memory_chunks'::regclass
                  AND attname  = 'embedding'
                  AND attnum   > 0
                  AND NOT attisdropped
            """)).fetchone()
            col_type = type_row[0] if type_row else ""
            # 形如 "vector(1536)" 或 "vector(768)"
            if f"vector({target_dim})" not in col_type:
                # 维度不匹配 → 删列重建（历史向量本就无效）
                conn.execute(text("ALTER TABLE memory_chunks DROP COLUMN embedding"))
                conn.execute(text(
                    f"ALTER TABLE memory_chunks ADD COLUMN embedding vector({target_dim})"
                ))

        # ── 建立 HNSW 近似最近邻索引（已存在则跳过）──────────────────────
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_memory_chunks_embedding_cosine
                ON memory_chunks
                USING hnsw (embedding vector_cosine_ops)
            """))
        except Exception:  # noqa: BLE001
            pass  # 旧版 pgvector 无 HNSW，退化到 IVFFlat 或顺序扫描均可接受


def _ensure_llm_provider_columns() -> None:
    """开发环境兼容迁移：为已有 llm_providers 表补齐 provider_type 列。"""
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE llm_providers ADD COLUMN IF NOT EXISTS provider_type VARCHAR(20) NOT NULL DEFAULT 'text'"
        ))


# 自动建表（开发用，生产建议改用 Alembic）
Base.metadata.create_all(bind=engine)
_ensure_project_columns()
_ensure_outline_node_columns()
_ensure_character_columns()
_ensure_character_relationship_columns()
_ensure_foreshadow_columns()
_ensure_memory_embedding_column()
_ensure_llm_provider_columns()
seed_llm_from_env_if_empty()

app = FastAPI(
    title="Novel System API",
    description="小说创作管理系统后端",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ForwardedHostASGIMiddleware)

# 注册路由
app.include_router(projects.router, prefix="/api/v1")
app.include_router(world_settings.router, prefix="/api/v1")
app.include_router(characters.router, prefix="/api/v1")
app.include_router(outline.router, prefix="/api/v1")
app.include_router(chapters.router, prefix="/api/v1")
app.include_router(chapter_indexes.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(generate.router, prefix="/api/v1")
app.include_router(admin_llm.router, prefix="/api/v1")
app.include_router(admin_llm_calls.router, prefix="/api/v1")
app.include_router(llm_public.router, prefix="/api/v1")
# 新增模块路由
app.include_router(storylines.router, prefix="/api/v1")
app.include_router(power_systems.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
app.include_router(items.router, prefix="/api/v1")
app.include_router(factions.router, prefix="/api/v1")
app.include_router(foreshadows.router, prefix="/api/v1")
app.include_router(quality_debts.router, prefix="/api/v1")
app.include_router(cover_router.router, prefix="/api/v1")

ensure_cover_storage_dir()
app.mount(
    "/api/v1/covers/files",
    StaticFiles(directory=str(resolved_cover_storage_dir())),
    name="novel_cover_files",
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
