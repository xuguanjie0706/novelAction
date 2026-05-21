"""
Bootstrap LangGraph 节点实现 — 需要自定义 ctx 操作的复杂节点。

节点职责：emit step_start → 调用对应 step 函数 → emit step_done → 返回 state patch。
失败时 interrupt 暂停，等待用户 retry_step resume，不继续后续步骤。

代码红线：本文件 < 600 行（登记册过渡）；新逻辑优先抽到 step_failure / 步骤模块。
"""
from __future__ import annotations

import asyncio

from app.services.bootstrap.graph import BootstrapState, _make_svc, emit, _resolve_config
from app.services.bootstrap.step_failure import pause_for_step_retry, user_wants_step_retry
from app.services.llm_errors import format_llm_error_message


async def node_characters(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 5：生成人物库。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step="characters", label="生成人物库...")
        try:
            chars = await asyncio.wait_for(svc._gen_characters(project, ctx), timeout=300.0)
        except asyncio.TimeoutError:
            msg = "人物库生成超时（5 分钟），请重试"
        except Exception as exc:
            msg = format_llm_error_message(exc)
        else:
            ctx.setdefault("protagonist", "主角")
            ctx["_char_ids"] = [str(c.id) for c in chars]
            preview = "、".join(c.name for c in chars[:3]) if chars else "（跳过）"
            emit(run_id, "step_done", db, step="characters", count=len(chars), preview=preview)
            return {"ctx": ctx, "completed_steps": ["characters"]}

        user = await pause_for_step_retry(state, config, step="characters", message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": ctx, "errors": [{"step": "characters", "reason": msg}]}


async def node_skills_items(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 6 + 7 并行：功法技能 + 关键道具。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step="skills", label="生成核心功法技能...")
        emit(run_id, "step_start", db, step="items", label="生成关键道具法宝...")
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    svc._gen_key_skills(project, ctx),
                    svc._gen_key_items(project, ctx),
                    return_exceptions=True,
                ),
                timeout=240.0,
            )
        except asyncio.TimeoutError:
            msg = "功法/道具并行生成超时，请重试"
            user = await pause_for_step_retry(state, config, step="skills", message=msg, ctx=ctx)
            if user_wants_step_retry(user):
                continue
            return {"ctx": ctx, "errors": [{"step": "skills_items", "reason": "timeout"}]}

        failed: list[tuple[str, BaseException]] = []
        for step_name, res in (("skills", results[0]), ("items", results[1])):
            if isinstance(res, BaseException):
                emit(
                    run_id, "error", db, step=step_name,
                    message=f"生成失败：{format_llm_error_message(res)}",
                )
                failed.append((step_name, res))

        if failed:
            step_name, res = failed[0]
            msg = format_llm_error_message(res)
            user = await pause_for_step_retry(
                state, config, step=step_name, message=msg, ctx=ctx, emit_error=False,
            )
            if user_wants_step_retry(user):
                continue
            return {"ctx": ctx, "errors": [{"step": step_name, "reason": msg}]}

        skills = results[0] if not isinstance(results[0], BaseException) else []
        items = results[1] if not isinstance(results[1], BaseException) else []
        emit(run_id, "step_done", db, step="skills", count=len(skills))
        emit(run_id, "step_done", db, step="items", count=len(items))
        return {"ctx": ctx, "completed_steps": ["skills", "items"]}


async def node_volumes(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 9：卷级大纲。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step="volumes", label="规划卷级结构...")
        try:
            nodes = await asyncio.wait_for(svc._gen_volumes(project, ctx), timeout=300.0)
        except asyncio.TimeoutError:
            msg = "卷级结构生成超时（5 分钟），请重试"
        except Exception as exc:
            msg = f"卷级结构生成失败：{format_llm_error_message(exc)}"
        else:
            ctx["_volume_ids"] = [str(n.id) for n in nodes]
            emit(
                run_id, "step_done", db, step="volumes", count=len(nodes),
                preview=f"共{len(nodes)}卷" if nodes else "（跳过）",
            )
            return {"ctx": ctx, "completed_steps": ["volumes"]}

        user = await pause_for_step_retry(state, config, step="volumes", message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": ctx, "errors": [{"step": "volumes", "reason": msg}]}


async def node_relations(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 11：人物关系。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    from app.models import Project, Character
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    char_ids = ctx.pop("_char_ids", None) or []
    if char_ids:
        chars = db.query(Character).filter(Character.id.in_(char_ids)).all()
    else:
        chars = db.query(Character).filter(
            Character.project_id == state.get("project_id")
        ).all()

    while True:
        emit(run_id, "step_start", db, step="relations", label="建立人物关系...")
        try:
            rels = await asyncio.wait_for(svc._gen_relations(project, chars, ctx), timeout=240.0)
        except asyncio.TimeoutError:
            msg = "人物关系生成超时，请重试"
        except Exception as exc:
            msg = f"人物关系生成失败：{format_llm_error_message(exc)}"
        else:
            emit(run_id, "step_done", db, step="relations", count=len(rels))
            return {"ctx": ctx, "completed_steps": ["relations"]}

        user = await pause_for_step_retry(state, config, step="relations", message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": ctx, "errors": [{"step": "relations", "reason": msg}]}


async def node_vol1_chapters(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 12.5：第一卷章级大纲。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    from app.models import Project, OutlineNode
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    volume_ids = ctx.get("_volume_ids") or []
    volumes = (
        db.query(OutlineNode)
        .filter(OutlineNode.id.in_(volume_ids), OutlineNode.node_type == "volume")
        .order_by(OutlineNode.sort_order.asc())
        .all()
        if volume_ids else []
    )

    while True:
        emit(run_id, "step_start", db, step="vol1_chapters", label="生成第一卷章级大纲...")
        try:
            plans = await asyncio.wait_for(
                svc._gen_vol1_chapter_plans(project, volumes, ctx), timeout=360.0,
            )
        except asyncio.TimeoutError:
            msg = "章级大纲生成超时（6 分钟），请重试"
            user = await pause_for_step_retry(
                state, config, step="vol1_chapters", message=msg, ctx=ctx,
            )
            if user_wants_step_retry(user):
                continue
            return {"ctx": ctx, "errors": [{"step": "vol1_chapters", "reason": "timeout"}]}
        except Exception as exc:
            msg = f"章级大纲生成失败：{format_llm_error_message(exc)}"
            user = await pause_for_step_retry(
                state, config, step="vol1_chapters", message=msg, ctx=ctx,
            )
            if user_wants_step_retry(user):
                continue
            return {"ctx": ctx, "errors": [{"step": "vol1_chapters", "reason": str(exc)}]}

        ctx["_vol1_plan_ids"] = [str(p.id) for p in plans]
        vol1 = volumes[0] if volumes else None
        if vol1 and db:
            db.refresh(vol1)
        from app.services.outline_linter.sse_payload import build_vol1_chapters_sse_payload

        sse = build_vol1_chapters_sse_payload(
            plans,
            ctx,
            volume_extra=(vol1.extra if vol1 and isinstance(vol1.extra, dict) else None),
        )
        linter_message = sse.pop("linter_message", None)
        if sse.get("linter_blocked") and linter_message:
            user = await pause_for_step_retry(
                state, config, step="vol1_chapters", message=linter_message, ctx=ctx,
            )
            if user_wants_step_retry(user):
                continue
            return {"ctx": ctx, "errors": [{"step": "vol1_chapters", "reason": linter_message}]}

        emit(run_id, "step_done", db, step="vol1_chapters", **sse)
        return {"ctx": ctx, "completed_steps": ["vol1_chapters"]}


async def node_ch1_scenes(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 13：第1章场景蓝图。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    from app.models import Project, OutlineNode
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    vol1_plan_ids = ctx.get("_vol1_plan_ids") or []
    vol1_plans = (
        db.query(OutlineNode)
        .filter(OutlineNode.id.in_(vol1_plan_ids), OutlineNode.node_type == "chapter_plan")
        .order_by(OutlineNode.sort_order.asc())
        .all()
        if vol1_plan_ids else []
    )

    while True:
        emit(run_id, "step_start", db, step="ch1_scenes", label="生成第1章场景蓝图...")
        try:
            scenes = await asyncio.wait_for(
                svc._gen_ch1_scenes(project, vol1_plans, ctx), timeout=240.0,
            )
        except asyncio.TimeoutError:
            msg = "场景蓝图生成超时，请重试"
        except Exception as exc:
            msg = f"场景蓝图生成失败：{format_llm_error_message(exc)}"
        else:
            emit(
                run_id, "step_done", db, step="ch1_scenes", count=len(scenes),
                preview=f"第1章共{len(scenes)}场" if scenes else "（跳过）",
            )
            return {"ctx": ctx, "completed_steps": ["ch1_scenes"]}

        user = await pause_for_step_retry(state, config, step="ch1_scenes", message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": ctx, "errors": [{"step": "ch1_scenes", "reason": msg}]}


async def node_consistency(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 14：全局一致性扫描（最后一步）。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step="consistency", label="全局一致性扫描...")
        try:
            issues = await asyncio.wait_for(svc._gen_consistency_scan(project, ctx), timeout=240.0)
        except asyncio.TimeoutError:
            msg = "一致性扫描超时，请重试"
        except Exception as exc:
            msg = f"一致性扫描失败：{format_llm_error_message(exc)}"
        else:
            emit(
                run_id, "step_done", db, step="consistency", count=len(issues),
                preview=f"发现{len(issues)}处需确认项" if issues else "无明显矛盾",
            )
            emit(run_id, "complete", db, persist_status="done", project_id=state.get("project_id"))
            return {"ctx": ctx, "completed_steps": ["consistency"]}

        user = await pause_for_step_retry(state, config, step="consistency", message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": ctx, "errors": [{"step": "consistency", "reason": msg}]}


async def node_emotion_villain(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 9.5 + 9.8 并行：情绪节律图 + 反派行动线。

    两步均只依赖卷骨架（Step 9 产物），互不依赖，合并为单节点并行执行节省一次 AI 调用时间。
    asyncio 事件循环保证 svc.db.commit() 在 await 之间不被抢占，并行写入 project.extra 安全。
    任一步失败不中断另一步，错误收集后统一上报。
    """
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step="emotion_arc", label="规划全书情绪节律...")
        emit(run_id, "step_start", db, step="villain_arc", label="生成反派独立行动线...")
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    svc._gen_emotion_arc(project, ctx),
                    svc._gen_villain_arc(project, ctx),
                    return_exceptions=True,
                ),
                timeout=240.0,
            )
        except asyncio.TimeoutError:
            msg = "情绪节律/反派行动线并行生成超时，请重试"
            user = await pause_for_step_retry(state, config, step="emotion_arc", message=msg, ctx=ctx)
            if user_wants_step_retry(user):
                continue
            return {"ctx": ctx, "errors": [{"step": "emotion_villain", "reason": "timeout"}]}

        failed: list[tuple[str, BaseException]] = []
        for step_name, res in (("emotion_arc", results[0]), ("villain_arc", results[1])):
            if isinstance(res, BaseException):
                emit(run_id, "error", db, step=step_name,
                     message=f"生成失败：{format_llm_error_message(res)}")
                failed.append((step_name, res))

        if failed:
            step_name, res = failed[0]
            msg = format_llm_error_message(res)
            user = await pause_for_step_retry(
                state, config, step=step_name, message=msg, ctx=ctx, emit_error=False,
            )
            if user_wants_step_retry(user):
                continue
            return {"ctx": ctx, "errors": [{"step": step_name, "reason": msg}]}

        emotion_arc = results[0] if not isinstance(results[0], BaseException) else []
        villain_arc = results[1] if not isinstance(results[1], BaseException) else []
        emit(run_id, "step_done", db, step="emotion_arc", count=len(emotion_arc))
        emit(run_id, "step_done", db, step="villain_arc", count=len(villain_arc))
        return {"ctx": ctx, "completed_steps": ["emotion_arc", "villain_arc"]}


async def node_memory_relations(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 10 + 11 并行：记忆库种子 + 人物关系。

    两步均只依赖人物库（Step 5 产物），互不依赖，写入不同表（MemoryChunk / CharacterRelationship），
    合并为单节点并行执行节省一次 AI 调用时间。
    """
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    from app.models import Character, Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    char_ids = ctx.pop("_char_ids", None) or []
    if char_ids:
        chars = db.query(Character).filter(Character.id.in_(char_ids)).all()
    else:
        chars = db.query(Character).filter(
            Character.project_id == state.get("project_id")
        ).all()

    while True:
        emit(run_id, "step_start", db, step="memory", label="生成记忆库种子...")
        emit(run_id, "step_start", db, step="relations", label="建立人物关系...")
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    svc._gen_memory(project, ctx),
                    svc._gen_relations(project, chars, ctx),
                    return_exceptions=True,
                ),
                timeout=300.0,
            )
        except asyncio.TimeoutError:
            msg = "记忆库/人物关系并行生成超时，请重试"
            user = await pause_for_step_retry(state, config, step="memory", message=msg, ctx=ctx)
            if user_wants_step_retry(user):
                continue
            return {"ctx": ctx, "errors": [{"step": "memory_relations", "reason": "timeout"}]}

        failed: list[tuple[str, BaseException]] = []
        for step_name, res in (("memory", results[0]), ("relations", results[1])):
            if isinstance(res, BaseException):
                emit(run_id, "error", db, step=step_name,
                     message=f"生成失败：{format_llm_error_message(res)}")
                failed.append((step_name, res))

        if failed:
            step_name, res = failed[0]
            msg = format_llm_error_message(res)
            user = await pause_for_step_retry(
                state, config, step=step_name, message=msg, ctx=ctx, emit_error=False,
            )
            if user_wants_step_retry(user):
                continue
            return {"ctx": ctx, "errors": [{"step": step_name, "reason": msg}]}

        memories = results[0] if not isinstance(results[0], BaseException) else []
        rels = results[1] if not isinstance(results[1], BaseException) else []
        emit(run_id, "step_done", db, step="memory", count=len(memories))
        emit(run_id, "step_done", db, step="relations", count=len(rels))
        return {"ctx": ctx, "completed_steps": ["memory", "relations"]}
