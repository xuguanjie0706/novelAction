"""prompt 公共底座：system 人设 + 紧凑上下文 / 对标 / 境界档位块。

prompts / prompts_extra / prompts_chapter 三个 builder 模块共享，
单独成模块以避免互相 import 成环。
"""

from __future__ import annotations

SYS_BASE = (
    "你是有15年经验的番茄/七猫大白文主编，专精移动端碎片化爽文。\n"
    "你的信条：读者要的是『情绪势能→爽点引爆→即时反馈→更强钩子』的循环，"
    "不是文学因果链。爽点要直给、要有观众、要让读者一眼看懂。\n"
    "信息密度要低，每章新增设定/新人物不超过给定上限；金手指当章见效；主角不许窝囊超过一章。\n"
    "只返回 JSON，不要任何解释、注释或 markdown 说明文字。"
)


def ctx_brief(ctx: dict) -> str:
    """把已生成产物压成紧凑上下文（早期步骤用；后期步骤用 ctx_rich 全量档案）。"""
    parts = []
    if "logline" in ctx:
        parts.append(f"一句话创意：{ctx['logline']}")
    if ctx.get("title_blurb"):
        tb = ctx["title_blurb"]
        parts.append(f"书名：{tb.get('chosen_title', '')}")
    if "golden_finger" in ctx:
        gf = ctx["golden_finger"]
        parts.append(f"金手指：{gf.get('name')}（{gf.get('core_ability', '')[:40]}）")
    if "power_ladder" in ctx:
        lv = ctx["power_ladder"].get("levels", [])
        parts.append("境界：" + "→".join(x.get("name", "") for x in lv[:8]))
    if "characters" in ctx:
        names = "、".join(c.get("name", "") for c in ctx["characters"][:6])
        parts.append(f"人物：{names}")
    if "storylines" in ctx:
        sl = "、".join(s.get("name", "") for s in ctx["storylines"])
        parts.append(f"故事线：{sl}")
    if "story_assets" in ctx and isinstance(ctx["story_assets"], dict):
        assets = ctx["story_assets"].get("plot_assets") or []
        if assets:
            aa = "、".join(
                f"{a.get('name', '')}({a.get('plot_role', '')})" for a in assets[:6]
            )
            parts.append(f"剧情资产（卷/章纲须围绕这批东西做文章，禁止另造同位宝物）：{aa}")
    return "\n".join(parts)


def benchmark_block(ctx: dict) -> str:
    """对标分析注入块：下游各步对齐对标特征（但禁止照抄任何作品情节/原句）。"""
    bm = ctx.get("benchmark") or {}
    if not bm:
        return ""
    books = "、".join(b.get("title", "") for b in (bm.get("reference_books") or [])[:5])
    sp = bm.get("style_profile") or {}
    style = "｜".join(
        f"{k}:{sp[k]}" for k in
        ("sentence_style", "pacing", "dialogue_density", "shuang_cadence", "narration_voice")
        if sp.get(k)
    )
    conv = "、".join(bm.get("setting_conventions") or [])
    tropes = "、".join(bm.get("tropes_to_use") or [])
    pit = "、".join(bm.get("pitfalls_to_avoid") or [])
    return (
        "\n【对标分析（生成须对齐这些特征；★只借鉴特征，禁止照抄任何作品的情节/人物/原句★）】\n"
        f"  对标书：{books}\n"
        + (f"  风格画像：{style}\n" if style else "")
        + (f"  设定套路：{conv}\n" if conv else "")
        + (f"  可用套路：{tropes}\n" if tropes else "")
        + (f"  避坑：{pit}\n" if pit else "")
    )


def ladder_block(ctx: dict) -> str:
    """境界体系档位清单（供卷/章对齐 realm rank）。"""
    levels = (ctx.get("power_ladder") or {}).get("levels") or []
    if not levels:
        return ""
    items = "　".join(f"{l.get('rank')}={l.get('name')}" for l in levels)
    return f"\n【境界体系档位（realm_rank 必须用这里的数字）】{items}\n"
