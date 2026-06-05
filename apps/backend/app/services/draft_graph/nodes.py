"""
draft_graph/nodes.py — chapter_draft_graph 的各节点实现。

节点列表与职责：
  load_context      — 加载 chapter/project/DB 数据，转为可序列化的 draft_ctx dict
  scene_planning    — 从 DB Scene 记录读取分场蓝图（已由 Bootstrap 生成）
  human_review_blueprint — interrupt()：展示蓝图，等待用户审阅
  draft_scenes      — 调用 draft_assist_stream，流式生成正文并推 token 事件
  quality_check     — 调用 AIService.quality_check，产出质检报告
  human_review_quality   — interrupt()：展示质检结果，等待用户决策（低分时触发）
  auto_revision     — 调用 AIService.draft_assist_stream 做局部修复
  debrief           — 调用 AIService.auto_extract_debrief，更新记忆与角色状态
  save_commit       — 将草稿写入 Chapter.content，更新 Scene.status

代码红线：本文件 ≤ 600 行；单函数 ≤ 150 行。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from langgraph.types import interrupt

from app.database import SessionLocal
from app.models import Chapter, Character, Project, StoryLine
from app.utils.chapter_numbering import display_chapter_number
from app.utils.writing_style import resolve_project_writing_style
from app.models.generation_job import GenerationJob
from app.models.scene import Scene
from app.routers.ai.draft_routes import _build_draft_context
from app.services.ai_service import AIService
from app.services.draft_graph.events import emit, update_job
from app.services.draft_graph.quality_helper import run_quality_check
from app.services.draft_graph.state import ChapterDraftState
from app.services.llm_config import resolve_gemini_connection

logger = logging.getLogger(__name__)

# 节点进度里程碑（百分比）
_PROGRESS = {
    "load_context": 5,
    "scene_planning": 12,
    "human_review_blueprint": 15,
    "draft_scenes": 65,
    "quality_check": 75,
    "human_review_quality": 78,
    "auto_revision": 88,
    "debrief": 93,
    "save_commit": 100,
}


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def _make_ai_service(state: ChapterDraftState, db=None) -> AIService:
    """
    根据 state 中的 llm_provider_id / model_profile 创建 AIService 实例。

    与 gated_draft_routes 中的实例化逻辑保持一致，避免行为差异。
    AIService 的第一个位置参数是 profile（"gemini" | "default"），
    "local" 映射到 "default"，其余视为 "gemini"。

    @param db: 可选的已有 db session；传入时 AIService 复用它（节点自行管理生命周期）
    @returns 已配置的 AIService 实例
    """
    model_profile = state.get("model_profile", "gemini")
    profile = "gemini" if model_profile == "gemini" else "default"
    llm_provider_id = state.get("llm_provider_id")

    from uuid import UUID as _UUID
    provider_uuid = _UUID(llm_provider_id) if llm_provider_id else None

    return AIService(
        profile,
        db=db,
        llm_provider_id=provider_uuid,
    )


def _node_start(job_id: str, node_name: str) -> None:
    """标准节点开始动作：推 SSE 事件 + 更新 DB 状态。"""
    pct = _PROGRESS.get(node_name, 0)
    emit(job_id, "node_start", node=node_name, progress_pct=pct)
    update_job(job_id, current_node=node_name, progress_pct=pct, status="running")


def _node_done(job_id: str, node_name: str, **extra: Any) -> None:
    """标准节点完成动作：推 SSE 事件（带附加业务字段）。"""
    emit(job_id, "node_done", node=node_name, **extra)


# ═══════════════════════════════════════════════════════════════════════════
# 节点 1 — load_context
# ═══════════════════════════════════════════════════════════════════════════

async def load_context(state: ChapterDraftState) -> dict:
    """
    从 DB 加载 chapter / project 数据，调用 _build_draft_context 组装上下文字符串。

    所有产出均为可序列化类型（str/int/bool/dict），供下游节点直接使用。
    不持有 DB 对象引用。

    @returns state 更新字典，包含 chapter_title / phase / positioning /
             word_target / draft_ctx
    @raises RuntimeError: chapter 或 project 不存在
    """
    job_id = state["job_id"]
    _node_start(job_id, "load_context")

    db = SessionLocal()
    try:
        chapter = db.query(Chapter).filter(Chapter.id == state["chapter_id"]).first()
        if not chapter:
            raise RuntimeError(f"Chapter {state['chapter_id']} not found")

        project = db.query(Project).filter(Project.id == state["project_id"]).first()
        if not project:
            raise RuntimeError(f"Project {state['project_id']} not found")

        # 判断是否使用大 context（与 gated_draft_routes 逻辑一致）
        from app.services.ai.client import ClientMixin
        draft_ctx = await _build_draft_context(
            db=db,
            project_id=str(project.id),
            chapter=chapter,
            project=project,
        )
    finally:
        db.close()

    _node_done(job_id, "load_context", chapter_title=draft_ctx.get("chapter_title", ""))
    return {
        "chapter_title": draft_ctx.get("chapter_title", chapter.title or ""),
        "phase": draft_ctx.get("phase", ""),
        "positioning": draft_ctx.get("positioning"),
        "word_target": draft_ctx.get("word_target", 2300),
        "draft_ctx": draft_ctx,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 节点 2 — scene_planning
# ═══════════════════════════════════════════════════════════════════════════

async def scene_planning(state: ChapterDraftState) -> dict:
    """
    从 DB Scene 记录读取本章场景蓝图（Bootstrap Step 13 已生成）。

    若 DB 无 Scene 记录，则生成一条默认占位蓝图（单场），保证下游节点不因空蓝图崩溃。
    人工在前端编辑 Scene 记录后，此节点会读取最新版。

    @returns {"scene_blueprint": list[dict]}
    """
    job_id = state["job_id"]
    _node_start(job_id, "scene_planning")

    db = SessionLocal()
    try:
        # 优先按 outline_node_id 查，其次按 chapter_id 查
        scenes = []
        if state.get("outline_node_id"):
            scenes = (
                db.query(Scene)
                .filter(
                    Scene.project_id == state["project_id"],
                    Scene.outline_node_id == state["outline_node_id"],
                )
                .order_by(Scene.order)
                .all()
            )
        if not scenes and state.get("chapter_id"):
            scenes = (
                db.query(Scene)
                .filter(
                    Scene.project_id == state["project_id"],
                    Scene.chapter_id == state["chapter_id"],
                )
                .order_by(Scene.order)
                .all()
            )

        blueprint = [
            {
                "order": s.order,
                "title": s.title or "",
                "location_name": s.location_name or "",
                "goal": s.goal or "",
                "conflict": s.conflict or "",
                "turn": s.turn or "",
                "hook": s.hook or "",
                "hook_strength": s.hook_strength or 3,
                "word_budget": s.word_budget or 400,
                "pacing": s.pacing or "mid",
            }
            for s in scenes
        ]

        if not blueprint:
            # 无 Scene 记录时降级为单场全章写作
            blueprint = [{"order": 1, "title": "全章", "word_budget": state.get("word_target", 2300)}]
            logger.warning("job %s: no Scene records found, using fallback blueprint", job_id)

    finally:
        db.close()

    _node_done(job_id, "scene_planning", scene_count=len(blueprint))
    return {"scene_blueprint": blueprint}


# ═══════════════════════════════════════════════════════════════════════════
# 节点 3 — human_review_blueprint（可选 interrupt）
# ═══════════════════════════════════════════════════════════════════════════

async def human_review_blueprint(state: ChapterDraftState) -> dict:
    """
    场景蓝图人工审阅节点。

    skip_blueprint_review=True 时直接通过；否则 interrupt() 挂起，
    等待 POST /jobs/{id}/input 提交 {"action": "approve"|"rewrite"|"skip",
    "directive": "..."} 后 resume。

    @returns {"blueprint_decision": str, "blueprint_directive": str}
    """
    job_id = state["job_id"]
    _node_start(job_id, "human_review_blueprint")

    if state.get("skip_blueprint_review", False):
        _node_done(job_id, "human_review_blueprint", decision="approve", auto=True)
        return {"blueprint_decision": "approve", "blueprint_directive": ""}

    interrupt_data = {
        "type": "blueprint_review",
        "scene_blueprint": state.get("scene_blueprint", []),
        "options": ["approve", "rewrite", "skip"],
    }

    # 更新 DB：告知前端需要什么输入
    update_job(
        job_id,
        status="waiting_input",
        user_input_schema=interrupt_data,
    )
    emit(job_id, "waiting_input", schema=interrupt_data)

    # ── 挂起，等待 POST /input resume ───────────────────────────────────
    decision: dict = interrupt(interrupt_data)

    action = decision.get("action", "approve")
    directive = decision.get("directive", "")
    _node_done(job_id, "human_review_blueprint", decision=action)
    return {"blueprint_decision": action, "blueprint_directive": directive,
            "iteration_count": state.get("iteration_count", 0) + (1 if action == "rewrite" else 0)}


# ═══════════════════════════════════════════════════════════════════════════
# 节点 4 — draft_scenes（核心生成节点）
# ═══════════════════════════════════════════════════════════════════════════

async def draft_scenes(state: ChapterDraftState) -> dict:
    """
    调用 AIService.draft_assist_stream，流式生成本章正文。

    每个 token 片段推送 event=token（persist=False），不写 DB；
    生成完毕后推送 event=draft_done（persist=True），记录字数。

    若存在场景蓝图，将其序列化并追加到 user_prompt，让模型按场写作。

    @returns {"draft_content": str, "draft_word_count": int}
    """
    job_id = state["job_id"]
    _node_start(job_id, "draft_scenes")

    # ── 构建 user_prompt：拼入用户指令 + 蓝图摘要 ──────────────────────
    parts: list[str] = []
    if state.get("user_directives"):
        parts.append(f"【作者特别指令】{state['user_directives']}")
    if state.get("blueprint_directive"):
        parts.append(f"【蓝图修改指令】{state['blueprint_directive']}")
    if state.get("quality_directive"):
        parts.append(f"【质检重写指令】{state['quality_directive']}")
    user_prompt = "\n".join(parts)

    draft_ctx: dict = state.get("draft_ctx", {})
    svc = _make_ai_service(state)

    full_content = ""
    try:
        async for chunk in svc.draft_assist_stream(
            **{k: v for k, v in draft_ctx.items() if k != "chapter_title"},
            chapter_title=state.get("chapter_title", ""),
            user_prompt=user_prompt,
            word_target=state.get("word_target", 2300),
            phase=state.get("phase"),
            positioning=state.get("positioning"),
            replace_existing=True,
        ):
            full_content += chunk
            # token 事件不写 DB，高频写会有性能问题
            emit(job_id, "token", content=chunk, persist=False)
    except Exception as exc:
        logger.exception("draft_scenes failed for job %s", job_id)
        emit(job_id, "node_error", node="draft_scenes", message=str(exc))
        return {
            "draft_content": full_content,
            "draft_word_count": len(full_content),
            "errors": [{"node": "draft_scenes", "message": str(exc)}],
        }

    word_count = len(full_content)
    _node_done(job_id, "draft_scenes", word_count=word_count)
    return {"draft_content": full_content, "draft_word_count": word_count}


# ═══════════════════════════════════════════════════════════════════════════
# 节点 5 — quality_check
# ═══════════════════════════════════════════════════════════════════════════

async def quality_check(state: ChapterDraftState) -> dict:
    """
    对当前草稿执行 AI 质检，产出结构化质检报告（JSON）。

    委托 quality_helper.run_quality_check 完成上下文组装 + AI 调用 + DB 写回。

    @returns {"quality_report": dict, "quality_score": int}
    """
    job_id = state["job_id"]
    _node_start(job_id, "quality_check")

    db = SessionLocal()
    try:
        svc = _make_ai_service(state, db=db)
        report = await run_quality_check(
            db=db,
            project_id=state["project_id"],
            chapter_id=state["chapter_id"],
            draft_content=state.get("draft_content", ""),
            chapter_title=state.get("chapter_title", ""),
            svc=svc,
        )
    except Exception as exc:
        logger.exception("quality_check failed for job %s", job_id)
        db.rollback()
        emit(job_id, "node_error", node="quality_check", message=str(exc))
        return {
            "quality_report": None,
            "quality_score": -1,
            "errors": [{"node": "quality_check", "message": str(exc)}],
        }
    finally:
        db.close()

    score = report.get("overall_score", 0) if isinstance(report, dict) else 0
    _node_done(job_id, "quality_check", score=score)
    return {"quality_report": report, "quality_score": int(score)}


# ═══════════════════════════════════════════════════════════════════════════
# 节点 6 — human_review_quality（可选 interrupt）
# ═══════════════════════════════════════════════════════════════════════════

async def human_review_quality(state: ChapterDraftState) -> dict:
    """
    质检结果人工审阅节点（低分或 skip_quality_review=False 时触发）。

    skip_quality_review=True 时自动选择 accept（达标）或 auto_fix（不达标）；
    否则 interrupt() 挂起，等待 POST /jobs/{id}/input 提交
    {"action": "accept"|"auto_fix"|"rewrite", "directive": "..."} 后 resume。

    @returns {"quality_decision": str, "quality_directive": str}
    """
    job_id = state["job_id"]
    _node_start(job_id, "human_review_quality")

    score = state.get("quality_score", -1)
    threshold = state.get("quality_threshold", 75)

    if state.get("skip_quality_review", False):
        auto_decision = "accept" if score < 0 or score >= threshold else "auto_fix"
        _node_done(job_id, "human_review_quality", decision=auto_decision, auto=True)
        return {"quality_decision": auto_decision, "quality_directive": ""}

    interrupt_data = {
        "type": "quality_review",
        "quality_report": state.get("quality_report"),
        "score": score,
        "threshold": threshold,
        "options": ["accept", "auto_fix", "rewrite"],
    }
    update_job(job_id, status="waiting_input", user_input_schema=interrupt_data)
    emit(job_id, "waiting_input", schema=interrupt_data)

    decision: dict = interrupt(interrupt_data)

    action = decision.get("action", "accept")
    directive = decision.get("directive", "")
    _node_done(job_id, "human_review_quality", decision=action)
    return {"quality_decision": action, "quality_directive": directive,
            "iteration_count": state.get("iteration_count", 0) + (1 if action == "rewrite" else 0)}


# ═══════════════════════════════════════════════════════════════════════════
# 节点 7 — auto_revision
# ═══════════════════════════════════════════════════════════════════════════

async def auto_revision(state: ChapterDraftState) -> dict:
    """
    基于质检报告和用户指令，调用 AI 对草稿做局部修正（非整章重写）。

    将质检问题列表格式化为 user_prompt 约束，复用 draft_assist_stream 生成修正版。

    @returns {"draft_content": str, "draft_word_count": int, "iteration_count": int}
    """
    job_id = state["job_id"]
    _node_start(job_id, "auto_revision")

    report = state.get("quality_report") or {}
    suggestions = report.get("suggestions", report.get("improvement_suggestions", []))
    svc = _make_ai_service(state)
    draft_ctx: dict = state.get("draft_ctx", {})

    fix_directive_parts = ["【AI 自动修复模式：根据质检反馈改进以下问题】"]
    if isinstance(suggestions, list):
        for i, s in enumerate(suggestions[:5], 1):
            fix_directive_parts.append(f"{i}. {s}")
    elif isinstance(suggestions, str):
        fix_directive_parts.append(suggestions)
    if state.get("quality_directive"):
        fix_directive_parts.append(f"【用户额外指令】{state['quality_directive']}")
    fix_directive_parts.append("【当前草稿（请在此基础上修正，保留已有优点）】")
    fix_directive_parts.append(state.get("draft_content", ""))
    user_prompt = "\n".join(fix_directive_parts)

    full_content = ""
    try:
        async for chunk in svc.draft_assist_stream(
            **{k: v for k, v in draft_ctx.items() if k != "chapter_title"},
            chapter_title=state.get("chapter_title", ""),
            user_prompt=user_prompt,
            word_target=state.get("word_target", 2300),
            phase=state.get("phase"),
            positioning=state.get("positioning"),
            replace_existing=True,
        ):
            full_content += chunk
            emit(job_id, "token", content=chunk, persist=False)
    except Exception as exc:
        logger.exception("auto_revision failed for job %s", job_id)
        emit(job_id, "node_error", node="auto_revision", message=str(exc))
        return {
            "draft_content": state.get("draft_content", ""),
            "draft_word_count": state.get("draft_word_count", 0),
            "iteration_count": state.get("iteration_count", 0) + 1,
            "errors": [{"node": "auto_revision", "message": str(exc)}],
        }

    word_count = len(full_content)
    _node_done(job_id, "auto_revision", word_count=word_count)
    return {
        "draft_content": full_content,
        "draft_word_count": word_count,
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 节点 8 — debrief
# ═══════════════════════════════════════════════════════════════════════════

async def debrief(state: ChapterDraftState) -> dict:
    """
    对完成草稿执行自动复盘：提取记忆种子、更新角色状态。
    失败时仅记录 error，不中断流程（复盘是增量优化，不阻塞章节落库）。

    @returns {} 或 {"errors": [...]}
    """
    job_id = state["job_id"]
    _node_start(job_id, "debrief")

    db = SessionLocal()
    try:
        chapter = db.query(Chapter).filter(Chapter.id == state["chapter_id"]).first()
        if not chapter:
            _node_done(job_id, "debrief", skipped=True)
            return {}

        # 构建 character_states — auto_extract_debrief 直接访问 c['id']，必须包含
        characters = (
            db.query(Character)
            .filter(Character.project_id == state["project_id"])
            .all()
        )
        character_states = [
            {
                "id": str(c.id),
                "name": c.name or "",
                "current_realm": c.current_realm or "",
                "current_status": c.current_status or "alive",
                "current_location": c.current_location or "",
            }
            for c in characters[:20]
        ]

        # 构建 storylines — auto_extract_debrief 直接访问 s['id']/s['line_type']/s['status']
        storylines = (
            db.query(StoryLine)
            .filter(StoryLine.project_id == state["project_id"])
            .all()
        )
        storylines_data = [
            {
                "id": str(s.id),
                "name": s.name or "",
                "line_type": getattr(s, "line_type", "") or "",
                "status": getattr(s, "status", "active") or "active",
                "core_conflict": s.description or "",
            }
            for s in storylines[:10]
        ]

        project = db.query(Project).filter(Project.id == state["project_id"]).first()
        project_genre = project.genre if project else None

        from app.services.bootstrap.fanqie_realm_policy import (
            build_fanqie_realm_discipline_for_project,
        )

        svc = _make_ai_service(state, db=db)
        await svc.auto_extract_debrief(
            chapter_content=state.get("draft_content", ""),
            chapter_title=chapter.title or "",
            chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
            character_states=character_states,
            storylines=storylines_data,
            genre=project_genre,
            writing_style=resolve_project_writing_style(project),
            realm_discipline_block=build_fanqie_realm_discipline_for_project(
                db, str(state["project_id"]),
            ),
        )
        db.commit()
    except Exception as exc:
        logger.exception("debrief failed for job %s (non-fatal)", job_id)
        emit(job_id, "node_error", node="debrief", message=str(exc), fatal=False)
        return {"errors": [{"node": "debrief", "message": str(exc), "fatal": False}]}
    finally:
        db.close()

    _node_done(job_id, "debrief")
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# 节点 9 — save_commit
# ═══════════════════════════════════════════════════════════════════════════

async def save_commit(state: ChapterDraftState) -> dict:
    """
    将最终草稿写入 Chapter.content，创建 ChapterVersion 快照并更新 job 结果。
    终态节点：执行后 job.status = completed。

    @returns {} （终态节点无需更新 graph state）
    """
    job_id = state["job_id"]
    _node_start(job_id, "save_commit")

    db = SessionLocal()
    try:
        from app.models import ChapterVersion
        chapter = db.query(Chapter).filter(Chapter.id == state["chapter_id"]).first()
        if not chapter:
            raise RuntimeError(f"Chapter {state['chapter_id']} not found at save_commit")

        content = state.get("draft_content", "")
        chapter.content = content
        chapter.word_count = state.get("draft_word_count", len(content))

        # 创建版本快照
        version = ChapterVersion(
            chapter_id=chapter.id,
            content=content,
            word_count=chapter.word_count,
            version_note=f"Job {job_id[:8]} 生成（质检 {state.get('quality_score', -1)} 分）",
        )
        db.add(version)
        db.commit()
        db.refresh(chapter)

        result = {"chapter_id": str(chapter.id), "word_count": chapter.word_count,
                  "quality_score": state.get("quality_score", -1)}
    except Exception as exc:
        logger.exception("save_commit failed for job %s", job_id)
        db.rollback()
        update_job(job_id, status="failed", error_detail=str(exc))
        emit(job_id, "job_failed", message=str(exc))
        return {"errors": [{"node": "save_commit", "message": str(exc)}]}
    finally:
        db.close()

    update_job(job_id, status="completed", progress_pct=100, result=result)
    emit(job_id, "job_complete", **result)
    return {}
