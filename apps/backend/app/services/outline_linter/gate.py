"""落库门禁（GEN-02）与批次重试（GEN-01）。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.services.outline_linter.run import persist_linter_report
from app.services.outline_linter.schemas import LinterReport

logger = logging.getLogger(__name__)

# 命中任一条即阻断整卷章纲 commit（须修后重生成）
BLOCKING_RULE_IDS = frozenset({
    "CH-04",   # choice_cost 空
    "CH-08",   # core_event 空
    "VL-01",   # 章数配额不符
    "SEQ-07",  # 第二批首章未承接
    "RP-01",   # 读者承诺超窗
    "CM-03",   # 谜题过早揭晓
    "GEN-01",  # 批次数漂移（截断后仍标）
})


def report_blocks_commit(report: LinterReport) -> bool:
    """是否存在阻断级 linter 问题。"""
    return any(issue.rule_id in BLOCKING_RULE_IDS for issue in report.issues)


def finalize_volume_chapter_commit(
    svc: Any,
    project: Any,
    volume_node: Any,
    all_results: list[Any],
    *,
    ctx: dict | None = None,
) -> list[Any]:
    """章纲全部生成完毕后的统一落库：先 linter，阻断则 rollback。

    Returns:
        成功落库时返回 all_results；阻断时返回 [] 并在 volume.extra 标记 linter_blocked。
    """
    if not all_results:
        return []

    from app.services.outline_linter.run import run_volume_linter

    from app.services.outline_linter.helpers import chapter_from_node
    from app.services.outline_linter.rules_sequence import lint_semantic_duplicates

    report = run_volume_linter(svc.db, project, volume_node, chapters=all_results)
    report.issues.extend(
        lint_semantic_duplicates([chapter_from_node(n) for n in all_results])
    )
    report.finalize_status()

    if report_blocks_commit(report):
        svc.db.rollback()
        from app.models import OutlineNode

        vol = (
            svc.db.query(OutlineNode)
            .filter(OutlineNode.id == volume_node.id)
            .first()
        )
        if vol:
            persist_linter_report(vol, report)
            extra = dict(vol.extra or {})
            extra["linter_blocked"] = True
            extra["linter_block_reason"] = (
                f"critical 规则命中："
                f"{[i.rule_id for i in report.issues if i.rule_id in BLOCKING_RULE_IDS][:6]}"
            )
            vol.extra = extra
            flag_modified(vol, "extra")
            svc.db.commit()
        logger.error(
            "GEN-02 阻断落库：项目=%s 卷=%s critical=%d issues=%d",
            project.id,
            volume_node.title,
            report.critical_count,
            len(report.issues),
        )
        if ctx is not None:
            ctx["linter_blocked"] = True
            ctx["linter_last_report"] = report.to_dict()
        return []

    svc.db.commit()
    from app.models import OutlineNode
    from app.services.outline_linter.run import persist_linter_report as persist

    db_vol = svc.db.query(OutlineNode).filter(OutlineNode.id == volume_node.id).first()
    target = db_vol or volume_node
    persist(target, report)
    svc.db.commit()
    _log_linter_report(project, target, report)
    if ctx is not None:
        ctx["linter_blocked"] = False
    return all_results


def _log_linter_report(project: Any, volume_node: Any, report: LinterReport) -> None:
    if report.status == "ok":
        logger.info("outline_linter 通过：项目=%s 卷=%s", project.id, volume_node.title)
        return
    logger.warning(
        "outline_linter %s：项目=%s 卷=%s issues=%d critical=%d high=%d",
        report.status,
        project.id,
        volume_node.title,
        len(report.issues),
        report.critical_count,
        report.high_count,
    )
    for issue in report.issues[:8]:
        if issue.severity in ("critical", "high"):
            logger.warning(
                "  [%s] %s (章%s)",
                issue.rule_id,
                issue.message,
                issue.chapter_number_in_volume or "-",
            )
