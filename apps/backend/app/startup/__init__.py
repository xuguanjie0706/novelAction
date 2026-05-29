# startup 包：无法通过 Alembic 表达的运行时 DDL 见 legacy_ddl；业务列请写 migration。
from .db_schema import run_pre_start_schema
from .legacy_ddl import run_startup_ddl

__all__ = ["run_pre_start_schema", "run_startup_ddl"]
