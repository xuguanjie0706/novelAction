"""dabai 正文设定一致性校验（规则优先，不做文采质检）。"""
from __future__ import annotations

import re
from typing import Any

from app.models import Chapter, OutlineNode, Project
from app.services.dabai.outline_plan import resolve_chapter_plan


def _realm_names(db, project: Project) -> dict[int, str]:
    from app.models import PowerSystem
    out: dict[int, str] = {}
    for ps in db.query(PowerSystem).filter(PowerSystem.project_id == project.id).all():
        for lv in (ps.levels or []):
            if isinstance(lv, dict) and lv.get("rank"):
                out[int(lv["rank"])] = str(lv.get("name", ""))
    extra = project.extra or {}
    for lv in (extra.get("power_ladder") or {}).get("levels") or []:
        if isinstance(lv, dict) and lv.get("rank"):
            out[int(lv["rank"])] = str(lv.get("name", ""))
    return out


def _plain_content(chapter: Chapter) -> str:
    return re.sub(r"<[^>]+>", "", chapter.content or "").strip().lower()


def _payoff_keywords(payoff: str, yaqu: str) -> list[str]:
    """从 payoff/yaqu 抽 3~8 字检索锚点，不用 shuang_type 标签字面量。"""
    raw = re.sub(r"[^\u4e00-\u9fff]", "", f"{payoff} {yaqu}")
    if len(raw) < 4:
        return []
    anchors: list[str] = []
    for size in (6, 5, 4, 3):
        for i in range(0, len(raw) - size + 1):
            seg = raw[i:i + size]
            if seg not in anchors:
                anchors.append(seg)
    return anchors[:8]


def check_dabai_consistency(
    db,
    project: Project,
    chapter: Chapter,
    *,
    plan_node: OutlineNode | None = None,
) -> dict[str, Any]:
    """返回 {consistency_pass, warnings[], blockers[]}。

    仅 DBC-01（境界倒退）为阻断项；地点/爽点只做高置信度提示，避免误报淹没作者。
    """
    warnings: list[dict] = []
    blockers: list[dict] = []

    if not plan_node:
        plan_node = resolve_chapter_plan(db, str(project.id), chapter)
    if not plan_node:
        return {"consistency_pass": True, "warnings": [], "blockers": [], "status": "ok"}

    extra = plan_node.extra or {}
    dabai = extra.get("dabai") or {}
    realm_rank = extra.get("realm_rank")
    plain = _plain_content(chapter)
    if not plain:
        return {"consistency_pass": True, "warnings": [], "blockers": [], "status": "ok"}

    realm_map = _realm_names(db, project)

    # DBC-01 境界词（阻断）
    if realm_rank and realm_rank in realm_map:
        lower_levels = [n.lower() for r, n in realm_map.items() if r < int(realm_rank) and n]
        for low in lower_levels:
            if low in plain:
                blockers.append({
                    "rule_id": "DBC-01",
                    "message": f"正文出现低于本章档位的境界「{low}」",
                })
                break

    # DBC-02 地点扫描已停用：正则扫正文误报率过高（如「坐落于青云山」「排山」），
    # 设定一致性暂以境界档位（DBC-01）为主；地点漂移交给复盘/人工审阅。

    # DBC-03 爽点：用 payoff/yaqu 短语锚点，不要求「群嘲反转」等类型标签出现在正文
    payoff = (dabai.get("shuang_payoff") or "").strip()
    yaqu = (dabai.get("yaqu_setup") or "").strip()
    if payoff and len(plain) >= 200:
        anchors = _payoff_keywords(payoff, yaqu)
        if anchors and not any(a in plain for a in anchors):
            warnings.append({
                "rule_id": "DBC-03",
                "message": "正文与章纲爽点/憋屈描述关联较弱（可忽略，以人工审阅为准）",
            })

    passed = not blockers
    if not passed:
        score = 40
    elif warnings:
        score = 90
    else:
        score = 100
    return {
        "consistency_pass": passed,
        "warnings": warnings,
        "blockers": blockers,
        "status": "blocked" if blockers else ("warning" if warnings else "ok"),
        "overall_score": score,
    }
