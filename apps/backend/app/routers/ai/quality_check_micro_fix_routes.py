"""章节质检报告：按优化建议局部修改正文（非整章重写）。"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter
from app.routers.ai.micro_patch_apply import apply_micro_patch_to_chapter
from app.schemas.chapter import ChapterOut
from app.services.ai_service import AIService
from app.utils.chapter_manuscript import (
    html_to_plain_for_revision,
    split_plain_manuscript_and_index_block,
)

router = APIRouter()


class QualityCheckMicroFixRequest(BaseModel):
    chapter_id: UUID
    """为空时读取章节 ``last_quality_report``。"""
    suggestions: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    """聚焦单条建议时在列表中的下标（0-based）。"""
    focus_suggestion_index: int | None = None
    author_notes: str = ""
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: UUID | None = None


class QualityCheckMicroFixResponse(BaseModel):
    chapter: ChapterOut
    rationale: str = ""
    original_excerpt: str = ""
    replacement_excerpt: str = ""


def _normalize_suggestion_lines(raw: list) -> list[str]:
    lines: list[str] = []
    for item in raw or []:
        if isinstance(item, str) and item.strip():
            lines.append(item.strip())
        elif isinstance(item, dict):
            text = (
                str(item.get("description") or "")
                or str(item.get("comment") or "")
                or str(item.get("suggestion") or "")
                or str(item.get("summary") or "")
            ).strip()
            if text:
                lines.append(text)
    return lines


def _collect_fix_brief_from_report(report: dict, focus_index: int | None) -> tuple[str, str]:
    """从质检报告组装 problem_summary 与 fix_direction。"""
    suggestions = _normalize_suggestion_lines(report.get("suggestions") or [])
    issues: list[str] = []
    for issue in report.get("issues") or []:
        if isinstance(issue, dict):
            desc = str(issue.get("description") or issue.get("summary") or "").strip()
            if desc:
                issues.append(desc)
        elif isinstance(issue, str) and issue.strip():
            issues.append(issue.strip())

    dim_notes: list[str] = []
    for key, dim in (report.get("dimensions") or {}).items():
        if not isinstance(dim, dict):
            continue
        status = str(dim.get("status") or "")
        score = dim.get("score")
        try:
            score_f = float(score) if score is not None else 10.0
        except (TypeError, ValueError):
            score_f = 10.0
        if status in ("warning", "fail") or score_f < 7:
            comment = str(dim.get("comment") or "").strip()
            if comment:
                dim_notes.append(f"[{key}] {comment}")

    if focus_index is not None and 0 <= focus_index < len(suggestions):
        focus = suggestions[focus_index]
        problem = focus
        direction = focus
        context_parts = issues[:3] + dim_notes[:3]
        if context_parts:
            problem = f"{focus}\n\n相关上下文：\n" + "\n".join(f"- {p}" for p in context_parts)
        return problem, direction

    parts: list[str] = []
    if suggestions:
        parts.append("优化建议：\n" + "\n".join(f"- {s}" for s in suggestions[:6]))
    if issues:
        parts.append("问题项：\n" + "\n".join(f"- {i}" for i in issues[:6]))
    if dim_notes:
        parts.append("低分维度：\n" + "\n".join(f"- {n}" for n in dim_notes[:6]))
    summary = (report.get("summary") or "").strip()
    if summary:
        parts.insert(0, f"整体评价：{summary}")
    combined = "\n\n".join(parts).strip()
    if not combined:
        return "", ""
    return combined, suggestions[0] if suggestions else combined


@router.post("/quality-check-micro-fix", response_model=QualityCheckMicroFixResponse)
async def quality_check_micro_fix(
    project_id: str,
    req: QualityCheckMicroFixRequest,
    db: Session = Depends(get_db),
):
    """
    根据质检优化建议，由模型产出「original_excerpt → replacement_excerpt」，
    在**整章叙事纯文本**上校验唯一匹配后替换，再写回简单段落 HTML。
    """
    chapter = (
        db.query(Chapter)
        .filter(Chapter.id == req.chapter_id, Chapter.project_id == project_id)
        .first()
    )
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    plain = html_to_plain_for_revision(chapter.content)
    body, _index_block = split_plain_manuscript_and_index_block(plain)
    if not (body or "").strip():
        raise HTTPException(400, "章节叙事正文为空，无法进行局部微调")

    suggestions = [s.strip() for s in req.suggestions if s and s.strip()]
    issues = [i.strip() for i in req.issues if i and i.strip()]
    report = chapter.last_quality_report if isinstance(chapter.last_quality_report, dict) else {}

    if req.focus_suggestion_index is not None:
        if not suggestions:
            suggestions = _normalize_suggestion_lines(report.get("suggestions") or [])
        if not suggestions:
            raise HTTPException(400, "无可用优化建议可修复")
        problem, direction = _collect_fix_brief_from_report(
            {
                "suggestions": suggestions,
                "issues": issues or report.get("issues"),
                "dimensions": report.get("dimensions"),
            },
            req.focus_suggestion_index,
        )
    elif suggestions or issues:
        problem_parts: list[str] = []
        if suggestions:
            problem_parts.append("优化建议：\n" + "\n".join(f"- {s}" for s in suggestions[:6]))
        if issues:
            problem_parts.append("问题项：\n" + "\n".join(f"- {i}" for i in issues[:6]))
        problem = "\n\n".join(problem_parts)
        direction = suggestions[0] if suggestions else (issues[0] if issues else "")
    else:
        problem, direction = _collect_fix_brief_from_report(report, None)

    if not problem.strip():
        raise HTTPException(400, "请先完成章节质检，或传入优化建议后再试")

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    patch = await svc.quality_report_micro_patch(
        narrative_body=body,
        chapter_title=chapter.title or "",
        problem_summary=problem,
        fix_direction=direction,
        author_notes=req.author_notes or "",
    )

    if patch.get("error") and not (patch.get("original_excerpt") or "").strip():
        raise HTTPException(502, detail=f"模型调用失败：{patch.get('error')}")

    orig = (patch.get("original_excerpt") or "").strip()
    repl = (patch.get("replacement_excerpt") or "").strip()
    rationale = (patch.get("rationale") or "").strip()

    if not orig or not repl:
        raise HTTPException(
            422,
            detail={
                "message": "模型未给出可应用的摘录替换，请缩短建议范围、切换长上下文线路，或改用整章重写",
                "rationale": rationale or patch.get("error") or "",
            },
        )

    try:
        apply_micro_patch_to_chapter(
            db,
            chapter,
            original_excerpt=orig,
            replacement_excerpt=repl,
            snapshot_tag="quality_check_micro_patch",
            version_note="质检快速修复前自动备份",
        )
    except ValueError as exc:
        msg = str(exc)
        if "未找到" in msg:
            raise HTTPException(
                422,
                detail={
                    "message": "模型给出的原文摘录在正文中未找到（可能标点/空格不一致），请手动修改或改用整章重写",
                    "rationale": rationale,
                },
            ) from exc
        if "出现" in msg and "次" in msg:
            raise HTTPException(
                422,
                detail={
                    "message": msg + "；请缩短/加长摘录锚点或改用整章重写",
                    "rationale": rationale,
                },
            ) from exc
        raise HTTPException(400, detail=msg) from exc

    return QualityCheckMicroFixResponse(
        chapter=chapter,
        rationale=rationale,
        original_excerpt=orig,
        replacement_excerpt=repl,
    )
