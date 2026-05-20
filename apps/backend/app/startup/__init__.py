# startup 包：仅保留无法通过 Alembic migration 表达的运行时 DDL 和数据修复。
# 新增业务字段请通过 alembic revision 添加 migration 文件，禁止在此包中新增 DDL。
from .legacy_ddl import run_startup_ddl

__all__ = ["run_startup_ddl"]
