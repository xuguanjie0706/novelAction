"""Step 9 卷级骨架生成 prompt。"""
from __future__ import annotations

from app.models import Project
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.protagonist_progression import build_protagonist_progression_prompt_block
from app.services.bootstrap.volume_beats import VOLUME_JSON_BEAT_SCHEMA
from app.services.bootstrap.antagonist_roster import build_antagonist_ladder_prompt_block
from app.services.bootstrap.volume_entity_registry import build_volume_entity_prompt_block
from app.services.bootstrap.storyline_weave_blocks import build_storyline_weave_volumes_block
from app.services.bootstrap.volume_chapter_starts import build_volume_global_ranges_block
from app.services.outline_planning import words_to_plan


def build_fanfic_volumes_block(ctx: dict) -> str:
    """同人专用卷骨架约束（仅 fanfic 线注入；通用线/番茄线 ctx 无 fanfic_positioning → 空串）。

    解决卷骨架「盲生成」：把原著时间线锚点、分歧点、切入点喂给卷级导演单，
    并在原著无修真体系时解除境界铁律，避免给都市/言情同人硬套金丹元婴。
    """
    fp = ctx.get("fanfic_positioning")
    if not fp:
        return ""
    canon = ctx.get("fanfic_canon") or {}
    dev = ctx.get("fanfic_deviation") or {}
    entry = ctx.get("fanfic_entry") or {}
    ladder = ctx.get("power_ladder") or {}

    lines = ["\n【同人·原著时间线与魔改节奏（卷骨架必须贯彻）】"]
    lines.append(
        f"  原著：{fp.get('source_work_title', '')} · {fp.get('fanfic_trope_label', '')} · "
        f"贴合{fp.get('canon_fidelity', 'medium')}"
    )
    anchors = canon.get("timeline_anchors") or []
    if anchors:
        lines.append("  原著时间线锚点（卷级推进须与之对齐/错开，不得无视）：")
        for a in anchors[:6]:
            lines.append(f"    · {a}")
    if dev.get("divergence_point"):
        lines.append(f"  首处分歧点：{dev['divergence_point']}（此前贴原著，此后走同人主线）")
    if entry.get("entry_chapter_hint"):
        lines.append(f"  切入位置：{entry['entry_chapter_hint']}（第一卷须从此处附近起笔）")
    if dev.get("main_plot_promise"):
        lines.append(f"  同人主线新增价值：{dev['main_plot_promise']}")
    lines.append(
        "  ⚠️ 卷节奏铁律：卷与卷之间沿「原著时间线 × 同人分歧扩大」双轴推进——"
        "前期贴原著借势造爽点，中期分歧扩大与原著走向背离，后期完全进入同人主线高潮；"
        "禁止逐卷复述原著剧情，每卷必须有相对原著的新增价值。"
    )
    psrc = str(canon.get("power_system_from_source") or "")
    has_realm = bool(ladder.get("social_ladder")) and "无明确体系" not in psrc
    if not has_realm:
        lines.append(
            "  ⚠️ 本书原著无修真/数值等级体系：protagonist_realm_start/end 与 volume_boss_realm "
            "请填「社会地位/势力位阶/影响力层级」，禁止套用金丹/元婴/斗罗等修真境界名；"
            "卷级战力曲线铁律按「地位/资源升级」理解。"
        )
    return "\n".join(lines) + "\n"


def build_volumes_prompt(project: Project, ctx: dict) -> tuple[str, str]:
    """返回 (system, user_prompt)。"""
    system = (
        "你是有30年经验的网络小说结构策划专家，负责卷级「导演单」而不仅是目录标题。"
        "只返回 JSON 数组，不要任何说明文字。"
    )

    storyline_hint = build_storyline_weave_volumes_block(ctx)
    tw = int(project.target_words or 1_200_000)
    plan = words_to_plan(tw)
    n_volumes = plan["total_volumes"]
    total_chapters_hint = plan["total_chapters"]
    per_vol = max(15, total_chapters_hint // max(n_volumes, 1))
    remainder = total_chapters_hint - per_vol * n_volumes
    planned_hint = [per_vol + (1 if i < remainder else 0) for i in range(n_volumes)]
    global_ranges_block = build_volume_global_ranges_block(planned_hint)

    positioning = ctx.get("positioning") or {}
    positioning_block = ""
    if isinstance(positioning, dict) and positioning:
        _pos_lines = []
        for key, label in (
            ("target_audience", "目标读者"),
            ("tropes", "核心爽点"),
            ("face_slap_pattern", "打脸节奏"),
            ("emotional_arc", "感情线占比"),
            ("pace_type", "节奏类型"),
            ("taboo_lines", "红线禁忌"),
            ("selling_point", "核心卖点"),
        ):
            val = positioning.get(key)
            if not val:
                continue
            if key == "tropes" and isinstance(val, list):
                val = "、".join(str(t) for t in val if t)
            elif key == "taboo_lines" and isinstance(val, list):
                val = "；".join(str(t) for t in val if t)
            _pos_lines.append(f"  {label}：{val}")
        if _pos_lines:
            positioning_block = "\n【立项定位（每卷必须贯彻）】\n" + "\n".join(_pos_lines) + "\n"

    kit_block = get_genre_kit_block(ctx)
    from app.services.bootstrap.pipeline.hook_context import collect_step_hooks

    fanfic_block = collect_step_hooks("volumes", ctx) or build_fanfic_volumes_block(ctx)
    entity_block = build_volume_entity_prompt_block(ctx)
    roster_block = build_antagonist_ladder_prompt_block(ctx, n_volumes)
    protagonist_progression_block = build_protagonist_progression_prompt_block(ctx, n_volumes)

    villain_block = ""
    villain_timelines = ctx.get("villain_timelines", [])
    if villain_timelines:
        villain_block = (
            "\n【反派行动时间线（卷级 phase 与燃点须与之对齐）】\n"
            + "\n".join(f"- {vt}" for vt in villain_timelines)
            + "\n⚠️ 反派明显占优的卷 → phase=dark_hour；反派计划被终结的卷 → phase=climax。\n"
        )

    char_profiles = ctx.get("char_profiles") or {}
    protagonist = ctx.get("protagonist", "主角")
    protag_block = ""
    if isinstance(char_profiles, dict) and protagonist in char_profiles:
        p = char_profiles[protagonist]
        if isinstance(p, dict):
            protag_block = (
                f"\n【主角行为驱动（燃点/高潮须由此欲望与恐惧推导）】\n"
                f"  恐惧/创伤：{p.get('core_wound') or '（未设定）'}\n"
                f"  当前欲望：{p.get('current_desire') or '（未设定）'}\n"
            )

    prompt = f"""小说：《{ctx['project_title']}》主角：{ctx.get('protagonist', '主角')}
创意：{ctx.get('logline')}
立意与类型：{ctx.get('premise', '')[:700] or '（未填写）'}
设定摘要：{ctx.get('settings_summary', '')}{storyline_hint}{villain_block}{positioning_block}{fanfic_block}{entity_block}{roster_block}{kit_block}{protag_block}

主线核心角色：{', '.join(ctx.get('char_names', []))}
⚠️ 节拍描述必须用到上述已命名角色/势力；可提及职能配角但核心燃点须绑定具名角色。
⚠️ 卷间差异化铁律（你一次生成全部卷，必须横向对比）：各卷 beat_highlights 的爽点场景/桥段
   不得雷同——禁止每卷都套用同一模板（如卷卷「宗门大比打脸」「禁地夺宝突破」）。
   舞台规模、对手层级、爽感类型须逐卷升级，体现「越往后格局越大」；后卷不得重复前卷已用过的爆点形式。

根据故事规模规划卷级结构，返回 JSON 数组。
【字数目标】全书 {tw:,} 字，约 {total_chapters_hint} 章；**必须恰好 {n_volumes} 卷**。
每卷 planned_chapters 填 15-80（标准 30 或 60）；各卷之和尽量接近 {total_chapters_hint} 章。
{global_ranges_block}{protagonist_progression_block}
【卷级战力曲线铁律】
- protagonist_realm_start / protagonist_realm_end 必填（可带小境，如「金丹境初期→金丹境后期」）。
- volume_boss / volume_boss_realm 必填；大境 rank 须 ≥ 前卷；同大境须更高小境（初期<中期<后期<圆满）。
- volume_boss_realm rank ≤ protagonist_realm_end 大境 rank + 2。
- summary/conflict 中出现的境界须与 protagonist_realm_end / volume_boss_realm 一致。

【phase 阶段（必填单值，表示整卷情绪走向，不等于高潮章号）】
  opening / rising / turning / dark_hour / climax / ending
  第一卷固定 opening；全书须含 climax；卷数少时可合并 turning+dark_hour。

{VOLUME_JSON_BEAT_SCHEMA}

[
  {{
    "title": "第一卷：卷标题",
    "sort_order": 0,
    "summary": "本卷核心剧情，120字内",
    "hook": "留给下一卷的悬念种子（不是本卷高潮本身）",
    "conflict": "本卷主要矛盾",
    "protagonist_realm_start": "本卷初主角境界名",
    "protagonist_realm_end": "本卷末主角境界名",
    "volume_boss": "当卷核心对立角色名",
    "volume_boss_realm": "BOSS 境界名",
    "volume_boss_path": "",
    "volume_boss_path_rank": "",
    "planned_chapters": 30,
    "phase": "opening",
    "beat_highlights": [],
    "volume_climax": {{ "chapter_hint": 26, "description": "…" }},
    "emotional_turning_point": {{ "chapter_hint": 15, "description": "…" }},
    "must_payoff_before_vol_end": [],
    "pacing_skeleton": "…"
  }}
]
只返回 JSON 数组。"""

    return system, prompt
