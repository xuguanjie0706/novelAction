"""写作风格档位（writing_style）读取工具。

设计动机：plain（白话直白/番茄纯爽文）/ standard / dense 三档贯穿正文写作、质检、
复盘多条链路。各处都直接 `project.extra` 现读极易写法不一（有的只读顶层、有的只读
positioning）。本模块统一收口，保证「番茄书全链路都认得自己是 plain」。

写入侧约定见 bootstrap/steps/project.py：顶层 `extra.writing_style` 与
`extra.positioning.writing_style` 同时落库；本工具两处都兜底读取。
"""
from __future__ import annotations

from typing import Any, Optional

_VALID = ("plain", "standard", "dense")


def normalize_writing_style(value: Any) -> str:
    """把任意输入规整为合法档位；非法/空值回落 ``standard``。"""
    v = str(value or "").strip().lower()
    return v if v in _VALID else "standard"


def writing_style_from_extra(extra: Optional[dict]) -> str:
    """从 Project.extra（dict）解析 writing_style。

    优先读顶层 ``writing_style``，回退 ``positioning.writing_style``，再回退 standard。
    """
    pe = extra if isinstance(extra, dict) else {}
    raw = pe.get("writing_style")
    if not raw:
        pos = pe.get("positioning")
        if isinstance(pos, dict):
            raw = pos.get("writing_style")
    return normalize_writing_style(raw)


def resolve_project_writing_style(project: Any) -> str:
    """从 Project 模型实例解析 writing_style；project 为空时返回 standard。"""
    if project is None:
        return "standard"
    return writing_style_from_extra(getattr(project, "extra", None))
