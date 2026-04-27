#!/usr/bin/env bash
# 本地快速重启：释放前后端端口后后台启动 uvicorn + vite。
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
NOVEL_LOCAL_BACKEND_PORT="${NOVEL_LOCAL_BACKEND_PORT:-8000}"
NOVEL_LOCAL_FRONTEND_PORT="${NOVEL_LOCAL_FRONTEND_PORT:-5173}"

kill_port() {
  local port=$1
  local pids
  pids="$(lsof -ti ":${port}" 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "正在结束占用端口 ${port} 的进程: ${pids}"
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
}

kill_port "${NOVEL_LOCAL_BACKEND_PORT}"
kill_port "${NOVEL_LOCAL_FRONTEND_PORT}"
sleep 0.3

mkdir -p "${ROOT}/.local/logs"

VENV_ACTIVATE=""
# 优先 backend/.venv（bootstrap：venv / Windows 下 penv），其次根目录 .venv（旧版）
if [[ -f "${ROOT}/backend/.venv/bin/activate" ]]; then
  VENV_ACTIVATE="${ROOT}/backend/.venv/bin/activate"
elif [[ -f "${ROOT}/.venv/bin/activate" ]]; then
  VENV_ACTIVATE="${ROOT}/.venv/bin/activate"
else
  echo "提示: 未找到虚拟环境，请先执行: bash bootstrap.sh"
  echo "  （或: cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt）"
  exit 1
fi

if [[ ! -d "${ROOT}/frontend/node_modules" ]]; then
  echo "提示: 未找到 frontend/node_modules，请先执行: cd frontend && npm install"
  exit 1
fi

(
  cd "${ROOT}/backend"
  # shellcheck source=/dev/null
  source "${VENV_ACTIVATE}"
  exec uvicorn app.main:app --reload --host 127.0.0.1 --port "${NOVEL_LOCAL_BACKEND_PORT}"
) >"${ROOT}/.local/logs/backend.log" 2>&1 &
echo "${!}" >"${ROOT}/.local/logs/backend.pid"
echo "后端已启动 PID $(cat "${ROOT}/.local/logs/backend.pid")，日志: .local/logs/backend.log"

(
  cd "${ROOT}/frontend"
  export VITE_API_PROXY_TARGET="http://127.0.0.1:${NOVEL_LOCAL_BACKEND_PORT}"
  exec npm run dev -- --port "${NOVEL_LOCAL_FRONTEND_PORT}"
) >"${ROOT}/.local/logs/frontend.log" 2>&1 &
echo "${!}" >"${ROOT}/.local/logs/frontend.pid"
echo "前端已启动 PID $(cat "${ROOT}/.local/logs/frontend.pid")，日志: .local/logs/frontend.log"

echo ""
echo "  本地前端: http://localhost:${NOVEL_LOCAL_FRONTEND_PORT}"
echo "  本地 API:  http://127.0.0.1:${NOVEL_LOCAL_BACKEND_PORT}/docs"
echo "  查看日志: tail -f .local/logs/backend.log .local/logs/frontend.log"
