"""dabai Bootstrap 收尾规则质检（无 LLM）。"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models import Character, OutlineNode, Project
from app.services.bootstrap.antagonist_roster import ensure_ladder_characters
from app.services.bootstrap.steps.dabai.dabai_converge import (
    repair_dabai_volume_boss_binding,
    sync_ctx_char_maps,
)

logger = logging.getLogger(__name__)


def run_dabai_bootstrap_lint(svc: Any, project: Project, ctx: dict) -> dict:
    """卷间境界单调、地图非空、首卷 opening phase。"""
    chars = svc.db.query(Character).filter(Character.project_id == project.id).all()
    chars = ensure_ladder_characters(svc, project, ctx, chars)
    sync_ctx_char_maps(ctx, chars)
    repaired = repair_dabai_volume_boss_binding(svc, project, ctx)
    if repaired:
        logger.info("dabai.converge 回填 volume_boss project=%s 卷数=%d", project.id, repaired)
    issues: list[dict] = []
    volumes = (
        svc.db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )
    last_end = None
    for i, vol in enumerate(volumes):
        extra = vol.extra or {}
        rs = extra.get("realm_start_rank")
        re_ = extra.get("realm_end_rank")
        wm = extra.get("world_map") or {}
        num = i + 1
        if not wm.get("locations"):
            issues.append({
                "rule_id": "DBL-01", "severity": "high", "volume": num,
                "message": f"第{num}卷缺少 world_map.locations",
            })
        if rs is None or re_ is None:
            issues.append({
                "rule_id": "DBL-02", "severity": "critical", "volume": num,
                "message": "缺少 realm_start_rank / realm_end_rank",
            })
        elif re_ < rs:
            issues.append({
                "rule_id": "DBL-03", "severity": "critical", "volume": num,
                "message": f"境界区间倒置 start={rs} end={re_}",
            })
        if last_end is not None and rs is not None and rs < last_end:
            issues.append({
                "rule_id": "DBL-04", "severity": "critical", "volume": num,
                "message": f"卷间境界回退 start={rs} < 上卷 end={last_end}",
            })
        if last_end is not None and rs is not None:
            last_end = re_ if re_ is not None else last_end
        elif re_ is not None:
            last_end = re_
        if num == 1 and (vol.phase or "") != "opening":
            issues.append({
                "rule_id": "DBL-05", "severity": "medium", "volume": 1,
                "message": "首卷 phase 应为 opening",
            })

    blocked = any(i["severity"] == "critical" for i in issues)
    report = {
        "status": "blocked" if blocked else ("warning" if issues else "ok"),
        "issue_count": len(issues),
        "issues": issues,
    }
    extra = dict(project.extra or {})
    extra["dabai_lint"] = report
    extra["bootstrap_mode"] = "dabai"
    project.extra = extra
    try:
        flag_modified(project, "extra")
    except (AttributeError, TypeError):
        pass
    svc.db.commit()
    ctx["dabai_lint"] = report
    logger.info(
        "dabai.bootstrap_lint project=%s status=%s issues=%d",
        project.id, report["status"], len(issues),
    )
    return report
