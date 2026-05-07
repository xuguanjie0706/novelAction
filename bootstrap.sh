#!/usr/bin/env bash

# novelAction 环境 bootstrap
# - Windows：用 https://github.com/hmasdev/penv 创建 apps/backend/.venv（嵌入版 Python）
# - macOS / Linux：默认用 Astral「uv」管理 Python + venv + 依赖（https://github.com/astral-sh/uv）
#   若 uv 不可用且未跳过安装，会回退到 python -m venv + pip
#   BOOTSTRAP_USE_UV=0 可强制走旧版 venv；BOOTSTRAP_SKIP_UV_INSTALL=1 不自动装 uv
# 用法：在项目根目录执行 bash bootstrap.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_VERSION_FILE="$ROOT_DIR/.python-version"
BACKEND_DIR="$ROOT_DIR/apps/backend"
BACKEND_PYPROJECT="$BACKEND_DIR/pyproject.toml"
BACKEND_REQUIREMENTS="$BACKEND_DIR/requirements.txt"
CLIENT_DIR="$ROOT_DIR/apps/client"
ADMIN_DIR="$ROOT_DIR/apps/frontend"

PENV_GIT_URL="${PENV_GIT_URL:-https://github.com/hmasdev/penv.git}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*" >&2; }
success() { echo -e "${GREEN}[OK]${NC}    $*" >&2; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*" >&2; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

read_embed_python_version() {
  if [ -f "$PYTHON_VERSION_FILE" ]; then
    local line
    line="$(grep -v '^[[:space:]]*$' "$PYTHON_VERSION_FILE" | head -n1 | tr -d '[:space:]')"
    if [ -n "$line" ]; then
      echo "$line"
      return 0
    fi
  fi
  echo "3.12.7"
}

# 后端统一强制 CPython 3.12.7，避免团队环境漂移（尤其是误用 3.9）
normalize_backend_python_version() {
  local v="${1:-}"
  if [ "$v" = "3.12.7" ]; then
    echo "3.12.7"
    return 0
  fi
  if [ -n "$v" ]; then
    warn "Python ${v} 不符合统一版本要求，改用 3.12.7。"
  fi
  echo "3.12.7"
}

# 确保 PATH 含常见 uv 安装位置（install.sh 默认 ~/.local/bin）
uv_prepend_path() {
  case "${PATH:-}" in
    *"${HOME}/.local/bin"*) ;;
    *) export PATH="${HOME}/.local/bin:${PATH}" ;;
  esac
}

ensure_uv() {
  uv_prepend_path
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi

  if [ "${BOOTSTRAP_SKIP_UV_INSTALL:-0}" = "1" ]; then
    warn "BOOTSTRAP_SKIP_UV_INSTALL=1，不自动安装 uv。"
    return 1
  fi

  case "$(uname -s)" in
    Darwin)
      ensure_homebrew
      if brew list uv >/dev/null 2>&1; then
        :
      else
        info "正在通过 Homebrew 安装 uv（Python 环境管理：venv + pip 一体）…"
        brew install uv
      fi
      ;;
    Linux)
      info "正在通过官方脚本安装 uv 到 ~/.local/bin …"
      if ! curl -fsSL https://astral.sh/uv/install.sh | sh; then
        warn "uv 安装脚本失败。"
        return 1
      fi
      uv_prepend_path
      ;;
    *)
      return 1
      ;;
  esac

  command -v uv >/dev/null 2>&1
}

install_backend_uv_unix() {
  local py_ver
  py_ver="$(normalize_backend_python_version "$(read_embed_python_version)")"

  if [ -d "$BACKEND_DIR/.venv" ] && [ "${BOOTSTRAP_RECREATE_VENV:-0}" = "1" ]; then
    warn "BOOTSTRAP_RECREATE_VENV=1，删除已有 apps/backend/.venv …"
    rm -rf "$BACKEND_DIR/.venv"
  fi

  info "使用 uv 创建 apps/backend/.venv（Python ${py_ver}，缺解释器时会自动下载）…"
  (cd "$BACKEND_DIR" && uv venv .venv --python "$py_ver")

  if [ -f "$BACKEND_REQUIREMENTS" ]; then
    info "使用 uv pip 按 requirements.txt 安装后端依赖…"
    (cd "$BACKEND_DIR" && uv pip install -r requirements.txt)
  else
    warn "未找到 apps/backend/requirements.txt，跳过依赖安装。"
  fi

  success "后端 uv 环境就绪（macOS/Linux）"
}

is_windows_env() {
  case "$(uname -s 2>/dev/null)" in
    CYGWIN* | MINGW* | MSYS*) return 0 ;;
  esac
  [ "${OS:-}" = "Windows_NT" ] && return 0
  return 1
}

apply_brew_shellenv() {
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    return 0
  fi
  if [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)" 2>/dev/null || export PATH="/usr/local/bin:$PATH"
    return 0
  fi
  return 1
}

download_install_homebrew() {
  case "$(uname -s)" in
    Darwin) ;;
    *)
      error "自动安装 Homebrew 仅支持 macOS。"
      exit 1
      ;;
  esac

  info "正在下载并安装 Homebrew（可能需要输入本机密码）..."
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || {
    error "Homebrew 安装失败。请检查网络或代理后重试。"
    exit 1
  }

  apply_brew_shellenv || true
}

ensure_homebrew() {
  if command -v brew >/dev/null 2>&1; then
    return 0
  fi

  if apply_brew_shellenv && command -v brew >/dev/null 2>&1; then
    return 0
  fi

  if [ "${BOOTSTRAP_SKIP_HOMEBREW_INSTALL:-0}" = "1" ]; then
    error "未找到 Homebrew。请安装后重试，或去掉 BOOTSTRAP_SKIP_HOMEBREW_INSTALL 以允许自动安装。"
    exit 1
  fi

  download_install_homebrew

  if ! command -v brew >/dev/null 2>&1; then
    apply_brew_shellenv || true
  fi

  if ! command -v brew >/dev/null 2>&1; then
    error "Homebrew 已安装，但当前 shell 仍无法找到 brew。请执行: eval \"\$(/opt/homebrew/bin/brew shellenv)\""
    exit 1
  fi
}

ensure_brew_package() {
  local package_name="$1"

  ensure_homebrew
  if brew list "$package_name" >/dev/null 2>&1; then
    return 0
  fi

  info "正在通过 Homebrew 安装 $package_name..."
  brew install "$package_name"
}

# macOS：用于引导 venv 的 Python 3.12.7（与 .python-version 一致）
ensure_python312_darwin() {
  if [ -n "${BOOTSTRAP_PYTHON312:-}" ] && [ -x "${BOOTSTRAP_PYTHON312}" ]; then
    success "使用 BOOTSTRAP_PYTHON312=${BOOTSTRAP_PYTHON312}"
    return 0
  fi

  local p candidates=(
    python3.12
    /opt/homebrew/bin/python3.12
    /usr/local/bin/python3.12
  )

  for p in "${candidates[@]}"; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; assert sys.version_info[:3] == (3, 12, 7)' >/dev/null 2>&1; then
      export BOOTSTRAP_PYTHON312="$(command -v "$p")"
      success "检测到 Python 3.12.7: ${BOOTSTRAP_PYTHON312}"
      return 0
    fi
  done

  local prefix
  if prefix="$(brew --prefix python@3.12 2>/dev/null)"; then
    if [ -x "${prefix}/bin/python3.12" ]; then
      export BOOTSTRAP_PYTHON312="${prefix}/bin/python3.12"
      success "使用 Homebrew Python 3.12: ${BOOTSTRAP_PYTHON312}"
      return 0
    fi
  fi

  if [ "${BOOTSTRAP_SKIP_PYTHON312_INSTALL:-0}" = "1" ]; then
    error "未找到 Python 3.12.7。请安装 python@3.12（3.12.7）或设置 BOOTSTRAP_PYTHON312。"
    exit 1
  fi

  ensure_brew_package python@3.12
  prefix="$(brew --prefix python@3.12)"
  if [ ! -x "${prefix}/bin/python3.12" ]; then
    error "已安装 python@3.12，但未找到 ${prefix}/bin/python3.12"
    exit 1
  fi
  export BOOTSTRAP_PYTHON312="${prefix}/bin/python3.12"
  success "已安装并选用 Python 3.12.7: ${BOOTSTRAP_PYTHON312}"
}

ensure_python312_linux() {
  if [ -n "${BOOTSTRAP_PYTHON312:-}" ] && [ -x "${BOOTSTRAP_PYTHON312}" ]; then
    success "使用 BOOTSTRAP_PYTHON312=${BOOTSTRAP_PYTHON312}"
    return 0
  fi
  if command -v python3.12 >/dev/null 2>&1 && python3.12 -c 'import sys; assert sys.version_info[:3] == (3, 12, 7)' >/dev/null 2>&1; then
    export BOOTSTRAP_PYTHON312="$(command -v python3.12)"
    success "检测到 Python 3.12.7: ${BOOTSTRAP_PYTHON312}"
    return 0
  fi
  error "未找到 python3.12.7。请用发行版包管理器安装 Python 3.12.7 后重试，或设置 BOOTSTRAP_PYTHON312。"
  exit 1
}

resolve_windows_bootstrap_python() {
  if [ -n "${BOOTSTRAP_PYTHON312:-}" ] && [ -x "${BOOTSTRAP_PYTHON312}" ]; then
    echo "${BOOTSTRAP_PYTHON312}"
    return 0
  fi
  if command -v py >/dev/null 2>&1; then
    if py -3.12 -c "import sys; assert sys.version_info[:3] == (3, 12, 7)" >/dev/null 2>&1; then
      py -3.12 -c "import sys; print(sys.executable)"
      return 0
    fi
    if py -3 -c "import sys; assert sys.version_info[:3] == (3, 12, 7)" >/dev/null 2>&1; then
      py -3 -c "import sys; print(sys.executable)"
      return 0
    fi
  fi
  return 1
}

install_backend_penv_windows() {
  local py_boot ver venv_py clear_flag

  py_boot="$(resolve_windows_bootstrap_python)" || {
    error "Windows 上未找到可用的 Python 3.12.7（尝试 py -3.12）。请先安装 Python 3.12.7。"
    exit 1
  }

  ver="$(normalize_backend_python_version "$(read_embed_python_version)")"
  info "使用 penv 安装嵌入版 Python ${ver} 到 apps/backend/.venv …"

  "$py_boot" -m pip install --disable-pip-version-check -q "git+${PENV_GIT_URL}"

  clear_flag=""
  if [ "${BOOTSTRAP_PENV_CLEAR:-0}" = "1" ]; then
    clear_flag="--clear"
  fi

  "$py_boot" -m penv "$BACKEND_DIR/.venv" --python-version "$ver" $clear_flag

  venv_py="$BACKEND_DIR/.venv/Scripts/python.exe"
  if [ ! -f "$venv_py" ]; then
    error "penv 完成后未找到 $venv_py"
    exit 1
  fi

  info "升级 pip / setuptools / wheel…"
  "$venv_py" -m pip install --default-timeout=120 --retries 5 --upgrade pip setuptools wheel

  if [ -f "$BACKEND_PYPROJECT" ]; then
    warn "存在 pyproject.toml，请自行用该环境安装；当前脚本按 requirements.txt 安装。"
  fi

  if [ -f "$BACKEND_REQUIREMENTS" ]; then
    info "按 requirements.txt 安装后端依赖…"
    "$venv_py" -m pip install --default-timeout=120 --retries 5 -r "$BACKEND_REQUIREMENTS"
  else
    warn "未找到 apps/backend/requirements.txt，跳过 pip 依赖。"
  fi

  success "后端 penv 环境就绪（Windows）"
}

# 不经过 uv：手写 venv + pip（兼容 BOOTSTRAP_USE_UV=0 或 uv 不可用）
install_backend_venv_legacy_unix() {
  case "$(uname -s)" in
    Darwin)
      ensure_python312_darwin
      ;;
    Linux)
      ensure_python312_linux
      ;;
    *)
      error "不支持的系统: $(uname -s)"
      exit 1
      ;;
  esac

  info "使用标准库 venv 创建 apps/backend/.venv（未使用 uv）。"

  if [ -d "$BACKEND_DIR/.venv" ] && [ "${BOOTSTRAP_RECREATE_VENV:-0}" = "1" ]; then
    warn "BOOTSTRAP_RECREATE_VENV=1，删除已有 apps/backend/.venv …"
    rm -rf "$BACKEND_DIR/.venv"
  fi

  if [ ! -d "$BACKEND_DIR/.venv" ]; then
    info "创建 venv: apps/backend/.venv …"
    "$BOOTSTRAP_PYTHON312" -m venv "$BACKEND_DIR/.venv"
  else
    success "复用已有 apps/backend/.venv（若 Python 版本不对请设置 BOOTSTRAP_RECREATE_VENV=1 后重跑）"
  fi

  local venv_py="$BACKEND_DIR/.venv/bin/python"

  if ! "$venv_py" -m pip --version >/dev/null 2>&1; then
    warn "当前 venv 中缺少 pip，尝试 python -m ensurepip …"
    if "$venv_py" -m ensurepip --upgrade 2>/dev/null; then
      success "ensurepip 已恢复 pip"
    else
      warn "ensurepip 失败，删除并重建 apps/backend/.venv …"
      rm -rf "$BACKEND_DIR/.venv"
      "$BOOTSTRAP_PYTHON312" -m venv "$BACKEND_DIR/.venv"
      if ! "$venv_py" -m pip --version >/dev/null 2>&1; then
        "$venv_py" -m ensurepip --upgrade || {
          error "新建 venv 后仍无 pip，请检查 BOOTSTRAP_PYTHON312 指向的 Python 是否完整。"
          exit 1
        }
      fi
    fi
  fi

  info "升级 pip / setuptools / wheel…"
  "$venv_py" -m pip install --default-timeout=120 --retries 5 --upgrade pip setuptools wheel

  if [ -f "$BACKEND_REQUIREMENTS" ]; then
    info "按 requirements.txt 安装后端依赖…"
    "$venv_py" -m pip install --default-timeout=120 --retries 5 -r "$BACKEND_REQUIREMENTS"
  else
    warn "未找到 apps/backend/requirements.txt，跳过 pip 依赖。"
  fi

  success "后端 venv 环境就绪（Unix，legacy）"
}

install_backend_venv_unix() {
  if [ "${BOOTSTRAP_USE_UV:-1}" != "0" ]; then
    uv_prepend_path
    if ensure_uv; then
      install_backend_uv_unix
      return 0
    fi
    warn "uv 不可用，回退到 venv + pip。"
  else
    info "BOOTSTRAP_USE_UV=0，使用 venv + pip。"
  fi
  install_backend_venv_legacy_unix
}

install_backend_dependencies() {
  if [ "${BOOTSTRAP_SKIP_BACKEND:-0}" = "1" ]; then
    warn "已设置 BOOTSTRAP_SKIP_BACKEND=1，跳过后端依赖安装。"
    return 0
  fi

  if is_windows_env; then
    install_backend_penv_windows
  else
    uv_prepend_path
    install_backend_venv_unix
  fi
}

ensure_pnpm() {
  if command -v pnpm >/dev/null 2>&1; then
    return 0
  fi
  if command -v corepack >/dev/null 2>&1; then
    info "启用 corepack 并激活 pnpm 9..."
    corepack enable >/dev/null 2>&1 || true
    corepack prepare pnpm@9 --activate >/dev/null 2>&1 || true
  fi
  if command -v pnpm >/dev/null 2>&1; then
    return 0
  fi
  error "未找到 pnpm。Node 18+ 可执行: corepack enable && corepack prepare pnpm@9 --activate；或 npm install -g pnpm"
  exit 1
}

ensure_node() {
  if command -v npm >/dev/null 2>&1; then
    return 0
  fi

  if [ "${BOOTSTRAP_SKIP_NODE_INSTALL:-0}" = "1" ]; then
    error "未找到 npm。请安装 Node.js 后重试，或去掉 BOOTSTRAP_SKIP_NODE_INSTALL 以允许自动安装。"
    exit 1
  fi

  if is_windows_env; then
    error "未找到 npm。请从 https://nodejs.org 安装 Node.js LTS 后重试。"
    exit 1
  fi

  case "$(uname -s)" in
    Darwin)
      ensure_brew_package node
      ;;
    Linux)
      error "未找到 npm。请先安装 Node.js（发行版包或 nvm）。"
      exit 1
      ;;
    *)
      error "未找到 npm。请先安装 Node.js。"
      exit 1
      ;;
  esac
}

install_node_dependencies_in() {
  local APP_DIR="$1"
  local LABEL="${2:-前端}"
  local PKG_JSON="$APP_DIR/package.json"

  if [ ! -f "$PKG_JSON" ]; then
    return 0
  fi

  ensure_node
  ensure_pnpm
  info "pnpm install ${LABEL}: $APP_DIR"
  (cd "$APP_DIR" && pnpm install)
}

install_frontend_dependencies() {
  if [ "${BOOTSTRAP_SKIP_FRONTEND:-0}" = "1" ]; then
    warn "已设置 BOOTSTRAP_SKIP_FRONTEND=1，跳过前端依赖安装。"
    return 0
  fi

  if [ -f "$ROOT_DIR/pnpm-workspace.yaml" ] && [ -f "$ROOT_DIR/package.json" ]; then
    ensure_node
    ensure_pnpm
    info "pnpm install（仓库根 workspace：apps/client + apps/frontend）"
    (cd "$ROOT_DIR" && pnpm install)
    return 0
  fi

  install_node_dependencies_in "$CLIENT_DIR" "创作端 (apps/client)"
  install_node_dependencies_in "$ADMIN_DIR" "管理后台 (apps/frontend)"
}

main() {
  case "$(uname -s)" in
    Darwin)
      ensure_homebrew
      ;;
    Linux)
      : # 不强制 Homebrew；Python 见 ensure_python312_linux
      ;;
  esac

  install_backend_dependencies
  install_frontend_dependencies

  success "bootstrap 完成"
  echo ""
  echo "下一步："
  echo "  cp apps/backend/.env.example apps/backend/.env   # 填写 API Key 等"
  echo "  ./restart.sh"
  echo ""
  if is_windows_env; then
    echo "Windows：后端虚拟环境由 penv 创建；可选 BOOTSTRAP_PENV_CLEAR=1 强制清空重建。"
  else
    echo "macOS/Linux：默认用 uv 管理 apps/backend/.venv；强制旧逻辑: BOOTSTRAP_USE_UV=0 bash bootstrap.sh"
    echo "常用工具：uv（本脚本）| pyenv（多版本）| pipenv / poetry（Pipfile/lock）| conda（科学栈）"
  fi
}

main "$@"
