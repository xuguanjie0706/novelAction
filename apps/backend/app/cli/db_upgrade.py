"""将当前 DATABASE_URL 指向的库升到 Alembic head（与启动钩子逻辑一致）。"""
from __future__ import annotations

from app.startup.db_schema import run_pre_start_schema


def main() -> int:
    rev = run_pre_start_schema()
    print(f"OK: schema aligned (alembic revision={rev or 'skipped'})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        raise SystemExit(1) from exc
