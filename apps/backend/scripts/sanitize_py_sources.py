#!/usr/bin/env python3
"""检测并修复 Python 源文件中的 NUL / UTF-16 污染。

macOS 或 Windows 编辑器误存为 UTF-16、或通过 scp/rsync 上传时，源码会出现
``\\x00`` 字节，导致 ``py_compile`` / ``import`` 报
``SyntaxError: source code string cannot contain null bytes``。

用法::

    cd apps/backend
    python scripts/sanitize_py_sources.py --check   # CI / 部署前自检
    python scripts/sanitize_py_sources.py             # 就地修复
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ROOTS = ("app", "scripts", "alembic")


_SKIP_DIR_NAMES = frozenset({
    ".venv", "venv", "__pycache__", ".git", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "node_modules",
})


def _iter_py_files(roots: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if any(part in _SKIP_DIR_NAMES for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    for path in sorted(_BACKEND_ROOT.glob("*.py")):
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            files.append(path)
    return sorted(files)


def _has_binary_pollution(raw: bytes) -> bool:
    return b"\x00" in raw or raw.startswith((b"\xff\xfe", b"\xfe\xff"))


def _decode_corrupted(raw: bytes) -> str:
    """将含 NUL 或 UTF-16 BOM 的字节序列还原为 UTF-8 文本。"""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")

    if b"\x00" not in raw:
        return raw.decode("utf-8")

    null_ratio = raw.count(b"\x00") / max(len(raw), 1)
    if null_ratio > 0.1:
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue

    cleaned = raw.replace(b"\x00", b"")
    return cleaned.decode("utf-8")


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def inspect_bytes(raw: bytes) -> bool:
    """若字节流需修复则返回 True。"""
    return _has_binary_pollution(raw)


def sanitize_file(path: Path, *, dry_run: bool = False) -> bool:
    """修复单个文件；有改动返回 True。"""
    raw = path.read_bytes()
    if not inspect_bytes(raw):
        return False

    text = _normalize_newlines(_decode_corrupted(raw))
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return True


def run_check(roots: list[Path]) -> int:
    """仅检测，发现污染文件则 exit 1。"""
    bad: list[Path] = []
    for path in _iter_py_files(roots):
        if inspect_bytes(path.read_bytes()):
            bad.append(path)

    if not bad:
        print(f"OK: {_count_scanned(roots)} Python files, no NUL/UTF-16 pollution")
        return 0

    print(f"ERROR: {len(bad)} file(s) contain NUL bytes or UTF-16 BOM:", file=sys.stderr)
    for path in bad[:30]:
        rel = path.relative_to(_BACKEND_ROOT)
        nul = path.read_bytes().count(b"\x00")
        print(f"  - {rel} ({nul} NUL byte(s))", file=sys.stderr)
    if len(bad) > 30:
        print(f"  ... and {len(bad) - 30} more", file=sys.stderr)
    print(
        "Fix: cd apps/backend && python scripts/sanitize_py_sources.py",
        file=sys.stderr,
    )
    return 1


def run_fix(roots: list[Path]) -> int:
    """就地修复污染文件。"""
    fixed: list[Path] = []
    for path in _iter_py_files(roots):
        if sanitize_file(path):
            fixed.append(path)

    scanned = len(_iter_py_files(roots))
    if fixed:
        print(f"Fixed {len(fixed)}/{scanned} Python file(s):")
        for path in fixed[:20]:
            print(f"  - {path.relative_to(_BACKEND_ROOT)}")
        if len(fixed) > 20:
            print(f"  ... and {len(fixed) - 20} more")
    else:
        print(f"OK: {scanned} Python files, nothing to fix")
    return 0


def _count_scanned(roots: list[Path]) -> int:
    return len(_iter_py_files(roots))


def _resolve_roots(names: list[str]) -> list[Path]:
    return [_BACKEND_ROOT / name for name in names]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检测，发现 NUL/UTF-16 污染时 exit 1",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        default=list(_DEFAULT_ROOTS),
        help=f"相对 apps/backend 的扫描目录（默认: {', '.join(_DEFAULT_ROOTS)}）",
    )
    args = parser.parse_args(argv)
    roots = _resolve_roots(args.roots)
    return run_check(roots) if args.check else run_fix(roots)


if __name__ == "__main__":
    raise SystemExit(main())
