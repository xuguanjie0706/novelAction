"""
context_builder.py — 章节写作上下文构建服务（聚合壳）

拆分说明：
  context_builder_continuity.py → build_continuity_context / build_chapter_index_context / fmt_index_item
  context_builder_brief.py      → build_writing_brief_context / build_plot_dossier_context /
                                   format_world_setting_context / read_setting_section /
                                   string_ids / json_ref_ids
  context_builder_chat.py       → format_outline_chat_context / format_writing_chat_context /
                                   format_outline_chat_node / format_outline_chat_foreshadows /
                                   append_reference_chapters_to_writing_context

本文件仅做全量重导出，保持调用方 `from app.services.ai.context_builder import ...` 不变。
"""

from app.services.ai.context_builder_brief import (  # noqa: F401
    build_plot_dossier_context,
    build_writing_brief_context,
    format_world_setting_context,
    json_ref_ids,
    read_setting_section,
    string_ids,
)
from app.services.ai.context_builder_chat import (  # noqa: F401
    append_reference_chapters_to_writing_context,
    format_outline_chat_context,
    format_outline_chat_foreshadows,
    format_outline_chat_node,
    format_writing_chat_context,
)
from app.services.ai.context_builder_continuity import (  # noqa: F401
    build_chapter_index_context,
    build_continuity_context,
    fmt_index_item,
)
