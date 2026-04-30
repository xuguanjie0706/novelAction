from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.config import settings
from app.database import engine, Base
from app.routers import projects, world_settings, characters, outline, chapters, chapter_indexes, ai, generate, admin_llm, llm_public, admin_llm_calls
from app.routers import storylines, power_systems, skills, items, factions
from app.routers import foreshadows
from app.services.llm_config import seed_llm_from_env_if_empty


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


# 自动建表（开发用，生产建议改用 Alembic）
Base.metadata.create_all(bind=engine)
_ensure_project_columns()
_ensure_outline_node_columns()
_ensure_character_columns()
_ensure_character_relationship_columns()
_ensure_foreshadow_columns()
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


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
