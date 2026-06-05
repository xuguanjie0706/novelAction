"""
context_assembler.py — 分层检索上下文装配器

设计动机：替代旧版 _build_draft_context 的「全量拍平注入」模式。
按 OutlineNode 上的结构化索引（involved_character_ids / storyline_ids /
key_skill_ids / key_item_ids）做过滤，分三层注入：
  Tier 1 硬约束（~8K token，必须全量）
  Tier 2 本章关联（~15K token，按索引过滤）
  Tier 3 语义检索（~10K token，按需召回）

三条写作路径分别调用不同粒度的 assemble 方法：
  assemble_full          → A/B 路径（draft-assist / gated-draft）
  assemble_for_scene_plan → C1（scene-plan-save）
  assemble_for_scene_draft → C2（scene-draft/stream）

返回值说明：
  assemble_full 返回 dict，键与 draft_assist_stream 参数一一对应，
  可直接 **ctx 解包调用。这保证了对下游接口的零改动兼容。
"""
from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    Chapter,
    Character,
    ChapterIndex,
    Foreshadow,
    OutlineNode,
    Project,
    QualityDebt,
    Scene,
    StoryLine,
    WorldSetting,
)
from app.routers.ai.text_utils import plain_text, strip_tail_meta_lines, truncate
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block
from app.utils.chapter_numbering import display_chapter_number
from app.services.ai.context_queries import (
    format_character_block,
    query_due_foreshadows_block,
    query_due_promises_block,
    query_filtered_characters,
    query_mystery_constraints_block,
    query_narrative_arc_block,
    query_related_factions_block,
    query_relationships_block,
    query_relevant_settings_block,
)
from app.services.ai.context_assembler_helpers import (
    build_volume_progress,
)
from app.services.ai.draft_ctx_bridge import resolve_draft_bridge_context
from app.services.ai.storyline_weave_engine import query_storyline_weave_context_block

logger = logging.getLogger(__name__)


# ── A/B 路径：完整装配（替代旧 _build_draft_context） ──

async def assemble_full(
    db: Session,
    project_id: str,
    chapter: Chapter,
    project: Project,
) -> dict:
    """
    组装起笔/续写所需的全部上下文字段，返回 dict。

    与旧版 _build_draft_context 接口完全兼容（返回相同的 key 集合），
    但内部改为按 OutlineNode 索引做分层检索，大幅减少 token 消耗。

    被 draft-assist/stream 与 gated-draft-stream 共享调用。

    Returns:
        包含所有 draft_assist_stream kwargs 所需字段的字典
    """
    # ── 加载 OutlineNode ──
    outline_node: OutlineNode | None = None
    if chapter.outline_node_id:
        outline_node = db.query(OutlineNode).filter(
            OutlineNode.id == chapter.outline_node_id
        ).first()

    # ── 从 OutlineNode 提取本章实体索引 ──
    char_ids = _extract_ids(outline_node, "involved_character_ids")
    storyline_ids = _extract_ids(outline_node, "storyline_ids")

    # ── Tier 1：硬约束（必须全量注入） ──

    # 立项定位
    positioning_value = _resolve_positioning(project)

    # 卷阶段
    phase_value = _resolve_phase(db, outline_node)
    phase_lower = (phase_value or "").strip().lower()
    is_opening = phase_lower in ("opening", "开局期", "新手村")

    # 卷索引（用于 emotion_arc / villain_arc / core_mysteries）
    volume_index = _resolve_volume_index(db, outline_node)
    ch_no = chapter.sort_order or 0

    # 上章结尾
    prev_chapter = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.sort_order < chapter.sort_order,
    ).order_by(Chapter.sort_order.desc()).first()
    prev_tail = _build_prev_tail(prev_chapter)

    # 章节已有内容
    existing_content = plain_text(chapter.content)
    narr_existing, _ = split_plain_manuscript_and_index_block(existing_content)
    if narr_existing.strip():
        existing_content = narr_existing.strip()

    # ── Tier 2：本章关联（按索引过滤） ──

    # 人物：只查出场人物（含 appearance/clothing/trauma）
    characters = query_filtered_characters(db, project_id, char_ids)
    char_summary = "\n".join(format_character_block(c) for c in characters)
    chapter_manifest_names = _build_manifest_names(
        db, project_id, characters, char_ids, outline_node, chapter
    )

    # 人物关系（新增）
    relationships_block = query_relationships_block(db, project_id, char_ids)
    if relationships_block:
        char_summary = char_summary + "\n\n" + relationships_block

    # 势力（按出场人物关联，含层级/领地）
    factions_block = query_related_factions_block(db, project_id, characters)

    storyline_summary = query_storyline_weave_context_block(
        db, project_id, storyline_ids, ch_no,
        outline_node_id=str(outline_node.id) if outline_node else None,
    )

    # 世界观设定（按章纲关键词过滤，非全量）
    query_kw = " ".join(filter(None, [
        outline_node.summary if outline_node else None,
        outline_node.hook if outline_node else None,
        chapter.title or "",
    ]))
    world_summary = query_relevant_settings_block(db, project_id, query_kw, max_count=4)

    # 读者承诺（窗口内到期）
    from app.routers.ai.draft_context import _build_reader_promise_context
    reader_promise_context = _build_reader_promise_context(db, project_id, ch_no)

    # 核心谜题约束（新增）
    mystery_block = query_mystery_constraints_block(project, volume_index)

    # 情绪弧 + 反派弧（按本卷，非全量）
    narrative_arc_block = query_narrative_arc_block(project, volume_index)

    # 力量体系
    from app.routers.ai.draft_context import build_power_systems_draft_block
    power_systems_context = build_power_systems_draft_block(db, project_id)

    # ── Tier 3：检索层（记忆/章节索引/连续性账本） ──

    # 语义记忆（缩减 top_k：从 74 降到 30）
    from app.services.rag_retrieval_service import retrieve_and_log_draft_context
    _mem_query = " ".join(filter(None, [
        outline_node.summary if outline_node else None,
        outline_node.conflict if outline_node else None,
        outline_node.highlight if outline_node else None,
    ])) or chapter.title or ""

    _merged, memory_summary, _rag_log, rag_retrieval_snapshot = await retrieve_and_log_draft_context(
        db,
        project_id=project_id,
        chapter_id=chapter.id,
        query=_mem_query,
        top_k_semantic=30,
        max_chapter=chapter.sort_order,
        recency_limit=6,
        large_context=True,
        commit=False,
    )

    # 连续性账本（保留，但已通过 Tier 2 减少其他区块的冗余）
    from app.services.ai.context_builder import (
        build_continuity_context,
        build_chapter_index_context,
        build_writing_brief_context,
        build_plot_dossier_context,
    )
    continuity_context = build_continuity_context(
        db=db, project_id=project_id, chapter=chapter, outline_node=outline_node,
    )
    draft_bridge_context = resolve_draft_bridge_context(
        db, project_id, chapter, project, outline_node, prev_chapter, prev_tail,
    )
    chapter_index_context = build_chapter_index_context(
        db=db, project_id=project_id, chapter=chapter,
    )

    # 写作简报（技能/道具/势力投料）
    writing_brief_context = build_writing_brief_context(
        db=db, project_id=project_id, chapter=chapter,
        outline_node=outline_node,
    )

    # 卷内进度感
    _vol_progress = build_volume_progress(db, project_id, outline_node)
    if _vol_progress:
        writing_brief_context = writing_brief_context + _vol_progress

    # 情节档案 + 质检债务（开局期跳过）
    if is_opening:
        plot_dossier_context = ""
        quality_debt_context = ""
    else:
        plot_dossier_context = build_plot_dossier_context(db, project_id, chapter)
        from app.routers.ai.quality_debt import (
            build_quality_debt_context,
            pending_quality_debts_for_chapter,
        )
        quality_debt_context = build_quality_debt_context(
            pending_quality_debts_for_chapter(
                db=db, project_id=project_id, chapter=chapter, limit=12,
            )
        )

    # ── 追加约束块到 writing_brief ──

    # 势力档案
    if factions_block:
        writing_brief_context = writing_brief_context + "\n\n" + factions_block

    # 核心谜题
    if mystery_block:
        writing_brief_context = writing_brief_context + "\n\n" + mystery_block

    # 情绪/反派弧
    if narrative_arc_block:
        writing_brief_context = writing_brief_context + "\n\n" + narrative_arc_block

    # 一致性矛盾
    from app.routers.ai.draft_helpers import (
        _build_consistency_issues_block,
        _calc_hook_requirement,
    )
    project_extra = project.extra if isinstance(project.extra, dict) else {}
    _issues_block = _build_consistency_issues_block(
        project_extra=project_extra,
        manifest_names=chapter_manifest_names,
    )
    if _issues_block:
        continuity_context = continuity_context + _issues_block

    # 第一卷 1–10 章：注入完整开局承诺（与上章/章纲/卷骨架衔接）
    from app.services.ai.opening_contract_context import append_opening_contract_draft_brief

    writing_brief_context = append_opening_contract_draft_brief(
        db, project, chapter, outline_node, volume_index, prev_tail, writing_brief_context,
    )

    from app.services.bootstrap.volume_beats import append_volume_beat_draft_brief

    _vol_for_beats = None
    if outline_node and outline_node.parent_id:
        _vol_for_beats = db.query(OutlineNode).filter(
            OutlineNode.id == outline_node.parent_id,
        ).first()
    writing_brief_context = append_volume_beat_draft_brief(
        _vol_for_beats, outline_node, writing_brief_context,
    )

    # 爽点结算章硬约束
    _face_slap = (positioning_value or {}).get("face_slap_pattern") or ""
    _hook_req = _calc_hook_requirement(
        phase=phase_value or "",
        sort_order=chapter.sort_order or 0,
        face_slap_pattern=_face_slap,
    )
    if _hook_req:
        writing_brief_context = writing_brief_context + _hook_req

    # 复盘闭环指令
    from app.routers.ai.draft_context import (
        _build_prev_directives,
        _build_reader_feedback_context,
        _append_hook_trend_warning,
        _build_scene_blueprint,
    )
    prev_directives_str = _build_prev_directives(outline_node)

    # 上章读者反馈
    _reader_feedback = _build_reader_feedback_context(db, project_id, prev_chapter)
    if _reader_feedback:
        writing_brief_context = writing_brief_context + _reader_feedback

    # hook 趋势预警
    writing_brief_context = _append_hook_trend_warning(
        db, project_id, chapter.sort_order or 0, writing_brief_context
    )

    # Scene 蓝图
    scene_blueprint = _build_scene_blueprint(db, project_id, chapter, outline_node)

    # 戏份预算与强制 POV
    pov_character_name = ""
    character_screen_time = {}
    if outline_node:
        if outline_node.pov_character:
            pov_character_name = outline_node.pov_character.name
        character_screen_time = outline_node.character_screen_time or {}

    story_day_str = (outline_node.extra or {}).get("story_day", "") if outline_node else ""
    word_target_val = _resolve_word_target(outline_node)

    # 境界快照：仅出场人物（番茄线规范到主轴阶梯名，避免筑基等套话进入写章硬约束）
    realm_snapshot_value: dict = {}
    for c in characters[:8]:
        if not c.name or not (c.current_realm or "").strip():
            continue
        realm_snapshot_value[c.name] = (c.current_realm or "").strip()
    from app.services.bootstrap.fanqie_normalize import is_fanqie_project

    if is_fanqie_project(project):
        from app.models import PowerSystem
        from app.routers.outline.helpers.realm_whitelist import build_realm_rank_map
        from app.services.bootstrap.fanqie_realm_policy import (
            normalize_realm_label_for_primary_axis,
        )

        pss = (
            db.query(PowerSystem)
            .filter(PowerSystem.project_id == project_id)
            .order_by(PowerSystem.sort_order)
            .all()
        )
        name_to_rank, _, _ = build_realm_rank_map(pss)
        if name_to_rank:
            sanitized: dict = {}
            for c in characters[:8]:
                if not c.name or not (c.current_realm or "").strip():
                    continue
                canonical, _ = normalize_realm_label_for_primary_axis(
                    c.current_realm or "", name_to_rank,
                )
                sanitized[c.name] = canonical
            realm_snapshot_value = sanitized

    return dict(
        chapter_title=chapter.title or "",
        outline_hook=outline_node.hook or "" if outline_node else "",
        outline_summary=outline_node.summary or "" if outline_node else "",
        outline_conflict=outline_node.conflict or "" if outline_node else "",
        outline_highlight=outline_node.highlight or "" if outline_node else "",
        # 只读章纲原始规划文本（status=planned 的意图层）；
        # 权威台账（status=open）由 continuity_context 的「未回收伏笔」区块承载，两者不再重叠。
        outline_foreshadow=(outline_node.extra or {}).get("foreshadow", "") if outline_node else "",
        outline_power_milestone=outline_node.power_milestone or "" if outline_node else "",
        outline_emotional_tone=outline_node.emotional_tone or "" if outline_node else "",
        story_day=story_day_str,
        chapter_manifest=chapter_manifest_names,
        prev_chapter_tail=prev_tail,
        world_summary=world_summary,
        character_summary=char_summary,
        storyline_summary=storyline_summary,
        memory_summary=memory_summary,
        existing_content=existing_content,
        premise=project.premise or "",
        continuity_context=continuity_context,
        chapter_index_context=chapter_index_context,
        quality_debt_context=quality_debt_context,
        writing_brief_context=writing_brief_context,
        plot_dossier_context=plot_dossier_context,
        word_target=word_target_val,
        phase=phase_value,
        positioning=positioning_value,
        genre=project.genre or "",
        pov_character_name=pov_character_name,
        character_screen_time=character_screen_time,
        scene_blueprint=scene_blueprint,
        reader_promise_context=reader_promise_context,
        prev_directives=prev_directives_str,
        realm_snapshot=realm_snapshot_value,
        power_systems_context=power_systems_context,
        draft_bridge_context=draft_bridge_context,
        rag_retrieval_log_id=str(_rag_log.id),
        rag_retrieval_snapshot=rag_retrieval_snapshot,
    )


# ── C2 路径：场景起草上下文（补强「裸写」问题） ──

def assemble_for_scene_draft(
    db: Session, project_id: str, scene: Scene, project: Project,
) -> dict:
    """为逐场起草补入完整人物档案/关系/势力/谜题（解决旧版「裸写」问题）。"""
    # 在场人物完整档案
    on_stage_ids = [str(cid) for cid in (scene.characters_on_stage or [])]
    if scene.pov_character_id and str(scene.pov_character_id) not in on_stage_ids:
        on_stage_ids.insert(0, str(scene.pov_character_id))

    characters = query_filtered_characters(db, project_id, on_stage_ids)
    character_context = "\n".join(format_character_block(c) for c in characters)

    # 人物关系
    relationships = query_relationships_block(db, project_id, on_stage_ids)
    if relationships:
        character_context = character_context + "\n\n" + relationships

    # 势力
    factions = query_related_factions_block(db, project_id, characters)

    # 卷索引和项目级约束
    outline_node = None
    if scene.outline_node_id:
        outline_node = db.query(OutlineNode).filter(
            OutlineNode.id == scene.outline_node_id
        ).first()
    volume_index = _resolve_volume_index(db, outline_node)

    # 核心谜题
    mystery = query_mystery_constraints_block(project, volume_index)

    # 情绪/反派弧
    narrative_arc = query_narrative_arc_block(project, volume_index)

    # 拼接为统一 context 字符串
    extra_context_parts = [character_context]
    if factions:
        extra_context_parts.append(factions)
    if mystery:
        extra_context_parts.append(mystery)
    if narrative_arc:
        extra_context_parts.append(narrative_arc)

    return {
        "character_context": "\n\n".join(extra_context_parts),
        "character_names": [c.name for c in characters],
    }


# ── C1 路径：分场规划补充上下文 ──

def assemble_for_scene_plan(
    db: Session, project_id: str, outline_node: OutlineNode, project: Project,
) -> dict:
    """为分场规划追加人物关系/情绪弧/反派弧/核心谜题约束。"""
    char_ids = _extract_ids(outline_node, "involved_character_ids")
    volume_index = _resolve_volume_index(db, outline_node)

    relationships = query_relationships_block(db, project_id, char_ids)
    narrative_arc = query_narrative_arc_block(project, volume_index)
    mystery = query_mystery_constraints_block(project, volume_index)

    extra_parts = []
    if relationships:
        extra_parts.append(relationships)
    if narrative_arc:
        extra_parts.append(narrative_arc)
    if mystery:
        extra_parts.append(mystery)

    return {
        "extra_constraints": "\n\n".join(extra_parts),
    }


# ── 内部辅助函数 ──

def _extract_ids(node: OutlineNode | None, field: str) -> list[str]:
    """从 OutlineNode 安全提取 UUID 列表为字符串列表。"""
    if not node:
        return []
    raw = getattr(node, field, None) or []
    return [str(x) for x in raw if x]


def _resolve_positioning(project: Project) -> dict | None:
    """解析 positioning：优先 extra.positioning，回退 story_core.positioning。"""
    extra = getattr(project, "extra", None) or {}
    if isinstance(extra, dict):
        pos = extra.get("positioning")
        if isinstance(pos, dict) and pos:
            return pos
    core = getattr(project, "story_core", None) or {}
    if isinstance(core, dict):
        pos = core.get("positioning")
        if isinstance(pos, dict) and pos:
            return pos
    return None


def _resolve_phase(db: Session, outline_node: OutlineNode | None) -> str | None:
    """解析卷阶段 phase：优先 node.phase，回退 parent volume.phase。"""
    if outline_node is None:
        return None
    phase = getattr(outline_node, "phase", None)
    if not phase:
        phase = (outline_node.extra or {}).get("phase")
    if not phase and outline_node.parent_id is not None:
        volume = db.query(OutlineNode).filter(
            OutlineNode.id == outline_node.parent_id
        ).first()
        if volume is not None:
            phase = getattr(volume, "phase", None) or (volume.extra or {}).get("phase")
    return phase


def _resolve_volume_index(db: Session, outline_node: OutlineNode | None) -> int:
    """解析当前卷序号（0-based）。"""
    if not outline_node:
        return 0
    # chapter_plan → parent 是 volume
    vol = outline_node
    if outline_node.node_type == "chapter_plan" and outline_node.parent_id:
        vol = db.query(OutlineNode).filter(
            OutlineNode.id == outline_node.parent_id
        ).first() or outline_node
    return vol.sort_order or 0


def _resolve_word_target(outline_node: OutlineNode | None) -> int:
    """从 OutlineNode 解析字数目标。"""
    if not outline_node:
        return 2300
    return int(
        outline_node.expected_words
        or (outline_node.extra or {}).get("word_estimate")
        or 2300
    )


def _build_prev_tail(prev_chapter: Chapter | None) -> str:
    """构建上章结尾文本（最多 3000 字符）。"""
    if not prev_chapter or not prev_chapter.content:
        return ""
    prev_plain = plain_text(prev_chapter.content)
    prev_body, _ = split_plain_manuscript_and_index_block(prev_plain)
    base_prev = prev_body.strip() if prev_body.strip() else prev_plain
    clean = strip_tail_meta_lines(base_prev)
    limit = 3000
    return clean[-limit:] if len(clean) > limit else clean


def _build_manifest_names(
    db: Session, project_id: str, characters: list[Character],
    char_ids: list[str], outline_node: OutlineNode | None, chapter: Chapter,
) -> list[str]:
    """优先 involved_character_ids 角色名；无索引回退核心角色 + 近 5 章出场。"""
    if char_ids:
        return [c.name for c in characters if c.name]

    # 回退逻辑（与旧版一致）
    seen: set[str] = set()
    names: list[str] = []

    all_chars = db.query(Character).filter(
        Character.project_id == project_id
    ).all()
    for c in all_chars:
        if not c.name:
            continue
        is_core = c.role in ("protagonist", "antagonist") or (c.character_tier == "core")
        if is_core and c.name not in seen:
            names.append(c.name)
            seen.add(c.name)

    if chapter.sort_order and chapter.sort_order > 1:
        recent = (
            db.query(ChapterIndex)
            .filter(
                ChapterIndex.project_id == project_id,
                ChapterIndex.chapter_number < chapter.sort_order,
                ChapterIndex.chapter_number >= max(1, chapter.sort_order - 5),
            )
            .order_by(ChapterIndex.chapter_number.desc())
            .all()
        )
        for ci in recent:
            for fa in (ci.first_appearances or [])[:8]:
                name = (fa.get("name") if isinstance(fa, dict) else "") or ""
                name = name.strip()
                if name and name not in seen:
                    names.append(name)
                    seen.add(name)
                if len(names) >= 12:
                    break

    return names[:12]
