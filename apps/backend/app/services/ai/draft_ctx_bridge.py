"""
写章跨章桥接块装配（从 context_assembler 拆出，遵守 600 行红线）。

``assemble_full`` 仅调用 ``resolve_draft_bridge_context``；实际内容由
``draft_continuity_bridge`` 聚合（锁定节拍 / 语风 / 认知边界 / 风格守门）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Chapter, OutlineNode, Project


def resolve_draft_bridge_context(
    db: Session,
    project_id: str,
    chapter: Chapter,
    project: Project,
    outline_node: OutlineNode | None,
    prev_chapter: Chapter | None,
    prev_tail: str,
) -> str:
    """组装 ``draft_bridge_context`` 纯文本块，供 ``draft_stream`` 注入 prompt。"""
    from app.services.ai.draft_continuity_bridge import build_draft_continuity_bridge_block

    return build_draft_continuity_bridge_block(
        db=db,
        project_id=project_id,
        chapter=chapter,
        project=project,
        outline_node=outline_node,
        prev_chapter=prev_chapter,
        prev_tail=prev_tail,
    )
