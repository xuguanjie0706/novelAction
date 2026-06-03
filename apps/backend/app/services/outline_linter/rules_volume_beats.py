"""卷级节拍 linter（VB-*）：章纲是否覆盖卷级燃点/高潮锚点。"""
from __future__ import annotations

from app.services.bootstrap.volume_beats import has_volume_beats, volume_beats_from_extra
from app.services.outline_linter.helpers import ChapterSnapshot, text_overlap
from app.services.outline_linter.schemas import LinterIssue


def _chapter_in_volume_number(ch: ChapterSnapshot) -> int:
    return (ch.sort_order or 0) + 1


def _chapter_text_blob(ch: ChapterSnapshot) -> str:
    parts = [
        ch.title or "",
        ch.summary or "",
        ch.hook or "",
        ch.highlight or "",
        ch.conflict or "",
    ]
    ex = ch.extra or {}
    for key in (
        "end_hook",
        "choice_cost",
        "protagonist_choice",
        "core_event",
        "promise_fulfilled",
    ):
        parts.append(str(ex.get(key) or ""))
    return " ".join(parts)


def _find_nearby_chapter(
    chapters: list[ChapterSnapshot],
    target: int,
    window: int = 1,
) -> ChapterSnapshot | None:
    for ch in chapters:
        n = _chapter_in_volume_number(ch)
        if abs(n - target) <= window:
            return ch
    return None


def lint_volume_beats(
    chapters: list[ChapterSnapshot],
    volume_extra: dict,
    *,
    planned_chapters: int,
    volume_phase: str = "",
) -> list[LinterIssue]:
    """检查章纲是否落实卷级 beat_highlights / volume_climax（无节拍数据时跳过）。"""
    if not has_volume_beats(volume_extra) or not chapters:
        return []

    beats = volume_beats_from_extra(volume_extra)
    issues: list[LinterIssue] = []

    highlights = beats.get("beat_highlights") or []
    if isinstance(highlights, list) and len(highlights) < 2:
        issues.append(LinterIssue(
            rule_id="VB-00",
            severity="medium",
            scope="volume",
            message=f"卷级燃点仅 {len(highlights)} 条，建议 2～4 条",
            suggestion="在 Bootstrap 卷闸门或卷编辑中补全 beat_highlights",
        ))

    # VB-08：燃点类型过度单一（≥3 条但去重后 ≤1 种）——「整卷清一色打脸」信号
    valid_beats = [
        b for b in highlights
        if isinstance(b, dict) and (b.get("description") or "").strip()
    ]
    if len(valid_beats) >= 3:
        beat_types = {(b.get("beat_type") or "").strip() for b in valid_beats}
        beat_types.discard("")
        if len(beat_types) <= 1:
            only = next(iter(beat_types), "face_slap")
            issues.append(LinterIssue(
                rule_id="VB-08",
                severity="medium",
                scope="volume",
                message=f"卷级燃点类型单一（{len(valid_beats)} 条均为 {only}），缺乏爽感多样性",
                suggestion="混入 reveal/power_up/relationship_turn 等不同类型，避免整卷清一色打脸",
            ))

    for i, b in enumerate(highlights, 1):
        if not isinstance(b, dict):
            continue
        hint = int(b.get("chapter_hint") or 0)
        desc = (b.get("description") or "").strip()
        if not hint or not desc:
            continue
        if planned_chapters and hint > planned_chapters:
            issues.append(LinterIssue(
                rule_id="VB-01",
                severity="high",
                scope="volume",
                message=f"燃点#{i} 锚定第 {hint} 章，超出卷配额 {planned_chapters}",
                suggestion="调整 chapter_hint 或卷 planned_chapters",
            ))
            continue
        nearby = _find_nearby_chapter(chapters, hint, window=1)
        if not nearby:
            issues.append(LinterIssue(
                rule_id="VB-02",
                severity="high",
                scope="volume",
                message=f"燃点#{i}（目标第 {hint} 章）附近无对应章纲节点",
                suggestion="补章或调整燃点章号",
                chapter_number_in_volume=hint,
            ))
            continue
        blob = _chapter_text_blob(nearby)
        if not text_overlap(blob, desc, min_len=2):
            issues.append(LinterIssue(
                rule_id="VB-03",
                severity="high",
                scope="volume",
                message=(
                    f"第 {_chapter_in_volume_number(nearby)} 章章纲与燃点#{i}描述无明显呼应："
                    f"「{desc[:40]}…」"
                ),
                suggestion="改写该章 core_event / end_hook 使含燃点关键词",
                chapter_number_in_volume=_chapter_in_volume_number(nearby),
                node_id=nearby.id,
            ))
        beat_type = (b.get("beat_type") or "").strip()
        if beat_type == "face_slap" and not (nearby.extra or {}).get("has_face_slap"):
            issues.append(LinterIssue(
                rule_id="VB-04",
                severity="medium",
                scope="chapter",
                message=f"燃点#{i} 为打脸类，但第 {_chapter_in_volume_number(nearby)} 章未标 has_face_slap",
                suggestion="将该章 has_face_slap 设为 true 并写具体打脸场面",
                chapter_number_in_volume=_chapter_in_volume_number(nearby),
                node_id=nearby.id,
            ))

    climax = beats.get("volume_climax")
    if isinstance(climax, dict) and climax.get("description"):
        ch_hint = int(climax.get("chapter_hint") or 0)
        desc = str(climax["description"]).strip()
        if ch_hint and planned_chapters:
            tail_start = max(int(planned_chapters * 0.7), 1)
            if ch_hint < tail_start:
                issues.append(LinterIssue(
                    rule_id="VB-05",
                    severity="medium",
                    scope="volume",
                    message=(
                        f"卷末高潮锚在第 {ch_hint} 章，早于卷后 30% 起点（第 {tail_start} 章）"
                    ),
                    suggestion="将 volume_climax.chapter_hint 后移至卷末段",
                ))
        nearby = _find_nearby_chapter(chapters, ch_hint, window=1) if ch_hint else None
        if nearby and desc and not text_overlap(_chapter_text_blob(nearby), desc, min_len=2):
            issues.append(LinterIssue(
                rule_id="VB-06",
                severity="high",
                scope="volume",
                message=(
                    f"第 {_chapter_in_volume_number(nearby)} 章未呼应卷末高潮："
                    f"「{desc[:50]}…」"
                ),
                suggestion="强化该章 end_hook / core_event 作为卷内总清算",
                chapter_number_in_volume=_chapter_in_volume_number(nearby),
                node_id=nearby.id,
            ))
        elif ch_hint and not nearby:
            issues.append(LinterIssue(
                rule_id="VB-06",
                severity="high",
                scope="volume",
                message=f"卷末高潮锚定第 {ch_hint} 章，但章纲中无对应节点",
                suggestion="补章或调整高潮章号",
                chapter_number_in_volume=ch_hint,
            ))

    if volume_phase in ("dark_hour", "turning"):
        turning = beats.get("emotional_turning_point")
        if not (isinstance(turning, dict) and turning.get("description")):
            issues.append(LinterIssue(
                rule_id="VB-07",
                severity="medium",
                scope="volume",
                message=f"phase={volume_phase} 的卷建议填写 emotional_turning_point",
                suggestion="在卷级导演单中补充主角认知/关系转折点",
            ))

    return issues
