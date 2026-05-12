"""大纲路由共享工具函数（质检、幂等签名、卷线上下文等）。

实现已拆至 ``helpers/`` 子包；本模块仅做聚合导出，保持
``from app.routers.outline.helpers_core import *`` 等既有引用不变。
"""

from __future__ import annotations

from app.routers.outline.helpers.chapter_context import (
    _format_book_quality_continuity_state,
    _format_global_outline_context,
    _format_json_list,
    _format_outline_batch_goal,
    _format_outline_word_budget_context,
    _format_previous_chapters_context,
    _format_rolling_continuity_state,
    _outline_batch_size,
)
from app.routers.outline.helpers.duplicate_sig import _chapter_duplicate_signature
from app.routers.outline.helpers.embedding_dup import (
    SEMANTIC_DUP_THRESHOLD_HIGH,
    SEMANTIC_DUP_THRESHOLD_MEDIUM,
    SEMANTIC_DUP_WINDOW_BOOK,
    SEMANTIC_DUP_WINDOW_VOLUME,
    analyze_outline_embedding_duplicates,
    compute_outline_chapter_vectors,
    _cosine_similarity,
    _detect_outline_embedding_duplicates,
    _outline_chapter_signature_text,
)
from app.routers.outline.helpers.expand_context import (
    _ai_expand_prior_foreshadow_budget,
    _ai_expand_prior_plot_budget,
    _anchor_volume_for_expand,
    _build_overdue_foreshadow_ledger,
    _build_prior_foreshadow_ledger,
    _chapter_plan_root_volume,
    _compact_prior_volume_plot_lines,
    _format_prior_volumes_plot_context,
    _load_existing_chapter_context,
    _outline_node_to_chapter_context,
    _prior_volume_chapter_plan_nodes,
    _sort_chapter_plan_nodes,
)
from app.routers.outline.helpers.hard_rules import _detect_outline_hard_rule_issues
from app.routers.outline.helpers.quality_ui import (
    _format_outline_quality_label,
    _merge_outline_quality_reports,
    _sse_outline_quality_progress,
)
from app.routers.outline.helpers.realm_timeline import (
    DEBRIEF_REALM_MILESTONES_EXTRA_KEY,
    build_protagonist_realm_timeline,
    merge_outline_and_debrief_realm_milestones,
    _build_realm_rank_map,
    _collect_power_system_whitelist,
    _collect_protagonist_anchor_names,
    _detect_outline_terminology_issues,
    _extract_max_realm_from_chapters,
    _extract_protagonist_realm_rank,
    _protagonist_realm_attributed,
    _rank_for_realm_label,
    _realm_display_name_for_rank,
    _scan_banned_terms,
)
from app.routers.outline.helpers.detectors import (
    _collect_character_aliases,
    _detect_outline_character_death_continuity,
    _detect_outline_foreshadow_issues,
    _detect_outline_power_curve_issues,
    _detect_outline_theme_alignment_issues,
    _name_near_marker,
    _theme_is_self_determination,
)
from app.routers.outline.helpers.revisions import (
    _apply_outline_patch_to_node,
    _chapter_number_value,
    _create_outline_revision,
    _create_quality_revision,
    _load_volume_chapter_context,
    _outline_node_plan_fields,
    _outline_snapshot_payload,
    _with_outline_quality,
)
from app.routers.outline.helpers.severity import _HARD_RULE_SEVERITY_TO_SCORE
from app.routers.outline.helpers.story_bible import _format_outline_quality_story_bible
from app.routers.outline.helpers.text_utils import (
    _clean_outline_text,
    _sanitize_generated_outline_chapter,
    _sanitize_xuanhuan_outline_text,
)
from app.routers.outline.helpers.tree import build_tree

__all__ = [
    "DEBRIEF_REALM_MILESTONES_EXTRA_KEY",
    "SEMANTIC_DUP_THRESHOLD_HIGH",
    "SEMANTIC_DUP_THRESHOLD_MEDIUM",
    "SEMANTIC_DUP_WINDOW_BOOK",
    "SEMANTIC_DUP_WINDOW_VOLUME",
    "analyze_outline_embedding_duplicates",
    "build_protagonist_realm_timeline",
    "build_tree",
    "compute_outline_chapter_vectors",
    "merge_outline_and_debrief_realm_milestones",
    "_HARD_RULE_SEVERITY_TO_SCORE",
    "_ai_expand_prior_foreshadow_budget",
    "_ai_expand_prior_plot_budget",
    "_anchor_volume_for_expand",
    "_apply_outline_patch_to_node",
    "_build_overdue_foreshadow_ledger",
    "_build_prior_foreshadow_ledger",
    "_build_realm_rank_map",
    "_chapter_duplicate_signature",
    "_chapter_number_value",
    "_chapter_plan_root_volume",
    "_clean_outline_text",
    "_collect_character_aliases",
    "_collect_power_system_whitelist",
    "_collect_protagonist_anchor_names",
    "_compact_prior_volume_plot_lines",
    "_cosine_similarity",
    "_create_outline_revision",
    "_create_quality_revision",
    "_detect_outline_character_death_continuity",
    "_detect_outline_embedding_duplicates",
    "_detect_outline_foreshadow_issues",
    "_detect_outline_hard_rule_issues",
    "_detect_outline_power_curve_issues",
    "_detect_outline_terminology_issues",
    "_detect_outline_theme_alignment_issues",
    "_extract_max_realm_from_chapters",
    "_extract_protagonist_realm_rank",
    "_format_book_quality_continuity_state",
    "_format_global_outline_context",
    "_format_json_list",
    "_format_outline_batch_goal",
    "_format_outline_quality_label",
    "_format_outline_quality_story_bible",
    "_format_outline_word_budget_context",
    "_format_previous_chapters_context",
    "_format_prior_volumes_plot_context",
    "_format_rolling_continuity_state",
    "_load_existing_chapter_context",
    "_load_volume_chapter_context",
    "_merge_outline_quality_reports",
    "_name_near_marker",
    "_outline_batch_size",
    "_outline_chapter_signature_text",
    "_outline_node_plan_fields",
    "_outline_node_to_chapter_context",
    "_outline_snapshot_payload",
    "_prior_volume_chapter_plan_nodes",
    "_protagonist_realm_attributed",
    "_rank_for_realm_label",
    "_realm_display_name_for_rank",
    "_sanitize_generated_outline_chapter",
    "_sanitize_xuanhuan_outline_text",
    "_scan_banned_terms",
    "_sort_chapter_plan_nodes",
    "_sse_outline_quality_progress",
    "_theme_is_self_determination",
    "_with_outline_quality",
]


def __getattr__(name: str):
    """测试与少量调用方从本模块取 ``_outline_quality_nodes_for_scope``（定义在 qa_internal）。"""
    if name == "_outline_quality_nodes_for_scope":
        from app.routers.outline import qa_internal

        return qa_internal._outline_quality_nodes_for_scope
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
