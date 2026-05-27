"""写前故事线织网预警（整章路径 SSE：storyline_pre_warn）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.ai.chapter_ingredients import THRESHOLDS
from app.services.ai.storyline_weave_engine import compute_directive


def compute_storyline_pre_warn_events(
    db: Session,
    project_id: str,
    chapter_number: int,
    *,
    outline_node_id: str | None = None,
    ack_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    基于 weave_engine + 断档逻辑生成本章故事线预警事件列表。

    Returns:
        若干 ``{"event": "storyline_pre_warn", ...}`` 载荷（可被前端逐条 ack）。
    """
    from app.models import OutlineNode, StoryLine

    ack_set = {str(x) for x in (ack_ids or [])}
    events: list[dict[str, Any]] = []
    ch_no = chapter_number or 1

    directive = compute_directive(
        db,
        project_id,
        ch_no,
        outline_node_id=outline_node_id,
    )

    threshold = THRESHOLDS["STORYLINE_GAP"]
    node = None
    if outline_node_id:
        node = db.query(OutlineNode).filter(
            OutlineNode.id == outline_node_id,
            OutlineNode.project_id == project_id,
        ).first()

    all_nodes = db.query(
        OutlineNode.sort_order,
        OutlineNode.storyline_ids,
    ).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
        OutlineNode.sort_order < ch_no,
    ).all()

    lines = db.query(StoryLine).filter(StoryLine.project_id == project_id).all()

    for sl in lines:
        sid = str(sl.id)
        if sid in ack_set:
            continue
        last_ch = 0
        for n in all_nodes:
            sids = [str(x) for x in (n.storyline_ids or [])]
            if sid in sids and (n.sort_order or 0) > last_ch:
                last_ch = n.sort_order or 0
        gap = ch_no - last_ch if last_ch > 0 else 0
        if last_ch > 0 and gap > threshold:
            warn_id = f"gap:{sid}"
            if warn_id in ack_set:
                continue
            events.append({
                "event": "storyline_pre_warn",
                "warn_id": warn_id,
                "severity": "warning",
                "storyline_id": sid,
                "storyline_name": sl.name,
                "title": f"「{sl.name}」已 {gap} 章未推进",
                "detail": f"断档阈值 {threshold} 章，本章建议写入该线节拍。",
                "suggested_action": "在正文或章纲中推进该故事线",
            })

    if directive.crossover_instruction:
        warn_id = "crossover:chapter"
        if warn_id not in ack_set:
            events.append({
                "event": "storyline_pre_warn",
                "warn_id": warn_id,
                "severity": "info",
                "title": "本章为故事线交叉点",
                "detail": directive.crossover_instruction,
                "suggested_action": "交叉须同时改变两条线的轨迹",
            })

    for pb in directive.planned_beats:
        if pb.must_advance and pb.storyline_id not in ack_set:
            warn_id = f"beat:{pb.storyline_id}"
            if warn_id in ack_set:
                continue
            events.append({
                "event": "storyline_pre_warn",
                "warn_id": warn_id,
                "severity": "warning",
                "storyline_id": pb.storyline_id,
                "storyline_name": pb.name,
                "title": f"计划节拍：{pb.name}",
                "detail": pb.beat or "（见卷级导演单）",
                "suggested_action": "本章须落实该节拍或等价戏剧动作",
            })

    for dc in directive.drift_corrections:
        warn_id = f"drift:{hash(dc) & 0xFFFF}"
        if warn_id in ack_set:
            continue
        events.append({
            "event": "storyline_pre_warn",
            "warn_id": warn_id,
            "severity": "critical",
            "title": "故事线漂移补偿",
            "detail": dc,
            "suggested_action": "优先回归原计划节拍",
        })

    return events
