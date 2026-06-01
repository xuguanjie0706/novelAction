import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database import get_db
from app.models import (
    Chapter,
    ChapterCoherenceReport,
    ChapterIndex,
    Character,
    MemoryChunk,
    Project,
    StoryLine,
    WorldSetting,
    ChapterVersion,
)
from app.services.ai_service import AIService
from app.utils.chapter_numbering import display_chapter_number
from app.routers.ai.constants import _MAX_COHERENCE_APPLY_CHAPTERS
from app.routers.ai.context import format_world_setting_context
from app.routers.ai.schemas import (
    ChapterCoherenceApplyCommitRequest,
    ChapterCoherenceApplyPreviewRequest,
    ChapterCoherenceCheckRequest,
    CoherenceApplyFocusSelection,
    SaveChapterCoherenceReportRequest,
)
from app.routers.ai.text_utils import plain_text, truncate

router = APIRouter()


def _merge_coherence_with_focus(result: dict, sel: CoherenceApplyFocusSelection) -> dict:
    """用勾选下标过滤列表型字段；scores/summary 等保留原报告。"""
    out = dict(result)
    issues = list(result.get("cross_chapter_issues") or [])
    sugs = list(result.get("suggestions") or [])
    evs = list(result.get("chapter_evaluations") or [])

    def pick(arr: list, indices: list) -> list:
        idxs = sorted({i for i in indices if isinstance(i, int) and i >= 0})
        return [arr[i] for i in idxs if i < len(arr)]

    out["cross_chapter_issues"] = pick(issues, sel.cross_chapter_issue_indices)
    out["suggestions"] = pick(sugs, sel.suggestion_indices)
    out["chapter_evaluations"] = pick(evs, sel.chapter_evaluation_indices)
    return out


def _count_focus_items(d: dict) -> int:
    return len(d.get("cross_chapter_issues") or []) + len(d.get("suggestions") or []) + len(d.get("chapter_evaluations") or [])


@router.post("/chapter-coherence-check")
async def chapter_coherence_check(
    project_id: str,
    req: ChapterCoherenceCheckRequest,
    db: Session = Depends(get_db),
):
    if len(req.chapter_ids) < 2:
        raise HTTPException(400, "至少选择2个章节进行连贯性检测")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    chapters = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.id.in_(req.chapter_ids),
    ).all()
    if len(chapters) != len(set(req.chapter_ids)):
        raise HTTPException(400, "存在无效章节ID，或章节不属于当前小说")

    chapters = sorted(chapters, key=lambda c: c.sort_order)
    sort_orders = [c.sort_order for c in chapters]
    min_so = min(sort_orders)
    max_so = max(sort_orders)

    project_context_parts = []
    if project.premise:
        project_context_parts.append(f"作品基本面：{truncate(project.premise, 4000)}")

    settings = db.query(WorldSetting).filter(WorldSetting.project_id == project_id).all()
    if settings:
        setting_limit = 60
        setting_len = 1200
        project_context_parts.append(
            "世界观设定：\n" + "\n".join(
                f"- {format_world_setting_context(s, content_limit=setting_len)}"
                for s in settings[:setting_limit]
            )
        )

    characters = db.query(Character).filter(Character.project_id == project_id).all()
    if characters:
        char_limit = 80
        project_context_parts.append(
            "人物状态：\n" + "\n".join(
                f"- {c.name}: 境界={c.current_realm or '未知'}；位置={c.current_location or '未知'}；"
                f"状态={c.current_status or 'alive'}；动机={truncate(c.motivation, 180)}"
                for c in characters[:char_limit]
            )
        )

    storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["planned", "active", "climax"]),
    ).order_by(StoryLine.sort_order).all()
    if storylines:
        storyline_limit = 50
        project_context_parts.append(
            "故事线进度：\n" + "\n".join(
                f"- {s.name}（{s.status}）：{truncate(s.core_conflict or s.description, 500)}；"
                f"关键节拍={json.dumps(s.key_beats or [], ensure_ascii=False)[:1600]}"
                for s in storylines[:storyline_limit]
            )
        )

    index_rows = (
        db.query(ChapterIndex, Chapter)
        .join(Chapter, Chapter.id == ChapterIndex.chapter_id)
        .filter(
            ChapterIndex.project_id == project_id,
            Chapter.project_id == project_id,
            Chapter.sort_order <= max_so,
        )
        .order_by(Chapter.sort_order)
        .all()
    )
    if index_rows:
        index_window = list(index_rows)
        project_context_parts.append(
            "章节索引与伏笔：\n" + "\n".join(
                f"- 第{display_chapter_number(ch.title, ch.sort_order)}章：核心事件={json.dumps(idx.core_events or [], ensure_ascii=False)[:700]}; "
                f"章末钩子={idx.ending_hook or ''}; "
                f"未回收/已回收伏笔={json.dumps(idx.actual_foreshadows_laid or [], ensure_ascii=False)[:700]} / "
                f"{json.dumps(idx.actual_foreshadows_resolved or [], ensure_ascii=False)[:700]}"
                for idx, ch in index_window
            )
        )

    memory_rows = (
        db.query(MemoryChunk, Chapter)
        .join(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(
            MemoryChunk.project_id == project_id,
            Chapter.project_id == project_id,
            Chapter.sort_order <= max_so,
        )
        .order_by(Chapter.sort_order.desc())
        .limit(100)
        .all()
    )
    if memory_rows:
        project_context_parts.append(
            "记忆库：\n" + "\n".join(
                f"- 第{display_chapter_number(ch.title, ch.sort_order)}章 {m.title or m.memory_type}: {truncate(m.content, 700)}"
                for m, ch in memory_rows
            )
        )

    project_context = "\n\n".join(project_context_parts)
    payload = [
        {
            "id": str(c.id),
            "sort_order": c.sort_order,
            "title": c.title,
            "content": c.content or "",
        }
        for c in chapters
    ]

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    result = await svc.chapter_coherence_check(
        project_title=project.title,
        chapters=payload,
        project_context=project_context,
    )
    result["selected_chapter_count"] = len(payload)
    result["selected_chapter_ids"] = [p["id"] for p in payload]
    return result


@router.post("/chapter-coherence-reports")
def save_chapter_coherence_report(
    project_id: str,
    req: SaveChapterCoherenceReportRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    if len(req.selected_chapter_ids) < 2:
        raise HTTPException(400, "至少选择2个章节才能保存检测记录")

    chapter_count = len(req.selected_chapter_ids)
    report = ChapterCoherenceReport(
        project_id=project_id,
        name=(req.name or f"连贯性检测（{chapter_count}章）").strip()[:200],
        model_profile=req.model_profile,
        selected_chapter_ids=req.selected_chapter_ids,
        result=req.result or {},
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {
        "id": str(report.id),
        "name": report.name,
        "model_profile": report.model_profile,
        "selected_chapter_ids": report.selected_chapter_ids,
        "result": report.result,
        "apply_events": report.apply_events or [],
        "created_at": report.created_at,
    }


@router.get("/chapter-coherence-reports")
def list_chapter_coherence_reports(
    project_id: str,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    safe_limit = 1 if limit < 1 else (100 if limit > 100 else limit)
    reports = (
        db.query(ChapterCoherenceReport)
        .filter(ChapterCoherenceReport.project_id == project_id)
        .order_by(ChapterCoherenceReport.created_at.desc())
        .limit(safe_limit)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "model_profile": r.model_profile,
            "selected_chapter_ids": r.selected_chapter_ids or [],
            "result": r.result or {},
            "apply_events": r.apply_events or [],
            "created_at": r.created_at,
        }
        for r in reports
    ]


@router.post("/chapter-coherence-apply/preview")
async def chapter_coherence_apply_preview(
    project_id: str,
    req: ChapterCoherenceApplyPreviewRequest,
    db: Session = Depends(get_db),
):
    """
    根据已保存的连贯性评测记录，调用模型生成「最小幅度」正文修订预览（不写库）。
    远程 Gemini 建议一次处理多章；本地模型按章顺序调用。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    report = (
        db.query(ChapterCoherenceReport)
        .filter(
            ChapterCoherenceReport.id == req.report_id,
            ChapterCoherenceReport.project_id == project_id,
        )
        .first()
    )
    if not report:
        raise HTTPException(404, "评测记录不存在或不属于当前项目")

    result = report.result if isinstance(report.result, dict) else {}
    if result.get("error"):
        raise HTTPException(400, "该评测记录解析失败，无法用于修订正文")

    coherence_for_apply = result
    if req.focus_selection is not None:
        coherence_for_apply = _merge_coherence_with_focus(result, req.focus_selection)
        if _count_focus_items(coherence_for_apply) == 0:
            raise HTTPException(400, "请至少勾选一项评测条目（跨章风险、建议或章节点评）再生成修订预览")

    raw_ids = report.selected_chapter_ids or []
    if len(raw_ids) < 2:
        raise HTTPException(400, "该评测记录章节数不足")
    if len(raw_ids) > _MAX_COHERENCE_APPLY_CHAPTERS:
        raise HTTPException(
            400,
            f"一次最多修订 {_MAX_COHERENCE_APPLY_CHAPTERS} 章，请拆分评测记录后再试",
        )

    chapters = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.id.in_(raw_ids))
        .all()
    )
    if len(chapters) != len(set(raw_ids)):
        raise HTTPException(400, "记录中的章节已不存在或不属于本项目，无法修订")

    order = {str(cid): i for i, cid in enumerate(raw_ids)}
    chapters = sorted(chapters, key=lambda c: order.get(str(c.id), 9999))

    payload = [
        {
            "id": str(c.id),
            "sort_order": c.sort_order,
            "title": c.title,
            "content": c.content or "",
        }
        for c in chapters
    ]

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    try:
        rows = await svc.apply_coherence_revisions(
            project_title=project.title,
            coherence=coherence_for_apply,
            chapters=payload,
            focus_keywords=req.focus_keywords,
            revision_note=req.revision_note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e

    out = []
    for row in rows:
        cid = row.get("chapter_id")
        ch = next((c for c in chapters if str(c.id) == str(cid)), None)
        title = ch.title if ch else ""
        unchanged = bool(row.get("unchanged"))
        revised = (row.get("revised_content") or "").strip()
        orig = (ch.content or "") if ch else ""
        out.append(
            {
                "chapter_id": str(cid),
                "chapter_title": title,
                "unchanged": unchanged or not revised,
                "change_note": row.get("change_note") or "",
                "revised_content": "" if unchanged or not revised else revised,
                "previous_plain": plain_text(orig),
                "previous_plain_preview": plain_text(orig)[:320],
                "revised_plain_preview": plain_text(revised if revised else orig)[:320],
            }
        )

    return {
        "report_id": str(report.id),
        "revisions": out,
    }


@router.post("/chapter-coherence-apply/commit")
def chapter_coherence_apply_commit(
    project_id: str,
    req: ChapterCoherenceApplyCommitRequest,
    db: Session = Depends(get_db),
):
    """将预览阶段返回的修订写入章节正文（每条须有非空 revised_content）。"""
    from app.routers.chapters import count_words, normalize_chapter_sort_orders

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    report = (
        db.query(ChapterCoherenceReport)
        .filter(
            ChapterCoherenceReport.id == req.report_id,
            ChapterCoherenceReport.project_id == project_id,
        )
        .first()
    )
    if not report:
        raise HTTPException(404, "评测记录不存在或不属于当前项目")

    allowed = {str(x) for x in (report.selected_chapter_ids or [])}
    applied = []
    for item in req.revisions:
        cid = str(item.chapter_id)
        if cid not in allowed:
            raise HTTPException(400, f"章节 {cid} 不在该评测记录所选范围内")
        text = (item.revised_content or "").strip()
        if not text:
            continue
        chapter = (
            db.query(Chapter)
            .filter(Chapter.id == cid, Chapter.project_id == project_id)
            .first()
        )
        if not chapter:
            raise HTTPException(404, f"章节不存在: {cid}")
        if (chapter.content or "").strip() == text:
            applied.append({"chapter_id": cid, "skipped": True, "reason": "与当前正文相同"})
            continue

        snap_wc = count_words(chapter.content or "")
        snap = ChapterVersion(
            chapter_id=chapter.id,
            content=chapter.content,
            word_count=snap_wc,
            note="连贯性评测修订前快照",
            is_auto=True,
        )
        db.add(snap)
        chapter.content = text
        chapter.word_count = count_words(text)
        applied.append({"chapter_id": cid, "skipped": False, "word_count": chapter.word_count})

    if applied:
        events = list(report.apply_events) if report.apply_events else []
        events.append(
            {
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "applied": applied,
            }
        )
        report.apply_events = events

    db.commit()
    db.refresh(report)
    normalize_chapter_sort_orders(db, project_id)
    return {
        "report_id": str(req.report_id),
        "applied": applied,
        "apply_events": report.apply_events or [],
    }
