"""dabai 卷章纲懒展开：爽点节拍 + 境界/地图硬约束。"""
from __future__ import annotations

import logging
from typing import Any

from dabai.config import DabaiConfig
from dabai.linter import lint_chapters

from app.models import OutlineNode, Project
from app.services.bootstrap.chapter_plan_batches import chapter_plan_batch_ranges, log_chapter_plan_batches
from app.services.bootstrap.chapter_plan_guard import existing_chapter_sort_orders
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts.dabai_prompts import build_chapter_plans_dabai_prompt
from app.services.llm_token_budgets import max_tokens_vol_expand_chapters
from app.services.outline_quality.contract import Issue, IssueSet
from app.services.outline_quality.issue_log import record_issue_set
from app.utils.chapter_numbering import normalize_chapter_plan_title

logger = logging.getLogger(__name__)


def _tail_of(batch: list[dict]) -> str:
    if not batch:
        return ""
    last = batch[-1]
    return (last.get("end_hook") or last.get("shuang_payoff") or "").strip()


def _realm_max(ctx: dict) -> int | None:
    names = ctx.get("power_level_names") or []
    return len(names) if names else None


def _enforce_realm(batch: list[dict], running: int, vr_hi: int | None, rmax: int | None) -> int:
    cap = min([x for x in (vr_hi, rmax) if x] or [10 ** 9])
    for ch in batch:
        rr = ch.get("realm_rank")
        rr = rr if isinstance(rr, int) and rr >= running else running
        rr = min(int(rr), cap)
        ch["realm_rank"] = rr
        running = rr
    return running


def _vol_dict(volume_node: OutlineNode) -> dict:
    extra = volume_node.extra if isinstance(volume_node.extra, dict) else {}
    return {
        "title": volume_node.title,
        "phase": volume_node.phase,
        "planned_chapters": extra.get("planned_chapters", 30),
        "realm_start_rank": extra.get("realm_start_rank"),
        "realm_end_rank": extra.get("realm_end_rank"),
        "world_map": extra.get("world_map") or {},
        "big_beats": extra.get("big_beats"),
        "volume_climax": extra.get("volume_climax"),
    }


def _chapter_display_title(ch: dict) -> str:
    """章名：优先 AI title，否则从爽感/憋屈句截取。"""
    raw = (ch.get("title") or "").strip()
    if raw:
        return raw
    payoff = (ch.get("shuang_payoff") or "").strip()
    if payoff:
        return payoff[:28] + ("…" if len(payoff) > 28 else "")
    yaqu = (ch.get("yaqu_setup") or "").strip()
    if yaqu:
        return yaqu[:28] + ("…" if len(yaqu) > 28 else "")
    return "未命名"


def _persist_dabai_linter_to_volume(volume_node: OutlineNode, report) -> None:
    """将 dabai linter 结果写入 volume.extra，供大纲页 VolumeLinterPanel 消费。"""
    from sqlalchemy.orm.attributes import flag_modified

    extra = dict(volume_node.extra or {})
    issues = []
    for i in report.issues:
        issues.append({
            "rule_id": i.rule_id,
            "severity": i.severity,
            "scope": "chapter" if i.chapter else "volume",
            "message": i.message,
            "suggestion": i.suggestion or "",
            "chapter_number_in_volume": i.chapter,
        })
    critical = sum(1 for x in issues if x["severity"] == "critical")
    high = sum(1 for x in issues if x["severity"] == "high")
    extra["linter_version"] = "dabai-v1"
    extra["linter_status"] = report.status
    extra["linter_issues"] = issues
    extra["linter_summary"] = {
        "issue_count": len(issues),
        "critical_count": critical,
        "high_count": high,
    }
    if report.blocked:
        extra["linter_blocked"] = True
        from app.services.outline_linter.user_facing import build_linter_block_payload

        extra["linter_user_message"] = build_linter_block_payload(
            {
                "status": report.status,
                "issue_count": len(issues),
                "critical_count": critical,
                "high_count": high,
                "issues": issues,
            },
            chapter_count=len(issues),
        ).get("linter_message", "")
    else:
        extra.pop("linter_blocked", None)
        extra.pop("linter_user_message", None)
    volume_node.extra = extra
    try:
        flag_modified(volume_node, "extra")
    except (AttributeError, TypeError):
        pass


def _dabai_lint_to_issue_set(
    report, *, volume_node_id: str, chapters: list[dict],
) -> IssueSet:
    issues = []
    for i in report.issues:
        issues.append(Issue(
            rule_id=i.rule_id,
            severity=i.severity,
            dimension="dabai_beat" if i.rule_id.startswith("DB") else "realm_spine",
            message=i.message,
            suggestion=i.suggestion or "",
            chapter_number=i.chapter,
            scope="chapter" if i.chapter else "volume",
        ))
    return IssueSet(volume_node_id=volume_node_id, issues=issues)


async def gen_vol_chapter_plans_dabai(
    svc: Any,
    project: Project,
    volume_node: OutlineNode,
    ctx: dict,
    *,
    written_summaries: list[str] | None = None,
    open_promises: list | None = None,
    memory_chunks: list[str] | None = None,
    editorial_prompt_block: str = "",
    chapter_from: int = 1,
    chapter_to: int | None = None,
    seed_nodes: list[OutlineNode] | None = None,
) -> list[OutlineNode]:
    """大白文章纲展开：分批 LLM + realm 硬保证 + dabai linter 落台账。"""
    del written_summaries, open_promises, memory_chunks, editorial_prompt_block
    if volume_node.node_type != "volume":
        raise ValueError("volume_node 必须为 volume")

    vol = _vol_dict(volume_node)
    planned = int(vol.get("planned_chapters") or 30)
    chapter_to = chapter_to if chapter_to is not None else planned
    chapter_from = max(1, min(chapter_from, planned))
    chapter_to = max(chapter_from, min(chapter_to, planned))

    vol_extra = volume_node.extra or {}
    vr_lo = int(vol_extra.get("realm_start_rank") or 1)
    vr_hi = vol_extra.get("realm_end_rank") or _realm_max(ctx)
    rmax = _realm_max(ctx)

    all_results: list[OutlineNode] = list(seed_nodes or [])
    occupied = existing_chapter_sort_orders(svc.db, volume_node.id)
    running = vr_lo
    prev_tail = ""

    if seed_nodes:
        last_extra = (seed_nodes[-1].extra or {}) if seed_nodes else {}
        running = int(last_extra.get("realm_rank") or vr_lo)
        prev_tail = (seed_nodes[-1].highlight or "") if seed_nodes else ""

    completion_budget = max_tokens_vol_expand_chapters()
    ranges = [
        (max(bs, chapter_from), min(be, chapter_to))
        for bs, be in chapter_plan_batch_ranges(planned, completion_budget)
        if be >= chapter_from and bs <= chapter_to
    ]
    log_chapter_plan_batches(
        logger, tag="dabai_vol_chapters", planned=planned,
        ranges=ranges, max_completion_tokens=completion_budget,
    )

    accumulated_dicts: list[dict] = []

    for batch_start, batch_end in ranges:
        system, prompt = build_chapter_plans_dabai_prompt(
            ctx,
            vol=vol,
            batch_start=batch_start,
            batch_end=batch_end,
            prev_tail=prev_tail,
            realm_floor=running,
        )
        raw = await svc._call_with_retry(
            system, prompt, task="bootstrap.dabai_vol_chapters",
            max_tokens=completion_budget,
        )
        batch = parse_json(raw)
        if not isinstance(batch, list):
            batch = batch.get("chapters", []) if isinstance(batch, dict) else []
        for i, ch in enumerate(batch):
            if isinstance(ch, dict):
                ch["chapter_number"] = batch_start + i
        running = _enforce_realm(batch, running, vr_hi, rmax)
        prev_tail = _tail_of(batch)
        accumulated_dicts.extend(batch)

        for ch in batch:
            if not isinstance(ch, dict):
                continue
            ch_num = int(ch.get("chapter_number") or 1)
            sort_order = ch_num - 1
            if sort_order in occupied:
                continue
            extra = {
                "bootstrap_mode": "dabai",
                "realm_rank": ch.get("realm_rank"),
                "location_name": ch.get("location_name"),
                "dabai": {
                    "shuang_type": ch.get("shuang_type"),
                    "yaqu_setup": ch.get("yaqu_setup"),
                    "emotion_turn": ch.get("emotion_turn"),
                    "yinbao": ch.get("yinbao"),
                    "shuang_payoff": ch.get("shuang_payoff"),
                    "witnesses": ch.get("witnesses") or [],
                    "new_info_count": ch.get("new_info_count", 1),
                    "is_big_beat": ch.get("is_big_beat", False),
                },
            }
            node = OutlineNode(
                project_id=project.id,
                parent_id=volume_node.id,
                node_type="chapter_plan",
                title=normalize_chapter_plan_title(ch_num, _chapter_display_title(ch)),
                summary=ch.get("shuang_payoff") or ch.get("yaqu_setup"),
                hook=(ch.get("end_hook") or "").strip() or None,
                highlight=(ch.get("end_hook") or "").strip() or None,
                phase=volume_node.phase,
                expected_words=int(ch.get("expected_words") or 2000),
                sort_order=sort_order,
                extra=extra,
            )
            svc.db.add(node)
            all_results.append(node)
        svc.db.commit()

    gf_name = (project.extra or {}).get("golden_finger", {}).get("name", "")
    cfg = DabaiConfig()
    ch_dicts = [
        {
            "chapter_number": n.sort_order + 1,
            **((n.extra or {}).get("dabai") or {}),
            "realm_rank": (n.extra or {}).get("realm_rank"),
            "end_hook": n.highlight,
        }
        for n in all_results if n.node_type == "chapter_plan"
    ]
    report = lint_chapters(
        ch_dicts, cfg,
        realm_max=rmax,
        realm_range=(vr_lo, vr_hi),
        volumes=[vol],
        golden_finger_name=gf_name,
    )
    issue_set = _dabai_lint_to_issue_set(
        report, volume_node_id=str(volume_node.id), chapters=ch_dicts,
    )
    record_issue_set(svc.db, project.id, issue_set)
    _persist_dabai_linter_to_volume(volume_node, report)
    svc.db.commit()
    if report.blocked:
        logger.warning(
            "dabai vol_chapters linter blocked project=%s volume=%s issues=%d",
            project.id, volume_node.id, len(report.issues),
        )
    return all_results
