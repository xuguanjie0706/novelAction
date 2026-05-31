"""按卷懒展开章纲专用上下文构建器（主入口）。

与 context.hydrate_ctx_from_project 的差异
-----------------------------------------
hydrate_ctx_from_project 仅做「数据库 → 基础字段」映射，用于补生成设定卡等
轻量场景。此模块面向「生成第 N 卷章级大纲」，需要总编辑级别的全域上下文：

  Tier 1  不变量        立项定位 / 境界体系 / 世界观 / 流派指导      → context_vol_tier12.py
  Tier 2  卡司状态      人物心理档案 / 关系张力台账 / 当前弧度进展    → context_vol_tier12.py
  Tier 3  故事现状      故事线进度 / 伏笔台账 / 读者承诺欠账          → context_vol_tier345.py
  Tier 4  时序锚点      全卷骨架 / 前卷末状态 / 反派独立时间线        → context_vol_tier345.py
  Tier 5  节奏统计      已写字数/章数 / 打脸密度统计 / 情感线出现频率 → context_vol_tier345.py
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models import OutlineNode, Project
from app.services.bootstrap.context_vol_tier12 import (
    _build_cast_ctx,
    _build_positioning_block,
    _build_power_block,
    _build_relations_block,
    _build_world_settings_block,
)
from app.services.bootstrap.context_vol_tier345 import (
    _build_foreshadow_block,
    _build_pacing_stats,
    _build_reader_promises_block,
    _build_storylines_ctx,
    _build_villain_block,
    _build_volumes_skeleton,
)


def build_vol_expand_ctx(
    db: Session,
    project: Project,
    volume_node: OutlineNode,
) -> tuple[dict, str]:
    """为按卷懒展开构建总编辑级上下文。

    Args:
        db:          数据库会话。
        project:     当前项目。
        volume_node: 目标卷 OutlineNode（node_type 必须为 "volume"）。

    Returns:
        (ctx_dict, editorial_prompt_block)
        - ctx_dict：传给 gen_vol_chapter_plans 的 ctx，含所有 bootstrap 级字段。
        - editorial_prompt_block：直接插入 prompt 的富上下文字符串。
    """
    project_id = str(project.id)
    ctx: dict = {
        "logline": project.logline or "",
        "premise": project.premise or "",
        "target_words": int(project.target_words or 1_200_000),
        "project_title": project.title or "未命名",
        "genre": project.genre or "玄幻",
        "world_overview": project.world_overview or "",
        "story_core": project.story_core if isinstance(project.story_core, dict) else {},
    }

    # ── 流派工具包 ─────────────────────────────────────────────────────────────
    try:
        from app.services.genre_kit import get_genre_kit, normalize_genre, render_kit_for_prompt
        kit = get_genre_kit(normalize_genre(ctx["genre"]))
        ctx["genre_kit"] = kit
        ctx["genre_kit_prompt"] = render_kit_for_prompt(kit)
    except Exception:
        ctx["genre_kit"] = {}
        ctx["genre_kit_prompt"] = ""

    # ── Tier 1 ─────────────────────────────────────────────────────────────────
    positioning, positioning_block = _build_positioning_block(project)
    ctx["positioning"] = positioning

    opening_contract = (project.extra or {}).get("opening_contract", {})
    ctx["opening_contract"] = opening_contract
    ctx["settings_summary"] = ""

    power_block = _build_power_block(db, project_id, ctx)
    world_block = _build_world_settings_block(db, project_id)

    # ── Tier 2 ─────────────────────────────────────────────────────────────────
    cast_block = _build_cast_ctx(db, project_id, ctx)
    relation_triggers_str, relations_block = _build_relations_block(db, project_id)
    ctx["relation_triggers"] = relation_triggers_str

    # ── Tier 3 ─────────────────────────────────────────────────────────────────
    storylines_block = _build_storylines_ctx(db, project_id, ctx)
    foreshadow_block = _build_foreshadow_block(db, project_id)
    promises_block = _build_reader_promises_block(db, project_id)

    # ── Tier 4 ─────────────────────────────────────────────────────────────────
    villain_timelines_str, volumes_block, prev_vol_ending_block = _build_volumes_skeleton(
        db, project_id, volume_node
    )
    ctx["villain_timelines"] = [villain_timelines_str] if villain_timelines_str else []
    villain_block = _build_villain_block(db, project_id, ctx)

    # ── Tier 5 ─────────────────────────────────────────────────────────────────
    pacing_block = _build_pacing_stats(db, project_id, volume_node)

    # ── 新步骤产物块（Step 9.5/9.8/11.5）───────────────────────────────────────
    from app.services.bootstrap.context_new_steps import build_new_steps_blocks
    emotion_arc_block, villain_arc_block, core_mysteries_block = build_new_steps_blocks(
        project, volume_node, ctx
    )

    # ── 历史高频问题回灌（支柱一：源头减少问题）─────────────────────────────────
    # A/B 开关：project.extra.enable_issue_feedback（默认开）；失败不阻断生成。
    enable_feedback = bool((project.extra or {}).get("enable_issue_feedback", True))
    ctx["enable_issue_feedback"] = enable_feedback
    issue_feedback_block = ""
    if enable_feedback:
        try:
            from app.services.outline_quality.feedback_block import build_issue_feedback_block
            from app.services.outline_quality.issue_log import top_frequent_issues
            top_issues = top_frequent_issues(
                db, project_id, limit=8, min_severity="high",
                exclude_volume_node_id=volume_node.id,
            )
            issue_feedback_block = build_issue_feedback_block(top_issues)
        except Exception:
            logger.warning("issue_feedback 回灌失败（不阻断生成）", exc_info=True)
            issue_feedback_block = ""

    # ── 番茄增强上下文（pace_type == "fast" 时注入）───────────────────────────
    fanqie_block = ""
    if positioning.get("pace_type") == "fast":
        from app.services.bootstrap.context_vol_fanqie import build_fanqie_enhance_block
        fanqie_block = build_fanqie_enhance_block(project, volume_node, ctx)

    # ── 组合 editorial_prompt_block ────────────────────────────────────────────
    genre_kit_block = (ctx.get("genre_kit_prompt") or "").strip()
    if genre_kit_block and not genre_kit_block.startswith("\n"):
        genre_kit_block = "\n" + genre_kit_block

    editorial_blocks = [
        b for b in [
            positioning_block, genre_kit_block, power_block, world_block,
            fanqie_block,  # 番茄增强（落差/金手指/打脸/节奏图）
            volumes_block, prev_vol_ending_block,
            emotion_arc_block, villain_arc_block, core_mysteries_block,
            cast_block, relations_block, villain_block,
            storylines_block, foreshadow_block, promises_block, pacing_block,
            issue_feedback_block,
        ]
        if b
    ]
    editorial_prompt_block = "\n".join(editorial_blocks)

    return ctx, editorial_prompt_block
