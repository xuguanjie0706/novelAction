"""大白文（爽点节拍器）独立分支 API。

路由前缀 /api/v1/dabai，与精品文链路完全隔离。生成走独立 dabai 模块 pipeline。

端点：
  POST   /dabai/projects            一句话 → 生成 + 落库（非流式），返回详情
  POST   /dabai/projects/stream     SSE 流式生成：边生成边落库 + 推 8 步进度
  GET    /dabai/projects            当前用户的大白文列表
  GET    /dabai/projects/{id}       详情（设定 + 卷 + 章纲节拍 + linter）
  DELETE /dabai/projects/{id}       删除
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.user import User
from app.services.dabai_persist import DabaiPersister, persist_bootstrap_result
from app.services.dabai_write import build_prose_prompt, mock_prose

logger = logging.getLogger("dabai.api")

router = APIRouter(prefix="/dabai", tags=["dabai"])


class GenerateRequest(BaseModel):
    logline: str = Field(..., min_length=2, max_length=200, description="一句话创意")
    mock: bool = Field(default=False, description="离线 mock（不调真实 LLM）")
    # 模型/线路选择：沿用通用分支约定（local 走 .env，gemini 走 llm_providers/env）
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None
    volume_count: int = Field(default=6, ge=1, le=20)
    volume_chapters: int = Field(default=30, ge=5, le=120)
    big_beat_every: int = Field(default=5, ge=2, le=15)
    chapter_batch_size: int = Field(default=30, ge=5, le=60)


def _resolve_connection(
    db: Session, model_profile: str, llm_provider_id: Optional[UUID],
) -> tuple[str, str, str]:
    """沿用通用分支的模型选择，解析 (base_url, api_key, model)。

    与 AIService.__init__ 同源：
      - gemini：resolve_gemini_connection(db, llm_provider_id)（DB 默认/指定线路 > 环境 GEMINI_*）
      - local ：.env 的 LLM_BASE_URL / LLM_API_KEY / AI_MODEL
    解析失败抛 400（提示去管理后台配线路或勾选 mock）。
    """
    from app.config import settings
    if model_profile == "gemini":
        from app.services.llm_config import (
            normalize_openai_base_url, resolve_gemini_connection,
        )
        conn = resolve_gemini_connection(db, llm_provider_id)
        if not conn:
            raise HTTPException(
                status_code=400,
                detail="未配置远程大模型：请在管理后台「大模型」新增并启用，或勾选离线 mock。",
            )
        return normalize_openai_base_url(conn[0]), (conn[2] or "").strip() or "not-required", conn[1]
    model = (settings.AI_MODEL or "").strip()
    if not model:
        raise HTTPException(
            status_code=400,
            detail="未配置本地模型：请在 .env 设置 AI_MODEL，或选远程线路 / 勾选 mock。",
        )
    return settings.LLM_BASE_URL, (settings.LLM_API_KEY or "").strip() or "not-required", model


def _cfg_from_req(req: GenerateRequest, db: Session):
    from dabai.config import DabaiConfig
    cfg = DabaiConfig(
        logline=req.logline.strip(), mock=req.mock,
        volume_count=req.volume_count, volume_chapters=req.volume_chapters,
        big_beat_every=req.big_beat_every, chapter_batch_size=req.chapter_batch_size,
    )
    if not req.mock:
        cfg.base_url, cfg.api_key, cfg.model = _resolve_connection(
            db, req.model_profile, req.llm_provider_id,
        )
    return cfg


def _build_call(cfg, req: GenerateRequest, db: Session, user: User):
    """构造注入式异步调用器。

    - mock：DabaiLLM（离线样本）。
    - 真实：复用通用分支 AIService._call_ai（继承计费 / 调用日志 / 任务级采样）。
    """
    if req.mock:
        from dabai.pipeline import dabai_llm_call
        return dabai_llm_call(cfg)
    from dabai.llm_client import parse_json
    from app.services.ai.service import AIService
    ai = AIService(profile=req.model_profile, db=db,
                   llm_provider_id=req.llm_provider_id, user_id=user.id)

    async def call(step: str, system: str, user_prompt: str, meta: dict | None):
        text = await ai._call_ai(system, user_prompt, task=f"dabai.{step}")
        return parse_json(text)

    return call


def _meta_from_cfg(cfg, failed_steps: list[str]) -> dict:
    return {
        "volume_count": cfg.volume_count, "volume_chapters": cfg.volume_chapters,
        "chapter_batch_size": cfg.chapter_batch_size, "mock": cfg.mock,
        "model": cfg.model, "failed_steps": failed_steps,
    }


# ── 序列化 ───────────────────────────────────────────────────────────────────
def _detail(p: DabaiProject) -> dict:
    return {
        "id": str(p.id), "logline": p.logline, "title": p.title,
        "status": p.status, "mock": p.mock,
        "benchmark": p.benchmark or {},
        "positioning": p.positioning or {}, "golden_finger": p.golden_finger or {},
        "power_ladder": p.power_ladder or {},
        "factions": [{"name": f.name, "stance": f.stance, "role": f.role,
                      "power_tier": f.power_tier, "note": f.note} for f in p.factions],
        "characters": [{"name": c.name, "role": c.role, "tier": c.tier,
                        "start_realm": c.start_realm, "persona": c.persona,
                        "function": c.function, **(c.extra or {})} for c in p.characters],
        "storylines": [{"name": s.name, "type": s.type, "summary": s.summary}
                       for s in p.storylines],
        "linter_report": p.linter_report or {}, "meta": p.meta or {},
        "failed_steps": p.failed_steps or [],
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "volumes": [{"id": str(v.id), "volume_number": v.volume_number, "title": v.title,
                     "phase": v.phase, "planned_chapters": v.planned_chapters,
                     "big_beats": v.big_beats or [], "volume_climax": v.volume_climax,
                     "end_hook": v.end_hook,
                     "realm_start_rank": v.realm_start_rank, "realm_end_rank": v.realm_end_rank}
                    for v in p.volumes],
        "chapter_outlines": [{
            "id": str(c.id), "chapter_number": c.chapter_number, "title": c.title,
            "shuang_type": c.shuang_type, "yaqu_setup": c.yaqu_setup,
            "emotion_turn": c.emotion_turn, "yinbao": c.yinbao,
            "shuang_payoff": c.shuang_payoff, "witnesses": c.witnesses or [],
            "end_hook": c.end_hook, "new_info_count": c.new_info_count,
            "involved_characters": c.involved_characters or [],
            "is_big_beat": c.is_big_beat, "expected_words": c.expected_words,
            "realm_rank": c.realm_rank,
            "content": c.content, "status": c.status or "planned",
        } for c in p.chapter_outlines],
    }


def _summary(p: DabaiProject) -> dict:
    rep = p.linter_report or {}
    return {
        "id": str(p.id), "logline": p.logline, "title": p.title,
        "status": p.status, "mock": p.mock,
        "linter_status": rep.get("status"), "linter_score": rep.get("score"),
        "volume_count": len(p.volumes), "chapter_count": len(p.chapter_outlines),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _owned_or_404(db: Session, project_id: UUID, user: User) -> DabaiProject:
    p = db.query(DabaiProject).filter(DabaiProject.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="大白文项目不存在")
    if user.id is not None and p.user_id is not None and p.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该项目")
    return p


# ── 生成（非流式）────────────────────────────────────────────────────────────
@router.post("/projects")
async def generate_project(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """运行大白文 bootstrap（爽点节拍器）并落库，返回完整详情。"""
    from dabai.pipeline import collect_bootstrap

    cfg = _cfg_from_req(req, db)
    try:
        result = await collect_bootstrap(cfg, _build_call(cfg, req, db, user))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"生成失败：{exc}") from exc
    project = persist_bootstrap_result(db, result, user.id)
    return _detail(project)


# ── 生成（SSE 流式，边生成边落库）────────────────────────────────────────────
def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/projects/stream")
async def generate_project_stream(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """流式生成：逐步 yield 进度并增量落库（中断也不丢已生成部分）。"""
    from dabai.pipeline import aiter_bootstrap

    cfg = _cfg_from_req(req, db)
    call = _build_call(cfg, req, db, user)
    persister = DabaiPersister(db, cfg, user.id)

    async def event_gen():
        try:
            agen = aiter_bootstrap(cfg, call)
            async for ev in agen:
                kind = ev["event"]
                async for line in _handle_event(persister, cfg, ev, kind):
                    yield line
        except Exception as exc:  # noqa: BLE001
            logger.error("dabai 流式生成异常：%s", exc)
            yield _sse({"event": "error", "message": str(exc)})

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _handle_event(persister: DabaiPersister, cfg, ev: dict, kind: str):
    """单事件：增量落库 + 产出 SSE 行（异步生成器）。"""
    if kind == "bootstrap_start":
        persister.create()
        yield _sse({"event": "project_created",
                    "project_id": str(persister.project.id), "steps": ev["steps"]})
    elif kind == "step_start":
        yield _sse({"event": "step_start", "step": ev["step"]})
    elif kind == "step_done":
        persister.save_step(ev["step"], ev["data"])
        yield _sse({"event": "step_done", "step": ev["step"], "count": ev["count"]})
    elif kind == "chapter_batch":
        total = persister.save_chapter_batch(ev["data"])
        yield _sse({"event": "chapter_batch", "batch_start": ev["batch_start"],
                    "batch_end": ev["batch_end"], "total": total})
    elif kind == "step_error":
        yield _sse({"event": "step_error", "step": ev["step"], "message": ev["message"]})
    elif kind == "linter_done":
        d = ev["data"]
        yield _sse({"event": "linter_done", "status": d.get("status"),
                    "score": d.get("score"), "issue_count": d.get("issue_count")})
    elif kind == "bootstrap_end":
        persister.finalize(ev.get("linter_report"), ev.get("failed_steps", []),
                           _meta_from_cfg(cfg, ev.get("failed_steps", [])))
        yield _sse({"event": "done", "project_id": str(persister.project.id)})


# ── 章节正文写作（流式）──────────────────────────────────────────────────────
class WriteRequest(BaseModel):
    mock: bool = Field(default=False, description="离线 mock 正文（不调真实 LLM）")
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None


@router.post("/projects/{project_id}/chapters/{chapter_id}/draft/stream")
async def draft_chapter_stream(
    project_id: UUID,
    chapter_id: UUID,
    req: WriteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """流式写一章正文（简化大白文链路），完成后落库 content + status=written。"""
    project = _owned_or_404(db, project_id, user)
    ch = (
        db.query(DabaiChapterOutline)
        .filter(DabaiChapterOutline.id == chapter_id,
                DabaiChapterOutline.project_id == project.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="章节不存在")
    system, user_prompt = build_prose_prompt(project, ch)

    async def gen():
        chunks: list[str] = []
        try:
            if req.mock:
                for seg in mock_prose(project, ch):
                    chunks.append(seg)
                    yield _sse({"event": "chunk", "delta": seg})
            else:
                from app.services.ai.service import AIService
                ai = AIService(profile=req.model_profile, db=db,
                               llm_provider_id=req.llm_provider_id, user_id=user.id)
                async for delta in ai._stream_ai(
                    system, user_prompt, task="dabai.write",
                    max_tokens=max(1200, (ch.expected_words or 2000) * 2),
                ):
                    if not delta:
                        continue
                    chunks.append(delta)
                    yield _sse({"event": "chunk", "delta": delta})
        except Exception as exc:  # noqa: BLE001
            logger.error("dabai 正文流式异常 chapter=%s：%s", chapter_id, exc)
            yield _sse({"event": "error", "message": str(exc)})
            return
        ch.content = "".join(chunks)
        ch.status = "written"
        db.commit()
        yield _sse({"event": "done", "chapter_id": str(chapter_id),
                    "word_count": len(ch.content)})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── 查询 / 删除 ──────────────────────────────────────────────────────────────
@router.get("/projects")
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    q = db.query(DabaiProject)
    if user.id is not None:
        q = q.filter(DabaiProject.user_id == user.id)
    rows = q.order_by(DabaiProject.created_at.desc()).all()
    return {"items": [_summary(p) for p in rows], "total": len(rows)}


@router.get("/projects/{project_id}")
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _detail(_owned_or_404(db, project_id, user))


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    p = _owned_or_404(db, project_id, user)
    db.delete(p)
    db.commit()
    return {"ok": True, "deleted": str(project_id)}
