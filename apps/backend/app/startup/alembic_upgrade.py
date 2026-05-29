"""启动时将 PostgreSQL schema 与 Alembic head 对齐。

老库（有 ``projects`` 但无 ``alembic_version``）会先 ``stamp`` 到 consolidate 修订，
再 ``upgrade head``，避免从链首重跑 ``CREATE TABLE`` 与 ``create_all`` 冲突。
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.config import settings

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_ROOT / "alembic.ini"
_DEFAULT_LEGACY_STAMP = "p1q2r3s4t5u6"


def _alembic_config() -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return cfg


def _has_table(engine: Engine, name: str) -> bool:
    return inspect(engine).has_table(name)


def get_alembic_current_revision(engine: Engine) -> str | None:
    """读取 ``alembic_version``；表不存在或未 stamp 时返回 ``None``。"""
    if not _has_table(engine, "alembic_version"):
        return None
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
        return str(row[0]) if row and row[0] else None


def _current_revision(engine: Engine) -> str | None:
    return get_alembic_current_revision(engine)


def get_alembic_head_revision() -> str:
    """返回迁移链 head revision id（供 health / 诊断）。"""
    script = ScriptDirectory.from_config(_alembic_config())
    head = script.get_current_head()
    if not head:
        raise RuntimeError("Alembic 迁移链未定义 head")
    return head


def ensure_alembic_at_head(*, engine: Engine) -> str:
    """
    将数据库 revision 升到 head；必要时对遗留库 stamp。

    Returns:
        执行后的 ``alembic_version.version_num``。

    Raises:
        RuntimeError: upgrade 后仍落后于 head。
    """
    cfg = _alembic_config()
    head = get_alembic_head_revision()
    current = _current_revision(engine)

    if current is None and _has_table(engine, "projects"):
        legacy = (settings.ALEMBIC_LEGACY_STAMP_REVISION or _DEFAULT_LEGACY_STAMP).strip()
        logger.warning(
            "检测到未纳入 Alembic 的已有库（无 alembic_version，projects 已存在），"
            "stamp=%s 后 upgrade head=%s",
            legacy,
            head,
        )
        command.stamp(cfg, legacy)
        current = _current_revision(engine)

    if current != head:
        logger.info("alembic upgrade head（%s → %s）", current or "(empty)", head)
        command.upgrade(cfg, "head")

    after = _current_revision(engine)
    if after != head:
        raise RuntimeError(
            f"数据库 schema 未对齐：alembic current={after!r}, head={head!r}。"
            "请在 apps/backend 执行：alembic upgrade head"
        )
    logger.info("Alembic 已对齐 head=%s", after)
    return after or head
