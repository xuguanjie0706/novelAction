"""核心谜题 linter（CM-*）。"""

from __future__ import annotations

from typing import Any

from app.services.outline_linter.chapter_index import build_global_chapter_index
from app.services.outline_linter.helpers import (
    FORESHADOW_HEAT_MARK,
    FORESHADOW_LAY_MARK,
    FORESHADOW_RESOLVE_MARK,
    ChapterSnapshot,
)
from app.services.outline_linter.schemas import LinterIssue


def _foreshadow_text_for_global(
    db: Any,
    project_id: Any,
    global_chapter: int,
    node_to_global: dict[str, int],
) -> str:
    from app.models import OutlineNode

    for node in (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .all()
    ):
        if node_to_global.get(str(node.id)) == global_chapter:
            return ((node.extra or {}).get("foreshadow") or "").strip()
    return ""


def _chapter_snapshots_foreshadow(chapters: list[ChapterSnapshot], global_start: int) -> dict[int, str]:
    return {
        global_start + ch.sort_order: ch.ex_str("foreshadow")
        for ch in chapters
    }


def lint_core_mysteries(
    db: Any,
    project_id: Any,
    chapters: list[ChapterSnapshot],
    *,
    volume_start_global: int,
    project_extra: dict | None,
) -> list[LinterIssue]:
    """校验 Project.extra.core_mysteries 与章纲伏笔字段。"""
    issues: list[LinterIssue] = []
    mysteries = (project_extra or {}).get("core_mysteries") or []
    if not isinstance(mysteries, list) or not mysteries:
        return issues

    node_to_global, max_global = build_global_chapter_index(db, project_id)
    local_fs = _chapter_snapshots_foreshadow(chapters, volume_start_global)

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

        if lay:
            fs = local_fs.get(lay, "") or _foreshadow_text_for_global(
                db, project_id, lay, node_to_global
            )
            if name and name not in fs and FORESHADOW_LAY_MARK not in fs:
                issues.append(LinterIssue(
                    rule_id="CM-01",
                    severity="high",
                    scope="volume",
                    message=f"核心谜题「{name}」应在第{lay}章埋下，章纲伏笔字段未体现",
                    suggestion=f"第{lay}章伏笔写：埋[{name}|主题:…]",
                ))

        for hc in heat_chapters:
            if not isinstance(hc, int):
                continue
            fs = local_fs.get(hc, "") or _foreshadow_text_for_global(
                db, project_id, hc, node_to_global
            )
            if name and name not in fs and FORESHADOW_HEAT_MARK not in fs:
                issues.append(LinterIssue(
                    rule_id="CM-02",
                    severity="high",
                    scope="volume",
                    message=f"核心谜题「{name}」应在第{hc}章加热，章纲伏笔字段未体现",
                    suggestion=f"第{hc}章伏笔写：加热[{name}+手法]",
                ))

        if lay and reveal and reveal < lay + 10:
            issues.append(LinterIssue(
                rule_id="CM-03",
                severity="critical",
                scope="volume",
                message=f"谜题「{name}」揭晓章（{reveal}）距埋设章（{lay}）不足10章",
                suggestion="推迟揭晓章号或提前埋设章号，保证间隔至少10章",
            ))

        if reveal and max_global > reveal:
            fs = local_fs.get(reveal, "") or _foreshadow_text_for_global(
                db, project_id, reveal, node_to_global
            )
            if FORESHADOW_RESOLVE_MARK not in fs and (name and name not in fs):
                issues.append(LinterIssue(
                    rule_id="CM-04",
                    severity="medium",
                    scope="volume",
                    message=f"谜题「{name}」已过揭晓章（第{reveal}章），章纲未见「收[…]」回收",
                    suggestion=f"在第{reveal}章伏笔写：收[{name}]",
                ))

    if mysteries and not has_identity:
        issues.append(LinterIssue(
            rule_id="CM-05",
            severity="medium",
            scope="volume",
            message="核心谜题清单缺少「身份之谜」类型",
            suggestion="至少保留一条身份类核心谜题",
        ))

    reveal_chapters.sort()
    for i in range(1, len(reveal_chapters)):
        if reveal_chapters[i] - reveal_chapters[i - 1] < 15:
            issues.append(LinterIssue(
                rule_id="CM-06",
                severity="low",
                scope="volume",
                message=(
                    f"两条核心谜题揭晓章相距仅 "
                    f"{reveal_chapters[i] - reveal_chapters[i - 1]} 章（建议≥15）"
                ),
                suggestion="分散揭晓高潮",
            ))
            break

    return issues
