#!/usr/bin/env bash
# 本地一键启动：uvicorn（apps/backend）+ 创作端 Vite（apps/client）+ 管理后台（apps/frontend）
# 依赖：pnpm（推荐 corepack：corepack enable && corepack prepare pnpm@9 --activate）
# 用法：在项目根目录执行 ./restart.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f "${ROOT}/.env.local.ports" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/.env.local.ports"
  set +a
fi
NOVEL_LOCAL_BACKEND_PORT="${NOVEL_LOCAL_BACKEND_PORT:-9000}"
# 兼容旧变量名 NOVEL_LOCAL_FRONTEND_PORT
NOVEL_LOCAL_CLIENT_PORT="${NOVEL_LOCAL_CLIENT_PORT:-${NOVEL_LOCAL_FRONTEND_PORT:-3173}}"
NOVEL_LOCAL_ADMIN_PORT="${NOVEL_LOCAL_ADMIN_PORT:-3174}"

kill_port() {
  local port=$1
  local pids
  # 仅杀 LISTEN 进程：``lsof -ti :PORT`` 在 macOS 上会匹配「本端或远端涉及该端口」的套接字，
  # 会把 **连到后端的 Vite/Node 代理** 一并列进来并 kill -9，导致「一重启前后端全挂」。
  pids="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "正在结束在端口 ${port} 上监听的进程: ${pids}"
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
}

# 结束本仓库 apps/backend 下全部 uvicorn 父进程与 --reload 子 worker（multiprocessing.spawn_main 等）。
# 仅匹配命令行含「项目/apps/backend/.venv/bin/python」的进程，避免误杀其他项目 Python。
# 背景：只杀 LISTEN 端口会留下僵尸 worker，各自持有 SQLAlchemy 连接池，导致 Postgres「too many clients」。
kill_backend_process_tree() {
  local pattern pid args killed=0
  local -a patterns=(
    "${ROOT}/apps/backend/.venv/bin/python"
  )
  if [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
    patterns+=("${ROOT}/backend/.venv/bin/python")
  fi

  for pattern in "${patterns[@]}"; do
    while read -r pid; do
      [[ -n "${pid}" ]] || continue
      args="$(ps -p "${pid}" -o args= 2>/dev/null || true)"
      [[ -z "${args}" ]] && continue
      echo "正在结束后端残留进程 ${pid}"
      kill -9 "${pid}" 2>/dev/null || true
      killed=1
    done < <(pgrep -f "${pattern}" 2>/dev/null || true)
  done

  # 无 .venv 路径时（极少见）：仅杀 apps/backend 目录下的 uvicorn
  while read -r pid; do
    [[ -n "${pid}" ]] || continue
    args="$(ps -p "${pid}" -o args= 2>/dev/null || true)"
    [[ "${args}" == *"${ROOT}/apps/backend"* && "${args}" == *"uvicorn"* ]] || continue
    echo "正在结束后端残留进程 ${pid}（uvicorn）"
    kill -9 "${pid}" 2>/dev/null || true
    killed=1
  done < <(pgrep -f "${ROOT}/apps/backend" 2>/dev/null || true)

  if [[ "${killed}" -eq 1 ]]; then
    echo "已清理 apps/backend 全部 uvicorn / reload worker（释放 PostgreSQL 连接）"
    sleep 0.5
  fi
}

kill_port "${NOVEL_LOCAL_BACKEND_PORT}"
kill_port "${NOVEL_LOCAL_CLIENT_PORT}"
kill_port "${NOVEL_LOCAL_ADMIN_PORT}"

# 清理上次 backend.pid（僵死 uvicorn 可能已不是 LISTEN，但仍占用连接池）
if [[ -f "${ROOT}/.local/logs/backend.pid" ]]; then
  old_backend_pid="$(cat "${ROOT}/.local/logs/backend.pid" 2>/dev/null || true)"
  if [[ -n "${old_backend_pid}" ]] && kill -0 "${old_backend_pid}" 2>/dev/null; then
    echo "正在结束上次后端进程: ${old_backend_pid}"
    kill -9 "${old_backend_pid}" 2>/dev/null || true
  fi
fi

kill_backend_process_tree

# 兜底：结束仍占用后端端口的 python（出站连接；避免误杀非 python）
while read -r pid; do
  [[ -n "${pid}" ]] || continue
  cmd="$(ps -p "${pid}" -o comm= 2>/dev/null || true)"
  if [[ "${cmd}" == *python* ]]; then
    kill -9 "${pid}" 2>/dev/null || true
  fi
done < <(lsof -nP -iTCP:"${NOVEL_LOCAL_BACKEND_PORT}" -t 2>/dev/null || true)

sleep 0.5

mkdir -p "${ROOT}/.local/logs"

run_pnpm_dev() {
  local dir="$1"
  local vite_port="$2"
  cd "${ROOT}/${dir}"
  export VITE_API_PROXY_TARGET="http://127.0.0.1:${NOVEL_LOCAL_BACKEND_PORT}"
  if command -v pnpm >/dev/null 2>&1; then
    exec pnpm run dev -- --port "${vite_port}"
  fi
  exec npx --yes pnpm@9 run dev -- --port "${vite_port}"
}

# 使用 venv 内 python 的绝对路径，避免 conda/base 污染 PATH 时 `python` 仍指向系统解释器
VENV_PYTHON=""
if [[ -x "${ROOT}/apps/backend/.venv/bin/python" ]]; then
  VENV_PYTHON="${ROOT}/apps/backend/.venv/bin/python"
elif [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  VENV_PYTHON="${ROOT}/backend/.venv/bin/python"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  VENV_PYTHON="${ROOT}/.venv/bin/python"
else
  echo "提示: 未找到虚拟环境 Python（apps/backend/.venv/bin/python），请先执行: bash bootstrap.sh"
  echo "  （或: cd apps/backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt）"
  exit 1
fi

EXPECTED_PYTHON_VERSION="3.12.7"
ACTUAL_PYTHON_VERSION="$("${VENV_PYTHON}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
if [[ "${ACTUAL_PYTHON_VERSION}" != "${EXPECTED_PYTHON_VERSION}" ]]; then
  echo "错误: 当前后端虚拟环境 Python 版本为 ${ACTUAL_PYTHON_VERSION}，必须为 ${EXPECTED_PYTHON_VERSION}。"
  echo "请执行: BOOTSTRAP_RECREATE_VENV=1 bash bootstrap.sh"
  exit 1
fi

if [[ ! -d "${ROOT}/apps/client/node_modules" ]] || [[ ! -d "${ROOT}/apps/frontend/node_modules" ]]; then
  echo "提示: 未找到 apps/client 或 apps/frontend 的 node_modules。"
  echo "  请在仓库根目录执行: bash bootstrap.sh"
  echo "  或手动: (cd apps/client && pnpm install) && (cd apps/frontend && pnpm install)"
  exit 1
fi

# 后端在 import app.main 时会立即连库（create_all / 兼容迁移），PostgreSQL 未就绪会直接崩溃。
# 注意：Docker 容器显示 Running ≠ Postgres 已 accept；刚 up 时常需数秒初始化。
check_postgres_ready() {
  (
    cd "${ROOT}/apps/backend"
    "${VENV_PYTHON}" -c "
from sqlalchemy import create_engine, text
from app.config import settings
engine = create_engine(settings.DATABASE_URL)
with engine.connect() as conn:
    conn.execute(text('SELECT 1'))
"
  )
}

wait_for_postgres() {
  local max_attempts=15
  local attempt=1
  while [[ "${attempt}" -le "${max_attempts}" ]]; do
    if check_postgres_ready 2>/dev/null; then
      return 0
    fi
    if [[ "${attempt}" -eq 1 ]]; then
      echo "等待 PostgreSQL 就绪（容器刚启动时可能需要几秒）..."
    fi
    echo "  重试 ${attempt}/${max_attempts}..."
    sleep 2
    attempt=$((attempt + 1))
  done
  return 1
}

if ! wait_for_postgres; then
  echo "错误: 无法连接 PostgreSQL，后端无法启动（与 embedding 等业务代码无关）。"
  echo "  连接串见 apps/backend/.env 中的 DATABASE_URL（默认 localhost:5432）。"
  echo ""
  echo "  诊断（最后一次连接尝试的详细错误）："
  check_postgres_ready || true
  echo ""
  echo "  若使用本仓库 Docker 数据库："
  echo "    colima start                    # 若 Docker 报 docker.sock 不存在"
  echo "    docker-compose up -d postgres redis"
  echo "    docker ps                       # 确认 0.0.0.0:5432->5432 已映射"
  echo ""
  echo "  数据库就绪后重新执行: ./restart.sh"
  exit 1
fi

if [[ "${SKIP_ALEMBIC_UPGRADE:-0}" != "1" ]]; then
  echo "同步数据库 schema（create_all + alembic upgrade head）..."
  if ! (
    cd "${ROOT}/apps/backend"
    "${VENV_PYTHON}" -m app.cli.db_upgrade
  ); then
    echo "错误: 数据库迁移失败。可查看上方输出，或在 apps/backend 手动执行: alembic upgrade head"
    echo "  临时跳过迁移启动（不推荐）: SKIP_ALEMBIC_UPGRADE=1 ./restart.sh"
    exit 1
  fi
fi

(
  cd "${ROOT}/apps/backend"
  exec "${VENV_PYTHON}" -m uvicorn app.main:app --reload --host 127.0.0.1 --port "${NOVEL_LOCAL_BACKEND_PORT}"
) >"${ROOT}/.local/logs/backend.log" 2>&1 &
echo "${!}" >"${ROOT}/.local/logs/backend.pid"
echo "后端已启动 PID $(cat "${ROOT}/.local/logs/backend.pid")，日志: .local/logs/backend.log"

_backend_listen_ok=0
for _ in 1 2 3 4 5 6; do
  if lsof -nP -iTCP:"${NOVEL_LOCAL_BACKEND_PORT}" -sTCP:LISTEN -t >/dev/null 2>&1; then
    _backend_listen_ok=1
    break
  fi
  sleep 1
done
if [[ "${_backend_listen_ok}" -eq 0 ]]; then
  echo "警告: 端口 ${NOVEL_LOCAL_BACKEND_PORT} 未在监听，后端可能启动失败。最近日志："
  tail -n 8 "${ROOT}/.local/logs/backend.log" 2>/dev/null || true
  echo "  完整日志: tail -f .local/logs/backend.log"
  echo "  若为 Address already in use，请再执行一次 ./restart.sh（会先释放端口）"
fi

(
  run_pnpm_dev apps/client "${NOVEL_LOCAL_CLIENT_PORT}"
) >"${ROOT}/.local/logs/client.log" 2>&1 &
echo "${!}" >"${ROOT}/.local/logs/client.pid"
echo "创作端已启动 PID $(cat "${ROOT}/.local/logs/client.pid")，日志: .local/logs/client.log"

(
  run_pnpm_dev apps/frontend "${NOVEL_LOCAL_ADMIN_PORT}"
) >"${ROOT}/.local/logs/admin.log" 2>&1 &
echo "${!}" >"${ROOT}/.local/logs/admin.pid"
echo "管理后台已启动 PID $(cat "${ROOT}/.local/logs/admin.pid")，日志: .local/logs/admin.log"

echo ""
echo "  创作端（小说）: http://localhost:${NOVEL_LOCAL_CLIENT_PORT}"
echo "  管理后台:       http://localhost:${NOVEL_LOCAL_ADMIN_PORT}"
echo "  本地 API:       http://127.0.0.1:${NOVEL_LOCAL_BACKEND_PORT}/docs"
echo "  查看日志:       tail -f .local/logs/backend.log .local/logs/client.log .local/logs/admin.log"
