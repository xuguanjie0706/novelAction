"""Step 12 开局追读承诺生成 prompt（须锚定卷一骨架与已落库设定）。

职责边界（2026-06，「无事实承诺」改造）
--------------------------------------
开局承诺只负责**追读手法**（钩子 / 爽点形态 / 伏笔 / 节奏 / 避坑），是开局质量的
"提前聚焦器"。它**不是、也禁止成为剧情事实的来源**——谁第几章死、谁杀谁、境界突破
到第几层、Boss 归属哪一卷，全部由 roster（Step 4.5）与卷骨架（Step 9，即大纲）唯一
裁定。承诺需要点名时只能"引用"这些既定事实，不得自行发明。

这样设计的原因：承诺与大纲并存时，凡承诺擅自裁定事实（如"第10章斩杀陆长歌"而 roster
将陆长歌定为第3卷 Boss），两者必然矛盾。把承诺约束为"无事实"，从根上消除这一类冲突；
``opening_contract_consistency.OC-LADDER`` 仅作存量数据与漏网的兜底网。
"""

from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.context import get_genre_kit_block
from app.services.xuanhuan_lexicon import (
    format_modern_blacklist_for_prompt,
    is_xuanhuan_like_genre,
)


def _vol1_plot_block(vol1: Any | None) -> str:
    if not vol1:
        return "（卷一骨架尚未落库，请基于 volumes_summary 推断）"
    parts = [
        f"卷名：{vol1.title or '第一卷'}",
        f"phase：{vol1.phase or 'opening'}",
        f"摘要：{(vol1.summary or '').strip() or '（未填写）'}",
        f"核心冲突：{(vol1.conflict or '').strip() or '（未填写）'}",
        f"卷末悬念：{(vol1.hook or '').strip() or '（未填写）'}",
    ]
    return "\n".join(parts)


def _protagonist_psych_block(ctx: dict) -> str:
    protagonist = ctx.get("protagonist", "主角")
    profiles = ctx.get("char_profiles") or {}
    p = profiles.get(protagonist) if isinstance(profiles, dict) else None
    if not isinstance(p, dict):
        return ""
    return (
        f"\n【主角「{protagonist}」行为驱动（承诺须由此出发，不可写与人物无关的泛化钩子）】\n"
        f"  核心恐惧/创伤：{p.get('core_wound') or '（未设定）'}\n"
        f"  当前欲望：{p.get('current_desire') or '（未设定）'}\n"
        f"  价值观：{p.get('values') or '（未设定）'}\n"
        f"  人物弧线：{p.get('arc') or '（未设定）'}\n"
    )


def _extra_arc_block(project: Project) -> str:
    extra = project.extra if isinstance(project.extra, dict) else {}
    parts: list[str] = []
    mysteries = extra.get("core_mysteries")
    if isinstance(mysteries, list) and mysteries:
        ms = "；".join(
            str(m.get("title") or m.get("question") or m)[:40]
            for m in mysteries[:5]
            if m
        )
        if ms:
            parts.append(f"核心谜题（前10章须加热其中至少1条）：{ms}")
    villain = extra.get("villain_arc")
    if isinstance(villain, list) and villain:
        v0 = villain[0] if villain else {}
        if isinstance(v0, dict):
            hint = (v0.get("volume_plan") or v0.get("plan") or str(v0))[:120]
            if hint:
                parts.append(f"第一卷反派行动线：{hint}")
    return "\n".join(parts)


def _ladder_constraint_block(project: Project) -> str:
    """卷级 Boss 归属表 + 越权清算硬约束。

    让承诺生成 LLM 看见"哪个 Boss 属于哪一卷"，从源头杜绝"开局承诺击杀后续卷 Boss"
    这一与大纲必然矛盾的设定冲突（与 opening_contract_consistency.OC-LADDER 同一事实源）。
    """
    from app.services.bootstrap.antagonist_roster import load_antagonist_ladder

    ladder = load_antagonist_ladder(project)
    if not ladder:
        return ""
    lines: list[str] = ["【卷级 Boss 归属表（承诺不得越权清算后续卷 Boss）】"]
    for row in ladder:
        if not isinstance(row, dict):
            continue
        try:
            vi = int(row.get("vol_index"))
        except (TypeError, ValueError):
            continue
        name = str(row.get("boss_name") or row.get("name") or "").strip()
        if not name:
            continue
        realm = str(row.get("realm_at_climax") or row.get("realm_at_debut") or "").strip()
        tag = "✅本卷可清算" if vi == 0 else "⛔开局禁止承诺其死亡"
        lines.append(f"  第{vi + 1}卷 Boss：{name}（{realm or '境界未定'}）— {tag}")
    return "\n".join(lines) if len(lines) > 1 else ""


def build_opening_contract_prompt(
    project: Project,
    ctx: dict,
    *,
    vol1: Any | None = None,
) -> tuple[str, str]:
    """构建 Step 12 的 system + user prompt。"""
    positioning = ctx.get("positioning") or {}
    tropes = positioning.get("tropes", [])
    pace_type = positioning.get("pace_type", "medium")
    target_audience = positioning.get("target_audience", "")
    genre = ctx.get("genre", project.genre or "玄幻")
    kit_block = get_genre_kit_block(ctx)
    taboo_lines = positioning.get("taboo_lines") or []
    if isinstance(taboo_lines, list):
        taboo_text = "；".join(str(t) for t in taboo_lines if t)
    else:
        taboo_text = str(taboo_lines or "")
    modern_block = (
        "\n" + format_modern_blacklist_for_prompt()
        if is_xuanhuan_like_genre(genre)
        else ""
    )

    protagonist = ctx.get("protagonist", "主角")
    core_chars = "、".join(ctx.get("core_char_names") or []) or "（未设定）"
    factions = ctx.get("faction_summary") or "（未设定）"
    storyline = ctx.get("storyline_summary") or "（未设定）"
    relations = ctx.get("relation_triggers") or "（无）"
    villain_summary = ctx.get("villain_arc_summary") or ""
    extra_arc = _extra_arc_block(project)
    ladder_block = _ladder_constraint_block(project)

    system = (
        "你是有30年经验的网络小说总编辑，专门做开局追读策划。"
        "你的产出只管「怎么让读者追下去」的手法（钩子/爽点形态/伏笔/节奏/避坑），"
        "**绝不裁定任何剧情事实**（谁第几章死、谁杀谁、境界突破到第几层、Boss 属于哪一卷）——"
        "这些由 roster 与卷骨架唯一决定，你只能引用、不得发明。"
        "你只输出与本书已落库设定严格绑定的承诺，禁止套话与万能模板。"
        "只返回 JSON，不要任何解释文字。"
    )

    prompt = f"""小说：《{ctx.get('project_title', project.title or '未命名')}》（{genre}）
主角：{protagonist}  起点境界：{ctx.get('power_level_names', ['（未知）'])[0] if ctx.get('power_level_names') else '（未知）'}
创意：{ctx.get('logline', project.logline or '')}
核心爽点：{', '.join(tropes) if isinstance(tropes, list) else tropes or '（未设定）'}
节奏类型：{pace_type}
目标读者：{target_audience or '（未设定）'}
世界观：{(project.world_overview or ctx.get('world_overview') or '')[:400]}

【卷一骨架（前10章承诺必须服务于此，不得偏离）】
{_vol1_plot_block(vol1)}

【故事线与势力（承诺须点名或暗示具体线/势力，禁止「神秘势力」式空话）】
故事线：{storyline}
主要势力：{factions}
关系触发事件：{relations}
核心角色：{core_chars}
{villain_summary and '反派行动线摘要：' + villain_summary[:300] or ''}
{extra_arc and chr(10) + extra_arc or ''}
{ladder_block}
{_protagonist_psych_block(ctx)}

请为本书开局前10章制定「追读承诺清单」。每一项必须：
1) 引用上方已有人物名/冲突/谜题/关系中的至少一个具体元素；
2) 说明该承诺如何推进卷一核心冲突（不是孤立噱头）；
3) 禁止使用「展示实力」「悬念丛生」「读者期待」等空泛表述。
4) 【铁律·只写手法不定事实】承诺只负责「怎么让读者追下去」，**不负责也禁止裁定任何剧情事实**——
   包括：某角色第几章死亡、谁杀谁、境界突破到第几层、Boss 归属哪一卷。这些由 roster 与卷骨架
   （大纲）唯一决定。承诺需要点名时只能**引用**上方「卷级 Boss 归属表」的既定事实
   （如「本卷可清算目标为第1卷 Boss 王九」），禁止自行发明人物生死/境界数字。
   尤其禁止承诺击杀第2卷及以后的 Boss——开局根本不可能兑现，必与大纲矛盾。

返回JSON（只写手法/读者情绪，不写"谁死/谁被杀"这类大纲事实）：
{{
  "first_200_words_test": "第一章前200字必须完成的3件事：1) xxx 2) xxx 3) xxx（具体到场景/信息/情绪，须含主角名或核心痛点）",
  "chapter1_hook": "第1章末尾钩子：读者必须知道答案才肯继续的那个问题（须与卷一冲突/关系线直接相关）",
  "chapter3_payoff": "第3章小爽点：主角前3章收获的第一次正反馈（反转/扬眉吐气/资源）。只写『读者爽在哪、情绪如何』的手法；不要替大纲裁定击杀谁/谁死。若涉及对手，只能是开局小角色或引用 roster 第1卷可清算目标",
  "chapter5_foreshadow": "第5章必须埋下的长线伏笔：能支撑读者追到第30章的那个谜（具体到人物或秘密，可与核心谜题呼应；只点'埋什么谜'，不预设其结局）",
  "chapter10_subscribe_reason": "第10章末尾订阅钩：读者为什么非看第11章不可（具体手法+未解问题，须承接前9章某条伏笔或关系；只写'留什么悬念'，不要承诺某 Boss 之死等大纲事实）",
  "opening_traps_to_avoid": ["开局必须避免的3个坑（针对本书题材与卷一冲突的具体风险；玄幻/仙侠须含现代术语出戏类）"],
  "chapter_rhythm": "前10章节奏：哪章快哪章慢，何时第一次打脸，何时第一次情感连接（50字内，须对应具体章号）"
}}
{('红线禁忌：' + taboo_text) if taboo_text else ''}
{kit_block}
{modern_block}
玄幻/仙侠：承诺文案须用古风表达，禁止逆向工程、科学解析、工业化、市场调研等现代用语。"""

    return system, prompt
