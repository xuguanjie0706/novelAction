"""卷级 linter 规则（VL-*）。"""

from __future__ import annotations

from typing import Any

from app.services.outline_linter.helpers import (
    FORESHADOW_RESOLVE_MARK,
    ChapterSnapshot,
    bigram_overlap,
    count_face_slap_windows,
    distinct_foreshadow_lay_lines,
    face_slap_bounds,
    is_placeholder,
)
from app.services.outline_linter.schemas import LinterIssue


def lint_volume(
    chapters: list[ChapterSnapshot],
    *,
    planned_chapters: int,
    volume_phase: str,
    pace_type: str,
    prev_volume_hook: str | None = None,
    is_first_volume: bool = False,
) -> list[LinterIssue]:
    issues: list[LinterIssue] = []
    planned = planned_chapters or 30
    count = len(chapters)

    # VL-01：章数不符降为 high（非阻断）。
    # AI 截断是 token / 模型问题，不应阻断用户查看已生成内容；
    # ±2 章容差（极小误差可接受），超出则警告。
    _tolerance = 2
    if abs(count - planned) > _tolerance:
        severity_vl01 = "high"  # 原 critical 已从 BLOCKING_RULE_IDS 移除
        issues.append(LinterIssue(
            rule_id="VL-01",
            severity=severity_vl01,
            scope="volume",
            message=f"章纲数量 {count} 与卷配额 {planned} 不符（差 {planned - count:+d} 章）",
            suggestion="重新生成或强制采用后在大纲页手动补章",
        ))

    orders = [ch.sort_order for ch in chapters]
    if orders and orders != list(range(len(orders))):
        issues.append(LinterIssue(
            rule_id="VL-02",
            severity="high",
            scope="volume",
            message="章节排序序号不连续",
            suggestion="将章节排序调整为从 0 起连续递增",
        ))

    slap_flags = [bool((ch.extra or {}).get("has_face_slap")) for ch in chapters]
    slap_total = sum(slap_flags)
    if chapters and slap_total == 0 and pace_type != "none":
        issues.append(LinterIssue(
            rule_id="VL-03",
            severity="high",
            scope="volume",
            message="全卷未标记任何「打脸/爽点」章节",
            suggestion="按立项打脸节奏补若干爽点章",
        ))

    if chapters:
        min_slap, max_slap, window = face_slap_bounds(pace_type, count)
        if slap_total < min_slap:
            issues.append(LinterIssue(
                rule_id="VL-04",
                severity="medium",
                scope="volume",
                message=f"打脸章 {slap_total} 少于节奏下限 {min_slap}",
                suggestion="增加打脸标记章节",
            ))
        elif slap_total > max_slap:
            issues.append(LinterIssue(
                rule_id="VL-04",
                severity="low",
                scope="volume",
                message=f"打脸章 {slap_total} 多于节奏上限 {max_slap}",
                suggestion="适当降低打脸密度",
            ))
        empty_windows = count_face_slap_windows(chapters, window)
        if empty_windows:
            issues.append(LinterIssue(
                rule_id="VL-04",
                severity="medium",
                scope="volume",
                message=f"存在连续 {window} 章无打脸（窗口起点章号示例：{empty_windows[0] + 1}）",
                suggestion=f"每 {window} 章至少 1 次打脸",
            ))

    lay_themes = distinct_foreshadow_lay_lines(chapters)
    if count >= 30 and len(lay_themes) < 2:
        issues.append(LinterIssue(
            rule_id="VL-05",
            severity="high",
            scope="volume",
            message=f"贯穿伏笔线仅 {len(lay_themes)} 条（需 ≥2）",
            suggestion="在伏笔字段使用「埋[内容|主题:关联]」格式增加卷内长线",
        ))

    resolve_count = sum(
        1 for ch in chapters if FORESHADOW_RESOLVE_MARK in ch.ex_str("foreshadow")
    )
    if count >= 30 and resolve_count == 0 and not is_first_volume:
        issues.append(LinterIssue(
            rule_id="VL-06",
            severity="medium",
            scope="volume",
            message="卷内无「收[」伏笔回收",
            suggestion="卷末至少回收一条伏笔",
        ))

    if chapters:
        sl_sets = {tuple(sorted(str(x) for x in ch.storyline_ids)) for ch in chapters}
        sl_sets.discard(tuple())
        if len(sl_sets) <= 1 and any(ch.storyline_ids for ch in chapters):
            issues.append(LinterIssue(
                rule_id="VL-07",
                severity="medium",
                scope="volume",
                message="全卷仅推进单一故事线组合",
                suggestion="交叉推进支线",
            ))

    if prev_volume_hook and chapters:
        first = chapters[0]
        hook = (first.hook or "").strip()
        cost = first.ex_str("choice_cost")
        if not bigram_overlap(prev_volume_hook, hook):
            issues.append(LinterIssue(
                rule_id="VL-09",
                severity="high",
                scope="volume",
                message="第1章开篇未承接上一卷末悬念",
                suggestion="开篇须让读者感到上卷悬念仍在发酵",
                field="hook",
                chapter_number_in_volume=1,
                node_id=first.id,
            ))
        if cost and not bigram_overlap(prev_volume_hook, cost):
            issues.append(LinterIssue(
                rule_id="VL-10",
                severity="medium",
                scope="volume",
                message="第1章「选择代价」未体现上一卷末后遗症",
                field="extra.choice_cost",
                chapter_number_in_volume=1,
                node_id=first.id,
            ))

    if is_first_volume and chapters:
        issues.extend(_lint_opening_contract(chapters))

    return issues


def _lint_opening_contract(chapters: list[ChapterSnapshot]) -> list[LinterIssue]:
    """开局卷前10章轻量检查（无 opening_contract 数据时跳过 OC-02/03）。"""
    issues: list[LinterIssue] = []
    first10 = [ch for ch in chapters if ch.chapter_number <= 10]
    if not first10:
        return issues

    ch3 = next((ch for ch in chapters if ch.chapter_number == 3), None)
    if ch3:
        had_slap_before = any(
            bool((ch.extra or {}).get("has_face_slap"))
            for ch in chapters
            if ch.chapter_number <= 3
        )
        if not had_slap_before:
            issues.append(LinterIssue(
                rule_id="OC-02",
                severity="high",
                scope="volume",
                message="前3章均未标记「打脸/爽点」",
                suggestion="按开局规划在前3章内安排一次爽点兑现",
                chapter_number_in_volume=3,
            ))

    ch5 = next((ch for ch in chapters if ch.chapter_number == 5), None)
    from app.services.outline_linter.helpers import chapter_has_foreshadow_lay

    if ch5 and not chapter_has_foreshadow_lay(ch5):
        issues.append(LinterIssue(
            rule_id="OC-03",
            severity="high",
            scope="volume",
            message="第5章未埋设长线伏笔（foreshadow_ops 须含 op=lay）",
            suggestion="按开局规划在第5章埋下跨卷伏笔：foreshadow_ops 增加 {\"op\":\"lay\",\"name\":\"…\",\"theme\":\"…\"}",
            chapter_number_in_volume=5,
            node_id=ch5.id,
        ))

    ch10 = next((ch for ch in chapters if ch.chapter_number == 10), None)
    if ch10:
        end = ch10.end_hook_text()
        if is_placeholder(end) or len(end) < 12:
            issues.append(LinterIssue(
                rule_id="OC-04",
                severity="high",
                scope="volume",
                message="第10章章末钩子偏弱",
                field="extra.end_hook",
                chapter_number_in_volume=10,
                node_id=ch10.id,
            ))

    return issues


def get_positioning_pace(project_extra: dict | None) -> str:
    pos = (project_extra or {}).get("positioning") or {}
    if isinstance(pos, dict):
        return str(pos.get("pace_type") or "medium")
    return "medium"


def prev_volume_hook_from_db(db: Any, project_id: Any, volume_sort_order: int) -> str | None:
    if not volume_sort_order:
        return None
    from app.models import OutlineNode

    prev = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
            OutlineNode.sort_order == volume_sort_order - 1,
        )
        .first()
    )
    if not prev:
        return None
    hook = (prev.hook or "").strip()
    return hook or None
