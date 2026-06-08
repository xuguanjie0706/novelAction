"""斗破线 Step 2：单条斗气主轴（replaces 通用 power_systems 的修仙多轴）。

设计动机
--------
通用 power_systems 对「玄幻」会走修仙五轴（灵根/天劫/飞升/丹道…），这与斗气大陆纯爽文
（《斗破苍穹》式）的设定根本冲突——本线只要**一条斗气阶位主轴**（斗者→斗帝），不要灵气、
不要渡劫、不要平行副轴。故本步骤直接生成单主轴并落 PowerSystem，绕开多轴架构师。

落库后用通用 ``persist_legacy_systems`` + ``sync_ctx_after_persist`` 同步 ctx，
保证下游（功法/法宝/人物/卷骨架）拿到标准的 power_level_names / power_level_registry，
与通用线零差异。红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

import logging
from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts.doupo_prompts import build_doupo_power_axis_prompt
from app.services.bootstrap.steps.power_systems.persist import (
    persist_legacy_systems,
    sync_ctx_after_persist,
)
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

logger = logging.getLogger(__name__)


async def gen_doupo_power_axis(svc: Any, project: Project, ctx: dict) -> list:
    """生成单条斗气主轴并落库为 PowerSystem。

    @returns PowerSystem 列表（供薄壳判定步骤成功 / count）。
    """
    # 斗破线题材统一按「玄幻」走流派工具箱，但力量主轴由本步骤独占生成
    ctx.setdefault("genre", "玄幻")

    system, prompt = build_doupo_power_axis_prompt(ctx)
    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.power_systems",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        # 容错：模型可能包了一层 {"systems": [...]} 或 {"power_systems": [...]}
        if isinstance(data, dict):
            data = data.get("systems") or data.get("power_systems") or [data]
        else:
            data = []

    # 只保留单主轴：强制第一条为 primary，丢弃任何多余副轴（斗气大陆无平行体系）
    data = [d for d in data if isinstance(d, dict)][:1]
    for d in data:
        d["axis_role"] = "primary"
        d.setdefault("system_type", "cultivation")

    results = persist_legacy_systems(svc, project, data)
    sync_ctx_after_persist(ctx, project, results)

    if results and not (project.world_overview or "").strip():
        project.world_overview = results[0].description or ""
        svc.db.commit()
    ctx["world_overview"] = project.world_overview or ctx.get("world_overview", "")

    logger.info(
        "doupo.power_axis 完成 project=%s 阶位数=%d 主轴=%s",
        project.id,
        len(ctx.get("power_level_names") or []),
        ctx.get("power_system_name", ""),
    )
    return results
