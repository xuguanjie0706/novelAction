#!/usr/bin/env python3
"""
check_file_sizes.py — 文件行数红线检查脚本

依据 CLAUDE.md「代码结构红线」：
  软警戒线（warn）：400 行
  硬上限（error）：600 行

策略：
  - 「已知违规」列表（KNOWN_VIOLATIONS）记录 lint 上线前已存在的超限文件，
    这些文件不会导致 CI 失败，但会在输出中标注（激励治理，不阻断日常开发）。
  - 「豁免」（SKIP_PATTERNS / SKIP_DIRS）用于自动生成文件、测试、三方代码等，
    不做任何检查。
  - 新增的超限文件（不在已知违规列表）会导致 CI 以非零码退出。

退出码：
  0 — 无新增超限文件（存量已知违规不影响退出码）
  N — N 个新增超限文件（N > 0）

用法：
  python scripts/check_file_sizes.py [--warn-only] [--root <repo_root>]
"""
import argparse
import os
import sys
from pathlib import Path

# ─── 配置 ─────────────────────────────────────────────────────────────────────

SOFT_WARN = 400
HARD_LIMIT = 600

# 已知违规文件（lint 上线前已存在的超限文件）。
# 不阻断 CI，但输出中会标注，激励后续治理。
# 每项应在 CLAUDE.md「上帝文件登记册」中有对应说明。
# ── 请勿随意新增；新增时必须附带 CLAUDE.md 登记 + 拆分计划 ──
KNOWN_VIOLATIONS = {
    # ── ChapterEditor 包（已完成结构拆分，index/DebriefPanel 仍超限）──
    "Writing/ChapterEditor/index.tsx",          # 2146 行；待拆 TopToolBar/WarnPanel/ContextSidePanel JSX
    "Writing/ChapterEditor/DebriefPanel.tsx",   # 707 行；待拆 HistorySection/CharUpdateSection

    # ── 前端页面（冻结新增，等待拆分 PR）──
    "pages/OutlinePage.tsx",                    # 2099 行
    "pages/CharactersPage.tsx",                 # 1280 行
    "pages/ProjectDetailPage.tsx",              # 1188 行
    "pages/CluesPage.tsx",                      # 1007 行
    "pages/SettingsPage.tsx",                   # 710 行
    "pages/RhythmMapPage.tsx",                  # 678 行
    "pages/WorldBuildingPage.tsx",              # 1547 行；见拆分蓝图
    "pages/ReadingReviewPage.tsx",              # 1538 行；警告区

    # ── 前端组件 / API ──
    "api/client.ts",                            # 921 行；待按资源域拆包
    "types/index.ts",                           # 838 行；待按模块拆分
    "components/Layout/GenerationQueuePanel.tsx", # 1789 行；警告区
    "components/Bootstrap/hooks/useBootstrapStream.ts", # 611 行
    "components/BookshelfDetail/SectionContent.tsx",    # 601 行

    # ── 后端路由 ──
    "routers/outline/helpers_core.py",          # 2166 行；冻结，见蓝图
    "routers/outline/qa_internal.py",           # 878 行
    "routers/outline/helpers/realm_timeline.py", # 711 行
    "routers/ai/debrief_routes.py",             # 804 行
    "routers/cover.py",                         # 908 行

    # ── 后端 services ──
    "services/ai/context_builder.py",           # 795 行（原 context.py 迁入）
    "services/ai/outline_ai.py",               # 735 行
    "services/ai/debrief.py",                  # 638 行
    "services/bootstrap/context_vol_expand.py", # 634 行
}

# 跳过整个目录（不扫描）
SKIP_DIRS = {
    "node_modules", "__pycache__", ".venv", "dist", "build",
    ".git", ".mypy_cache", ".pytest_cache", "coverage",
    "tests",       # 测试文件不受行数限制
}

# 扫描的扩展名 + 对应根路径
SCAN_TARGETS = [
    ("apps/backend/app", {".py"}),
    ("apps/client/src", {".ts", ".tsx"}),
    ("apps/frontend/src", {".ts", ".tsx"}),
]

# 跳过的文件名模式（含字符串）— 自动生成文件
SKIP_PATTERNS = [
    ".d.ts",
    ".min.",
    "schema_",
    "_pb2.py",
]

# ─── 主逻辑 ──────────────────────────────────────────────────────────────────

def is_known_violation(path: Path) -> bool:
    """路径是否与已知违规列表的某条后缀匹配（跨平台路径分隔符）。"""
    path_str = str(path).replace("\\", "/")
    return any(suffix in path_str for suffix in KNOWN_VIOLATIONS)


def should_skip_name(name: str) -> bool:
    return any(pat in name for pat in SKIP_PATTERNS)


def count_lines(path: Path) -> int:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def scan(root: Path, warn_only: bool) -> int:
    """
    扫描所有目标文件。

    Args:
        root: repo 根目录
        warn_only: True 时只输出，不以非零码退出

    Returns:
        新增超限文件数量（已知违规不计入）
    """
    soft_warnings: list[tuple[str, int]] = []
    known_hard: list[tuple[str, int]] = []    # 已知违规的超限文件（输出但不报错）
    new_hard: list[tuple[str, int]] = []      # 新增的超限文件（报错）

    for rel_dir, exts in SCAN_TARGETS:
        scan_dir = root / rel_dir
        if not scan_dir.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(scan_dir):
            # 剪枝
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                suffix = Path(fname).suffix
                if suffix not in exts:
                    continue
                if should_skip_name(fname):
                    continue
                fpath = Path(dirpath) / fname
                lines = count_lines(fpath)
                rel = str(fpath.relative_to(root)).replace("\\", "/")

                if lines > HARD_LIMIT:
                    if is_known_violation(fpath):
                        known_hard.append((rel, lines))
                    else:
                        new_hard.append((rel, lines))
                elif lines > SOFT_WARN:
                    soft_warnings.append((rel, lines))

    # ── 输出 ──────────────────────────────────────────────────────────────
    if soft_warnings:
        print(f"\n⚠️  超软警戒线（>{SOFT_WARN} 行，建议计划拆分）：")
        for rel, n in sorted(soft_warnings, key=lambda x: -x[1]):
            print(f"   {n:5d}  {rel}")

    if known_hard:
        print(f"\n📋  已知超限文件（>{HARD_LIMIT} 行，登记在册，不阻断 CI）：")
        for rel, n in sorted(known_hard, key=lambda x: -x[1]):
            print(f"   {n:5d}  {rel}")

    if new_hard:
        print(f"\n🚫  新增超限文件（>{HARD_LIMIT} 行，PR 必须同步拆分）：")
        for rel, n in sorted(new_hard, key=lambda x: -x[1]):
            print(f"   {n:5d}  {rel}")

    print()
    if not new_hard and not soft_warnings and not known_hard:
        print("✅  全部行数红线检查通过（无任何超限文件）")
    elif not new_hard:
        print(f"✅  无新增超限文件（{len(known_hard)} 个已知违规在册，{len(soft_warnings)} 个告警）")
    else:
        print(f"❌  发现 {len(new_hard)} 个新增超限文件，请拆分后再合并 PR")
        print("    （提示：若为历史遗留文件，请在 scripts/check_file_sizes.py KNOWN_VIOLATIONS 中登记，")
        print("     并在 CLAUDE.md 上帝文件登记册中说明拆分计划）")

    if warn_only:
        return 0
    return len(new_hard)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--warn-only", action="store_true",
                        help="只输出，不以非零码退出（适合信息性 CI 步骤）")
    parser.add_argument("--root", default=".",
                        help="repo 根目录（默认：当前工作目录）")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    exit_code = scan(root, args.warn_only)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
