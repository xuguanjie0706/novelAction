"""Alembic 运行环境（线上 / 离线均走 app.config.settings 的 DATABASE_URL）。

设计说明
========
- 从 ``app.config.settings.DATABASE_URL`` 取连接串，避免与 main.py 双份维护；
- ``target_metadata`` 指向 ``app.database.Base.metadata``，自动覆盖所有
  ``app.models.*`` 已 import 的模型；
- 不强制 alembic 接管"全部 schema"。本仓库 main.py 仍保留
  ``_ensure_*_columns()`` 兼容老库；新增字段建议同时写两边，老库自动跟进，
  新部署走 ``alembic upgrade head``。
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 把 backend 根目录塞进 sys.path，env.py 才能 import app.*
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_HERE)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402

# 触发所有模型注册（保持与 app.models.__init__ 同步）
from app import models  # noqa: F401, E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 用 settings.DATABASE_URL 覆盖 alembic.ini 的占位
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：不连数据库，直接按版本脚本生成 SQL。"""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直接对真实数据库执行升级。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
