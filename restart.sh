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
  pids="$(lsof -ti ":${port}" 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "正在结束占用端口 ${port} 的进程: ${pids}"
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
}

kill_port "${NOVEL_LOCAL_BACKEND_PORT}"
kill_port "${NOVEL_LOCAL_CLIENT_PORT}"
kill_port "${NOVEL_LOCAL_ADMIN_PORT}"
sleep 0.3

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

(
  cd "${ROOT}/apps/backend"
  exec "${VENV_PYTHON}" -m uvicorn app.main:app --reload --host 127.0.0.1 --port "${NOVEL_LOCAL_BACKEND_PORT}"
) >"${ROOT}/.local/logs/backend.log" 2>&1 &
echo "${!}" >"${ROOT}/.local/logs/backend.pid"
echo "后端已启动 PID $(cat "${ROOT}/.local/logs/backend.pid")，日志: .local/logs/backend.log"

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
