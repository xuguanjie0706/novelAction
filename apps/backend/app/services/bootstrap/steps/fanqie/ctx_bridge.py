"""步骤：番茄阶段一 → 通用 ctx 桥接（无 LLM 调用）。

番茄专线在 power_ladder 完成后调用此函数，把番茄规划产物填充为通用步骤
（gen_factions / gen_storylines / gen_antagonist_ladder / gen_characters 等）
所依赖的 ctx 键，确保后续通用步骤能正常运行。

设计原则：
- 只做「有则填、无则推导」，不覆盖已存在的值（幂等）
- 所有推导都是纯确定性转换，不依赖 AI
- 如果某个 fanqie 字段缺失，静默降级（不抛异常）
"""
from __future__ import annotations

from typing import Any


def bridge_fanqie_to_generic_ctx(ctx: dict, project: Any) -> None:
    """
    Power_ladder 完成后运行，把番茄阶段产物转换为通用步骤所依赖的 ctx 键。

    修改 ctx（in-place）；不返回值。

    Args:
        ctx:     当前 Bootstrap ctx（in-place 修改）
        project: Project ORM 对象（读 world_overview / extra）
    """
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    contrast   = ctx.get("contrast_design")    or {}
    gf         = ctx.get("golden_finger")       or {}
    fsm        = ctx.get("face_slap_map")       or {}
    ladder     = ctx.get("power_ladder")        or {}

    # ── story_core（gen_factions / gen_storylines / gen_characters 依赖）──────
    # conflict 里嵌入主角名，让 gen_characters 感知并优先沿用该名字
    protagonist_name = (ctx.get("protagonist") or "").strip()
    state_headline = (contrast.get("initial_state_headline") or "").strip()
    conflict_text = (
        f"主角「{protagonist_name}」—— {state_headline}"
        if protagonist_name and state_headline
        else state_headline or protagonist_name
    )
    if not ctx.get("story_core"):
        ctx["story_core"] = {
            "conflict": conflict_text,
            "theme":    fanqie_pos.get("core_satisfaction", ""),
            "premise":  fanqie_pos.get("algo_hook", ""),
        }

    # ── world_overview（power_ladder 已写入 project.world_overview）──────────
    if not ctx.get("world_overview"):
        ctx["world_overview"] = (
            (project.world_overview if project else None)
            or ladder.get("world_core_rule", "")
        )

    # ── power_level_names（format_power_context_block 依赖）──────────────────
    if not ctx.get("power_level_names"):
        social = ladder.get("social_ladder") or []
        if social:
            ctx["power_level_names"] = [
                (t.get("name") or f"第{i + 1}阶")
                for i, t in enumerate(social)
                if isinstance(t, dict)
            ]

    # ── settings_summary（gen_volumes context_builder 依赖）──────────────────
    if not ctx.get("settings_summary"):
        core_rule  = (ladder.get("world_core_rule") or "").strip()
        wealth_vis = (ladder.get("wealth_visualization") or "").strip()
        power_vis  = (ladder.get("power_visualization") or "").strip()
        parts = [p for p in (core_rule, wealth_vis, power_vis) if p]
        if parts:
            ctx["settings_summary"] = "；".join(parts[:3])

    # ── villain_timelines（antagonist_ladder prompt 依赖）────────────────────
    if not ctx.get("villain_timelines"):
        esc = (fsm.get("escalation_path") or "").strip()
        if esc:
            ctx["villain_timelines"] = [esc]

    # ── faction_hint（antagonist_ladder / characters prompt 依赖）────────────
    if not ctx.get("faction_summary"):
        world_rule = (ladder.get("world_core_rule") or "").strip()
        if world_rule:
            ctx["faction_summary"] = f"世界规则：{world_rule}"

    # ── writing_style 透传（确保 positioning 内有 writing_style=plain）─────
    pos = dict(ctx.get("positioning") or {})
    if not pos.get("writing_style"):
        pos["writing_style"] = ctx.get("writing_style", "plain")
    if not pos.get("pace_type"):
        pos["pace_type"] = "fast"
    # 用 face_slap_map 的真实节奏更新 positioning，改善 gen_volumes 注入质量
    slap_rhythm = (fsm.get("slap_rhythm") or "").strip()
    if slap_rhythm:
        pos["face_slap_pattern"] = slap_rhythm
    escalation = (fsm.get("escalation_path") or "").strip()
    if escalation:
        pos["emotional_arc"] = escalation
    selling = (fanqie_pos.get("algo_hook") or fanqie_pos.get("core_satisfaction") or "").strip()
    if selling:
        pos["selling_point"] = selling
    ctx["positioning"] = pos

    # ── 金手指摘要（gen_storylines / gen_settings 参考用）────────────────────
    if not ctx.get("golden_finger_summary") and gf.get("finger_name"):
        ctx["golden_finger_summary"] = (
            f"{gf.get('finger_name')}（{(gf.get('mechanism') or '')[:80]}）"
        )

    # ── 番茄出场序列 → char_intro_hint（gen_characters 主角锁定辅助）─────────
    # contrast_design 已把 protagonist_name 写入 ctx["protagonist"]；
    # 此处额外写一个 hint，供 gen_characters prompt 使用。
    if ctx.get("protagonist") and not ctx.get("protagonist_locked"):
        ctx["protagonist_locked"] = ctx["protagonist"]
