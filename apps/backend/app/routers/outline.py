from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import json

from app.database import get_db
from app.models import OutlineNode, Project, WorldSetting, Character
from app.models.chapter import Chapter
from app.schemas import OutlineNodeCreate, OutlineNodeUpdate, OutlineNodeOut
from app.services.ai_service import AIService

router = APIRouter(prefix="/projects/{project_id}/outline", tags=["outline"])


def build_tree(nodes: List[OutlineNode]) -> List[OutlineNodeOut]:
    """把扁平列表组装成嵌套树（所有层级均按 sort_order 排序）"""
    node_map = {str(n.id): OutlineNodeOut.model_validate(n) for n in nodes}
    # model_validate(from_attributes) 会带入 SQLAlchemy 已加载的 children；
    # 若再按 parent_id 挂接，同一子节点会出现两次（卷下两篇、章重复等）。
    for node_out in node_map.values():
        node_out.children.clear()
    roots = []
    for node_out in node_map.values():
        if node_out.parent_id is None:
            roots.append(node_out)
        else:
            parent = node_map.get(str(node_out.parent_id))
            if parent:
                parent.children.append(node_out)

    def sort_recursive(node_list: list) -> None:
        node_list.sort(key=lambda x: x.sort_order)
        for n in node_list:
            if n.children:
                sort_recursive(n.children)

    sort_recursive(roots)
    return roots


@router.get("/", response_model=List[OutlineNodeOut])
def get_outline_tree(project_id: str, db: Session = Depends(get_db)):
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id
    ).order_by(OutlineNode.sort_order, OutlineNode.created_at).all()
    return build_tree(nodes)


@router.post("/", response_model=OutlineNodeOut, status_code=201)
def create_node(project_id: str, payload: OutlineNodeCreate, db: Session = Depends(get_db)):
    node = OutlineNode(project_id=project_id, **payload.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    return OutlineNodeOut.model_validate(node)


@router.patch("/{node_id}", response_model=OutlineNodeOut)
def update_node(project_id: str, node_id: str, payload: OutlineNodeUpdate, db: Session = Depends(get_db)):
    node = db.query(OutlineNode).filter(
        OutlineNode.id == node_id, OutlineNode.project_id == project_id
    ).first()
    if not node:
        raise HTTPException(404, "Outline node not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(node, field, value)
    db.commit()
    db.refresh(node)
    return OutlineNodeOut.model_validate(node)


@router.delete("/{node_id}", status_code=204)
def delete_node(project_id: str, node_id: str, db: Session = Depends(get_db)):
    node = db.query(OutlineNode).filter(
        OutlineNode.id == node_id, OutlineNode.project_id == project_id
    ).first()
    if not node:
        raise HTTPException(404, "Outline node not found")
    db.delete(node)
    db.commit()


# ─────────────────────────────────────────────────────────────
#  AI 展开大纲（五要素格式）
# ─────────────────────────────────────────────────────────────

class ExpandRequest(BaseModel):
    node_id: str
    chapter_count: int = 10
    model_profile: str = "default"   # default / gemini


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

    # 统计当前已有章节数（用于编号连续）
    existing_count = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).count()

    world_summary = " | ".join(f"{s.title}: {(s.content or '')[:80]}" for s in settings[:4])
    char_summary = " | ".join(
        f"{c.name}（{c.role}，{c.faction or ''}）{(c.personality or '')[:40]}"
        for c in characters[:5]
    )

    svc = AIService(profile=req.model_profile, db=db)

    async def stream():
        yield f"data: {json.dumps({'event': 'start'}, ensure_ascii=False)}\n\n"
        try:
            result = await svc.expand_outline(
                node_title=node.title,
                node_type=node.node_type,
                node_summary=node.summary or "",
                project_title=project.title if project else "未命名",
                genre=project.genre or "玄幻" if project else "玄幻",
                world_summary=world_summary,
                character_summary=char_summary,
                existing_chapters=existing_count,
                chapter_count=req.chapter_count,
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


# ─────────────────────────────────────────────────────────────
#  全量生成大纲（卷结构 + 逐卷章节计划）
# ─────────────────────────────────────────────────────────────

class FullGenerateRequest(BaseModel):
    scale_hint: str = "auto"      # auto / short / medium / long — 篇幅倾向，AI 自主决定结构
    model_profile: str = "default"
    clear_existing: bool = False


@router.post("/ai-full-generate")
async def ai_full_generate_outline(
    project_id: str,
    req: FullGenerateRequest,
    db: Session = Depends(get_db),
):
    """
    全量生成大纲：AI 自主决定卷数和每卷章节数，无需用户指定。
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

    world_summary = " | ".join(
        f"{s.title}: {(s.content or '')[:80]}" for s in settings_list[:4]
    )
    char_summary = " | ".join(
        f"{c.name}（{c.role}，{c.faction or ''}）{(c.personality or '')[:40]}"
        for c in characters[:5]
    )

    svc = AIService(profile=req.model_profile, db=db)

    # ── 共用：按批次为单个节点生成并写入章节计划 ──────────────
    async def fill_node_with_chapters(
        target_node: OutlineNode,
        planned_chapters: int,
        chapter_offset: int,
        step: int,
        total_steps: int,
    ):
        """
        为 target_node（卷或篇）生成章节计划并入库。
        target_node 为卷时自动建篇包装；为篇时直接挂章节。
        返回 (写入章节数, 新的 chapter_offset)。
        以 async generator 推送进度 SSE。
        """
        BATCH_SIZE = 40 if req.model_profile == "gemini" else 15
        batches: list[int] = []
        remaining = planned_chapters
        while remaining > 0:
            batches.append(min(remaining, BATCH_SIZE))
            remaining -= BATCH_SIZE

        all_chapters: list[dict] = []
        batch_error = False

        for batch_idx, batch_count in enumerate(batches):
            batch_offset = chapter_offset + len(all_chapters)
            try:
                result = await svc.expand_outline(
                    node_title=target_node.title,
                    node_type=target_node.node_type,
                    node_summary=target_node.summary or "",
                    project_title=project.title,
                    genre=project.genre or "玄幻",
                    world_summary=world_summary,
                    character_summary=char_summary,
                    existing_chapters=batch_offset,
                    chapter_count=batch_count,
                )
                batch_chapters = result.get("chapters", [])
                if not batch_chapters:
                    yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》第{batch_idx+1}批返回空，跳过'}, ensure_ascii=False)}\n\n"
                else:
                    all_chapters.extend(batch_chapters)
                    if len(batches) > 1:
                        yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》第{batch_idx+1}/{len(batches)}批完成（+{len(batch_chapters)} 章）'}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》第{batch_idx+1}批失败：{str(e)}', 'error': True}, ensure_ascii=False)}\n\n"
                batch_error = True

        if not all_chapters:
            yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》未获得有效章节，已跳过', 'error': True, 'done': True}, ensure_ascii=False)}\n\n"
            yield 0   # 用 yield 传回写入数量（async generator 不能 return value）
            return

        # 确定章节挂载的父节点：卷→先建篇；篇→直接挂
        if target_node.node_type == "volume":
            subtitle = target_node.title.split("：", 1)[1] if "：" in target_node.title else target_node.title
            arc_count = db.query(OutlineNode).filter(
                OutlineNode.parent_id == target_node.id,
                OutlineNode.node_type == "arc",
            ).count()
            arc_node = OutlineNode(
                project_id=project_id,
                parent_id=target_node.id,
                node_type="arc",
                title=f"第{arc_count + 1}篇：{subtitle}",
                summary=target_node.summary or "",
                sort_order=arc_count,
            )
            db.add(arc_node)
            db.flush()
            parent_id = arc_node.id
        else:
            parent_id = target_node.id

        for ci, ch in enumerate(all_chapters):
            db.add(OutlineNode(
                project_id=project_id,
                parent_id=parent_id,
                node_type="chapter_plan",
                title=f"第{ch.get('number', chapter_offset + ci + 1)}章：{ch.get('title', '未命名')}",
                summary=ch.get("core_event"),
                hook=ch.get("opening_hook"),
                highlight=ch.get("end_hook"),
                conflict=ch.get("character_change"),
                sort_order=ci,
                extra={
                    "foreshadow":    ch.get("foreshadow", ""),
                    "pacing":        ch.get("pacing", "medium"),
                    "word_estimate": ch.get("word_estimate", 3000),
                    "end_hook":      ch.get("end_hook", ""),
                },
            ))
        db.flush()
        db.commit()

        warn = "（部分批次失败）" if batch_error else ""
        yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》完成{warn}，写入 {len(all_chapters)} 章', 'done': True}, ensure_ascii=False)}\n\n"
        yield len(all_chapters)   # 最后 yield int，调用方接收后不转发给客户端

    # ── 判断走哪条路 ─────────────────────────────────
    def get_expandable_nodes() -> list[OutlineNode]:
        """
        收集已有大纲中尚无章节计划的节点。
        优先返回篇节点（arc）；若卷下无篇，则返回卷节点。
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

    # scale_hint → 默认章节数（续写模式用，规划模式由 AI 自主决定）
    _default_chapters = {"short": 10, "medium": 15, "long": 20}.get(req.scale_hint, 15)

    async def stream():
        # ── Step 0: 清除现有大纲（可选）──────────────────
        if req.clear_existing:
            db.query(Chapter).filter(
                Chapter.project_id == project_id
            ).update({"outline_node_id": None}, synchronize_session=False)
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
            #  续写模式：直接填充已有空卷/篇，不新建卷
            # ════════════════════════════════════════════
            total_steps = len(expandable)
            names = "、".join(f"《{n.title}》" for n in expandable)
            yield f"data: {json.dumps({'event': 'progress', 'step': 0, 'total': total_steps, 'label': f'发现 {len(expandable)} 个空节点，开始续写：{names}', 'done': True}, ensure_ascii=False)}\n\n"

            chapter_offset = db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id,
                OutlineNode.node_type == "chapter_plan",
            ).count()

            total_written = 0
            for step_i, target in enumerate(expandable):
                yield f"data: {json.dumps({'event': 'progress', 'step': step_i + 1, 'total': total_steps, 'label': f'正在展开《{target.title}》…'}, ensure_ascii=False)}\n\n"
                written = 0
                async for chunk in fill_node_with_chapters(
                    target, _default_chapters, chapter_offset,
                    step=step_i + 1, total_steps=total_steps,
                ):
                    if isinstance(chunk, int):
                        written = chunk
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

            try:
                structure = await svc.plan_full_structure(
                    project_title=project.title,
                    genre=project.genre or "玄幻",
                    logline=project.logline or "",
                    world_summary=world_summary,
                    character_summary=char_summary,
                    scale_hint=req.scale_hint,
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

            for vol in volumes_data:
                pc = vol.get("planned_chapters")
                if not isinstance(pc, int) or pc < 1:
                    vol["planned_chapters"] = _default_chapters

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
                    sort_order=existing_vol_count + i,
                )
                db.add(node)
                db.flush()
                volume_nodes.append((node, vol["planned_chapters"]))
            db.commit()

            vol_summary = "、".join(f"《{n.title}》{pc}章" for n, pc in volume_nodes)
            yield f"data: {json.dumps({'event': 'progress', 'step': 1, 'total': total_steps, 'label': f'结构规划完成：{vol_summary}，共 {total_chapters_planned} 章', 'done': True}, ensure_ascii=False)}\n\n"

            chapter_offset = db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id,
                OutlineNode.node_type == "chapter_plan",
            ).count()

            total_written = 0
            for vi, (vol_node, planned_chapters) in enumerate(volume_nodes):
                step = vi + 2
                yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'正在展开《{vol_node.title}》（{planned_chapters} 章）…'}, ensure_ascii=False)}\n\n"
                written = 0
                async for chunk in fill_node_with_chapters(
                    vol_node, planned_chapters, chapter_offset,
                    step=step, total_steps=total_steps,
                ):
                    if isinstance(chunk, int):
                        written = chunk
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


class CommitExpandRequest(BaseModel):
    parent_node_id: str
    chapters: List[dict]   # 前端确认后传回的章节列表


@router.post("/ai-expand/commit", response_model=List[OutlineNodeOut])
def commit_expand(
    project_id: str,
    req: CommitExpandRequest,
    db: Session = Depends(get_db),
):
    """把前端确认的章节计划批量写入大纲树"""
    parent = db.query(OutlineNode).filter(
        OutlineNode.id == req.parent_node_id,
        OutlineNode.project_id == project_id,
    ).first()
    if not parent:
        raise HTTPException(404, "Parent node not found")

    results = []
    for i, ch in enumerate(req.chapters):
        node = OutlineNode(
            project_id=project_id,
            parent_id=parent.id,
            node_type="chapter_plan",
            title=f"第{ch.get('number', i+1)}章：{ch.get('title', '未命名')}",
            summary=ch.get("core_event"),
            hook=ch.get("opening_hook"),
            highlight=ch.get("end_hook"),    # 章末钩子放 highlight 字段
            conflict=ch.get("character_change"),
            sort_order=i,
            extra={
                "foreshadow":    ch.get("foreshadow", ""),
                "pacing":        ch.get("pacing", "medium"),
                "word_estimate": ch.get("word_estimate", 3000),
                "end_hook":      ch.get("end_hook", ""),
            },
        )
        db.add(node)
        db.flush()
        results.append(node)

    db.commit()
    return [OutlineNodeOut.model_validate(n) for n in results]
