"""卷级章纲 linter 入口与落库。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.services.bootstrap.chapter_plan_batches import normalize_volume_planned_chapters
from app.services.outline_linter.chapter_index import build_volume_start_map
from app.services.outline_linter.helpers import chapter_from_node
from app.services.outline_linter.repair_hints import build_repair_seed
from app.services.outline_linter.rules_chapter import lint_chapters
from app.services.outline_linter.rules_lifecycle import run_lifecycle_rules
from app.services.outline_linter.rules_mysteries import lint_core_mysteries
from app.services.outline_linter.rules_promises import (
    lint_opening_contract_rp,
    lint_reader_promises,
)
from app.services.outline_linter.rules_sequence import lint_sequence
from app.services.outline_linter.rules_volume import (
    get_positioning_pace,
    lint_volume,
    prev_volume_hook_from_db,
)
from app.services.outline_linter.rules_volume_beats import lint_volume_beats
from app.services.outline_linter.schemas import LINTER_VERSION, LinterReport

logger = logging.getLogger(__name__)


def run_volume_linter(
    db: Session,
    project: Any,
    volume_node: Any,
    chapters: list[Any] | None = None,
) -> LinterReport:
    """对一卷 chapter_plan 运行 MVP linter。

    Args:
        db: 数据库会话。
        project: Project 模型。
        volume_node: node_type=volume 的 OutlineNode。
        chapters: 可选，已生成的章纲节点列表；为空则从 DB 查询。

    Returns:
        LinterReport（含 status / issues）。
    """
    from app.models import OutlineNode

    if chapters is None:
        chapters = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.parent_id == volume_node.id,
                OutlineNode.node_type == "chapter_plan",
            )
            .order_by(OutlineNode.sort_order.asc())
            .all()
        )

    snapshots = [chapter_from_node(n) for n in chapters]
    extra_vol = volume_node.extra or {}
    planned = normalize_volume_planned_chapters(extra_vol.get("planned_chapters", 30))
    raw_batch_starts = extra_vol.get("expand_batch_starts")
    if isinstance(raw_batch_starts, list):
        batch_boundaries = {int(x) for x in raw_batch_starts if isinstance(x, int) and x > 1}
    elif planned > 30:
        # 旧数据无批次元数据：沿用「第 31 章为第二批首章」假设
        batch_boundaries = {31}
    else:
        batch_boundaries = set()

    vol_phase = volume_node.phase or (snapshots[0].phase if snapshots else "rising")
    pace_type = get_positioning_pace(project.extra if isinstance(project.extra, dict) else {})
    vol_sort = int(volume_node.sort_order or 0)
    prev_hook = prev_volume_hook_from_db(db, project.id, vol_sort)
    project_extra = project.extra if isinstance(project.extra, dict) else {}
    volume_starts = build_volume_start_map(db, project.id)
    volume_start_global = volume_starts.get(vol_sort, 1)

    report = LinterReport()
    report.issues.extend(lint_chapters(snapshots))
    report.issues.extend(lint_sequence(
        snapshots,
        volume_phase=vol_phase or "rising",
        planned_chapters=planned,
        batch_boundary_chapters=batch_boundaries,
    ))
    report.issues.extend(lint_volume(
        snapshots,
        planned_chapters=planned,
        volume_phase=vol_phase or "rising",
        pace_type=pace_type,
        prev_volume_hook=prev_hook,
        is_first_volume=(vol_sort == 0),
    ))
    report.issues.extend(lint_volume_beats(
        snapshots,
        extra_vol,
        planned_chapters=planned,
        volume_phase=vol_phase or "rising",
    ))
    report.issues.extend(lint_reader_promises(
        db,
        project.id,
        snapshots,
        volume_start_global=volume_start_global,
    ))
    report.issues.extend(lint_core_mysteries(
        db,
        project.id,
        snapshots,
        volume_start_global=volume_start_global,
        project_extra=project_extra,
    ))
    if vol_sort == 0:
        opening_contract = project_extra.get("opening_contract") or {}
        if isinstance(opening_contract, dict):
            report.issues.extend(
                lint_opening_contract_rp(snapshots, opening_contract)
            )
    # 跨卷角色生命周期硬校验（死而复死 / 死后出场 / 阵营硬切 / 击杀承诺超窗）。
    # 自建全书事件时间轴，失败不得污染整卷 linter。
    try:
        report.issues.extend(run_lifecycle_rules(
            db, project, volume_node, volume_start_global=volume_start_global,
        ))
    except Exception:
        logger.warning("run_lifecycle_rules 跳过（不影响其余 linter）", exc_info=True)
    report.finalize_status()
    return report


def run_volume_linter_with_repair_seed(
    db: Session,
    project: Any,
    volume_node: Any,
    chapters: list[Any] | None = None,
    *,
    report: LinterReport | None = None,
) -> dict:
    """运行 linter 并附带 repair_seed。"""
    if report is None:
        report = run_volume_linter(db, project, volume_node, chapters=chapters)
    return {
        **report.to_dict(),
        "repair_seed": build_repair_seed(report),
    }


def persist_linter_report(volume_node: Any, report: LinterReport) -> None:
    """将 linter 结果写入 volume.extra。"""
    extra = dict(volume_node.extra or {})
    extra["linter_version"] = LINTER_VERSION
    extra["linter_status"] = report.status
    extra["linter_issues"] = [i.to_dict() for i in report.issues]
    extra["linter_summary"] = {
        "issue_count": len(report.issues),
        "critical_count": report.critical_count,
        "high_count": report.high_count,
    }
    volume_node.extra = extra
    flag_modified(volume_node, "extra")


async def run_volume_linter_enriched(
    db: Session,
    project: Any,
    volume_node: Any,
    chapters: list[Any] | None = None,
    *,
    use_embedding: bool = True,
) -> LinterReport:
    """完整 linter（含 Jaccard SEQ-05 + 可选 embedding SEQ-05E）。"""
    from app.services.outline_linter.helpers import chapter_from_node
    from app.services.outline_linter.rules_sequence import lint_semantic_duplicates

    report = run_volume_linter(db, project, volume_node, chapters=chapters)
    snaps = (
        [chapter_from_node(n) for n in chapters]
        if chapters
        else []
    )
    if not snaps:
        from app.models import OutlineNode

        nodes = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.parent_id == volume_node.id,
                OutlineNode.node_type == "chapter_plan",
            )
            .order_by(OutlineNode.sort_order.asc())
            .all()
        )
        snaps = [chapter_from_node(n) for n in nodes]
    report.issues.extend(lint_semantic_duplicates(snaps))
    if use_embedding and len(snaps) >= 2:
        from app.services.outline_linter.embedding_seq import (
            lint_embedding_duplicates_async,
        )

        report.issues.extend(
            await lint_embedding_duplicates_async(snaps, scope="volume")
        )
    report.finalize_status()
    return report


def apply_volume_linter(db: Session, project: Any, volume_node: Any) -> LinterReport:
    """运行 linter、写回卷节点、打日志（不阻断落库，供手动 API）。"""
    from app.services.outline_linter.gate import _log_linter_report

    report = run_volume_linter(db, project, volume_node)
    from app.services.outline_linter.helpers import chapter_from_node
    from app.services.outline_linter.rules_sequence import lint_semantic_duplicates
    from app.models import OutlineNode

    nodes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.parent_id == volume_node.id,
            OutlineNode.node_type == "chapter_plan",
        )
        .order_by(OutlineNode.sort_order.asc())
        .all()
    )
    snaps = [chapter_from_node(n) for n in nodes]
    report.issues.extend(lint_semantic_duplicates(snaps))
    report.finalize_status()
    persist_linter_report(volume_node, report)
    db.commit()
    _log_linter_report(project, volume_node, report)
    return report
