#!/usr/bin/env python3
"""CLI：将当前 DATABASE_URL 指向的库升到 Alembic head（与启动钩子逻辑一致）。"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.startup.db_schema import run_pre_start_schema  # noqa: E402


def main() -> int:
    rev = run_pre_start_schema()
    print(f"OK: schema aligned (alembic revision={rev or 'skipped'})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
