"""核心谜题 linter（CM-*）。"""

from __future__ import annotations

from typing import Any

from app.services.bootstrap.foreshadow_ops import mystery_op_covered
from app.services.outline_linter.helpers import ChapterSnapshot
from app.services.outline_linter.schemas import LinterIssue


def _chapter_snapshots_extra(chapters: list[ChapterSnapshot], global_start: int) -> dict[int, dict]:
    return {
        global_start + ch.sort_order: dict(ch.extra or {})
        for ch in chapters
    }


def _volume_global_chapters(
    chapters: list[ChapterSnapshot],
    volume_start_global: int,
) -> set[int]:
    """当前卷已展开 chapter_plan 对应的全书章号集合。"""
    if not chapters:
        return set()
    return {volume_start_global + ch.sort_order for ch in chapters}


def lint_core_mysteries(
    db: Any,
    project_id: Any,
    chapters: list[ChapterSnapshot],
    *,
    volume_start_global: int,
    project_extra: dict | None,
) -> list[LinterIssue]:
    """校验 Project.extra.core_mysteries 与当前卷已展开章纲的伏笔字段。

    仅检查 lay / heat / resolve 章号落在本卷已展开 chapter_plan 范围内的条目，
    未展开卷上的日程不在本卷 linter 中报错。
    """
    del db, project_id  # 卷内范围校验仅读当前 snapshots，不再跨卷查 DB

    issues: list[LinterIssue] = []
    mysteries = (project_extra or {}).get("core_mysteries") or []
    if not isinstance(mysteries, list) or not mysteries:
        return issues

    vol_globals = _volume_global_chapters(chapters, volume_start_global)
    if not vol_globals:
        return issues

    local_extra = _chapter_snapshots_extra(chapters, volume_start_global)

    has_identity = False
    reveal_chapters: list[int] = []

    for m in mysteries:
        if not isinstance(m, dict):
            continue
        name = (m.get("name") or "").strip()
        mtype = (m.get("mystery_type") or "").strip()
        lay = int(m.get("lay_chapter") or 0)
        reveal = int(m.get("reveal_chapter") or 0)
        heat_chapters = m.get("heat_chapters") or []
        if not isinstance(heat_chapters, list):
            heat_chapters = []

        if mtype == "identity":
            has_identity = True
        if reveal:
            reveal_chapters.append(reveal)

        if lay and lay in vol_globals:
            extra = local_extra.get(lay, {})
            if name and not mystery_op_covered(name, extra, "lay"):
                issues.append(LinterIssue(
                    rule_id="CM-01",
                    severity="high",
                    scope="volume",
                    message=f"核心谜题「{name}」应在第{lay}章埋下，章纲伏笔字段未体现",
                    suggestion=(
                        f'第{lay}章 foreshadow_ops 增加 '
                        f'{{"op":"lay","name":"{name}","theme":"…"}}'
                    ),
                ))

        for hc in heat_chapters:
            if not isinstance(hc, int) or hc not in vol_globals:
                continue
            extra = local_extra.get(hc, {})
            if name and not mystery_op_covered(name, extra, "heat"):
                issues.append(LinterIssue(
                    rule_id="CM-02",
                    severity="high",
                    scope="volume",
                    message=f"核心谜题「{name}」应在第{hc}章加热，章纲伏笔字段未体现",
                    suggestion=(
                        f'第{hc}章 foreshadow_ops 增加 '
                        f'{{"op":"heat","code":"…","note":"{name}推进"}}'
                    ),
                ))

        if (
            lay
            and reveal
            and lay in vol_globals
            and reveal in vol_globals
            and reveal < lay + 10
        ):
            issues.append(LinterIssue(
                rule_id="CM-03",
                severity="critical",
                scope="volume",
                message=f"谜题「{name}」揭晓章（{reveal}）距埋设章（{lay}）不足10章",
                suggestion="推迟揭晓章号或提前埋设章号，保证间隔至少10章",
            ))

        if reveal and reveal in vol_globals:
            extra = local_extra.get(reveal, {})
            if name and not mystery_op_covered(name, extra, "resolve"):
                issues.append(LinterIssue(
                    rule_id="CM-04",
                    severity="medium",
                    scope="volume",
                    message=f"谜题「{name}」已过揭晓章（第{reveal}章），章纲未见 resolve 回收",
                    suggestion=(
                        f'在第{reveal}章 foreshadow_ops 增加 '
                        f'{{"op":"resolve","code":"…","note":"{name}"}}'
                    ),
                ))

    if mysteries and not has_identity:
        issues.append(LinterIssue(
            rule_id="CM-05",
            severity="medium",
            scope="volume",
            message="核心谜题清单缺少「身份之谜」类型",
            suggestion="至少保留一条身份类核心谜题",
        ))

    reveals_in_vol = sorted(r for r in reveal_chapters if r in vol_globals)
    for i in range(1, len(reveals_in_vol)):
        if reveals_in_vol[i] - reveals_in_vol[i - 1] < 15:
            issues.append(LinterIssue(
                rule_id="CM-06",
                severity="low",
                scope="volume",
                message=(
                    f"两条核心谜题揭晓章相距仅 "
                    f"{reveals_in_vol[i] - reveals_in_vol[i - 1]} 章（建议≥15）"
                ),
                suggestion="分散揭晓高潮",
            ))
            break

    return issues
