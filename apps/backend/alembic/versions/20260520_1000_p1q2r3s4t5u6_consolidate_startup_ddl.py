"""整合 main.py 中 _ensure_xxx 启动 DDL 到 Alembic

Revision ID: p1q2r3s4t5u6
Revises: z9y8x7w6v5u4
Create Date: 2026-05-20

背景
====
此前 main.py 包含 17 个 _ensure_xxx_columns() 函数，在每次服务启动时直接执行 DDL，
完全绕开 Alembic，导致：
- alembic current 不能反映真实 DB schema
- 无法 downgrade
- CI 与生产 schema 可能不一致

本迁移将所有「仅由 startup 钩子管理」的 DDL 收录进 Alembic 历史，
所有语句均使用 IF NOT EXISTS，对已完成迁移的库安全幂等。

例外（不在本迁移中，仍在 startup 模块中）：
- memory_chunks/chapters 的 pgvector embedding 列（维度依赖运行时 settings.EMBEDDING_DIM）
- _claim_orphan_projects（数据迁移，需要读当前用户表状态）
- pgvector HNSW 索引（已由 e3f4a5b6c7d8 覆盖）

注意：所有之前单独迁移已覆盖的列（character_screen_time、pov_character_id、
speech_kit、phase、extra、user_id、foreshadow ledger 列等）在本迁移中重复执行
IF NOT EXISTS 为幂等 no-op，不会导致错误。
"""
from __future__ import annotations

from alembic import op

revision = "p1q2r3s4t5u6"
down_revision = "z9y8x7w6v5u4"
branch_labels = None
depends_on = None


def upgrade() -> None:  # noqa: C901
    # ── outline_nodes 补齐字段 ──────────────────────────────────────────────
    for ddl in [
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS storyline_ids JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS involved_character_ids JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS key_item_ids JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS key_skill_ids JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS emotional_tone VARCHAR(50)",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS pacing VARCHAR(20)",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS character_screen_time JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS pov_character_id UUID",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS phase VARCHAR(20)",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS power_milestone TEXT",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS foreshadows_laid JSON",
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS foreshadows_resolved JSON",
    ]:
        op.execute(ddl)

    # ── characters 补齐字段 ─────────────────────────────────────────────────
    for ddl in [
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
    ]:
        op.execute(ddl)

    # ── character_relationships 补齐字段 ───────────────────────────────────
    op.execute(
        "ALTER TABLE character_relationships "
        "ADD COLUMN IF NOT EXISTS is_dynamic VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE character_relationships "
        "ADD COLUMN IF NOT EXISTS evolution_note TEXT"
    )
    op.execute(
        "UPDATE character_relationships "
        "SET is_dynamic = 'stable' WHERE is_dynamic IS NULL"
    )

    # ── projects 补齐字段 ───────────────────────────────────────────────────
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS premise TEXT")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS user_id UUID")
    op.execute("""
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
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects (user_id)"
    )
    op.execute("""
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
    """)
    op.execute(
        "ALTER TABLE projects "
        "ADD COLUMN IF NOT EXISTS target_words INTEGER DEFAULT 1200000"
    )
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS extra JSON")

    # ── quality_debts 补齐字段 ─────────────────────────────────────────────
    op.execute(
        "ALTER TABLE quality_debts "
        "ADD COLUMN IF NOT EXISTS author_notes TEXT"
    )
    # chapter_id 允许 nullable（删章或归档时不硬删行）
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'quality_debts'
                  AND column_name = 'chapter_id'
                  AND is_nullable = 'NO'
            ) THEN
                ALTER TABLE quality_debts ALTER COLUMN chapter_id DROP NOT NULL;
            END IF;
        END $$;
    """)

    # ── foreshadows 补齐字段 ───────────────────────────────────────────────
    op.execute(
        "ALTER TABLE foreshadows "
        "ADD COLUMN IF NOT EXISTS planned_action VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE foreshadows "
        "ADD COLUMN IF NOT EXISTS foreshadow_type VARCHAR(30) DEFAULT 'hook'"
    )
    op.execute(
        "ALTER TABLE foreshadows "
        "ADD COLUMN IF NOT EXISTS min_distance INTEGER DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE foreshadows "
        "ADD COLUMN IF NOT EXISTS max_distance INTEGER DEFAULT 15"
    )
    op.execute(
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS paid_off_quality INTEGER"
    )
    op.execute(
        "ALTER TABLE foreshadows "
        "ADD COLUMN IF NOT EXISTS audience_aware INTEGER DEFAULT 3"
    )
    op.execute(
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS volume_budget JSON"
    )
    op.execute(
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS extra JSON DEFAULT '{}'"
    )
    op.execute(
        "UPDATE foreshadows SET planned_action = 'resolve' WHERE planned_action IS NULL"
    )
    op.execute(
        "UPDATE foreshadows SET foreshadow_type = 'hook' WHERE foreshadow_type IS NULL"
    )
    op.execute(
        "UPDATE foreshadows SET min_distance = 1 WHERE min_distance IS NULL"
    )
    op.execute(
        "UPDATE foreshadows SET max_distance = 15 WHERE max_distance IS NULL"
    )
    op.execute(
        "UPDATE foreshadows SET audience_aware = 3 WHERE audience_aware IS NULL"
    )

    # ── llm_providers 补齐字段 ─────────────────────────────────────────────
    op.execute(
        "ALTER TABLE llm_providers "
        "ADD COLUMN IF NOT EXISTS provider_type VARCHAR(20) NOT NULL DEFAULT 'text'"
    )

    # ── chapter_coherence_reports 补齐字段 ────────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'chapter_coherence_reports'
            ) THEN
                EXECUTE
                    'ALTER TABLE chapter_coherence_reports '
                    'ADD COLUMN IF NOT EXISTS apply_events JSON NOT NULL DEFAULT ''[]''::json';
                EXECUTE
                    'UPDATE chapter_coherence_reports '
                    'SET apply_events = ''[]''::json WHERE apply_events IS NULL';
            END IF;
        END $$;
    """)

    # ── cover_image_call_logs 补齐字段 ────────────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'cover_image_call_logs'
            ) THEN
                EXECUTE
                    'ALTER TABLE cover_image_call_logs '
                    'ADD COLUMN IF NOT EXISTS result_cover_url TEXT';
            END IF;
        END $$;
    """)

    # ── locations 索引（表由 Base.metadata.create_all 建立）──────────────
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'locations'
            ) THEN
                EXECUTE
                    'CREATE INDEX IF NOT EXISTS ix_locations_project_id '
                    'ON locations (project_id)';
            END IF;
        END $$;
    """)

    # ── scenes.location_id FK 列 ──────────────────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'locations'
            ) THEN
                EXECUTE
                    'ALTER TABLE scenes '
                    'ADD COLUMN IF NOT EXISTS location_id UUID '
                    'REFERENCES locations(id) ON DELETE SET NULL';
            END IF;
        END $$;
    """)

    # ── bootstrap_runs 表（新库由 create_all 建，旧库由本语句补） ─────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS bootstrap_runs (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
            project_id   UUID REFERENCES projects(id) ON DELETE SET NULL,
            status       VARCHAR(30) NOT NULL DEFAULT 'pending',
            error_message TEXT,
            logline      TEXT NOT NULL,
            mode         VARCHAR(20) NOT NULL DEFAULT 'sequential',
            model_profile VARCHAR(20) NOT NULL DEFAULT 'gemini',
            gate_data    JSON,
            events       JSON NOT NULL DEFAULT '[]',
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            updated_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── generation_jobs 表（新库由 create_all 建，旧库由本语句补） ─────────
    op.execute("""
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
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_generation_jobs_project_id "
        "ON generation_jobs (project_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_generation_jobs_user_id "
        "ON generation_jobs (user_id)"
    )


def downgrade() -> None:
    # 此迁移为补齐性 DDL，downgrade 仅供记录，生产不建议执行
    # 关键结构性字段不做 DROP，避免数据损失
    pass
