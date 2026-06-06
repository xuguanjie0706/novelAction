"""Bootstrap Fanqie 修仙线：境界主轴（替代 power_ladder 的修仙版）。

设计动机
--------
番茄通用 power_ladder 生成「社会五阶」，对修仙打脸流是结构性错配：修仙的爽感
引擎是境界体系本身。本 step 生成一条「单主轴 + 小境」的境界阶梯（8-12 大境，每境
含初期/中期/后期/圆满），命名要求自创以绕开公版套话，但放开（而非封禁）修仙母语。

与 power_ladder 完全兼容
-----------------------
产物填入与 power_ladder 相同的 ctx 键（``social_ladder`` 复用为大境数组，``tier``
即 rank），因此 ``hydrate_fanqie_power_ctx`` / ``sync_power_ladder_to_power_system`` /
``build_fanqie_realm_discipline_block`` 一行不改即可复用。新增键：
``axis_kind="cultivation"`` / ``realm_axis_name`` / ``sub_realm_segments`` /
``breakthrough_signature``，并落 ``Project.extra.fanqie_axis_kind="cultivation"``
供写作期重跑路径恢复境界纪律策略。

红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.prompts.cultivation_ladder_prompt import (
    build_cultivation_ladder_prompt,
)
from app.services.bootstrap.steps.fanqie._json_once import call_fanqie_json_once

_STEP = "power_ladder"  # 复用同一 step key（番茄图节点不变，仅内部分叉）

_MIN_REALMS = 8
_MAX_REALMS = 12


def _validate_cultivation(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "须为 JSON 对象"
    if not (data.get("realm_axis_name") or "").strip():
        return "realm_axis_name 不能为空"
    if not (data.get("world_core_rule") or "").strip():
        return "world_core_rule 不能为空"
    ladder = data.get("social_ladder")
    if not isinstance(ladder, list) or len(ladder) < _MIN_REALMS:
        return f"social_ladder 至少需要 {_MIN_REALMS} 个大境"
    # 主轴单调性：tier 必须存在且递增
    tiers: list[int] = []
    for item in ladder:
        if not isinstance(item, dict) or not (item.get("name") or "").strip():
            return "每个大境必须含非空 name"
        t = item.get("tier")
        if not isinstance(t, int):
            return "每个大境必须含整数 tier"
        tiers.append(t)
    if tiers != sorted(tiers) or len(set(tiers)) != len(tiers):
        return "大境 tier 必须严格递增且不重复"
    return None


async def gen_cultivation_ladder(svc: Any, project: Project, ctx: dict) -> dict:
    """
    生成修仙境界主轴：8-12 大境 × 四小境 + 境界压制可视化 + 破境外显。

    产物写入 ``Project.extra['power_ladder']``（语义为境界轴）并缓存到 ctx，
    收敛阶段同步到 PowerSystem 表。

    @returns power_ladder dict（axis_kind="cultivation"）
    @raises BootstrapStepError: JSON 解析或字段校验失败
    """
    system = "你是番茄修仙世界架构设计师，精通境界体系与越级打脸节奏。只返回 JSON，不要解释文字。"
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    gf = ctx.get("golden_finger") or {}
    fsm = ctx.get("face_slap_map") or {}

    prompt = build_cultivation_ladder_prompt(
        project_title=ctx.get("project_title", ""),
        genre_archetype=fanqie_pos.get("genre_archetype", ""),
        finger_name=gf.get("finger_name", ""),
        ceiling_description=gf.get("ceiling_description", ""),
        escalation_path=fsm.get("escalation_path", ""),
        logline=ctx.get("logline", ""),
    )

    data = await call_fanqie_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate_cultivation,
    )

    # 截断到 _MAX_REALMS，并强制 axis_kind 标记
    ladder = data.get("social_ladder") or []
    if len(ladder) > _MAX_REALMS:
        data["social_ladder"] = ladder[:_MAX_REALMS]
        end_t = data["social_ladder"][-1].get("tier")
        if isinstance(end_t, int):
            data["protagonist_end_tier"] = min(
                int(data.get("protagonist_end_tier") or end_t), end_t,
            )
    data["axis_kind"] = "cultivation"
    data.setdefault("sub_realm_segments", ["初期", "中期", "后期", "圆满"])

    extra = dict(project.extra or {})
    extra["power_ladder"] = data
    extra["fanqie_axis_kind"] = "cultivation"
    if not project.world_overview:
        project.world_overview = data.get("world_core_rule", "")
    project.extra = extra
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(project, "extra")
    svc.db.commit()

    ctx["power_ladder"] = data
    ctx["fanqie_axis_kind"] = "cultivation"
    ctx["world_overview"] = project.world_overview

    from app.services.bootstrap.fanqie_normalize import sync_power_ladder_to_power_system
    from app.services.bootstrap.fanqie_realm_policy import hydrate_fanqie_power_ctx

    hydrate_fanqie_power_ctx(ctx)
    sync_power_ladder_to_power_system(svc.db, project)
    return data
