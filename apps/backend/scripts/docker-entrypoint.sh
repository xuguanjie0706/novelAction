#!/bin/sh
# Docker 入口：先对齐 DB schema，再 exec 主进程（uvicorn 等）。
set -eu
cd /app
if [ "${SKIP_ALEMBIC_UPGRADE:-0}" != "1" ]; then
  echo "[entrypoint] running db schema sync (create_all + alembic upgrade head)..."
  python -m app.cli.db_upgrade
fi
exec "$@"
