"""大白文章节正文写作：简化版 prompt + 离线 mock 正文。

设计取向（对齐爽点节拍器）：大白话、短句多、对话多、节奏快；
爽点当众爆发要有围观者反应；金手指当章见效；不堆环境描写、不文绉绉；
结尾必须落在章末钩子（end_hook）。比通用写作链路更轻，无质检/复盘闭环。
"""

from __future__ import annotations

from app.models.dabai import DabaiChapterOutline, DabaiProject

_SYSTEM = (
    "你是番茄/七猫大白文写手，专写移动端爽文正文。硬要求：\n"
    "1. 大白话、口语化，短句多、对话多，一看就懂，不要文绉绉、不要堆环境描写；\n"
    "2. 节奏快但【不跳】：爽点可以当众爆发，但任何情绪/态度的反转都必须先有铺垫——\n"
    "   反转前给一个『扳机』（一个眼神、一句话、一个动作、一声系统提示、一段回忆闪念），\n"
    "   哪怕只有一两句，严禁从一种情绪直接硬切到另一种（如从'隐忍'直接到'狂笑装逼'）；\n"
    "3. 见证者反应要【分级递进】：先愣住/不信 → 再将信将疑 → 然后震惊 → 最后心服或恐惧，\n"
    "   不要一步到位瞬间变脸；主角的情绪转折也同样要有这条过渡线；\n"
    "4. 金手指当章见效，主角不窝囊；\n"
    "5. 分自然段，结尾必须落在给定的『章末钩子』上，留住读者；\n"
    "6. 只输出正文，不要标题、不要小标题、不要旁白说明。"
)


def build_prose_prompt(project: DabaiProject, ch: DabaiChapterOutline) -> tuple[str, str]:
    """据项目设定 + 本章爽点节拍章纲，构造正文写作 (system, user)。"""
    gf = project.golden_finger or {}
    ladder = project.power_ladder or {}
    levels = "、".join(x.get("name", "") for x in (ladder.get("levels") or [])[:7])
    chars = "、".join(c.name for c in project.characters[:8])
    target = ch.expected_words or 2000
    witnesses = "、".join(ch.witnesses or []) or "围观众人"
    # 文风对标：从对标分析的 style_profile 取特征，让正文文风同向（禁抄原句）
    sp = (project.benchmark or {}).get("style_profile") or {}
    style_line = "｜".join(
        f"{label}:{sp[key]}" for key, label in (
            ("sentence_style", "句式"), ("pacing", "节奏"),
            ("dialogue_density", "对话密度"), ("narration_voice", "腔调"),
        ) if sp.get(key)
    )
    style_block = (
        f"\n文风对标（贴这个风格写，但★禁止照抄任何对标作品的原句/情节★）：{style_line}\n"
        if style_line else ""
    )
    user = (
        f"《{project.title or project.logline}》\n"
        f"金手指：{gf.get('name', '')}（{gf.get('core_ability', '')}）\n"
        f"境界阶梯：{levels}\n"
        f"可用人物：{chars}\n"
        f"{style_block}\n"
        f"【本章爽点节拍（第{ch.chapter_number}章 {ch.title or ''}）】\n"
        f"  爽点类型：{ch.shuang_type or ''}\n"
        f"  憋屈铺垫：{ch.yaqu_setup or ''}\n"
        f"  引爆方式：{ch.yinbao or ''}\n"
        f"  爽感落点：{ch.shuang_payoff or ''}（见证者：{witnesses}）\n"
        f"  章末钩子：{ch.end_hook or ''}\n\n"
        f"按上面的节拍把第{ch.chapter_number}章正文写出来，目标约 {target} 字。\n"
        "推进顺序（务必带上情绪过渡，别硬跳）：\n"
        "  ① 先写憋屈铺垫，让读者替主角憋着（别拖）；\n"
        "  ② 给一个『情绪扳机』——主角从隐忍到出手的那一下转变，要有触发点"
        "（一句挑衅、一个细节、一段闪念、一声金手指提示），一两句即可；\n"
        "  ③ 金手指引爆爽点；\n"
        "  ④ 见证者反应分级递进（愣住→怀疑→震惊→心服/恐惧），不要瞬间翻脸；\n"
        "  ⑤ 末段落在章末钩子上。\n"
        "直接开写正文。"
    )
    return _SYSTEM, user


def mock_prose(project: DabaiProject, ch: DabaiChapterOutline) -> list[str]:
    """离线 mock 正文（分段，供前端流式拼接，无需 LLM）。

    刻意演示『情绪转变有铺垫』：憋屈 → 扳机（内心转变+触发）→ 引爆 →
    见证者反应分级递进（愣→疑→惊→服），而非瞬间硬切。
    """
    who = "、".join(ch.witnesses or []) or "众人"
    gf = (project.golden_finger or {}).get("name", "金手指")
    return [
        f"　　{ch.yaqu_setup or '又一次被人当众奚落'}。林凡攥紧了拳头，喉咙发紧，却还是把那口气咽了下去。\n\n",
        f"　　“就你也配？”{who}的讥讽像针一样扎过来。\n\n",
        # ② 情绪扳机：内心转变 + 触发点（铺垫，而非硬跳）
        "　　他本想再忍。可耳边那句“也配”，忽然和母亲临终前那个不甘的眼神重叠在了一起。\n\n"
        f"　　就在这一瞬，识海里，{gf}的提示音轻轻一响。林凡缓缓抬起头，眼神里的隐忍，一点点变成了冷。\n\n",
        # ③ 引爆
        f"　　{ch.yinbao or '一道力量自丹田奔涌而出'}——下一瞬，{ch.shuang_payoff or '全场寂静'}。\n\n",
        # ④ 见证者反应分级递进
        f"　　{who}先是一愣，只当自己看错了；再定睛细看，脸上的轻蔑慢慢挂不住了；"
        "直到那股气势实实在在压下来，才终于变成了不可置信的惊骇。\n\n",
        "　　“这……这怎么可能！”\n\n",
        "　　林凡拍了拍手，淡淡道：“就这？”\n\n",
        f"　　{ch.end_hook or '而更大的风暴，正在远处悄然逼近。'}\n",
    ]
