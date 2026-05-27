"""
storyline_weave_engine — 故事线织网统一计算入口（双路径注入层，v1.1）。

基于 StoryLine.extra 中的 volume_beats / crossover_nodes 计算本章执行指令；
无织网数据时回退到 key_beats + 断档逻辑（与 chapter_ingredients 兼容）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services.ai.ingredient_types import StorylineMove

@dataclass
class PlannedBeat:
    storyline_id: str
    name: str
    beat: str
    tension: int = 0
    vol_index: int = 0
    must_advance: bool = False
    gap_chapters: int = 0


@dataclass
class GapWarning:
    storyline_id: str
    name: str
    gap_chapters: int
    message: str


@dataclass
class WeaveDirective:
    """本章故事线执行指令（整章 / 分场共用）。"""

    planned_beats: list[PlannedBeat] = field(default_factory=list)
    crossover_instruction: str | None = None
    word_budget: dict[str, int] = field(default_factory=dict)
    drift_corrections: list[str] = field(default_factory=list)
    gap_warnings: list[GapWarning] = field(default_factory=list)
    tension_target: dict[str, int] = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        """整章路径：格式化为可拼入 storyline_summary 的约束文本块。"""
        lines: list[str] = ["【故事线织网约束】"]
        for pb in self.planned_beats:
            tag = "[MUST]" if pb.must_advance else "[计划]"
            lines.append(
                f"{tag} {pb.name}：{pb.beat or '（无计划节拍）'}"
                + (f"（张力目标 {pb.tension}）" if pb.tension else "")
                + (f"（已断档 {pb.gap_chapters} 章）" if pb.gap_chapters else ""),
            )
        if self.crossover_instruction:
            lines.append(f"★ 交叉点：{self.crossover_instruction}")
        for w in self.gap_warnings:
            lines.append(f"⚠ {w.message}")
        for dc in self.drift_corrections:
            lines.append(f"↩ {dc}")
        if self.word_budget:
            parts = [f"{k}~{v}字" for k, v in self.word_budget.items()]
            lines.append("篇幅建议：" + " / ".join(parts))
        return "\n".join(lines)

    def to_structured(self) -> dict[str, Any]:
        """分场路径：结构化数据供 Scene 分配。"""
        return {
            "planned_beats": [
                {
                    "storyline_id": b.storyline_id,
                    "name": b.name,
                    "beat": b.beat,
                    "tension": b.tension,
                    "must_advance": b.must_advance,
                    "gap_chapters": b.gap_chapters,
                }
                for b in self.planned_beats
            ],
            "crossover_instruction": self.crossover_instruction,
            "word_budget": self.word_budget,
            "drift_corrections": self.drift_corrections,
            "gap_warnings": [
                {"storyline_id": g.storyline_id, "name": g.name, "gap_chapters": g.gap_chapters}
                for g in self.gap_warnings
            ],
            "tension_target": self.tension_target,
        }


def _chapter_global_index(node, chapter_number: int) -> int:
    return chapter_number or (node.sort_order or 0) or 1


def _vol_index_for_chapter(db: Session, project_id: str, chapter_number: int) -> int:
    """根据已落库 volume 的 planned_chapters 累计推算卷索引。"""
    from app.models import OutlineNode

    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order.asc())
        .all()
    )
    if not volumes:
        return 0
    acc = 0
    for i, vol in enumerate(volumes):
        extra = vol.extra if isinstance(vol.extra, dict) else {}
        planned = int(extra.get("planned_chapters") or 60)
        acc += planned
        if chapter_number <= acc:
            return i
    return max(0, len(volumes) - 1)


def _relative_chapter_in_vol(chapter_number: int, vol_index: int, db: Session, project_id: str) -> int:
    from app.models import OutlineNode

    offset = 0
    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order.asc())
        .all()
    )
    for i, vol in enumerate(volumes):
        if i >= vol_index:
            break
        extra = vol.extra if isinstance(vol.extra, dict) else {}
        offset += int(extra.get("planned_chapters") or 60)
    return max(1, chapter_number - offset)


def compute_directive(
    db: Session,
    project_id: str,
    chapter_number: int,
    *,
    outline_node_id: str | None = None,
    chapter_word_target: int = 2500,
) -> WeaveDirective:
    """
    计算本章故事线织网指令。

    Args:
        db: SQLAlchemy Session
        project_id: 项目 UUID
        chapter_number: 全书章节序号
        outline_node_id: 可选章纲节点 ID（用于 storyline_ids 过滤）
        chapter_word_target: 本章目标字数（用于 word_budget 分配）
    """
    from app.models import OutlineNode, StoryLine

    directive = WeaveDirective()
    node = None
    if outline_node_id:
        node = db.query(OutlineNode).filter(
            OutlineNode.id == outline_node_id,
            OutlineNode.project_id == project_id,
        ).first()

    ch_num = _chapter_global_index(node, chapter_number)
    vol_index = _vol_index_for_chapter(db, project_id, ch_num)
    rel_ch = _relative_chapter_in_vol(ch_num, vol_index, db, project_id)

    lines = db.query(StoryLine).filter(StoryLine.project_id == project_id).order_by(
        StoryLine.sort_order.asc(),
    ).all()

    storyline_ids = (node.storyline_ids if node else None) or []
    if storyline_ids:
        id_set = {str(x) for x in storyline_ids}
        lines = [sl for sl in lines if str(sl.id) in id_set] or lines

    has_weave = any(
        isinstance(sl.extra, dict) and sl.extra.get("volume_beats")
        for sl in lines
    )

    if not has_weave:
        return directive

    for sl in lines:
        extra = sl.extra if isinstance(sl.extra, dict) else {}
        beats = extra.get("volume_beats") or []
        vol_beat = next(
            (b for b in beats if isinstance(b, dict) and int(b.get("vol_index", -1)) == vol_index),
            None,
        )
        if not vol_beat or not vol_beat.get("is_active", True):
            continue

        beat_text = (vol_beat.get("beat") or "").strip()
        tension = int(vol_beat.get("tension") or 0)
        hint_start = int(vol_beat.get("chapter_hint_start") or 0)
        hint_peak = int(vol_beat.get("chapter_hint_peak") or 0)
        must = False
        gap = 0
        if hint_start and rel_ch >= hint_start:
            must = True
        if hint_peak and abs(rel_ch - hint_peak) <= 2:
            must = True

        weight = float(extra.get("weight") or 0)
        if weight > 0 and chapter_word_target > 0:
            directive.word_budget[sl.name] = max(80, int(chapter_word_target * weight))

        directive.planned_beats.append(PlannedBeat(
            storyline_id=str(sl.id),
            name=sl.name,
            beat=beat_text,
            tension=tension,
            vol_index=vol_index,
            must_advance=must,
            gap_chapters=gap,
        ))
        if tension:
            directive.tension_target[sl.name] = tension

        for cx in extra.get("crossover_nodes") or []:
            if not isinstance(cx, dict):
                continue
            if int(cx.get("at_vol", -1)) == vol_index:
                trigger = cx.get("trigger") or ""
                other = cx.get("with") or ""
                if trigger:
                    directive.crossover_instruction = (
                        f"{sl.name}×{other}：{trigger}"
                    )

    from app.models import Project

    proj = db.query(Project).filter(Project.id == project_id).first()
    if proj and isinstance(proj.extra, dict):
        corrections = proj.extra.get("storyline_drift_corrections") or []
        if isinstance(corrections, list):
            directive.drift_corrections = [str(c) for c in corrections[:5]]

    _apply_gap_chapters(db, project_id, ch_num, lines, directive)
    return directive


def _apply_gap_chapters(
    db: Session,
    project_id: str,
    chapter_number: int,
    lines: list,
    directive: WeaveDirective,
) -> None:
    """将章纲断档章数合并进 planned_beats（与 chapter_ingredients 阈值一致）。"""
    from app.models import OutlineNode
    from app.services.ai.chapter_ingredients import THRESHOLDS

    threshold = THRESHOLDS["STORYLINE_GAP"]
    prev_nodes = db.query(
        OutlineNode.sort_order,
        OutlineNode.storyline_ids,
    ).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
        OutlineNode.sort_order < chapter_number,
    ).all()

    gap_by_id: dict[str, int] = {}
    for sl in lines:
        sid = str(sl.id)
        last_ch = 0
        for n in prev_nodes:
            sids = [str(x) for x in (n.storyline_ids or [])]
            if sid in sids and (n.sort_order or 0) > last_ch:
                last_ch = n.sort_order or 0
        gap = chapter_number - last_ch if last_ch > 0 else 0
        gap_by_id[sid] = gap

    for pb in directive.planned_beats:
        gap = gap_by_id.get(pb.storyline_id, 0)
        pb.gap_chapters = gap
        if gap > threshold:
            pb.must_advance = True

    existing_ids = {pb.storyline_id for pb in directive.planned_beats}
    for sl in lines:
        sid = str(sl.id)
        gap = gap_by_id.get(sid, 0)
        if gap > threshold and sid not in existing_ids:
            directive.gap_warnings.append(GapWarning(
                storyline_id=sid,
                name=sl.name,
                gap_chapters=gap,
                message=f"「{sl.name}」已断档 {gap} 章，本章必须推进",
            ))


def directive_to_storyline_moves(directive: WeaveDirective) -> list[StorylineMove]:
    """将 WeaveDirective 转为 ChapterIngredients 用的 StorylineMove 列表。"""
    moves: list[StorylineMove] = []
    for pb in directive.planned_beats:
        moves.append(StorylineMove(
            storyline_id=pb.storyline_id,
            name=pb.name,
            line_type="main",
            current_state="",
            gap_chapters=pb.gap_chapters,
            must_advance=pb.must_advance,
            suggested_beat=pb.beat,
        ))
    for gw in directive.gap_warnings:
        if any(m.storyline_id == gw.storyline_id for m in moves):
            continue
        moves.append(StorylineMove(
            storyline_id=gw.storyline_id,
            name=gw.name,
            line_type="sub",
            current_state="",
            gap_chapters=gw.gap_chapters,
            must_advance=True,
            suggested_beat="",
        ))
    moves.sort(key=lambda x: (not x.must_advance, -x.gap_chapters))
    return moves[:5]


def query_storyline_weave_context_block(
    db: Session,
    project_id: str,
    storyline_ids: list[str],
    chapter_number: int,
    *,
    outline_node_id: str | None = None,
) -> str:
    """
    整章路径 Tier2：织网约束块 + 旧版摘要（无织网时仅摘要）。

    替代直接调用 ``query_filtered_storylines_block`` 的织网场景。
    """
    from app.services.ai.context_queries import query_filtered_storylines_block

    legacy = query_filtered_storylines_block(db, project_id, storyline_ids)
    directive = compute_directive(
        db,
        project_id,
        chapter_number,
        outline_node_id=outline_node_id,
    )
    if not (
        directive.planned_beats
        or directive.crossover_instruction
        or directive.gap_warnings
        or directive.drift_corrections
        or directive.word_budget
    ):
        return legacy

    block = directive.to_prompt_block()
    if legacy:
        return f"{legacy}\n\n{block}"
    return block
