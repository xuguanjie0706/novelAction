"""大纲质检 / 修复工作流内部步骤（供 ``routes_quality`` 注册为后台任务与图节点）。"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Character,
    Faction,
    Foreshadow,
    Item,
    OutlineNode,
    OutlineRevision,
    PowerSystem,
    Project,
    Skill,
    StoryLine,
    WorldSetting,
)
from app.services.ai_service import AIService
from app.services.outline_planning import (
    TARGET_CHAPTERS_PER_VOLUME,
    TARGET_WORDS_PER_CHAPTER,
    normalize_volume_plan,
)
from app.services.workflow_graph import WorkflowGraph, WorkflowNode, workflow_runs

from app.routers.outline.helpers_core import *
from app.routers.outline.schemas import OutlineQualityCheckRequest, OutlineRepairRequest

async def _noop_outline_progress(_: dict[str, Any]) -> None:
    return None


async def _prepare_outline_quality_context(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    req: OutlineQualityCheckRequest = ctx["req"]

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    chapters = _load_existing_chapter_context(db, project_id, limit=1000)
    if not chapters:
        raise HTTPException(400, "当前项目还没有可质检的章节计划")

    story_core = project.story_core if isinstance(project.story_core, dict) else {}
    theme_statement = (req.theme_statement or story_core.get("theme") or "").strip()

    volume_nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.parent_id.is_(None),
        OutlineNode.node_type == "volume",
    ).order_by(OutlineNode.sort_order).all()
    global_outline_context = _format_global_outline_context([
        (
            node,
            (node.extra or {}).get("target_chapters", TARGET_CHAPTERS_PER_VOLUME)
            if isinstance(node.extra, dict)
            else TARGET_CHAPTERS_PER_VOLUME,
        )
        for node in volume_nodes
    ])

    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id,
    ).order_by(WorldSetting.created_at).all()
    characters = db.query(Character).filter(
        Character.project_id == project_id,
    ).order_by(Character.role, Character.created_at).all()
    storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
    ).order_by(StoryLine.sort_order, StoryLine.created_at).all()
    power_systems = db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id,
    ).order_by(PowerSystem.sort_order, PowerSystem.created_at).all()
    factions = db.query(Faction).filter(
        Faction.project_id == project_id,
    ).order_by(Faction.sort_order, Faction.created_at).all()
    items = db.query(Item).filter(
        Item.project_id == project_id,
    ).order_by(Item.sort_order, Item.created_at).all()
    skills = db.query(Skill).filter(
        Skill.project_id == project_id,
    ).order_by(Skill.sort_order, Skill.created_at).all()
    foreshadows = db.query(Foreshadow).filter(
        Foreshadow.project_id == project_id,
    ).order_by(Foreshadow.priority.desc(), Foreshadow.created_at).all()

    story_bible_context = _format_outline_quality_story_bible(
        project=project,
        settings=settings,
        characters=characters,
        storylines=storylines,
        power_systems=power_systems,
        factions=factions,
        items=items,
        skills=skills,
        foreshadows=foreshadows,
    )
    book_word_budget_context = _format_outline_word_budget_context(
        target_words=project.target_words,
        chapter_count=len(chapters),
        scope_label="全书",
    )

    return {
        **ctx,
        "project": project,
        "chapters": chapters,
        "theme_statement": theme_statement,
        "volume_nodes": volume_nodes,
        "global_outline_context": global_outline_context,
        "story_bible_context": story_bible_context,
        "book_word_budget_context": book_word_budget_context,
        "volume_reports": [],
        "power_systems": power_systems,
        "characters": characters,
        "foreshadows": foreshadows,
        "premise": project.premise or "",
    }


async def _quality_check_outline_volumes(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    req: OutlineQualityCheckRequest = ctx["req"]
    project: Project = ctx["project"]
    chapters: list[dict] = ctx["chapters"]
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress
    volume_nodes: list[OutlineNode] = ctx["volume_nodes"]
    if req.volume_node_id:
        volume_nodes = [node for node in volume_nodes if str(node.id) == str(req.volume_node_id)]
        if not volume_nodes:
            raise HTTPException(404, "Volume node not found")
    volume_reports: list[dict] = []

    if not volume_nodes:
        await publish({
            "event": "progress",
            "step": 1,
            "total": 3,
            "label": "未发现卷节点，跳过单卷大纲质检。",
            "done": True,
            "outline_quality_scope": "volume",
        })
        return {**ctx, "volume_reports": []}

    for index, volume in enumerate(volume_nodes, start=1):
        volume_chapters = _load_volume_chapter_context(db, project_id, volume)
        if not volume_chapters:
            await publish({
                "event": "progress",
                "step": index,
                "total": len(volume_nodes),
                "label": f"《{volume.title}》没有章节计划，跳过卷内质检。",
                "done": True,
                "outline_quality_scope": "volume",
                "progress_key": f"outline-quality-volume-{volume.id}",
            })
            continue

        first_number = _chapter_number_value(volume_chapters[0])
        previous_chapters = [
            chapter for chapter in chapters
            if _chapter_number_value(chapter) < first_number
        ]
        await publish({
            "event": "progress",
            "step": index,
            "total": len(volume_nodes),
            "label": f"正在质检《{volume.title}》卷内大纲…",
            "done": False,
            "outline_quality_scope": "volume",
            "progress_key": f"outline-quality-volume-{volume.id}",
        })

        hard_rule_report = _detect_outline_hard_rule_issues(
            volume_chapters,
            power_systems=ctx.get("power_systems"),
            genre=project.genre or "玄幻",
            scope="volume",
            characters=ctx.get("characters"),
            theme_statement=ctx.get("theme_statement", ""),
            premise=ctx.get("premise", ""),
            foreshadows=ctx.get("foreshadows"),
        )
        embedding_report = await analyze_outline_embedding_duplicates(
            volume_chapters,
            scope="volume",
        )
        hard_rule_report = _merge_outline_quality_reports(hard_rule_report, embedding_report)
        vol_max_ch = max((_chapter_number_value(c) for c in volume_chapters), default=0)
        overdue_ledger = _build_overdue_foreshadow_ledger(
            ctx.get("foreshadows") or [],
            vol_max_ch,
            max_chars=1800 if req.model_profile == "gemini" else 800,
        )
        svc = AIService(profile=req.model_profile, db=db, llm_provider_id=req.llm_provider_id)
        report = await svc.outline_quality_check(
            project_title=project.title,
            genre=project.genre or "玄幻",
            scope="volume",
            node_title=volume.title,
            node_summary=volume.summary or "",
            theme_statement=ctx["theme_statement"],
            story_bible_context=ctx["story_bible_context"],
            global_outline_context=ctx["global_outline_context"],
            previous_chapters_context=_format_previous_chapters_context(
                previous_chapters,
                max_items=24 if req.model_profile == "gemini" else 8,
            ),
            continuity_state=_format_rolling_continuity_state([
                *previous_chapters[-8:],
                *volume_chapters,
            ]),
            chapters=volume_chapters,
            word_budget_context="\n".join([
                ctx.get("book_word_budget_context", ""),
                _format_outline_word_budget_context(
                    target_words=(
                        ((volume.extra or {}).get("target_chapters") if isinstance(volume.extra, dict) else None)
                        or TARGET_CHAPTERS_PER_VOLUME
                    ) * TARGET_WORDS_PER_CHAPTER,
                    chapter_count=len(volume_chapters),
                    scope_label=f"卷《{volume.title}》",
                ),
            ]),
            overdue_foreshadow_ledger=overdue_ledger,
        )
        if svc._truncation_warnings:
            await publish({
                "event": "truncation_warning",
                "label": f"⚠️ 质检《{volume.title}》时部分上下文被截断，结果可能不完整",
                "details": svc._truncation_warnings,
            })
        report = _merge_outline_quality_reports(report, hard_rule_report)
        volume.extra = _with_outline_quality(volume, report)
        db.add(volume)
        db.commit()
        _create_quality_revision(
            db,
            project_id=project_id,
            scope="volume",
            report=report,
            volume_node=volume,
        )

        volume_report = {
            "node_id": str(volume.id),
            "title": volume.title,
            "report": report,
        }
        volume_reports.append(volume_report)
        await publish({
            "event": "progress",
            "step": index,
            "total": len(volume_nodes),
            "label": _format_outline_quality_label(volume.title, report, "volume"),
            "done": True,
            "error": bool(report.get("error")),
            "outline_quality_scope": "volume",
            "outline_quality_report": report,
            "progress_key": f"outline-quality-volume-{volume.id}",
        })

    return {**ctx, "volume_reports": volume_reports}


async def _quality_check_outline_book(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    project: Project = ctx["project"]
    chapters: list[dict] = ctx["chapters"]
    req: OutlineQualityCheckRequest = ctx["req"]
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress

    await publish({
        "event": "progress",
        "step": "book",
        "total": "book",
        "label": "正在质检全书大纲…",
        "done": False,
        "outline_quality_scope": "book",
        "progress_key": "outline-quality-book",
    })
    hard_rule_report = _detect_outline_hard_rule_issues(
        chapters,
        power_systems=ctx.get("power_systems"),
        genre=project.genre or "玄幻",
        scope="book",
        characters=ctx.get("characters"),
        theme_statement=ctx.get("theme_statement", ""),
        premise=ctx.get("premise", ""),
        foreshadows=ctx.get("foreshadows"),
    )
    embedding_report = await analyze_outline_embedding_duplicates(
        chapters,
        scope="book",
    )
    hard_rule_report = _merge_outline_quality_reports(hard_rule_report, embedding_report)
    book_max_ch = max((_chapter_number_value(c) for c in chapters), default=0)
    book_overdue_ledger = _build_overdue_foreshadow_ledger(
        ctx.get("foreshadows") or [],
        book_max_ch,
        max_chars=2000 if req.model_profile == "gemini" else 1000,
    )
    svc = AIService(profile=req.model_profile, db=db, llm_provider_id=req.llm_provider_id)
    report = await svc.outline_quality_check(
        project_title=project.title,
        genre=project.genre or "玄幻",
        scope="book",
        node_title="全书大纲",
        node_summary=project.logline or "",
        theme_statement=ctx["theme_statement"],
        story_bible_context=ctx["story_bible_context"],
        global_outline_context=ctx["global_outline_context"],
        previous_chapters_context="",
        continuity_state=_format_book_quality_continuity_state(chapters),
        chapters=chapters,
        word_budget_context=ctx.get("book_word_budget_context", ""),
        overdue_foreshadow_ledger=book_overdue_ledger,
    )
    if svc._truncation_warnings:
        await publish({
            "event": "truncation_warning",
            "label": "⚠️ 全书质检时部分上下文被截断，结果可能不完整",
            "details": svc._truncation_warnings,
        })
    report = _merge_outline_quality_reports(report, hard_rule_report)

    current_core = project.story_core if isinstance(project.story_core, dict) else {}
    project.story_core = {
        **current_core,
        "outline_quality": report,
    }
    db.add(project)
    db.commit()
    _create_quality_revision(
        db,
        project_id=project_id,
        scope="book",
        report=report,
    )

    result = {
        **report,
        "volume_reports": ctx.get("volume_reports", []),
    }
    await publish({
        "event": "progress",
        "step": "book",
        "total": "book",
        "label": _format_outline_quality_label("全书大纲", report, "book"),
        "done": True,
        "error": bool(report.get("error")),
        "outline_quality_scope": "book",
        "outline_quality_report": report,
        "progress_key": "outline-quality-book",
    })
    return {
        **ctx,
        "book_report": report,
        "result": result,
    }


def _relevant_repair_chapters(chapters: list[dict], quality_report: dict) -> list[dict]:
    issue_numbers: set[int] = set()
    for issue in quality_report.get("issues", []) if isinstance(quality_report, dict) else []:
        for number in issue.get("chapter_numbers", []) if isinstance(issue, dict) else []:
            if isinstance(number, int):
                issue_numbers.add(number)
    for number in quality_report.get("must_fix_chapter_numbers", []) if isinstance(quality_report, dict) else []:
        if isinstance(number, int):
            issue_numbers.add(number)
    if not issue_numbers:
        return chapters
    return [chapter for chapter in chapters if _chapter_number_value(chapter) in issue_numbers]


async def _snapshot_outline_before_repair(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    req: OutlineRepairRequest = ctx["repair_req"]
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress
    revision = _create_outline_revision(
        db,
        project_id=project_id,
        label="修复前大纲快照",
        source="pre_repair",
        scope="volume" if req.scope == "volume" else "book",
        volume_node_id=req.volume_node_id if req.scope == "volume" else None,
        note="AI 大纲修复工作流自动保存",
        meta={"repair_scope": req.scope},
    )
    await publish({
        "event": "progress",
        "step": "snapshot_before",
        "label": f"已保存修复前快照：{revision.label}",
        "done": True,
        "revision_id": str(revision.id),
    })
    return {**ctx, "pre_revision_id": str(revision.id)}


async def _build_outline_repair_plan(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    req: OutlineRepairRequest = ctx["repair_req"]
    project: Project = ctx["project"]
    chapters: list[dict] = ctx["chapters"]
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress

    quality_report = ctx.get("book_report") or ctx.get("result") or {}
    if req.scope == "volume":
        reports = ctx.get("volume_reports", [])
        quality_report = reports[0]["report"] if reports else ctx.get("result", {})
        if req.volume_node_id:
            volume = db.query(OutlineNode).filter(
                OutlineNode.id == req.volume_node_id,
                OutlineNode.project_id == project_id,
            ).first()
            if volume:
                chapters = _load_volume_chapter_context(db, project_id, volume)
                if not quality_report:
                    volume_extra = volume.extra if isinstance(volume.extra, dict) else {}
                    quality_report = volume_extra.get("outline_quality") or {}
    elif req.scope == "book":
        if not quality_report:
            project_core = project.story_core if isinstance(project.story_core, dict) else {}
            quality_report = project_core.get("outline_quality") or {}

    relevant_chapters = _relevant_repair_chapters(chapters, quality_report)
    await publish({
        "event": "progress",
        "step": "repair_plan",
        "label": f"正在生成修复补丁（{len(relevant_chapters)} 个相关章节）…",
        "done": False,
    })
    svc = AIService(profile=req.model_profile, db=db, llm_provider_id=req.llm_provider_id)
    repair_plan = await svc.outline_repair_plan(
        project_title=project.title,
        genre=project.genre or "玄幻",
        scope=req.scope,
        quality_report=quality_report,
        chapters=relevant_chapters,
        story_bible_context=ctx["story_bible_context"],
        global_outline_context=ctx["global_outline_context"],
        word_budget_context=_format_outline_word_budget_context(
            target_words=project.target_words,
            chapter_count=len(chapters if req.scope == "book" else relevant_chapters),
            scope_label="修复范围",
        ),
    )
    # 截断警告：如果有字段被实际截断，推送提示给前端
    if svc._truncation_warnings:
        await publish({
            "event": "truncation_warning",
            "label": "⚠️ 部分上下文因长度过大被截断，修复质量可能受影响",
            "details": svc._truncation_warnings,
        })
    await publish({
        "event": "progress",
        "step": "repair_plan",
        "label": repair_plan.get("summary") or f"修复补丁生成完成：{len(repair_plan.get('patches', []))} 条",
        "done": True,
        "error": bool(repair_plan.get("error")),
        "repair_plan": repair_plan,
    })
    return {**ctx, "repair_plan": repair_plan, "repair_quality_report": quality_report}


async def _apply_outline_repair_plan(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    repair_plan = ctx.get("repair_plan") or {}
    patches = repair_plan.get("patches") if isinstance(repair_plan, dict) else []
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).all()
    by_number = {
        _outline_node_to_chapter_context(node).get("number"): node
        for node in nodes
    }
    records = []
    for patch in patches if isinstance(patches, list) else []:
        if not isinstance(patch, dict):
            continue
        node = by_number.get(patch.get("chapter_number"))
        if not node:
            continue
        records.append(_apply_outline_patch_to_node(node, patch))
        db.add(node)
    db.commit()
    await publish({
        "event": "progress",
        "step": "apply_patches",
        "label": f"已应用 {len(records)} 条大纲修复补丁",
        "done": True,
        "applied_patches": records,
    })
    return {**ctx, "applied_patches": records}


async def _snapshot_outline_after_repair(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    req: OutlineRepairRequest = ctx["repair_req"]
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress
    revision = _create_outline_revision(
        db,
        project_id=project_id,
        label="修复后大纲快照",
        source="post_repair",
        scope="volume" if req.scope == "volume" else "book",
        volume_node_id=req.volume_node_id if req.scope == "volume" else None,
        note="AI 大纲修复工作流自动保存",
        meta={
            "repair_scope": req.scope,
            "pre_revision_id": ctx.get("pre_revision_id"),
            "applied_patches": ctx.get("applied_patches", []),
            "repair_plan": ctx.get("repair_plan", {}),
        },
    )
    result = {
        "scope": req.scope,
        "status": "done",
        "summary": f"已应用 {len(ctx.get('applied_patches', []))} 条大纲修复补丁",
        "pre_revision_id": ctx.get("pre_revision_id"),
        "post_revision_id": str(revision.id),
        "applied_patches": ctx.get("applied_patches", []),
        "repair_plan": ctx.get("repair_plan", {}),
    }
    await publish({
        "event": "progress",
        "step": "snapshot_after",
        "label": f"已保存修复后快照：{revision.label}",
        "done": True,
        "revision_id": str(revision.id),
    })
    return {**ctx, "post_revision_id": str(revision.id), "result": result}


def _outline_quality_nodes_for_scope(scope: str) -> list[WorkflowNode]:
    nodes = [
        WorkflowNode("prepare_outline_context", "读取大纲与故事圣经账本", _prepare_outline_quality_context),
    ]
    if scope in {"all", "volume"}:
        nodes.append(WorkflowNode("quality_check_volumes", "单卷大纲质检并写回卷节点", _quality_check_outline_volumes))
    if scope in {"all", "book"}:
        nodes.append(WorkflowNode("quality_check_book", "全书大纲质检并写回项目", _quality_check_outline_book))
    return nodes


async def _finalize_outline_quality_result(ctx: dict[str, Any]) -> dict[str, Any]:
    req: OutlineQualityCheckRequest = ctx["req"]
    if req.scope == "book":
        return ctx
    if req.scope == "volume":
        reports = ctx.get("volume_reports", [])
        if len(reports) == 1:
            return {
                **ctx,
                "result": {
                    **reports[0]["report"],
                    "node_id": reports[0]["node_id"],
                    "title": reports[0]["title"],
                },
            }
        return {
            **ctx,
            "result": {
                "scope": "volume",
                "status": "pass" if reports else "warning",
                "summary": f"完成 {len(reports)} 个卷节点质检。",
                "volume_reports": reports,
            },
        }
    return ctx


async def _execute_outline_quality_graph(ctx: dict[str, Any]) -> dict[str, Any]:
    req: OutlineQualityCheckRequest = ctx["req"]
    graph = WorkflowGraph([
        *_outline_quality_nodes_for_scope(req.scope),
        WorkflowNode("finalize_outline_quality_result", "整理大纲质检结果", _finalize_outline_quality_result),
    ])
    current = dict(ctx)
    for node in graph.nodes:
        result = node.handler(current)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[assignment]
        if isinstance(result, dict):
            current = result
    return current


async def _run_outline_quality_workflow(run_id: str, project_id: str, req_payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        req = OutlineQualityCheckRequest(**req_payload)

        async def publish(event: dict[str, Any]) -> None:
            await workflow_runs.publish(run_id, event)

        graph = WorkflowGraph([
            *_outline_quality_nodes_for_scope(req.scope),
            WorkflowNode("finalize_outline_quality_result", "整理大纲质检结果", _finalize_outline_quality_result),
        ])
        await workflow_runs.run_graph(run_id, graph, {
            "db": db,
            "project_id": project_id,
            "req": req,
            "publish": publish,
        })
    finally:
        db.close()


async def _run_outline_repair_workflow(run_id: str, project_id: str, req_payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        repair_req = OutlineRepairRequest(**req_payload)
        quality_req = OutlineQualityCheckRequest(**req_payload)

        async def publish(event: dict[str, Any]) -> None:
            await workflow_runs.publish(run_id, event)

        graph = WorkflowGraph([
            WorkflowNode("snapshot_before_repair", "保存修复前大纲快照", _snapshot_outline_before_repair),
            WorkflowNode("prepare_outline_context_for_repair", "读取大纲与故事圣经账本（供修复补丁）", _prepare_outline_quality_context),
            WorkflowNode("build_outline_repair_plan", "生成大纲修复补丁", _build_outline_repair_plan),
            WorkflowNode("apply_outline_repair_plan", "应用大纲修复补丁", _apply_outline_repair_plan),
            WorkflowNode("snapshot_after_repair", "保存修复后大纲快照", _snapshot_outline_after_repair),
            *_outline_quality_nodes_for_scope(repair_req.scope),
            WorkflowNode("finalize_outline_quality_result", "整理修复后质检结果", _finalize_outline_quality_result),
        ])
        await workflow_runs.run_graph(run_id, graph, {
            "db": db,
            "project_id": project_id,
            "req": quality_req,
            "repair_req": repair_req,
            "publish": publish,
        })
    finally:
        db.close()

