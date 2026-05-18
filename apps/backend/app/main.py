import asyncio

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
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
from app.dependencies import get_current_user, verify_project_access
from app.routers import projects, world_settings, characters, outline, chapters, chapter_indexes, ai, generate, admin_llm, llm_public, admin_llm_calls, admin_cover_image_calls, admin_rag_logs
from app.routers import storylines, power_systems, skills, items, factions
from app.routers import foreshadows, quality_debts
from app.routers import scenes, reader_promises, locations as locations_router
from app.routers import export as export_router
from app.routers import cover as cover_router
from app.routers import auth as auth_router
from app.routers import admin_auth as admin_auth_router
from app.routers import dashboard as dashboard_router
from app.routers import bootstrap_graph as bootstrap_graph_router
from app.routers import credits as credits_router
from app.routers import admin_credits as admin_credits_router
from app.routers import admin_redeem_codes as admin_redeem_codes_router
from app.routers import consistency_fix as consistency_fix_router
from app.routers import jobs as jobs_router
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
        # P2 戏份预算 / 强制 POV（与 ORM OutlineNode 一致）
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS character_screen_time JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS pov_character_id UUID",
        # 卷阶段标记，写章节模板分流（opening/rising/turning/dark_hour/climax/ending）
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS phase VARCHAR(20)",
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
        "ALTER TABLE characters ADD COLUMN IF NOT EXISTS speech_kit JSON",
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
        # 多用户隔离：项目归属用户。FK + 索引；旧数据保持 NULL，由 _claim_orphan_projects 回填。
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS user_id UUID",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_name = 'projects' AND constraint_name = 'fk_projects_user_id'
            ) AND EXISTS (
                SELECT 1 FROM information_schema.tables WHERE table_name = 'users'
            ) THEN
                ALTER TABLE projects
                    ADD CONSTRAINT fk_projects_user_id
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """,
        "CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects (user_id)",
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
        # Step 0 立项定位与作品级元设定挂在 extra JSON
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS extra JSON",
    ]
    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))


def _claim_orphan_projects() -> None:
    """
    多用户隔离一次性回填：把 user_id IS NULL 的历史项目归到最早注册的 active 用户。

    场景：在引入 Project.user_id 之前创建的项目，列升级后默认 NULL，对所有人不可见；
    本函数在没有任何 active 用户时不做任何动作（避免误归属）。该 UPDATE 幂等：
    回填一次后，后续启动 NULL 行集合为空，不再触发。
    """
    with engine.begin() as conn:
        # users 表必须存在；该函数在 create_all 之后调用
        row = conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'users'"
        )).fetchone()
        if not row:
            return
        conn.execute(text(
            """
            UPDATE projects
               SET user_id = (
                     SELECT id FROM users
                      WHERE is_active = TRUE
                      ORDER BY created_at ASC
                      LIMIT 1
                   )
             WHERE user_id IS NULL
               AND EXISTS (SELECT 1 FROM users WHERE is_active = TRUE)
            """
        ))


def _ensure_quality_debt_author_notes() -> None:
    """为 quality_debts 表补齐作者手动修复备注列。"""
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE quality_debts ADD COLUMN IF NOT EXISTS author_notes TEXT"
        ))


def _ensure_quality_debt_chapter_id_nullable() -> None:
    """允许 chapter_id 置空，删章或归档债务时不硬删行。"""
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE quality_debts ALTER COLUMN chapter_id DROP NOT NULL"
            ))
    except Exception:
        pass  # SQLite 等方言差异或已 nullable


def _ensure_foreshadow_columns() -> None:
    """
    开发环境兼容迁移：为已有 foreshadows 表补齐计划动作字段。
    """
    ddl_statements = [
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS planned_action VARCHAR(20)",
        # P2-W5-3 伏笔台账升级（与 ORM Foreshadow 一致）
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS foreshadow_type VARCHAR(30) DEFAULT 'hook'",
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS min_distance INTEGER DEFAULT 1",
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS max_distance INTEGER DEFAULT 15",
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS paid_off_quality INTEGER",
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS audience_aware INTEGER DEFAULT 3",
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS volume_budget JSON",
    ]
    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))
        conn.execute(text(
            "UPDATE foreshadows SET planned_action = 'resolve' WHERE planned_action IS NULL"
        ))
        conn.execute(text(
            "UPDATE foreshadows SET foreshadow_type = 'hook' WHERE foreshadow_type IS NULL"
        ))
        conn.execute(text(
            "UPDATE foreshadows SET min_distance = 1 WHERE min_distance IS NULL"
        ))
        conn.execute(text(
            "UPDATE foreshadows SET max_distance = 15 WHERE max_distance IS NULL"
        ))
        conn.execute(text(
            "UPDATE foreshadows SET audience_aware = 3 WHERE audience_aware IS NULL"
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


def _ensure_chapter_embedding_column() -> None:
    """
    开发环境兼容迁移：为已有 chapters 表添加 embedding 向量列，供章节语义检索使用。
    维度与 EMBEDDING_DIM 保持一致；维度不匹配时删列重建（历史向量本就无效）。
    pgvector 扩展不可用时静默跳过，语义检索降级到时间序。
    """
    from app.config import settings as app_settings

    target_dim = app_settings.EMBEDDING_DIM

    with engine.begin() as conn:
        # pgvector 扩展必须已启用（由 _ensure_memory_embedding_column 负责创建）
        row = conn.execute(text("""
            SELECT 1 FROM pg_extension WHERE extname = 'vector'
        """)).fetchone()
        if not row:
            return  # pgvector 未安装，跳过

        existing = conn.execute(text("""
            SELECT pg_catalog.format_type(atttypid, atttypmod)
            FROM pg_attribute
            WHERE attrelid = 'chapters'::regclass
              AND attname  = 'embedding'
              AND attnum   > 0
              AND NOT attisdropped
        """)).fetchone()

        if existing is None:
            conn.execute(text(
                f"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS embedding vector({target_dim})"
            ))
        elif f"vector({target_dim})" not in existing[0]:
            # 维度不匹配（如旧库 1536 → 新 768）：删列重建
            conn.execute(text("ALTER TABLE chapters DROP COLUMN embedding"))
            conn.execute(text(
                f"ALTER TABLE chapters ADD COLUMN embedding vector({target_dim})"
            ))


def _ensure_llm_provider_columns() -> None:
    """开发环境兼容迁移：为已有 llm_providers 表补齐 provider_type 列。"""
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE llm_providers ADD COLUMN IF NOT EXISTS provider_type VARCHAR(20) NOT NULL DEFAULT 'text'"
        ))


def _ensure_chapter_coherence_report_columns() -> None:
    """为已有 chapter_coherence_reports 表补齐改正文写入记录字段。"""
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE chapter_coherence_reports "
            "ADD COLUMN IF NOT EXISTS apply_events JSON NOT NULL DEFAULT '[]'::json"
        ))
        conn.execute(text(
            "UPDATE chapter_coherence_reports SET apply_events = '[]'::json WHERE apply_events IS NULL"
        ))


def _ensure_cover_image_call_logs_columns() -> None:
    """
    旧库只跑过首条 cover 迁移、未跑 result_cover_url 迁移时，ORM 读表会缺列 500。
    create_all 也不会给已存在表加列，此处与 outline/character 一致做 IF NOT EXISTS 补齐。
    """
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = 'cover_image_call_logs'"
            )
        ).fetchone()
        if not row:
            return
        conn.execute(
            text(
                "ALTER TABLE cover_image_call_logs "
                "ADD COLUMN IF NOT EXISTS result_cover_url TEXT"
            )
        )


def _ensure_locations_table() -> None:
    """
    开发环境兼容迁移：为 locations 表补充索引（幂等）。
    主表由 Base.metadata.create_all 建立；若模型未注册导致表尚未存在，跳过索引以免启动失败。
    """
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = 'locations'"
            )
        ).fetchone()
        if not row:
            return
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_locations_project_id ON locations (project_id)"
        ))


def _ensure_scene_location_id_column() -> None:
    """为 scenes 表启用 location_id FK 列（从注释预留状态正式启用）。"""
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS location_id UUID REFERENCES locations(id) ON DELETE SET NULL"
        ))


def _ensure_bootstrap_runs_table() -> None:
    """为旧库补齐 bootstrap_runs 表（Base.metadata.create_all 对已存在表无害，此处是安全兜底）。"""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bootstrap_runs (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
                project_id  UUID REFERENCES projects(id) ON DELETE SET NULL,
                status      VARCHAR(30) NOT NULL DEFAULT 'pending',
                error_message TEXT,
                logline     TEXT NOT NULL,
                mode        VARCHAR(20) NOT NULL DEFAULT 'sequential',
                model_profile VARCHAR(20) NOT NULL DEFAULT 'gemini',
                gate_data   JSON,
                events      JSON NOT NULL DEFAULT '[]',
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """))


def _ensure_generation_jobs_table() -> None:
    """为旧库补齐 generation_jobs 表（chapter_draft LangGraph 队列，Base.metadata.create_all 也会建，此处幂等兜底）。"""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS generation_jobs (
                id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id        UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                user_id           UUID REFERENCES users(id) ON DELETE SET NULL,
                job_type          VARCHAR(30) NOT NULL DEFAULT 'chapter_draft',
                status            VARCHAR(30) NOT NULL DEFAULT 'pending',
                current_node      VARCHAR(60),
                progress_pct      INTEGER NOT NULL DEFAULT 0,
                input_payload     JSON NOT NULL DEFAULT '{}',
                user_input_schema JSON,
                user_input        JSON,
                events            JSON NOT NULL DEFAULT '[]',
                result            JSON,
                error_detail      TEXT,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW(),
                completed_at      TIMESTAMPTZ
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_generation_jobs_project_id ON generation_jobs (project_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_generation_jobs_user_id ON generation_jobs (user_id)"
        ))


# 自动建表（开发用，生产建议改用 Alembic）
Base.metadata.create_all(bind=engine)
_ensure_project_columns()
_ensure_outline_node_columns()
_ensure_character_columns()
_ensure_character_relationship_columns()
_ensure_foreshadow_columns()
_ensure_quality_debt_author_notes()
_ensure_quality_debt_chapter_id_nullable()
_ensure_memory_embedding_column()
_ensure_chapter_embedding_column()
_ensure_llm_provider_columns()
_ensure_chapter_coherence_report_columns()
_ensure_cover_image_call_logs_columns()
_ensure_bootstrap_runs_table()
_ensure_generation_jobs_table()
_ensure_locations_table()
_ensure_scene_location_id_column()
_claim_orphan_projects()
seed_llm_from_env_if_empty()

app = FastAPI(
    title="Novel System API",
    description="小说创作管理系统后端",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.middleware("http")
async def llm_billing_user_context_middleware(request: Request, call_next):
    """将 Bearer JWT 解析为计费用户 UUID，写入 ContextVar。

    供 ``SamplingMixin`` 在 ``log_llm_call`` / 积分预检中统一读取，避免各路由漏传 ``AIService.user_id``。
    使用 ``http`` 中间件而非 ``BaseHTTPMiddleware``，以保证与路由在同异步上下文内传播 ContextVar。
    """
    from app.services.llm_billing_context import (
        billing_user_id_from_authorization_header,
        pop_llm_billing_user,
        push_llm_billing_user,
    )

    tok = push_llm_billing_user(
        billing_user_id_from_authorization_header(request.headers.get("Authorization"))
    )
    try:
        return await call_next(request)
    finally:
        pop_llm_billing_user(tok)


@app.on_event("startup")
async def _on_startup() -> None:
    """
    启动时保存 uvicorn 主事件循环，供 sync 路由（线程池）中的 embed_*_async 使用。
    sync 路由通过 run_coroutine_threadsafe 将 embedding 协程提交到此 loop。

    同时启动 generation job worker 恢复任务：
    扫描服务器重启前残留的 running/waiting_input/pending 任务，
    running/waiting_input → failed（MemorySaver 丢失），pending → 重新 enqueue。
    """
    from app.services.embedding_service import set_main_event_loop
    set_main_event_loop(asyncio.get_running_loop())

    # 生成任务恢复（非阻塞，内部有 2s 延迟等 DB 连接池稳定）
    from app.services.draft_graph.worker import recover_stale_jobs
    asyncio.create_task(recover_stale_jobs(), name="draft-job-recovery")


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ForwardedHostASGIMiddleware)

# 注册路由
# auth：自身完成登录鉴权，不需要外层依赖。
app.include_router(auth_router.router, prefix="/api/v1")

# credits：用户积分余额与流水（需 Bearer token）。
app.include_router(credits_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])

# admin/credits：管理员积分调账（需 admin token，路由内部再校验 role）。
app.include_router(admin_credits_router.router, prefix="/api/v1")

# admin/redeem-codes：管理员批量生成兑换码（需 admin token，路由内部再校验 role）。
app.include_router(admin_redeem_codes_router.router, prefix="/api/v1")

# consistency/fix：AI 辅助修复一致性扫描问题，写回 Character/Faction/Skill 表。
app.include_router(consistency_fix_router.router, prefix="/api/v1")

# admin/auth：管理后台独立登录入口（与创作端用户体系隔离），自身处理鉴权。
app.include_router(admin_auth_router.router, prefix="/api/v1")

# projects：列表/创建只需 current_user；详情/PATCH/DELETE/子配置由路由内部 _owned_or_404 校验。
app.include_router(projects.router, prefix="/api/v1")

# bootstrap（旧）：SSE 直连，向后兼容。
app.include_router(generate.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
# bootstrap（新）：LangGraph 可排队 + human-in-the-loop 闸门；鉴权由路由内部 get_current_user 处理。
app.include_router(bootstrap_graph_router.router, prefix="/api/v1")

# 生成任务队列：章节起草 LangGraph 队列（断线重连 + human interrupt）；鉴权由路由内部处理。
app.include_router(jobs_router.router, prefix="/api/v1")

# 全局只读/管理：需登录但不绑项目。
app.include_router(admin_llm.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(admin_llm_calls.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(admin_cover_image_calls.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(admin_rag_logs.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(llm_public.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])

# 首页 dashboard：跨项目聚合，仅需登录态。
app.include_router(dashboard_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])

# 所有形如 /projects/{project_id}/... 的子资源：统一挂 verify_project_access 校验归属。
_project_scoped_dep = [Depends(verify_project_access)]
app.include_router(world_settings.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(characters.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(outline.router, prefix="/api/v1", dependencies=_project_scoped_dep)
# 大纲工作流 WS：handler 内部以 ?token= 自行鉴权，不能挂 verify_project_access。
app.include_router(outline.ws_router, prefix="/api/v1")
app.include_router(chapters.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(chapter_indexes.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(ai.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(storylines.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(power_systems.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(skills.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(items.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(factions.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(foreshadows.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(export_router.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(quality_debts.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(scenes.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(reader_promises.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(locations_router.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(cover_router.router, prefix="/api/v1", dependencies=_project_scoped_dep)

ensure_cover_storage_dir()
app.mount(
    "/api/v1/covers/files",
    StaticFiles(directory=str(resolved_cover_storage_dir())),
    name="novel_cover_files",
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
