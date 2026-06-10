"""mode=dabai 专属 prompt（玄幻修仙大白文 · 极少 LLM 合并步）。"""
from __future__ import annotations

import json
from typing import Any

_SYS_DABAI = (
    "你是有15年经验的番茄/七猫玄幻修仙大白文主编。"
    "读者要的是：情绪势能→爽点引爆→即时反馈→更强钩子；境界阶梯清晰可数；"
    "金手指当章见效；禁止精品文式的强加代价/choice_cost。\n"
    "只返回 JSON，不要 markdown 或解释。"
)


def build_positioning_dabai_prompt(*, logline: str, premise: str) -> tuple[str, str]:
    system = (
        "你是网文市场分析 + 玄幻修仙选题编辑。\n"
        "一次输出 benchmark（对标）+ positioning（立项），定位须对齐对标。\n"
        "只返回 JSON。"
    )
    user = (
        f"一句话创意：{logline}\n"
        f"补充 premise：{(premise or '')[:400]}\n\n"
        "返回 JSON：\n"
        "{\n"
        '  "benchmark": {\n'
        '    "topic": "题材标签",\n'
        '    "reference_books": [{"title": "书名", "why_comparable": "...", '
        '"core_appeal": "...", "setting_motif": "...", "style_note": "..."}],\n'
        '    "style_profile": {"sentence_style": "短句", "pacing": "快", '
        '"dialogue_density": "高", "shuang_cadence": "3章一爆", "narration_voice": "口语"},\n'
        '    "setting_conventions": ["..."], "tropes_to_use": ["..."], '
        '"pitfalls_to_avoid": ["..."]\n'
        "  },\n"
        '  "positioning": {\n'
        '    "target_audience": "移动端碎片阅读小白",\n'
        '    "shuang_pool": ["打脸","升级","获宝","扮猪吃虎","装逼","群嘲反转","收小弟","救场","扬名"],\n'
        '    "face_slap_frequency": "每2-3章一次当众爽点",\n'
        '    "golden_three_strategy": "第1章蓄憋屈+金手指钩子；第2章见效；第3章当众打脸",\n'
        '    "pace_type": "fast", "emotional_arc": "憋屈→反击→扬名",\n'
        '    "taboo_lines": ["禁止文绉绉","禁止强加代价","禁止境界乱跳"],\n'
        '    "writing_style": "plain", "bootstrap_mode": "dabai",\n'
        '    "subgenre": "玄幻修仙", "core_satisfaction": "升级打脸"\n'
        "  }\n"
        "}"
    )
    return system, user


def dabai_to_generic_positioning(
    block: dict,
    *,
    benchmark: dict | None = None,
) -> dict:
    """dabai positioning → 通用 positioning 字段（供 gate resume / project 落库）。"""
    p = dict(block or {})
    p.setdefault("bootstrap_mode", "dabai")
    p.setdefault("writing_style", "plain")
    p.setdefault("pace_type", "fast")
    p.setdefault("target_audience", "移动端碎片阅读小白")
    tropes = p.get("shuang_pool") or p.get("tropes") or []
    if not tropes:
        tropes = ["升级打脸"]
    p.setdefault("tropes", tropes)
    p.setdefault("selling_point", p.get("core_satisfaction") or p.get("selling_point") or "升级打脸")
    if not str(p.get("face_slap_pattern") or "").strip():
        p["face_slap_pattern"] = (
            p.get("face_slap_frequency")
            or p.get("golden_three_strategy")
            or "每2-3章一次当众爽点"
        )
    if not p.get("reference_works"):
        refs: list[str] = []
        for rb in (benchmark or {}).get("reference_books") or []:
            if isinstance(rb, dict):
                title = str(rb.get("title") or "").strip()
                if title:
                    refs.append(title)
            elif isinstance(rb, str) and rb.strip():
                refs.append(rb.strip())
        p["reference_works"] = refs or ["玄幻修仙大白文对标"]
    if not p.get("taboo_lines"):
        p["taboo_lines"] = ["禁止文绉绉", "禁止强加代价", "禁止境界乱跳"]
    return p


def build_golden_power_dabai_prompt(ctx: dict) -> tuple[str, str]:
    contract = ctx.get("cultivation_contract") or {}
    levels = "、".join(ctx.get("power_level_names") or [])
    user = (
        f"小说：《{ctx.get('project_title', '')}》\n创意：{ctx.get('logline', '')}\n"
        f"境界大境：{levels or '（待生成8-12大境）'}\n"
        f"境界预算：全书 rank {contract.get('start_rank', 1)}→{contract.get('end_rank', '?')}\n\n"
        "一次返回 JSON（两块）：\n"
        "{\n"
        '  "golden_finger": {\n'
        '    "name": "金手指名", "type": "system/absorb/rebirth/talent",\n'
        '    "core_ability": "核心能力（大白话）", "limitation": "限制（勿写成道德负担）",\n'
        '    "upgrade_mechanism": "如何量化升级（如噬力值满即突破）",\n'
        '    "first_chapter_hook": "第1章末如何露出钩子"\n'
        "  },\n"
        '  "power_ladder_note": "与已生成大境对齐的一句话说明"\n'
        "}"
    )
    return _SYS_DABAI, user


def build_cast_world_dabai_prompt(ctx: dict, n_volumes: int) -> tuple[str, str]:
    pos = ctx.get("positioning") or {}
    pool = "、".join(pos.get("shuang_pool") or [])
    levels = "、".join(ctx.get("power_level_names") or [])
    user = (
        f"小说：《{ctx.get('project_title', '')}》\n创意：{ctx.get('logline', '')}\n"
        f"爽点池：{pool}\n全书 {n_volumes} 卷\n"
        f"境界体系（人物 start_realm / Boss boss_realm 必须从此列表精确选名）：{levels or '（待生成）'}\n\n"
        "一次返回 JSON（四块）：\n"
        "{\n"
        '  "factions": [{"name": "势力名", "stance": "压迫方/主角方/中立", '
        '"role": "在爽点循环中的作用", "power_tier": "最高战力档", "note": "前期/后期作用"}],\n'
        '  "characters": [{"name": "姓名（具体人名，禁止卷NBoss）", "role": "主角/打脸对象/女主/导师", '
        '"tier": "核心/arc", "start_realm": "起始境界（从境界体系列表选）", "persona": "性格", '
        '"function": "爽点功能"}],\n'
        '  "storylines": [{"name": "线名", "type": "main/revenge/romance/mystery", "summary": "一句话"}],\n'
        '  "antagonist_ladder": [{"volume_number": 1, "boss_name": "必须与 characters 中某反派姓名完全一致", '
        '"boss_realm": "对决境界（从境界体系列表选）", "faction": "所属势力", '
        '"face_slap_hook": "本卷打脸钩子"}]\n'
        "}\n"
        f"⚠️ antagonist_ladder 必须恰好 {n_volumes} 条；boss_name 禁止「卷1Boss」类占位；"
        "每卷 Boss 须在 characters 中已有同名档案（role=打脸对象/反派，tier=arc）。"
    )
    return _SYS_DABAI, user


def build_volumes_map_dabai_prompt(ctx: dict, n_volumes: int, planned: int) -> tuple[str, str]:
    contract = ctx.get("cultivation_contract") or {}
    windows = contract.get("volume_windows") or []
    win_lines = []
    for w in windows:
        win_lines.append(
            f"第{w.get('volume_number')}卷 rank {w.get('realm_start_rank')}→{w.get('realm_end_rank')}"
        )
    ladder = "、".join(
        f"{i + 1}={n}" for i, n in enumerate(ctx.get("power_level_names") or [])
    )
    user = (
        f"小说：《{ctx.get('project_title', '')}》\n创意：{ctx.get('logline', '')}\n"
        f"境界档位：{ladder}\n"
        + (f"【境界预算契约·必须遵守】\n" + "\n".join(win_lines) + "\n" if win_lines else "")
        + f"\n生成 {n_volumes} 卷，每卷 {planned} 章。\n"
        "返回 JSON 数组，每卷含爽点大节拍 + 本卷地图 + 境界区间：\n"
        "[{\n"
        '  "volume_number": 1, "title": "卷名", "phase": "opening",\n'
        f'  "planned_chapters": {planned},\n'
        '  "big_beats": ["2-3个大爆点"], "volume_climax": "卷末高潮", "end_hook": "勾下一卷",\n'
        '  "realm_start_rank": 1, "realm_end_rank": 2,\n'
        '  "volume_boss": "与对立面登记表 boss 完全一致",\n'
        '  "volume_boss_realm": "与登记表对决境界完全一致",\n'
        '  "world_map": {\n'
        '    "region_name": "区域名",\n'
        '    "locations": [{"name": "地点", "type": "city/wilderness/sect", '
        '"controller": "控制方", "danger": "safe/neutral/dangerous"}],\n'
        '    "travel_spine": ["地点A","地点B","地点C"],\n'
        '    "map_note": "本卷活动范围说明"\n'
        "  }\n"
        "}]"
    )
    return _SYS_DABAI, user


def build_chapter_plans_dabai_prompt(
    ctx: dict,
    *,
    vol: dict,
    batch_start: int,
    batch_end: int,
    prev_tail: str,
    realm_floor: int,
) -> tuple[str, str]:
    n = vol.get("planned_chapters", 30)
    wm = (vol.get("world_map") or vol.get("extra", {}).get("world_map") or {})
    locs = "、".join(
        x.get("name", "") for x in (wm.get("locations") or []) if isinstance(x, dict)
    )
    pool = "、".join((ctx.get("positioning") or {}).get("shuang_pool") or [])
    chars = "、".join(c.get("name", "") for c in (ctx.get("characters") or [])[:8])
    levels = " ".join(
        f"{l.get('rank')}={l.get('name')}"
        for l in (ctx.get("power_systems_full") or [{}])[0].get("levels", [])
        if isinstance(l, dict)
    )
    carry = ""
    if prev_tail:
        carry = f"\n【上批结尾承接】「{prev_tail[:120]}」\n"
    vr_lo = vol.get("realm_start_rank")
    vr_hi = vol.get("realm_end_rank")
    batch_count = batch_end - batch_start + 1
    user = (
        f"卷：{vol.get('title')} phase={vol.get('phase')} 共{n}章\n"
        f"本卷地图：{locs}\n本卷境界：{vr_lo}→{vr_hi} 本批起步 rank≥{realm_floor}\n"
        f"人物：{chars} 爽点类型：{pool}\n境界档位：{levels}\n"
        + carry
        + f"\n生成第{batch_start}～{batch_end}章（{batch_count}章）JSON 数组。\n"
        "每章：title（6～14字章名，概括本章爽点，禁止「未命名」）, shuang_type, yaqu_setup, "
        "emotion_turn, yinbao, shuang_payoff, witnesses, "
        "end_hook, new_info_count, involved_characters, is_big_beat, expected_words, "
        "realm_rank, location_name（须在本卷地图内）。禁止 choice_cost。"
    )
    system = _SYS_DABAI + (
        "\n章纲专项：憋屈→转折拍→引爆→爽感（有观众）→钩子；相邻章 shuang_type 不得相同。"
    )
    return system, user
