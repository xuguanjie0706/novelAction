"""大白文章节正文写作：prompt 组装。

实验书架写章经 ``dabai.py`` 注入上章结尾 / 前情 / 写前导演单，避免章间剧情重置。
"""

from __future__ import annotations

from dabai.golden_finger_bind import (
    is_awakening_chapter,
    is_gf_evolution_chapter,
    is_reversal_chapter,
    prose_bind_instructions,
    prose_earned_reversal_instructions,
)
from dabai.non_system import prefers_non_system, prose_system_taboo_block
from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.services.dabai.lab_ledger import protagonist_name
from app.services.dabai.lab_prompt_shared import build_witness_lock_block

_SYSTEM_BASE = (
    "你是番茄/七猫大白文写手，专写移动端爽文正文。硬要求：\n"
    "1. 大白话、口语化，短句多、对话多，一看就懂，不要文绉绉、不要堆环境描写；\n"
    "2. 节奏快但【不跳】：爽点可以当众爆发，但任何情绪/态度的反转都必须先有铺垫——\n"
    "   反转前给一个『扳机』（一个眼神、一句话、一个动作、一段回忆闪念），\n"
    "   哪怕只有一两句，严禁从一种情绪直接硬切到另一种；\n"
    "3. 见证者反应要【分级递进】：先愣住/不信 → 再将信将疑 → 然后震惊 → 最后心服或恐惧；\n"
    "4. 金手指当章见效，主角不窝囊；\n"
    "5. 分自然段，结尾必须落在给定的『章末钩子』上；\n"
    "6. 只输出正文，不要标题、不要小标题、不要旁白说明。"
)

_SYSTEM_BASE_ARTIFACT = (
    "你是番茄/七猫大白文写手，专写移动端爽文正文。硬要求：\n"
    "1. 大白话、口语化，短句多、对话多，一看就懂，不要文绉绉、不要堆环境描写；\n"
    "2. 节奏快但【不跳】：爽点可以当众爆发，但任何情绪/态度的反转都必须先有铺垫——\n"
    "   反转前给一个『扳机』（一个眼神、一句话、器物异鸣、精血倒流、一段回忆闪念），\n"
    "   哪怕只有一两句，严禁从一种情绪直接硬切到另一种；\n"
    "3. 见证者反应要【分级递进】：先愣住/不信 → 再将信将疑 → 然后震惊 → 最后心服或恐惧；\n"
    "4. 金手指当章见效，主角不窝囊；\n"
    "5. 分自然段，结尾必须落在给定的『章末钩子』上；\n"
    "6. 只输出正文，不要标题、不要小标题、不要旁白说明。"
)

_CONTINUITY_RULES = (
    "7. 衔接硬约束：若非第1章，开头必须正面承接【上章结尾】末句场景；\n"
    "   已发生的事不可推翻——金手指若已绑定禁止再写绑定流程；主角若已逆袭禁止写回废人/经脉尽断；\n"
    "   章纲憋屈拍须在当前事实下 reinterpret，不可把剧情时间线倒回上一章之前；\n"
    "8. 五拍各用紧凑篇幅，禁止重复铺陈同一桥段；严禁超过目标字数上限。"
)

# 开篇指令单源化：有导演单时，开篇怎么承接（紧接续写还是先写位移）以导演单
# 的「开头写法」与「衔接交代」为唯一裁决，避免静态规则与位移块多源打架。
_CONTINUITY_RULES_PREWARN = (
    "7. 衔接硬约束：开头必须按【写前导演单】的「开头写法」执行，正面承接上一章正文实际结尾；\n"
    "   导演单给出「衔接交代」时必须先写位移/转场，没给则紧接上章末句同一瞬间续写，禁止自行另起场景；\n"
    "   已发生的事不可推翻——金手指若已绑定禁止再写绑定流程；主角若已逆袭禁止写回废人/经脉尽断；\n"
    "   章纲憋屈拍须在当前事实下 reinterpret，不可把剧情时间线倒回上一章之前；\n"
    "8. 五拍各用紧凑篇幅，禁止重复铺陈同一桥段；严禁超过目标字数上限。"
)


def _build_lab_beat_block(ch: DabaiChapterOutline) -> str:
    witnesses = "、".join(ch.witnesses or []) if isinstance(ch.witnesses, list) else "围观众人"
    if not witnesses:
        witnesses = "围观众人"
    return "\n".join([
        f"  爽点类型：{ch.shuang_type or ''}",
        f"  场景载体：{ch.location or ''}",
        f"  憋屈铺垫：{ch.yaqu_setup or ''}",
        f"  转折扳机：{ch.emotion_turn or '（未给，按②自行设计一个触发点过渡）'}",
        f"  引爆方式：{ch.yinbao or ''}",
        f"  爽感落点：{ch.shuang_payoff or ''}（见证者：{witnesses}）",
        f"  章末钩子：{ch.end_hook or ''}",
    ])


def build_prose_prompt(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    *,
    prev_tail: str = "",
    recent_plot_block: str = "",
    pre_warn_block: str = "",
    scene_block: str = "",
    ledger_block: str = "",
    memory_block: str = "",
    clue_block: str = "",
    panel_block: str = "",
    prev_full_block: str = "",
    prev_hook_block: str = "",
    location_bridge_block: str = "",
    qc_feedback_block: str = "",
    replace_existing: bool = False,
    prior_content: str = "",
    user_instruction: str = "",
) -> tuple[str, str]:
    """据项目设定 + 本章五拍 + 分场调度 + 衔接上下文，构造正文写作 (system, user)。

    panel_block: 系统面板快照块（上章末存档的数值绝对基准），注入在 ledger 之前，
                 让模型在写任何战斗/修炼场景前先知道精确的境界/技能/冷却状态。
    scene_block: 分场调度块（lab_scene_plan 产物）。有分场时正文按场推进、
                 落实台词弹药与感官锚点；空串=降级为五拍直写。
    prev_full_block: 上一章完整正文块（已发生事实最高基准；正文质量优先，token 不设限）。
    prev_hook_block: 上章末钩单列硬约束（复盘实际钩子优先）。
    location_bridge_block: 规则层位移硬约束。开篇指令单源化：有 pre_warn_block
                 时调用方应传空串（位移裁决已并入导演单），仅导演单缺席时兜底注入。
    qc_feedback_block: 上一版质检反馈（lab_qc_feedback 产物），仅重写时注入——
                 重写须逐条修复质检问题，而非只「换写法」。
    """
    gf = project.golden_finger or {}
    artifact = prefers_non_system({
        "logline": project.logline or "",
        "positioning": project.positioning or {},
        "golden_finger": gf,
        "benchmark": project.benchmark or {},
    })
    ladder = project.power_ladder or {}
    level_list = ladder.get("levels") or []
    levels = "、".join(x.get("name", "") for x in level_list[:7])
    chars = "、".join(c.name for c in project.characters[:8])
    protag = protagonist_name(project)
    target = ch.expected_words or 2000
    hi = target + 200
    lo = max(1600, target - 200)

    realm_name = next(
        (l.get("name") for l in level_list if int(l.get("rank", -1)) == (ch.realm_rank or -1)),
        None,
    )
    realm_block = (
        f"\n本章主角境界：第{ch.realm_rank}档「{realm_name}」"
        "——正文须与此一致，★禁止写回更低境界、禁止本章内乱跳档★。\n"
        if ch.realm_rank and realm_name else ""
    )

    sp = (project.benchmark or {}).get("style_profile") or {}
    style_line = "｜".join(
        f"{label}:{sp[key]}" for key, label in (
            ("sentence_style", "句式"), ("pacing", "节奏"),
            ("dialogue_density", "对话密度"), ("narration_voice", "腔调"),
        ) if sp.get(key)
    )
    style_block = (
        f"\n文风对标（贴风格写，★禁止照抄对标原句/情节★）：{style_line}\n"
        if style_line else ""
    )

    # 关键节点可信度脚手架（②③）：不再限制在第1章——金手指首次觉醒、后续进阶/解锁、
    # 反败为胜/逆袭章都需要「铺垫 + 立得住的依据」，否则读者觉得开挂硬翻。可叠加。
    gf_name = gf.get("name", "")
    ch_dict = {
        "chapter_number": ch.chapter_number,
        "title": ch.title,
        "yinbao": ch.yinbao,
        "end_hook": ch.end_hook,
        "shuang_type": ch.shuang_type,
        "shuang_payoff": ch.shuang_payoff,
        "emotion_turn": ch.emotion_turn,
        "yaqu_setup": ch.yaqu_setup,
    }
    milestone_parts: list[str] = []
    if is_awakening_chapter(
        ch_dict, golden_finger_name=gf_name, artifact=artifact,
    ) or is_gf_evolution_chapter(ch_dict, golden_finger_name=gf_name):
        milestone_parts.append(
            prose_bind_instructions(gf_name=gf_name, artifact=artifact)
        )
    if is_reversal_chapter(ch_dict):
        milestone_parts.append(
            prose_earned_reversal_instructions(artifact=artifact)
        )
    bind_block = "".join(milestone_parts)

    has_continuity = bool(
        prev_tail.strip() or recent_plot_block.strip() or prev_full_block.strip()
    )
    system = (_SYSTEM_BASE_ARTIFACT if artifact else _SYSTEM_BASE)
    if has_continuity:
        system += (
            _CONTINUITY_RULES_PREWARN if pre_warn_block.strip() else _CONTINUITY_RULES
        )
    if artifact:
        system += prose_system_taboo_block()

    user_parts = [
        f"《{project.title or project.logline}》第{ch.chapter_number}章",
        f"POV 主角：{protag}（全文须用此名，禁止改名或用「少年/他」代称开章）",
        f"金手指：{gf.get('name', '')}（{gf.get('core_ability', '')}）",
        f"境界阶梯：{levels}",
        f"可用人物：{chars}",
        f"{style_block}{realm_block}{bind_block}".strip(),
    ]
    user_parts = [p for p in user_parts if p]

    if recent_plot_block.strip():
        user_parts.append(recent_plot_block.strip())
    if panel_block.strip():
        # 系统面板快照放在记忆回灌之前：它是精确数值基准，优先级高于文本记忆
        user_parts.append(panel_block.strip())
    if memory_block.strip():
        user_parts.append(memory_block.strip())
    if clue_block.strip():
        user_parts.append(clue_block.strip())
    if ledger_block.strip():
        user_parts.append(ledger_block.strip())
    if prev_full_block.strip():
        user_parts.append(prev_full_block.strip())
    if prev_hook_block.strip():
        user_parts.append(prev_hook_block.strip())
    if prev_tail.strip():
        user_parts.append(f"【上章结尾（须紧接下一瞬间续写）】\n{prev_tail.strip()[-800:]}")
    # 开篇指令单源化：导演单在场时位移裁决归导演单，规则块只在其缺席时兜底
    if location_bridge_block.strip() and not pre_warn_block.strip():
        user_parts.append(location_bridge_block.strip())
    witness_block = build_witness_lock_block(ch)
    if witness_block:
        user_parts.append(witness_block)
    if pre_warn_block.strip():
        user_parts.append(pre_warn_block.strip())
    if scene_block.strip():
        user_parts.append(scene_block.strip())
    if replace_existing and prior_content.strip():
        user_parts.append(
            "【上一版正文节选（须换写法：禁止复用相同开头句、相同段落顺序与相同对话原句）】\n"
            + prior_content.strip()[:450]
        )
    if replace_existing and qc_feedback_block.strip():
        user_parts.append(qc_feedback_block.strip())

    user_parts.append("【本章爽点节拍（章节要素，必须逐项落实）】")
    user_parts.append(_build_lab_beat_block(ch))

    if scene_block.strip():
        task = (
            f"按上面【分场调度】逐场写出第{ch.chapter_number}章正文，五拍是总纲、分场是施工图。"
            f"目标 {target} 字（允许 {lo}～{hi}），严禁超过 {hi} 字。"
            "每场按其 word_budget 写足：动作拆成连续画面、对话有来回、"
            "台词弹药必须用上（可微调措辞）、感官锚点落进正文；"
            "场与场之间用场末转折自然过渡，禁止『与此同时』式硬切。"
            "若有开篇指令，须按其方向开写，禁止把指令原文复制成正文首句。"
            "禁止套用「疼！钻心的疼！」等烂大街起手式。直接开写正文。"
        )
    else:
        task = (
            f"按上面五拍写出第{ch.chapter_number}章正文。"
            f"目标 {target} 字（允许 {lo}～{hi}），严禁超过 {hi} 字。"
            "推进：①憋屈（别拖）→ ②转折扳机 → ③引爆 → ④爽点+见证者分级反应 → ⑤章末钩子。"
            "同一章纲允许多种写法：开笔切入点、对话顺序、扳机细节须有变化，"
            "禁止套用「疼！钻心的疼！」等烂大街起手式。"
            "直接开写正文。"
        )
    if replace_existing:
        task = (
            "【整章重写】" + task
            + "必须 reinterpret 章纲五拍（换对话/换扳机细节/换引爆细节），"
            "以导演单与前情事实为准，情节结果不变但表述须与上一版明显不同。"
        )
        # 位移要求可能来自规则块（导演单缺席兜底）或导演单的「衔接交代」行
        if location_bridge_block.strip() or "衔接交代" in pre_warn_block:
            task += (
                "★跨场景衔接不可省略：开篇仍须先写位移/转场，"
                "禁止为换写法而跳过从上一章地点到本章地点的过程。"
            )
    user_parts.append(task)

    pos = project.positioning or {}
    tabs = pos.get("taboo_lines")
    if isinstance(tabs, list) and tabs:
        user_parts.append(f"禁忌：{'；'.join(str(t) for t in tabs[:3])}")

    instr = (user_instruction or "").strip()
    if instr:
        system += (
            "\n9. 【作者写作指令】优先级高于章纲/导演单/分场表述（情节底线与禁忌仍须遵守）。"
        )
        user_parts.append(
            "【作者写作指令（★最高优先级★：与章纲/导演单/分场冲突时以本指令为准；"
            "情节结果与禁忌红线仍须遵守）】\n"
            + instr[:2000]
        )

    return system, "\n\n".join(user_parts)
