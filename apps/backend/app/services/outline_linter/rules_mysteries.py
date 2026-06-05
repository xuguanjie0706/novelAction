"""核心谜题 linter（CM-*）。"""

from __future__ import annotations

from typing import Any

from app.services.outline_linter.chapter_index import build_global_chapter_index
from app.services.bootstrap.foreshadow_ops import mystery_op_covered
from app.services.outline_linter.helpers import ChapterSnapshot
from app.services.outline_linter.schemas import LinterIssue


def _foreshadow_extra_for_global(
    db: Any,
    project_id: Any,
    global_chapter: int,
    node_to_global: dict[str, int],
) -> dict:
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
            return dict(node.extra or {})
    return {}


def _chapter_snapshots_extra(chapters: list[ChapterSnapshot], global_start: int) -> dict[int, dict]:
    return {
        global_start + ch.sort_order: dict(ch.extra or {})
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

        if lay:
            extra = local_extra.get(lay) or _foreshadow_extra_for_global(
                db, project_id, lay, node_to_global
            )
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
            if not isinstance(hc, int):
                continue
            extra = local_extra.get(hc) or _foreshadow_extra_for_global(
                db, project_id, hc, node_to_global
            )
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

        if lay and reveal and reveal < lay + 10:
            issues.append(LinterIssue(
                rule_id="CM-03",
                severity="critical",
                scope="volume",
                message=f"谜题「{name}」揭晓章（{reveal}）距埋设章（{lay}）不足10章",
                suggestion="推迟揭晓章号或提前埋设章号，保证间隔至少10章",
            ))

        if reveal and max_global > reveal:
            extra = local_extra.get(reveal) or _foreshadow_extra_for_global(
                db, project_id, reveal, node_to_global
            )
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
