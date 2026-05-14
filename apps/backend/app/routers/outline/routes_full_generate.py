"""全量生成大纲（SSE，多步持久化）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Character, OutlineNode, OutlineRevision, PowerSystem, Project, WorldSetting
from app.models.chapter import Chapter
from app.services.ai_service import AIService
from app.services.outline_planning import (
    TARGET_CHAPTERS_PER_VOLUME,
    TARGET_WORDS_PER_CHAPTER,
    normalize_volume_plan,
)
from app.utils.chapter_numbering import normalize_chapter_plan_title

from app.routers.outline.helpers_core import *
from app.routers.outline.schemas import FullGenerateRequest

router = APIRouter()

@router.post("/ai-full-generate")
async def ai_full_generate_outline(
    project_id: str,
    req: FullGenerateRequest,
    db: Session = Depends(get_db),
):
    """
    全量生成大纲：AI 规划卷结构，后端按「每卷约 60 章」校准章节数。
      Step 0（可选）：清除现有大纲
      Step 1：AI 分析故事，规划卷级骨架（含每卷 planned_chapters），写入数据库
      Step 2~N：逐卷按 planned_chapters 生成章节计划，写入数据库
    全程 SSE 推送进度，边生成边持久化。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    settings_list = db.query(WorldSetting).filter(WorldSetting.project_id == project_id).all()
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    power_systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()

    world_summary = " | ".join(
        f"{s.title}: {(s.content or '')[:80]}" for s in settings_list[:4]
    )
    # 人物摘要补入境界信息，供 AI 生成时参考
    char_summary = " | ".join(
        f"{c.name}（{c.role}，境界:{c.current_realm or '未知'}/rank{c.realm_rank or '?'}，"
        f"{c.faction or '无阵营'}）{(c.personality or '')[:40]}"
        for c in characters[:6]
    )
    story_core = project.story_core if isinstance(project.story_core, dict) else {}
    theme_statement = (req.theme_statement or story_core.get("theme") or "").strip()

    # 境界白名单（从 PowerSystem.levels 提取，供每批 expand_outline 注入）
    realm_whitelist = sorted(_collect_power_system_whitelist(power_systems))
    # 境界名→rank 映射，用于跨批次追踪主角最高境界
    name_to_rank, _, _ = _build_realm_rank_map(power_systems)

    svc = AIService(profile=req.model_profile, db=db, llm_provider_id=req.llm_provider_id)

    # ── 共用：按批次为单个节点生成并写入章节计划 ──────────────
    async def fill_node_with_chapters(
        target_node: OutlineNode,
        planned_chapters: int,
        chapter_offset: int,
        step: int,
        total_steps: int,
        global_outline_context: str = "",
        prior_chapters: list[dict] | None = None,
    ):
        """
        为 target_node（卷或篇）生成章节计划并入库。
        target_node 为卷/旧篇时直接挂章节，不再自动创建篇。
        返回 (写入章节数, 新的 chapter_offset)。
        以 async generator 推送进度 SSE。
        """
        BATCH_SIZE = _outline_batch_size(req.model_profile)
        batches: list[int] = []
        remaining = planned_chapters
        while remaining > 0:
            batches.append(min(remaining, BATCH_SIZE))
            remaining -= BATCH_SIZE

        all_chapters: list[dict] = []
        batch_error = False
        batch_error_messages: list[str] = []

        # 跨批次追踪主角已达最高境界（从 prior_chapters 里先初始化）
        anchor_names = _collect_protagonist_anchor_names(characters)
        rolling_max_rank, rolling_max_realm = _extract_max_realm_from_chapters(
            prior_chapters or [],
            name_to_rank,
            protagonist_names=anchor_names or None,
        )

        for batch_idx, batch_count in enumerate(batches):
            batch_offset = chapter_offset + len(all_chapters)
            previous_context_limit = 24 if req.model_profile == "gemini" else 8
            context_chapters = [*(prior_chapters or []), *all_chapters]
            previous_chapters_context = _format_previous_chapters_context(
                context_chapters,
                max_items=previous_context_limit,
            )
            continuity_state = _format_rolling_continuity_state(
                context_chapters,
                protagonist_max_rank=rolling_max_rank,
                protagonist_max_realm=rolling_max_realm,
            )
            batch_goal = _format_outline_batch_goal(
                node_title=target_node.title,
                batch_offset=batch_offset,
                batch_count=batch_count,
                planned_chapters=planned_chapters,
                node_generated_chapters=len(all_chapters),
            )
            # 构建主角当前状态字符串（外部状态：境界/位置/存活）
            protagonist = next((c for c in characters if c.role == "protagonist"), None)
            if protagonist:
                ps_realm = (
                    f"{rolling_max_realm}（rank{rolling_max_rank}）"
                    if rolling_max_rank else f"{protagonist.current_realm or '未知'}"
                )
                protagonist_state = (
                    f"姓名：{protagonist.name} | "
                    f"当前境界（已达最高）：{ps_realm} | "
                    f"当前位置：{protagonist.current_location or '未知'} | "
                    f"当前状态：{protagonist.current_status or 'alive'}"
                )
                # 主角内层心理驱动（恐惧/欲望/价值观/弧线），补充外部状态的盲区
                psych_parts = []
                if protagonist.fear:
                    psych_parts.append(f"核心恐惧/创伤：{protagonist.fear}")
                if protagonist.motivation:
                    psych_parts.append(f"当前最强欲望：{protagonist.motivation}")
                if protagonist.values:
                    psych_parts.append(f"价值观：{protagonist.values}")
                if protagonist.arc:
                    psych_parts.append(f"人物弧线：{protagonist.arc}")
                protagonist_psychology = " | ".join(psych_parts)
            else:
                protagonist_state = (
                    f"主角已达最高境界：{rolling_max_realm}（rank{rolling_max_rank}）"
                    if rolling_max_rank else ""
                )
                protagonist_psychology = ""
            try:
                result = await svc.expand_outline(
                    node_title=target_node.title,
                    node_type=target_node.node_type,
                    node_summary=target_node.summary or "",
                    project_title=project.title,
                    genre=project.genre or "玄幻",
                    world_summary=world_summary,
                    character_summary=char_summary,
                    theme_statement=theme_statement,
                    existing_chapters=batch_offset,
                    chapter_count=batch_count,
                    global_outline_context=global_outline_context,
                    previous_chapters_context=previous_chapters_context,
                    continuity_state=continuity_state,
                    batch_goal=batch_goal,
                    realm_whitelist=realm_whitelist,
                    protagonist_state=protagonist_state,
                    protagonist_psychology=protagonist_psychology,
                )
                batch_chapters = [
                    _sanitize_generated_outline_chapter(ch, project.genre)
                    for ch in (result.get("chapters", []) or [])
                    if isinstance(ch, dict)
                ]
                if not batch_chapters:
                    detail = result.get("error") or result.get("raw") or "AI 未返回 chapters 数组"
                    batch_error = True
                    batch_error_messages.append(str(detail)[:180])
                    yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》第{batch_idx+1}批无有效章节：{str(detail)[:120]}', 'error': True}, ensure_ascii=False)}\n\n"
                else:
                    all_chapters.extend(batch_chapters)
                    # 每批完成后更新主角最高境界 rank，供下一批使用
                    new_max_rank, new_max_realm = _extract_max_realm_from_chapters(
                        batch_chapters,
                        name_to_rank,
                        protagonist_names=anchor_names or None,
                    )
                    if new_max_rank and (rolling_max_rank is None or new_max_rank > rolling_max_rank):
                        rolling_max_rank = new_max_rank
                        rolling_max_realm = new_max_realm
                    if len(batches) > 1:
                        yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》第{batch_idx+1}/{len(batches)}批完成（+{len(batch_chapters)} 章）'}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》第{batch_idx+1}批失败：{str(e)}', 'error': True}, ensure_ascii=False)}\n\n"
                batch_error = True
                batch_error_messages.append(str(e)[:180])

        if not all_chapters:
            reason = f"；原因：{batch_error_messages[-1]}" if batch_error_messages else ""
            yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》未获得有效章节，已跳过{reason}', 'error': True, 'done': True}, ensure_ascii=False)}\n\n"
            yield 0   # 用 yield 传回写入数量（async generator 不能 return value）
            return

        for ci, ch in enumerate(all_chapters):
            _word_est = int(ch.get("word_estimate") or TARGET_WORDS_PER_CHAPTER)
            db.add(OutlineNode(
                project_id=project_id,
                parent_id=target_node.id,
                node_type="chapter_plan",
                title=normalize_chapter_plan_title(
                    ch.get("number", chapter_offset + ci + 1),
                    ch.get("title"),
                ),
                summary=ch.get("core_event"),
                hook=ch.get("opening_hook"),
                highlight=ch.get("end_hook"),
                conflict=ch.get("character_change"),
                sort_order=ci,
                expected_words=_word_est,  # 同步写 DB 列（单一数据源）
                extra={
                    "foreshadow":    ch.get("foreshadow", ""),
                    "pacing":        ch.get("pacing", "medium"),
                    "word_estimate": _word_est,
                    "end_hook":      ch.get("end_hook", ""),
                    # 因果链四元组（欲望→障碍→选择→代价）
                    "protagonist_want":      ch.get("protagonist_want", ""),
                    "protagonist_obstacle":  ch.get("protagonist_obstacle", ""),
                    "protagonist_choice":    ch.get("protagonist_choice", ""),
                    "choice_cost":           ch.get("choice_cost", ""),
                    # 反派视角对齐 & 读者情绪目标
                    "villain_action":        ch.get("villain_action", ""),
                    "reader_emotion_target": ch.get("reader_emotion_target", ""),
                },
            ))
        db.flush()
        db.commit()

        warn = "（部分批次失败）" if batch_error else ""
        yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》完成{warn}，写入 {len(all_chapters)} 章', 'done': True}, ensure_ascii=False)}\n\n"
        yield {"generated_chapters": all_chapters}
        yield len(all_chapters)   # 最后 yield int，调用方接收后不转发给客户端

    # ── 判断走哪条路 ─────────────────────────────────
    def get_expandable_nodes() -> list[OutlineNode]:
        """
        收集已有大纲中尚无章节计划的节点。
        优先返回没有直接章节计划的卷；旧篇节点保留兼容展开。
        """
        existing_vols = db.query(OutlineNode).filter(
            OutlineNode.project_id == project_id,
            OutlineNode.parent_id.is_(None),
            OutlineNode.node_type == "volume",
        ).order_by(OutlineNode.sort_order).all()

        expandable: list[OutlineNode] = []
        for vol in existing_vols:
            arcs = db.query(OutlineNode).filter(
                OutlineNode.parent_id == vol.id,
                OutlineNode.node_type == "arc",
            ).order_by(OutlineNode.sort_order).all()

            if arcs:
                for arc in arcs:
                    has_chapters = db.query(OutlineNode).filter(
                        OutlineNode.parent_id == arc.id,
                        OutlineNode.node_type == "chapter_plan",
                    ).count() > 0
                    if not has_chapters:
                        expandable.append(arc)
            else:
                has_chapters = db.query(OutlineNode).filter(
                    OutlineNode.parent_id == vol.id,
                    OutlineNode.node_type == "chapter_plan",
                ).count() > 0
                if not has_chapters:
                    expandable.append(vol)

        return expandable

    # scale_hint → 续写模式默认章节数；规划模式会按总篇幅目标校准。
    _default_chapters = TARGET_CHAPTERS_PER_VOLUME

    async def stream():
        # ── Step 0: 清除现有大纲（可选）──────────────────
        if req.clear_existing:
            db.query(Chapter).filter(
                Chapter.project_id == project_id
            ).update({"outline_node_id": None}, synchronize_session=False)
            # outline_revisions.volume_node_id → outline_nodes.id，不先解除会触发 FK 错误
            db.query(OutlineRevision).filter(
                OutlineRevision.project_id == project_id,
            ).update({"volume_node_id": None}, synchronize_session=False)
            db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id
            ).delete(synchronize_session=False)
            db.commit()
            yield f"data: {json.dumps({'event': 'progress', 'step': 0, 'total': '?', 'label': '已清除现有大纲（章节正文已保留）', 'done': True}, ensure_ascii=False)}\n\n"

        # ── 分叉：续写模式 vs. 规划模式 ──────────────────
        expandable = get_expandable_nodes()
        use_fill_mode = (not req.clear_existing) and len(expandable) > 0

        if use_fill_mode:
            # ════════════════════════════════════════════
            #  续写模式：直接填充已有空卷/旧篇，不新建卷
            # ════════════════════════════════════════════
            total_steps = len(expandable)
            names = "、".join(f"《{n.title}》" for n in expandable)
            yield f"data: {json.dumps({'event': 'progress', 'step': 0, 'total': total_steps, 'label': f'发现 {len(expandable)} 个空节点，开始续写：{names}', 'done': True}, ensure_ascii=False)}\n\n"

            chapter_offset = db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id,
                OutlineNode.node_type == "chapter_plan",
            ).count()
            root_volumes = db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id,
                OutlineNode.parent_id.is_(None),
                OutlineNode.node_type == "volume",
            ).order_by(OutlineNode.sort_order).all()
            global_outline_context = _format_global_outline_context([
                (
                    node,
                    (node.extra or {}).get("target_chapters", _default_chapters)
                    if isinstance(node.extra, dict)
                    else _default_chapters,
                )
                for node in (root_volumes or expandable)
            ])
            existing_context_limit = 24 if req.model_profile == "gemini" else 8
            book_chapters_so_far = _load_existing_chapter_context(
                db,
                project_id,
                limit=existing_context_limit,
            )

            total_written = 0
            for step_i, target in enumerate(expandable):
                yield f"data: {json.dumps({'event': 'progress', 'step': step_i + 1, 'total': total_steps, 'label': f'正在展开《{target.title}》…'}, ensure_ascii=False)}\n\n"
                written = 0
                async for chunk in fill_node_with_chapters(
                    target, _default_chapters, chapter_offset,
                    step=step_i + 1, total_steps=total_steps,
                    global_outline_context=global_outline_context,
                    prior_chapters=book_chapters_so_far,
                ):
                    if isinstance(chunk, int):
                        written = chunk
                    elif isinstance(chunk, dict) and "generated_chapters" in chunk:
                        book_chapters_so_far = [
                            *book_chapters_so_far,
                            *chunk["generated_chapters"],
                        ]
                    else:
                        yield chunk
                chapter_offset += written
                total_written += written

            yield f"data: {json.dumps({'event': 'complete', 'message': f'续写完成！共为 {len(expandable)} 个节点写入 {total_written} 章'}, ensure_ascii=False)}\n\n"
            yield "data: {\"event\": \"end\"}\n\n"

        else:
            # ════════════════════════════════════════════
            #  规划模式：AI 从零规划卷结构，建卷再填章节
            # ════════════════════════════════════════════
            yield f"data: {json.dumps({'event': 'progress', 'step': 1, 'total': '?', 'label': 'AI 正在分析故事，规划卷章结构…'}, ensure_ascii=False)}\n\n"

            # 从 project.target_words 派生规划参数（单一数据源）
            from app.services.outline_planning import words_to_plan
            proj_target_words = int(project.target_words or 1_200_000)
            tw_plan = words_to_plan(proj_target_words)
            derived_scale_hint = tw_plan["scale_label"]

            try:
                structure = await svc.plan_full_structure(
                    project_title=project.title,
                    genre=project.genre or "玄幻",
                    logline=project.logline or "",
                    world_summary=world_summary,
                    character_summary=char_summary,
                    theme_statement=theme_statement,
                    scale_hint=derived_scale_hint,
                    target_words=proj_target_words,
                )
            except Exception as e:
                yield f"data: {json.dumps({'event': 'error', 'message': f'结构规划失败：{str(e)}'}, ensure_ascii=False)}\n\n"
                return

            if "error" in structure:
                yield f"data: {json.dumps({'event': 'error', 'message': structure['error']}, ensure_ascii=False)}\n\n"
                return

            volumes_data = structure.get("volumes", [])
            if not volumes_data:
                yield f"data: {json.dumps({'event': 'error', 'message': 'AI 未返回有效的卷结构，请重试'}, ensure_ascii=False)}\n\n"
                return

            volumes_data = normalize_volume_plan(volumes_data, target_words=proj_target_words)

            total_steps = 1 + len(volumes_data)
            total_chapters_planned = sum(v["planned_chapters"] for v in volumes_data)

            existing_vol_count = db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id,
                OutlineNode.parent_id.is_(None),
            ).count()

            volume_nodes: list[tuple[OutlineNode, int]] = []
            for i, vol in enumerate(volumes_data):
                node = OutlineNode(
                    project_id=project_id,
                    parent_id=None,
                    node_type="volume",
                    title=vol.get("title", f"第{existing_vol_count + i + 1}卷"),
                    summary=vol.get("summary", ""),
                    hook=vol.get("hook", ""),
                    conflict=vol.get("conflict", ""),
                    extra={
                        "theme_stage": vol.get("theme_stage", ""),
                        "character_arc": vol.get("character_arc", ""),
                        "target_chapters": TARGET_CHAPTERS_PER_VOLUME,
                        "target_words_per_chapter": TARGET_WORDS_PER_CHAPTER,
                    },
                    sort_order=existing_vol_count + i,
                )
                db.add(node)
                db.flush()
                volume_nodes.append((node, vol["planned_chapters"]))
            db.commit()

            vol_summary = "、".join(f"《{n.title}》{pc}章" for n, pc in volume_nodes)
            global_outline_context = _format_global_outline_context(volume_nodes)
            yield f"data: {json.dumps({'event': 'progress', 'step': 1, 'total': total_steps, 'label': f'结构规划完成：{vol_summary}，共 {total_chapters_planned} 章', 'done': True}, ensure_ascii=False)}\n\n"

            chapter_offset = db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id,
                OutlineNode.node_type == "chapter_plan",
            ).count()
            existing_context_limit = 24 if req.model_profile == "gemini" else 8
            book_chapters_so_far = _load_existing_chapter_context(
                db,
                project_id,
                limit=existing_context_limit,
            )

            total_written = 0
            for vi, (vol_node, planned_chapters) in enumerate(volume_nodes):
                step = vi + 2
                yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'正在展开《{vol_node.title}》（{planned_chapters} 章）…'}, ensure_ascii=False)}\n\n"
                written = 0
                async for chunk in fill_node_with_chapters(
                    vol_node, planned_chapters, chapter_offset,
                    step=step, total_steps=total_steps,
                    global_outline_context=global_outline_context,
                    prior_chapters=book_chapters_so_far,
                ):
                    if isinstance(chunk, int):
                        written = chunk
                    elif isinstance(chunk, dict) and "generated_chapters" in chunk:
                        book_chapters_so_far = [
                            *book_chapters_so_far,
                            *chunk["generated_chapters"],
                        ]
                    else:
                        yield chunk
                chapter_offset += written
                total_written += written

            yield f"data: {json.dumps({'event': 'complete', 'message': f'全量大纲生成完成！共 {len(volume_nodes)} 卷 {total_written} 章'}, ensure_ascii=False)}\n\n"
            yield "data: {\"event\": \"end\"}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
