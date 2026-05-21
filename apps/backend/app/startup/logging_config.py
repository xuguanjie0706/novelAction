"""应用日志：保证 ``app.*`` 写入 stderr（restart.sh 重定向到 .local/logs/backend.log）。"""

from __future__ import annotations

import logging
import sys


def ensure_app_logging() -> None:
    """为 ``app`` 命名空间挂 StreamHandler，避免仅有 uvicorn 访问日志、业务日志不可见。"""
    app_log = logging.getLogger("app")
    if app_log.level == logging.NOTSET or app_log.level > logging.INFO:
        app_log.setLevel(logging.INFO)
    if app_log.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s: %(message)s"),
    )
    app_log.addHandler(handler)
