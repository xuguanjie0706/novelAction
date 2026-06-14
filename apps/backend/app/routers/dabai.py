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

logger = logging.getLogger("dabai.api")

router = APIRouter(prefix="/dabai", tags=["dabai"])


class GenerateRequest(BaseModel):
    logline: str = Field(..., min_length=2, max_length=200, description="一句话创意")
    # 模型/线路选择：沿用通用分支约定（local 走 .env，gemini 走 llm_providers/env）
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None
    volume_count: int = Field(default=6, ge=1, le=20)
    volume_chapters: int = Field(default=30, ge=5, le=120)
    outline_expand_size: int = Field(
        default=15, ge=5, le=60,
        description="写作期卷展开窗口（建书一次出整卷；后续补全/新卷按此窗口，如 30/15=2 次）",
    )
    big_beat_every: int = Field(default=5, ge=2, le=15)
    # 五拍展开批默认 5（小批防模板化；与 dabai.config.chapter_batch_size 对齐）
    chapter_batch_size: int = Field(default=5, ge=5, le=60)


def _resolve_connection(
    db: Session, model_profile: str, llm_provider_id: Optional[UUID],
) -> tuple[str, str, str]:
    """沿用通用分支的模型选择，解析 (base_url, api_key, model)。

    与 AIService.__init__ 同源：
      - gemini：resolve_gemini_connection(db, llm_provider_id)（DB 默认/指定线路 > 环境 GEMINI_*）
      - local ：.env 的 LLM_BASE_URL / LLM_API_KEY / AI_MODEL
    解析失败抛 400（提示去管理后台配线路或 .env 本地模型）。
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
                detail="未配置远程大模型：请在管理后台「大模型」新增并启用。",
            )
        return normalize_openai_base_url(conn[0]), (conn[2] or "").strip() or "not-required", conn[1]
    model = (settings.AI_MODEL or "").strip()
    if not model:
        raise HTTPException(
            status_code=400,
            detail="未配置本地模型：请在 .env 设置 AI_MODEL，或选择远程线路。",
        )
    return settings.LLM_BASE_URL, (settings.LLM_API_KEY or "").strip() or "not-required", model


def _cfg_from_req(req: GenerateRequest, db: Session):
    from dabai.config import DabaiConfig
    cfg = DabaiConfig(
        logline=req.logline.strip(),
        volume_count=req.volume_count, volume_chapters=req.volume_chapters,
        outline_expand_size=req.outline_expand_size,
        big_beat_every=req.big_beat_every, chapter_batch_size=req.chapter_batch_size,
    )
    cfg.base_url, cfg.api_key, cfg.model = _resolve_connection(
        db, req.model_profile, req.llm_provider_id,
    )
    return cfg


def _build_call(cfg, req: GenerateRequest, db: Session, user: User):
    """构造注入式异步调用器（复用 AIService._call_ai：计费 / 调用日志 / 任务级采样）。"""
    from dabai.llm_client import parse_json
    from app.services.ai.service import AIService
    ai = AIService(profile=req.model_profile, db=db,
                   llm_provider_id=req.llm_provider_id, user_id=user.id)
    # 长输出步骤（单次整卷 beat+五拍 / 分批展开 / 修复）需要放开输出上限；
    # 其余设定步走网关默认，避免对小上限模型传超额 max_tokens。
    heavy_steps = {"volume_chapters", "chapter_outlines", "beat_sequence", "chapter_repair"}

    async def call(step: str, system: str, user_prompt: str, meta: dict | None):
        max_tokens = cfg.max_tokens if step in heavy_steps else None
        text = await ai._call_ai(system, user_prompt, max_tokens=max_tokens,
                                 task=f"dabai.{step}")
        return parse_json(text)

    return call


def _meta_from_cfg(cfg, failed_steps: list[str]) -> dict:
    return {
        "volume_count": cfg.volume_count, "volume_chapters": cfg.volume_chapters,
        "outline_expand_size": cfg.outline_expand_size,
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
                      "power_tier": f.power_tier, "note": f.note,
                      "locations": f.locations or []} for f in p.factions],
        "characters": [{"name": c.name, "role": c.role, "tier": c.tier,
                        "start_realm": c.start_realm, "persona": c.persona,
                        "function": c.function, **(c.extra or {})} for c in p.characters],
        "storylines": [{"name": s.name, "type": s.type, "summary": s.summary,
                        "nodes": s.nodes or [],
                        "bound_characters": s.bound_characters or []}
                       for s in p.storylines],
        "extra": p.extra or {},
        "linter_report": p.linter_report or {}, "meta": p.meta or {},
        "failed_steps": p.failed_steps or [],
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "volumes": [{"id": str(v.id), "volume_number": v.volume_number, "title": v.title,
                     "phase": v.phase, "planned_chapters": v.planned_chapters,
                     "big_beats": v.big_beats or [], "volume_climax": v.volume_climax,
                     "end_hook": v.end_hook,
                     "realm_start_rank": v.realm_start_rank, "realm_end_rank": v.realm_end_rank,
                     "extra": v.extra or {}}
                    for v in p.volumes],
        "chapter_outlines": [{
            "id": str(c.id), "chapter_number": c.chapter_number, "title": c.title,
            "shuang_type": c.shuang_type, "location": c.location,
            "yaqu_setup": c.yaqu_setup,
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
        failed = ev.get("failed_steps", [])
        beats = (ev.get("ctx") or {}).get("beat_sequence") or None
        persister.finalize(ev.get("linter_report"), failed,
                           _meta_from_cfg(cfg, failed),
                           extra_update={"beat_sequence_vol1": beats})
        report = persister.project.linter_report or {}
        if persister._chapter_seq > 0 and not failed:
            from app.services.dabai.lab_outline_lint import run_dabai_project_linter
            report = run_dabai_project_linter(persister.db, persister.project)
        if report.get("status") and report.get("status") != "pending":
            yield _sse({"event": "linter_done", "status": report.get("status"),
                        "score": report.get("score"),
                        "issue_count": report.get("issue_count")})
        yield _sse({"event": "done", "project_id": str(persister.project.id)})


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


@router.post("/projects/{project_id}/relint-outline")
def relint_outline(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """全书章纲 linter 重跑（读库最新章纲，写回 linter_report）。"""
    from app.services.dabai.lab_outline_lint import run_dabai_project_linter

    project = _owned_or_404(db, project_id, user)
    report = run_dabai_project_linter(db, project)
    return {"linter_report": report}


class ProjectSettingsRequest(BaseModel):
    """项目级写作偏好（当前仅叙事烈度档）。"""
    intensity: Literal["restrained", "standard", "loud"]


@router.patch("/projects/{project_id}/settings")
def update_project_settings(
    project_id: UUID,
    req: ProjectSettingsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """设置叙事烈度档（降调/默认/够炸）。双写 positioning + extra，下游统一读取。"""
    p = _owned_or_404(db, project_id, user)
    pos = dict(p.positioning or {})
    pos["intensity"] = req.intensity
    p.positioning = pos
    ext = dict(p.extra or {})
    ext["intensity"] = req.intensity
    p.extra = ext
    db.commit()
    db.refresh(p)
    return {"id": str(p.id), "intensity": req.intensity}


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


from app.routers.dabai_draft_routes import register_draft_routes

register_draft_routes(router)
