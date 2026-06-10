"""dabai 模式判定 — Bootstrap mode=dabai 与写作期分支共用。"""
from __future__ import annotations

from app.models import Project


def is_dabai_project(project: Project | None) -> bool:
    """是否为大白文·修仙 Bootstrap 产物。"""
    if not project:
        return False
    extra = project.extra or {}
    if extra.get("bootstrap_mode") == "dabai":
        return True
    pos = extra.get("positioning") or {}
    return pos.get("bootstrap_mode") == "dabai"
