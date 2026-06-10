"""context_assembler 辅助函数（拆出以控制主文件 ≤600 行）。"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import OutlineNode

logger = logging.getLogger(__name__)


def inject_vol_world_map(volume_node: OutlineNode | None, context: str) -> str:
    """将卷舞台地图块追加到写章上下文。

    dabai Bootstrap 在 OutlineNode.extra.world_map 写入地图数据；
    其他模式该字段不存在，安全返回原 context 不变。

    Args:
        volume_node: 卷级 OutlineNode（chapter_plan 的 parent），允许 None。
        context:     当前 writing_brief_context 字符串。

    Returns:
        追加地图块后的上下文字符串。
    """
    if volume_node is None:
        return context
    try:
        from app.services.bootstrap.context_vol_expand import _build_vol_world_map_block
        blk = _build_vol_world_map_block(volume_node)
        if blk:
            return context + "\n" + blk
    except Exception:
        logger.warning("inject_vol_world_map 失败（不影响写章）", exc_info=True)
    return context


def fmt_outline_foreshadows(node: OutlineNode | None) -> str:
    """章纲伏笔埋设/回收摘要，供 draft 上下文字段使用。"""
    if not node:
        return ""

    def _desc(items):
        return "；".join(
            d for f in (items or [])[:3]
            if (d := (f.get("description", "") if isinstance(f, dict) else str(f)))
        )

    laid_s, res_s = _desc(node.foreshadows_laid), _desc(node.foreshadows_resolved)
    parts: list[str] = []
    if laid_s:
        parts.append(f"埋[{laid_s}]")
    if res_s:
        parts.append(f"收[{res_s}]")
    return "  ".join(parts) or (node.extra or {}).get("foreshadow", "")


def build_volume_progress(
    db: Session,
    project_id: str,
    outline_node: OutlineNode | None,
) -> str:
    """构建卷内章节进度提示。"""
    if not outline_node or not outline_node.parent_id:
        return ""
    try:
        count = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.project_id == project_id,
                OutlineNode.parent_id == outline_node.parent_id,
                OutlineNode.node_type == "chapter_plan",
            )
            .count()
        )
        if count > 0:
            idx = (outline_node.sort_order or 0) + 1
            denom = max(count, idx)
            return (
                f"\n【卷内章节进度】本卷第 {idx}/{denom} 章"
                f"（{round(idx / denom * 100)}%）"
                f" — 节奏应与当前位置匹配，勿过早/过晚高潮"
            )
    except Exception:
        pass
    return ""
