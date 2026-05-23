"""AI 展开章节计划（SSE）与确认入库。"""

from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Character,
    Foreshadow,
    OutlineNode,
    PowerSystem,
    Project,
    WorldSetting,
)
from app.schemas import OutlineNodeOut
from app.services.ai_service import AIService
from app.services.outline_planning import TARGET_CHAPTERS_PER_VOLUME, TARGET_WORDS_PER_CHAPTER
from app.utils.chapter_numbering import normalize_chapter_plan_title

from app.routers.outline.helpers_core import *
from app.routers.outline.schemas import CommitExpandRequest, ExpandRequest

router = APIRouter()

@router.post("/ai-expand")
async def ai_expand_outline(
    project_id: str,
    req: ExpandRequest,
    db: Session = Depends(get_db),
):
    """
    为指定卷/篇节点 AI 生成详细章节计划（五要素卡片格式），SSE 流式返回。
    生成结果只推送给前端预览，不自动存库——由前端用户确认后调用
    POST /outline/ai-expand/commit 才入库。
    """
    node = db.query(OutlineNode).filter(
        OutlineNode.id == req.node_id,
        OutlineNode.project_id == project_id,
    ).first()
    if not node:
        raise HTTPException(404, "Node not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    settings = db.query(WorldSetting).filter(WorldSetting.project_id == project_id).all()
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    power_systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()

    # 统计当前已有章节数（用于编号连续）
    existing_count = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).count()

    world_summary = " | ".join(f"{s.title}: {(s.content or '')[:80]}" for s in settings[:4])

    # 境界白名单和 rank 映射
    realm_whitelist = sorted(_collect_power_system_whitelist(power_systems))
    name_to_rank, _, _ = _build_realm_rank_map(power_systems)

    def _build_char_summary(char_list: list) -> str:
        """构建角色摘要，区分主线核心与配角层级，补入境界信息。"""
        core = [c for c in char_list if (c.character_tier or "core") == "core"]
        supporting = [c for c in char_list if (c.character_tier or "core") != "core"]
        parts = ["以下为主线核心卡司（非全书全部人物，配角可按剧情需要引入）："]
        for c in core[:8]:
            parts.append(
                f"[核心]{c.name}（{c.role}，境界:{c.current_realm or '未知'}/rank{c.realm_rank or '?'}，"
                f"{c.faction or '无阵营'}）{(c.personality or '')[:40]}"
            )
        for c in supporting[:4]:
            parts.append(
                f"[配角]{c.name}（{c.role}，{c.faction or '无阵营'}）{(c.motivation or '')[:40]}"
            )
        return " | ".join(parts)

    char_summary = _build_char_summary(characters)

    # 加载前序已生成章节作为连续性上下文
    context_limit = 24
    prior_chapters = _load_existing_chapter_context(db, project_id, limit=context_limit)

    # 从前序章节提取主角已达最高境界
    anchor_names = _collect_protagonist_anchor_names(characters)
    prior_max_rank, prior_max_realm = _extract_max_realm_from_chapters(
        prior_chapters,
        name_to_rank,
        protagonist_names=anchor_names or None,
    )

    # 构建主角当前状态字符串
    protagonist = next((c for c in characters if c.role == "protagonist"), None)
    if protagonist:
        ps_realm = (
            f"{prior_max_realm}（rank{prior_max_rank}）"
            if prior_max_rank else f"{protagonist.current_realm or '未知'}"
        )
        protagonist_state = (
            f"姓名：{protagonist.name} | "
            f"当前境界（已达最高）：{ps_realm} | "
            f"当前位置：{protagonist.current_location or '未知'} | "
            f"当前状态：{protagonist.current_status or 'alive'}"
        )
    else:
        protagonist_state = (
            f"主角已达最高境界：{prior_max_realm}（rank{prior_max_rank}）"
            if prior_max_rank else ""
        )

    # 全书卷线蓝图（供当前卷知晓全局走向）
    root_volumes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.parent_id.is_(None),
        OutlineNode.node_type == "volume",
    ).order_by(OutlineNode.sort_order).all()
    global_outline_context = _format_global_outline_context([
        (n, (n.extra or {}).get("planned_chapters", TARGET_CHAPTERS_PER_VOLUME)
         if isinstance(n.extra, dict) else TARGET_CHAPTERS_PER_VOLUME)
        for n in root_volumes
    ])

    previous_chapters_context = _format_previous_chapters_context(prior_chapters, max_items=context_limit)
    continuity_state = _format_rolling_continuity_state(
        prior_chapters,
        protagonist_max_rank=prior_max_rank,
        protagonist_max_realm=prior_max_realm,
        characters=characters,
    )

    # 第二卷及以后：带入「严格早于当前卷」的已落库章纲情节链 + 伏笔（与全局最近 N 章窗口互补）
    all_outline_nodes = db.query(OutlineNode).filter(OutlineNode.project_id == project_id).all()
    id_map = {n.id: n for n in all_outline_nodes}
    anchor_vol = _anchor_volume_for_expand(node, id_map)
    prior_plot_context = ""
    prior_ledger_context = ""
    if anchor_vol is not None:
        prior_nodes = _prior_volume_chapter_plan_nodes(all_outline_nodes, id_map, anchor_vol)
        if prior_nodes:
            prior_ctx = [
                _outline_node_to_chapter_context(n) for n in _sort_chapter_plan_nodes(prior_nodes)
            ]
            plot_budget = _ai_expand_prior_plot_budget(req.model_profile)
            ledger_budget = _ai_expand_prior_foreshadow_budget(req.model_profile)
            prior_plot_context = _format_prior_volumes_plot_context(prior_ctx, plot_budget)
            foreshadow_rows = db.query(Foreshadow).filter(Foreshadow.project_id == project_id).all()
            prior_ledger_context = _build_prior_foreshadow_ledger(
                prior_ctx, foreshadow_rows, ledger_budget
            )

    story_core = project.story_core if project and isinstance(project.story_core, dict) else {}
    theme_statement = ""
    if project:
        theme_statement = (project.premise or "").strip() or (story_core.get("theme") or "").strip()
        theme_statement = theme_statement[:2000]

    svc = AIService(profile=req.model_profile, db=db, llm_provider_id=req.llm_provider_id)
    genre = (project.genre or "玄幻") if project else "玄幻"

    async def stream():
        yield f"data: {json.dumps({'event': 'start'}, ensure_ascii=False)}\n\n"
        try:
            result = await svc.expand_outline(
                node_title=node.title,
                node_type=node.node_type,
                node_summary=node.summary or "",
                project_title=project.title if project else "未命名",
                genre=genre,
                world_summary=world_summary,
                character_summary=char_summary,
                theme_statement=theme_statement,
                existing_chapters=existing_count,
                chapter_count=req.chapter_count,
                global_outline_context=global_outline_context,
                previous_chapters_context=previous_chapters_context,
                continuity_state=continuity_state,
                prior_volumes_plot_context=prior_plot_context,
                prior_foreshadow_ledger=prior_ledger_context,
                realm_whitelist=realm_whitelist,
                protagonist_state=protagonist_state,
            )
            err_msg = result.get("error") if isinstance(result, dict) else None
            chapters = result.get("chapters") if isinstance(result, dict) else None
            if err_msg or not isinstance(chapters, list) or len(chapters) == 0:
                detail = err_msg or "AI 未返回有效章节列表（可能是模型输出非 JSON 或格式不符）"
                yield f"data: {json.dumps({'event': 'error', 'message': detail}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'event': 'result', 'data': result}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: {\"event\": \"end\"}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.post("/ai-expand/commit", response_model=List[OutlineNodeOut])
def commit_expand(
    project_id: str,
    req: CommitExpandRequest,
    db: Session = Depends(get_db),
):
    """
    把前端确认的章节计划批量写入大纲树。
    直接把章节计划挂到选中的卷或旧篇节点下；新生成不再创建篇节点。
    """
    parent = db.query(OutlineNode).filter(
        OutlineNode.id == req.parent_node_id,
        OutlineNode.project_id == project_id,
    ).first()
    if not parent:
        raise HTTPException(404, "Parent node not found")

    results = []
    project = db.query(Project).filter(Project.id == project_id).first()
    genre = project.genre if project else None
    for i, ch in enumerate(req.chapters):
        safe_ch = _sanitize_generated_outline_chapter(ch, genre) if isinstance(ch, dict) else {}
        _word_est = int(safe_ch.get("word_estimate") or TARGET_WORDS_PER_CHAPTER)
        node = OutlineNode(
            project_id=project_id,
            parent_id=parent.id,
            node_type="chapter_plan",
            title=normalize_chapter_plan_title(safe_ch.get("number", i + 1), safe_ch.get("title")),
            summary=safe_ch.get("core_event"),
            hook=safe_ch.get("opening_hook"),
            highlight=safe_ch.get("end_hook"),    # 章末钩子放 highlight 字段
            conflict=safe_ch.get("character_change"),
            sort_order=i,
            expected_words=_word_est,  # 同步写 DB 列（单一数据源）
            extra={
                "foreshadow":    safe_ch.get("foreshadow", ""),
                "pacing":        safe_ch.get("pacing", "medium"),
                "word_estimate": _word_est,
                "end_hook":      safe_ch.get("end_hook", ""),
            },
        )
        db.add(node)
        db.flush()
        results.append(node)

    db.commit()
    return [OutlineNodeOut.model_validate(n) for n in results]
