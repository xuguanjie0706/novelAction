"""质量债务：局部摘录替换（微调正文，非整章流式重写）。"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from uuid import UUID

from app.database import get_db
from app.models import Chapter, ChapterVersion, QualityDebt
from app.routers.chapters import count_words
from app.schemas.chapter import ChapterOut
from app.routers.ai.quality_debt import resolve_chapter_for_quality_debt
from app.services.ai_service import AIService
from app.utils.chapter_manuscript import (
    html_to_plain_for_revision,
    plain_text_blocks_to_html,
    split_plain_manuscript_and_index_block,
)

router = APIRouter()


class QualityDebtMicroFixRequest(BaseModel):
    quality_debt_id: UUID
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: UUID | None = None


class QualityDebtMicroFixResponse(BaseModel):
    chapter: ChapterOut
    rationale: str = ""
    original_excerpt: str = ""
    replacement_excerpt: str = ""


@router.post("/quality-debt-micro-fix", response_model=QualityDebtMicroFixResponse)
async def quality_debt_micro_fix(
    project_id: str,
    req: QualityDebtMicroFixRequest,
    db: Session = Depends(get_db),
):
    """
    由模型产出「original_excerpt → replacement_excerpt」，在**整章叙事纯文本**上校验唯一匹配后替换，
    再写回简单段落 HTML（与续写/重写入库规则一致）。
    """
    debt = (
        db.query(QualityDebt)
        .filter(
            QualityDebt.project_id == project_id,
            QualityDebt.id == req.quality_debt_id,
        )
        .first()
    )
    if not debt:
        raise HTTPException(404, "Quality debt not found")
    if debt.status != "pending":
        raise HTTPException(400, "仅待处理债务可发起局部微调")

    chapter = resolve_chapter_for_quality_debt(db, project_id, debt)
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    plain = html_to_plain_for_revision(chapter.content)
    body, index_block = split_plain_manuscript_and_index_block(plain)
    if not (body or "").strip():
        raise HTTPException(400, "章节叙事正文为空，无法进行局部微调")

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    patch = await svc.quality_debt_micro_patch(
        narrative_body=body,
        chapter_title=chapter.title or "",
        debt_summary=debt.summary or "",
        suggested_fix=debt.suggested_fix or "",
        author_notes=debt.author_notes or "",
    )

    if patch.get("error") and not (patch.get("original_excerpt") or "").strip():
        raise HTTPException(
            502,
            detail=f"模型调用失败：{patch.get('error')}",
        )

    orig = (patch.get("original_excerpt") or "").strip()
    repl = (patch.get("replacement_excerpt") or "").strip()
    rationale = (patch.get("rationale") or "").strip()

    if not orig or not repl:
        raise HTTPException(
            422,
            detail={
                "message": "模型未给出可应用的摘录替换，请改用整章重写/续写，或切换长上下文线路后重试",
                "rationale": rationale or patch.get("error") or "",
            },
        )

    count = body.count(orig)
    if count == 0:
        raise HTTPException(
            422,
            detail={
                "message": "模型给出的原文摘录在正文中未找到（可能标点/空格不一致），请手动微调或改用整章重写",
                "rationale": rationale,
            },
        )
    if count > 1:
        raise HTTPException(
            422,
            detail={
                "message": f"摘录在正文中出现 {count} 次，无法安全自动替换；请缩短/加长摘录锚点或改用整章重写",
                "rationale": rationale,
            },
        )

    new_body = body.replace(orig, repl, 1)
    new_plain = new_body + (f"\n\n{index_block}" if index_block else "")
    new_html = plain_text_blocks_to_html(new_plain)

    snap_tail = f"\n\n--- quality_debt_micro_patch ---\n{orig}\n=>\n{repl}\n"
    prev_snap = (chapter.manuscript_raw_snapshot or "").strip()
    manuscript_raw_snapshot = (prev_snap + snap_tail).strip() if prev_snap else snap_tail.strip()

    try:
        if (chapter.content or "").strip():
            snap_wc = count_words(chapter.content or "")
            db.add(
                ChapterVersion(
                    chapter_id=chapter.id,
                    content=chapter.content,
                    word_count=snap_wc,
                    note="质量债务局部微调前自动备份",
                    is_auto=True,
                )
            )
            db.flush()
    except Exception:
        pass

    chapter.content = new_html
    chapter.word_count = count_words(new_html)
    chapter.manuscript_raw_snapshot = manuscript_raw_snapshot[:200000]
    debt.status = "resolved"
    db.commit()
    db.refresh(chapter)
    db.refresh(debt)

    return QualityDebtMicroFixResponse(
        chapter=chapter,
        rationale=rationale,
        original_excerpt=orig,
        replacement_excerpt=repl,
    )
