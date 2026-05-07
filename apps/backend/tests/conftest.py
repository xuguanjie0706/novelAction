"""pytest 全局钩子：强制后端测试统一在 Python 3.12.7 运行。"""

from __future__ import annotations

import sys

import pytest


REQUIRED_PYTHON_VERSION = (3, 12, 7)


def pytest_sessionstart(session: pytest.Session) -> None:
    """在测试会话启动时校验解释器版本，阻止 3.9 等环境误测。"""
    if sys.version_info[:3] == REQUIRED_PYTHON_VERSION:
        return

    current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    required = ".".join(str(part) for part in REQUIRED_PYTHON_VERSION)
    raise pytest.UsageError(
        "后端测试必须使用 Python "
        f"{required}，当前为 {current}。\n"
        "请执行: BOOTSTRAP_RECREATE_VENV=1 bash bootstrap.sh\n"
        "并使用: apps/backend/.venv/bin/python -m pytest"
    )
