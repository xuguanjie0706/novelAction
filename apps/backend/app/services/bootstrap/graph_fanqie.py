"""
graph_fanqie.py — 番茄小说专属 Bootstrap LangGraph（重构版）

拓扑（精简后，约10次 LLM 调用，较原版减少约40%）：
  Phase A  番茄算法定位
    fanqie_positioning → gate → project
  Phase B  番茄爽文公式（合并步骤，原三步→一次调用）
    → fanqie_formula（contrast+golden_finger+face_slap_map）→ power_ladder → ctx_bridge
  Phase C  世界构建（复用通用步骤函数）
    → factions → storylines → antagonist_ladder
    → characters → gate_characters
    → skills_items → settings（精简为3张核心卡）
  Phase D  卷级结构
    → volumes → gate_volumes
  Phase E  节奏 + 情绪
    → emotion_villain → rhythm_map（rule-based chapter_tags + LLM story_buffer）
  Phase F  记忆 / 伏笔 / 承诺
    → memory_relations → promise_seeds（core_mysteries+opening_contract 合并）
  Phase G  校验
    → signal_audit（含 consistency_issues，移除独立 consistency_scan）
    → END

精简决策（2026-06）：
- Phase B 合并：contrast/golden_finger/face_slap_map 三步→一次调用（-2 LLM）
- rhythm_map chapter_tags 改为规则生成，LLM 只跑 story_buffer（-0.8 LLM）
- core_mysteries + opening_contract 合并为 promise_seeds（-1 LLM）
- consistency_scan 移除（signal_audit 已输出 consistency_issues）（-1 LLM）

通用步骤（factions/storylines/...）直接复用 graph_nodes / graph_gates，
自动继承 writing_style=plain 和番茄 ctx，不另写 prompt。
代码红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

import asyncio
import logging

from langgraph.types import interrupt

from app.models import Project
from app.services.bootstrap.graph_ctx import sanitize_bootstrap_ctx
from app.services.bootstrap.graph import (
    BootstrapState,
    _make_svc,
    _persist,
    _resolve_config,
    _state_run_id,
    emit,
    get_fanqie_graph,
)
from app.services.bootstrap.json_once import BootstrapStepError
from app.services.bootstrap.steps.project import gen_project

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────
# 通用薄步骤执行器（Fanqie 版）
# ──────────────────────────────────────────────────────

def _fanqie_step_result_ok(result) -> tuple[bool, int]:
    """判断步骤产物是否有效；返回 (是否成功, 用于 step_done 的 count)。"""
    if isinstance(result, list):
        return len(result) > 0, len(result)
    if isinstance(result, dict):
        return bool(result), (1 if result else 0)
    return bool(result), (1 if result else 0)


async def _fanqie_step(
    state: BootstrapState,
    config: dict | None,
    step: str,
    label: str,
    fn,
    *,
    needs_project: bool = True,
) -> dict:
    """emit start → fn → emit done；失败则 interrupt 等待用户 retry_step（与同人线一致）。"""
    from app.services.bootstrap.step_failure import pause_for_step_retry, user_wants_step_retry
    from app.services.llm_errors import format_llm_error_message

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    project = None
    if needs_project:
        project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step=step, label=label)
        try:
            if needs_project:
                result = await asyncio.wait_for(fn(svc, project, ctx), timeout=300.0)
            else:
                result = await asyncio.wait_for(fn(svc, ctx), timeout=300.0)
        except BootstrapStepError as exc:
            msg = str(exc)
        except asyncio.TimeoutError:
            msg = f"{step} 超时（5 分钟），请重试或检查模型线路"
        except Exception as exc:
            msg = f"{step} 失败：{format_llm_error_message(exc)}"
            logger.warning("fanqie step %s failed: %s", step, exc)
        else:
            ok, count = _fanqie_step_result_ok(result)
            if ok:
                emit(run_id, "step_done", db, step=step, count=count)
                return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": [step]}
            msg = f"{step} 生成结果为空，请重试或更换模型线路"

        user = await pause_for_step_retry(state, config, step=step, message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": sanitize_bootstrap_ctx(ctx), "errors": [{"step": step, "reason": msg}]}


# ──────────────────────────────────────────────────────
# Phase A：番茄算法立项
# ──────────────────────────────────────────────────────

async def node_fanqie_positioning(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0：番茄算法立项，完成后置闸门等待确认。"""
    from app.services.bootstrap.steps.fanqie.algo_positioning import gen_algo_positioning

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="positioning", label="召开番茄算法立项会议...")
    ctx = dict(state.get("ctx") or {})
    ctx.update({"logline": state["logline"], "premise": state["premise"],
                "target_words": state["target_words"]})
    fanqie_pos = await gen_algo_positioning(svc, ctx)

    ctx["fanqie_positioning"] = fanqie_pos
    ctx["positioning"] = _to_generic_positioning(fanqie_pos)

    emit(run_id, "step_done", db, step="positioning", count=1,
         preview=fanqie_pos.get("genre_archetype", "")[:30])
    emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
         step="positioning", positioning=fanqie_pos,
         message="请确认番茄类型公式和核心爽感后点击「继续生成」")
    _persist(db, run_id, {}, gate_data={
        "kind": "positioning", "positioning": fanqie_pos,
        "logline": state["logline"], "premise": state.get("premise") or "",
        "target_words": state.get("target_words"),
    })
    return {"positioning": fanqie_pos, "ctx": ctx, "completed_steps": ["positioning"]}


async def node_fanqie_gate(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0 确认闸门：支持 approve / regenerate。"""
    from app.services.bootstrap.steps.fanqie.algo_positioning import gen_algo_positioning

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    positioning = dict(state.get("positioning") or {})
    ctx = dict(state.get("ctx") or {})

    while True:
        user_input = interrupt({"type": "positioning_gate", "step": "positioning",
                                "positioning": positioning})
        if not isinstance(user_input, dict):
            user_input = {}
        action = (user_input.get("action") or "approve").strip().lower()
        if action == "regenerate":
            ctx.update({"logline": state["logline"], "premise": state["premise"],
                        "target_words": state["target_words"]})
            positioning = await gen_algo_positioning(svc, ctx)
            ctx["fanqie_positioning"] = positioning
            ctx["positioning"] = _to_generic_positioning(positioning)
            emit(run_id, "step_done", db, step="positioning", count=1,
                 preview=positioning.get("genre_archetype", "")[:30])
            emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
                 step="positioning", positioning=positioning,
                 message="请再次确认番茄立项定位后继续生成")
            _persist(db, run_id, {}, gate_data={
                "kind": "positioning", "positioning": positioning,
                "logline": state["logline"], "premise": state.get("premise") or "",
                "target_words": state.get("target_words"),
            })
            continue
        updated = user_input.get("positioning", positioning)
        if not isinstance(updated, dict):
            updated = positioning
        ctx["fanqie_positioning"] = updated
        ctx["positioning"] = _to_generic_positioning(updated)
        emit(run_id, "gate_passed", db, persist_status="running",
             step="positioning", positioning=updated)
        return {"positioning": updated, "ctx": ctx}


async def node_project(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 1：创建 Project 记录（复用通用 gen_project）。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="project", label="生成项目基础信息...")
    ctx = dict(state.get("ctx") or {})
    project, ctx = await gen_project(svc, ctx)
    emit(run_id, "step_done", db, step="project", count=1,
         preview=f"《{project.title}》{project.genre}")
    _persist(db, run_id, {}, project_id=str(project.id))
    return {"project_id": str(project.id), "ctx": ctx, "completed_steps": ["project"]}


# ──────────────────────────────────────────────────────
# Phase B：番茄爽文公式（合并步骤）
# ──────────────────────────────────────────────────────

async def node_fanqie_formula(s, c=None):
    """一次调用完成落差设计 + 金手指工程 + 打脸地图（原三步合并）。"""
    from app.services.bootstrap.steps.fanqie.fanqie_formula import gen_fanqie_formula
    return await _fanqie_step(s, c, "fanqie_formula", "设计爽文公式（落差+金手指+打脸地图）...", gen_fanqie_formula)

async def _gen_power_axis(svc, project, ctx):
    """境界轴分发：修仙→cultivation_ladder，其余→通用 power_ladder（社会阶梯）。"""
    from app.services.bootstrap.fanqie_axis import is_xianxia_archetype

    if is_xianxia_archetype(ctx):
        from app.services.bootstrap.steps.fanqie.cultivation_ladder import gen_cultivation_ladder
        return await gen_cultivation_ladder(svc, project, ctx)
    from app.services.bootstrap.steps.fanqie.power_ladder import gen_power_ladder
    return await gen_power_ladder(svc, project, ctx)


async def node_power_ladder(s, c=None):
    return await _fanqie_step(s, c, "power_ladder", "构建境界主轴 / 权力阶梯...", _gen_power_axis)


async def node_ctx_bridge(state: BootstrapState, config: dict | None = None) -> dict:
    """Phase B→C 桥接：把番茄产物转换为通用 ctx 键（无 LLM 调用，静默执行）。

    持久化到 project.extra 的内容：
    1. positioning（含真实 face_slap_pattern/selling_point，build_full_ctx 依赖）
    2. fanqie_positioning（is_fanqie_project 检测 + 单步重跑 fanqie_ctx 恢复依赖）
    """
    from app.services.bootstrap.steps.fanqie.ctx_bridge import bridge_fanqie_to_generic_ctx
    from sqlalchemy.orm.attributes import flag_modified

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    ctx = dict(state.get("ctx") or {})
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    bridge_fanqie_to_generic_ctx(ctx, project)
    if project:
        extra = dict(project.extra or {})
        if ctx.get("positioning"):
            extra["positioning"] = ctx["positioning"]
        # fanqie_positioning 本体仅在 ctx/state 中，写入 extra 供后续重跑路径读取
        if ctx.get("fanqie_positioning"):
            extra["fanqie_positioning"] = ctx["fanqie_positioning"]
        project.extra = extra
        flag_modified(project, "extra")
        db.commit()
    return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": ["ctx_bridge"]}


# ──────────────────────────────────────────────────────
# Phase C：世界构建（复用通用步骤函数）
# ──────────────────────────────────────────────────────

async def node_factions(s, c=None):
    from app.services.bootstrap.steps.factions import gen_factions
    return await _fanqie_step(s, c, "factions", "生成势力体系（简版）...", gen_factions)

async def node_storylines(s, c=None):
    from app.services.bootstrap.steps.storylines import gen_storylines
    return await _fanqie_step(s, c, "storylines", "生成故事线...", gen_storylines)

async def node_antagonist_ladder(s, c=None):
    from app.services.bootstrap.steps.antagonist_ladder import gen_antagonist_ladder
    return await _fanqie_step(s, c, "antagonist_ladder", "规划卷级对立面阶梯...", gen_antagonist_ladder)

async def node_characters(state: BootstrapState, config: dict | None = None) -> dict:
    """人物生成：复用 graph_nodes.node_characters（自带重试 + gate_characters 联动）。"""
    from app.services.bootstrap.graph_nodes import node_characters as _generic_characters
    return await _generic_characters(state, config)

async def node_gate_characters(state: BootstrapState, config: dict | None = None) -> dict:
    from app.services.bootstrap.graph_gates import node_gate_characters as _gate
    return await _gate(state, config)

async def node_skills_items(state: BootstrapState, config: dict | None = None) -> dict:
    from app.services.bootstrap.graph_nodes import node_skills_items as _si
    return await _si(state, config)

async def node_settings(state: BootstrapState, config: dict | None = None) -> dict:
    """番茄版设定卡：仅生成 3 张直接影响场景和打脸的核心卡。

    番茄读者不看深度世界观；只保留「主角起点生存环境」「世界底层规则」
    「资源经济与稀缺机制」三张，其余略去节省 LLM token 和生成时间。
    """
    from app.services.bootstrap.steps.settings import gen_settings
    from app.services.bootstrap.prompts.blueprints import GEMINI_SETTING_BLUEPRINTS

    _KEEP = {"主角起点生存环境", "世界底层规则", "资源经济与稀缺机制"}
    fanqie_blueprints = [bp for bp in GEMINI_SETTING_BLUEPRINTS if bp.get("title") in _KEEP]
    if not fanqie_blueprints:
        fanqie_blueprints = GEMINI_SETTING_BLUEPRINTS[:3]

    async def _gen(svc, project, ctx):
        return await gen_settings(svc, project, ctx, blueprints=fanqie_blueprints)

    return await _fanqie_step(state, config, "settings", "生成世界观设定卡（番茄精简版，3张）...", _gen)


# ──────────────────────────────────────────────────────
# Phase D：卷级结构
# ──────────────────────────────────────────────────────

async def node_volumes(state: BootstrapState, config: dict | None = None) -> dict:
    """卷级骨架；失败时 interrupt 暂停。"""
    from app.services.bootstrap.steps.volumes import gen_volumes
    from app.services.bootstrap.step_failure import pause_for_step_retry, user_wants_step_retry
    from app.services.llm_errors import format_llm_error_message

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step="volumes", label="规划全书卷级骨架（卷纲）...")
        try:
            nodes = await asyncio.wait_for(gen_volumes(svc, project, ctx), timeout=300.0)
        except asyncio.TimeoutError:
            msg = "卷级结构生成超时（5 分钟），请重试"
        except Exception as exc:
            msg = f"卷级结构生成失败：{format_llm_error_message(exc)}"
        else:
            if nodes:
                ctx["_volume_ids"] = [str(n.id) for n in nodes]
                emit(run_id, "step_done", db, step="volumes", count=len(nodes),
                     preview=f"共{len(nodes)}卷")
                return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": ["volumes"]}
            msg = "卷级结构生成结果为空，请重试或更换模型线路"

        user = await pause_for_step_retry(state, config, step="volumes", message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": sanitize_bootstrap_ctx(ctx), "errors": [{"step": "volumes", "reason": msg}]}

async def node_gate_volumes(state: BootstrapState, config: dict | None = None) -> dict:
    from app.services.bootstrap.graph_gates import node_gate_volumes as _gate
    return await _gate(state, config)


# ──────────────────────────────────────────────────────
# Phase E：节奏 + 情绪
# ──────────────────────────────────────────────────────

async def node_emotion_villain(state: BootstrapState, config: dict | None = None) -> dict:
    from app.services.bootstrap.graph_nodes import node_emotion_villain as _ev
    return await _ev(state, config)

async def node_rhythm(s, c=None):
    from app.services.bootstrap.steps.fanqie.rhythm_map import gen_rhythm_map
    return await _fanqie_step(s, c, "rhythm_map", "生成爽点节奏图 + 剧情储量池...", gen_rhythm_map)


# ──────────────────────────────────────────────────────
# Phase F：记忆 / 伏笔 / 承诺
# ──────────────────────────────────────────────────────

async def node_memory_relations(state: BootstrapState, config: dict | None = None) -> dict:
    from app.services.bootstrap.graph_nodes import node_memory_relations as _mr
    return await _mr(state, config)

async def node_promise_seeds(s, c=None):
    """一次调用完成核心谜题预置 + 开局追读承诺（原两步合并）。"""
    from app.services.bootstrap.steps.fanqie.promise_seeds import gen_promise_seeds
    return await _fanqie_step(s, c, "promise_seeds", "预置谜题钩子 + 开局追读承诺...", gen_promise_seeds)


# ──────────────────────────────────────────────────────
# Phase G：校验
# signal_audit 已在内部写入 consistency_issues，无需独立 consistency_scan。
# ──────────────────────────────────────────────────────

async def node_audit(state: BootstrapState, config: dict | None = None) -> dict:
    """番茄算法双校验（最后一步，完成后 emit complete）。"""
    from app.services.bootstrap.steps.fanqie.signal_audit import gen_signal_audit

    patch = await _fanqie_step(state, config, "signal_audit", "执行番茄算法双校验...", gen_signal_audit)
    if patch.get("errors"):
        return patch

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    project_id = state.get("project_id")
    if project_id:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            merged_ctx = dict(state.get("ctx") or {})
            merged_ctx.update(patch.get("ctx") or {})
            from app.services.bootstrap.fanqie_normalize import converge_fanqie_project
            converge_fanqie_project(db, project, merged_ctx)
    emit(run_id, "complete", db, persist_status="done", project_id=project_id)
    return patch


# ──────────────────────────────────────────────────────
# 后台任务入口（委托 pipeline.runner）
# ──────────────────────────────────────────────────────

async def run_bootstrap_fanqie(
    run_id: str, *, logline: str, premise: str, target_words: int,
    model_profile: str, llm_provider_id, user_id,
    writing_style: str = "plain",
) -> None:
    from app.services.bootstrap.pipeline.runner import run_pipeline
    from app.services.bootstrap.pipeline.styles import STYLE_REGISTRY

    await run_pipeline(
        get_fanqie_graph(),
        STYLE_REGISTRY["fanqie"],
        run_id,
        logline=logline,
        premise=premise,
        target_words=target_words,
        model_profile=model_profile,
        llm_provider_id=llm_provider_id,
        user_id=user_id,
        writing_style=writing_style,
    )


async def resume_bootstrap_fanqie(
    run_id: str, resume_payload: dict, *,
    model_profile: str, llm_provider_id, user_id,
) -> None:
    from app.services.bootstrap.pipeline.runner import resume_pipeline

    await resume_pipeline(
        get_fanqie_graph(),
        run_id,
        resume_payload,
        model_profile=model_profile,
        llm_provider_id=llm_provider_id,
        user_id=user_id,
    )


# ──────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────

def _to_generic_positioning(fanqie_pos: dict) -> dict:
    """
    将番茄立项定位转换为通用 positioning 格式，
    供 gen_project 等复用步骤读取（不影响番茄专属字段）。
    注意：face_slap_pattern / emotional_arc 会在 ctx_bridge 阶段用真实值更新。
    """
    return {
        "target_audience": f"番茄男频·{fanqie_pos.get('genre_archetype', '')}读者",
        "tropes": fanqie_pos.get("platform_tags", []),
        "reference_works": fanqie_pos.get("competitor_works", []),
        "selling_point": fanqie_pos.get("algo_hook", ""),
        "face_slap_pattern": "每3章一小打，每10章一大打",
        "emotional_arc": "番茄爽文情绪曲线：压抑→爆发→余韵",
        "pace_type": "fast",
        "writing_style": "plain",
        "taboo_lines": (
            [str(fanqie_pos["taboo_check"])]
            if fanqie_pos.get("taboo_check")
            else ["无"]
        ),
    }
