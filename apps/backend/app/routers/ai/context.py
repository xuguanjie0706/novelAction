"""
context.py — 兼容 re-export（已退役）

原有逻辑已迁移至 `app.services.ai.context_builder`。
保留此文件使现有 `from app.routers.ai.context import ...` 不破坏。

新代码应直接从 `app.services.ai.context_builder` 导入。
"""
from app.services.ai.context_builder import (  # noqa: F401
    read_setting_section,
    format_world_setting_context,
    build_continuity_context,
    fmt_index_item,
    string_ids,
    json_ref_ids,
    build_writing_brief_context,
    build_chapter_index_context,
    build_plot_dossier_context,
    format_outline_chat_foreshadows,
    format_outline_chat_node,
    format_outline_chat_context,
    format_writing_chat_context,
    append_reference_chapters_to_writing_context,
)
