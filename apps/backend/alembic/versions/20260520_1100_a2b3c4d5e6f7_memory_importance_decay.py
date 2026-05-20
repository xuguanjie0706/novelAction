"""memory_chunks 增加重要度/访问统计字段（时效衰减 + 冲突检测基础）

Revision ID: a2b3c4d5e6f7
Revises: p1q2r3s4t5u6
Create Date: 2026-05-20

背景
====
三条新列：
- importance_score FLOAT(4)  — AI 提取时赋值 0.0-1.0，检索加权用
- access_count     INT        — 被 RAG 召回的累计次数（重要度热更新依据）
- last_accessed_at TIMESTAMP  — 最近一次被召回时间（时效衰减分析）

以上三列均有 IF NOT EXISTS 保护，对已跑过的库安全幂等。
"""
from __future__ import annotations

from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "p1q2r3s4t5u6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for ddl in [
        "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS importance_score FLOAT DEFAULT 0.5",
        "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0",
        "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMP WITH TIME ZONE",
    ]:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in [
        "ALTER TABLE memory_chunks DROP COLUMN IF EXISTS importance_score",
        "ALTER TABLE memory_chunks DROP COLUMN IF EXISTS access_count",
        "ALTER TABLE memory_chunks DROP COLUMN IF EXISTS last_accessed_at",
    ]:
        op.execute(ddl)
