"""Bootstrap ctx 与 DB 落库数据合并（resume / 步骤重试时补全缺失键）。"""

from __future__ import annotations

from typing import Any


def merge_ctx_with_project(db, project: Any, ctx: dict | None) -> dict:
    """以 ``build_full_ctx`` 为底，再叠 checkpoint 中的 ctx（保留运行中增量）。

    避免进程重启或 checkpoint 丢失后 ``project_title`` / ``settings_summary`` 等键缺失。
    """
    from app.services.bootstrap.step_regen import build_full_ctx

    base = build_full_ctx(db, project)
    overlay = dict(ctx or {})
    merged = {**base, **overlay}
    for key in (
        "project_title",
        "genre",
        "settings_summary",
        "power_summary",
        "storyline_summary",
        "volumes_summary",
        "protagonist",
    ):
        if not merged.get(key) and base.get(key):
            merged[key] = base[key]
    return merged
