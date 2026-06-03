"""按卷章纲懒展开 prompt 片段（JSON 骨架 + SEQ-01 章际衔接）。"""

from __future__ import annotations


def plain_chapter_plan_addendum() -> str:
    """白话直白（番茄纯爽文）章纲层硬约束块。

    上游章纲若信息密集，正文被迫照展开就会变稠，正文层的 plain 也压不住；
    故在章纲生成期就要求稀疏、单事件、直给钩子、大白话，给正文留出展开空间。
    """
    return (
        "\n\n【白话直白模式（番茄纯爽文，章纲层硬约束）】\n"
        "  · 每章只聚焦单一核心事件 + 单一爽点，禁止一章塞多条线、多个新设定、多个新名词；\n"
        "  · 新概念/新势力/新人物分散到不同章逐个引入，给正文留出「一次只讲一个」的空间；\n"
        "  · end_hook 用直给的强冲突/强敌登场/打脸预告，不要含蓄留白或意境化收尾；\n"
        "  · 章纲文字本身也用大白话，事件写清楚「谁、做了什么、结果如何」，便于直接开写。\n"
        "  · 替换现代词时优先选读者一眼能懂的常用说法，不必追求「拆方悟纹/灵机溯源」"
        "这类雅致意象——直白可懂优先于辞藻。"
    )


def fmt_storyline_names_block(storyline_ids_map: dict[str, str]) -> str:
    """故事线精确名称块，供 storyline_refs 原词填写。"""
    if not storyline_ids_map:
        return ""
    names_list = ", ".join(f'"{n}"' for n in storyline_ids_map)
    return (
        f"\n【故事线精确名称（storyline_refs 必须从以下名称中原词选择）】\n"
        f"  可用值：{names_list}\n"
        f"  ⚠️ 不得使用上方故事线块中显示的类型标签（如 main/romance），必须用此处的中文名称。\n"
    )


def fmt_written_summaries(summaries: list[str], max_items: int = 20) -> str:
    """已写章节摘要 prompt 块。"""
    if not summaries:
        return ""
    recent = summaries[-max_items:]
    lines = "\n".join(f"    {i + 1}. {s[:130]}" for i, s in enumerate(recent))
    return (
        f"\n【已写章节摘要（最近{len(recent)}章，按时序——本卷必须从此处自然接续）】\n"
        + lines
        + "\n  ⚠️ 本卷第1章的 opening_hook 必须能直接承接上面最后1条摘要的结局状态。"
    )


def build_carryover_seq_block(
    *,
    batch_start: int,
    batch_end: int,
    last_batch_tail_cost: str = "",
    protagonist_name: str = "",
) -> str:
    """与 outline_linter SEQ-01 对齐的章际衔接硬约束（本批 JSON 内相邻章 + 跨批首章）。"""
    protag = (protagonist_name or "").strip()
    protag_note = (
        f"禁止仅用主角名「{protag}」二字满足衔接（须用代价里的伤势/誓言/道具/关系等词组）。"
        if protag
        else "禁止仅用主角姓名二字满足衔接，须用代价里的具体词组。"
    )
    cross_batch = ""
    if batch_start > 1 and last_batch_tail_cost.strip():
        tail = last_batch_tail_cost.strip()[:140]
        cross_batch = (
            f"\n6. 跨批首章：本批第{batch_start}章 opening_hook 前 20 字内必须承接"
            f"上一批末章代价「{tail}」中的词组（≥2 连续汉字与原文相同），"
            f"不得另起新地图/新反派开场。\n"
        )
    return (
        f"\n【章际衔接 · SEQ-01（与落库 linter 完全一致，输出 JSON 前逐对自检）】\n"
        f"本批一次返回第{batch_start}～{batch_end}章。在同一 JSON 数组内，每一对 (第N章, 第N+1章)：\n"
        "1. 第 N+1 章 opening_hook 的【前半句】= 第 N 章 choice_cost 的即时后果"
        "（身体伤、誓言约束、暴露风险、资源枯竭等），【后半句】再切入本章新冲突。\n"
        "2. 第 N+1 章的 opening_hook 或 core_event 中，必须包含第 N 章 choice_cost 原文里"
        "至少一段连续 2 个汉字（子串匹配，与 linter 相同）。\n"
        f"3. {protag_note}\n"
        "4. 禁止「上章代价写满、下章开篇换镜头零重叠」——代价不是摘要装饰，是下一章第一句的燃料。\n"
        "5. 禁止情节倒带：若上章 end_hook 已完成「觉醒/黑火涌出/口头休妻/击杀」等节拍，"
        "下章 opening_hook 不得再写「觉醒剧痛/经脉重组/再度觉醒」等把同一节拍当本章起点；"
        "下章开篇须承接 end_hook 的**下一瞬间**（未决动作/对峙升级），新冲突写入 core_event。\n"
        f"{cross_batch}"
        "【生成后自检（每一对相邻章都要过）】\n"
        f"  从第{max(batch_start, 2)}章到第{batch_end}章：opening_hook 是否与上一章 choice_cost 有≥2字相同？\n"
        "  若任一对失败，先改 opening_hook 再输出 JSON，不要交卷。\n"
        "【反例 → 正例】\n"
        "  ❌ 代价「沸血丹…术后极度虚弱」→ 开篇「岩浆倒灌，神魂焚烧」（零重叠，像在重写炼化）\n"
        "  ✅ 代价「沸血丹…术后极度虚弱」→ 开篇「沸血丹余毒未散，他极度虚弱地倒在池边，韩长老已堵住去路」\n"
        "  ❌ 代价「左臂经脉烧毁，火焰纹路」→ 开篇「韩长老手指抵住咽喉」（未提左臂/经脉/纹路）\n"
        "  ✅ 同上 → 开篇「左臂经脉焦黑，火焰纹路刺目，韩长老的手指却掐住了他的咽喉」\n"
        "  ❌ 代价「立下血誓效忠韩长老」→ 开篇「黑色斗篷下拍出蛟骨」（新任务，未提血誓）\n"
        "  ✅ 同上 → 开篇「血誓烙纹隐隐发烫，他被迫低头将蛟骨拍在柜台上」\n"
    )


def build_chapter_plan_generation_tail(
    *,
    batch_start: int,
    batch_end: int,
    batch_count: int,
    is_fanqie: bool = False,
) -> str:
    """生成要求 + JSON 字段说明 + 编辑铁律（含强化 SEQ-01）。

    Args:
        is_fanqie: pace_type=="fast" 时为 True，启用番茄 JSON 字段和铁律。
    """
    chk_from = batch_start + 1 if batch_start < batch_end else batch_end

    if is_fanqie:
        from app.services.bootstrap.prompts.vol_chapter_fanqie import (
            fanqie_editorial_laws,
            fanqie_emotional_tone_options,
            fanqie_json_extra_fields,
            fanqie_word_budget_hint,
        )
        emo_options = fanqie_emotional_tone_options()
        extra_fields = fanqie_json_extra_fields()
        word_hint = fanqie_word_budget_hint()
        laws = fanqie_editorial_laws(chk_from, batch_end)
    else:
        emo_options = "exciting/tense/sad/romantic/mysterious/warm/anxious/epic"
        extra_fields = ""
        word_hint = (
            "（expected_words 参考：opening/ending≈2000-2400，rising≈2300，turning≈2400，"
            "dark_hour≈2600-2800，climax≈3000-3300；fast 节奏-200，slow/climax 节奏+200-500；"
            "有打脸/情感高点+200。请按章节实际情况填写，不要全部填同一个数字。）\n\n"
        )
        laws = (
            "# 编辑铁律（违反任何一条视为不合格输出）\n"
            "1. protagonist_want 必须是「主动欲望」而非「被动应付」——区别：主动=「他想要X」，被动=「他被迫处理Y」\n"
            "2. choice_cost 不能为空字符串——这是最高优先级约束。零代价的选择不是戏剧；"
            "格式示例：「答应了陆青云的条件，但被迫交出了令牌，下章必须面对陆青云派来监视的人」\n"
            "3. 🔴 章际因果链（SEQ-01，与 linter 同规则，本批内每一对相邻章都必须满足）：\n"
            "   a) 第 N+1 章 opening_hook 前半句 = 第 N 章 choice_cost 的即时后果，再切入新事件；\n"
            "   b) 第 N+1 章 opening_hook 或 core_event 须含第 N 章 choice_cost 原文中≥2连续相同汉字；\n"
            "   c) 禁止仅靠主角姓名满足 b)；须用代价里的伤势/丹药/誓言/诅咒/关系等词组；\n"
            f"   d) 输出前对第{chk_from}～{batch_end}章逐对自检，失败则改 opening_hook 再返回 JSON。\n"
            "4. end_hook 必须具体到手法（「主角打开了一扇他以为已经关闭的门」比「结局悬念」合格）\n"
            "5. villain_action 不能只写「（无）」——反派的独立行动是本书节奏的第二引擎\n"
            "6. core_event（即 summary）必须是 protagonist_choice 的直接后果，不能为空\n"
            "7. storyline_refs 必须交叉出现，主线不能连续 3 章独占（除非 phase=climax 的最后 5 章）\n"
            "8. 本卷内至少 2 条贯穿伏笔线：埋入章写「埋[xxx|主题:yyy]」，推进章写「加热[xxx+手法]」，回收章写「收[xxx]」\n"
            "9. promise_fulfilled：若本章是某条未兑现承诺的兑现章，必须填写承诺原文中的关键短语（2字以上）；"
            "其余章节填空字符串即可，不要填占位文字如「无」「暂无」。\n"
            "10. has_face_slap 的频率必须符合立项定位的 face_slap_pattern（不能全是 false）\n"
            "11. 若 phase=dark_hour，至少 40% 的章节 has_emotional_beat=true，且 pacing 不得连续 3 章是 fast\n"
            "12. involved_characters 只能使用上方已知人物名，不要发明新名字\n"
            "13. 玄幻/仙侠：core_event/opening_hook 等字段禁止现代 STEM/商业用语"
            "（逆向工程、解析改良、工业化、市场调研、畅销榜等），须用古风修仙表达\n"
            "只返回 JSON 数组，不要任何解释文字。"
        )

    default_words = 1800 if is_fanqie else 2200

    return (
        f"\n\n# 生成要求\n"
        f"请为本卷第{batch_start}～{batch_end}章生成{batch_count}个章节计划，返回JSON数组：\n"
        "[\n"
        "  {\n"
        f'    "chapter_number": {batch_start},\n'
        '    "title": "第X章：章节标题（≤12字，有画面感且制造期待——但必须点明本章 core_event 真实发生的主场景/转折，'
        '严禁标题党：不得以本章未实际发生的场景、地点或冲突命名，标题关键词应能在 core_event 中找到对应）",\n'
        "\n"
        "    // ── 欲望-障碍-选择-代价四元组（章节叙事引擎，必须严密因果）──\n"
        '    "protagonist_want": "主角这一章主动想要什么（必须是主动欲望，不是被动应付）",\n'
        '    "protagonist_obstacle": "什么具体阻止了他（内部恐惧或外部冲突，二选一或兼有）",\n'
        '    "protagonist_choice": "他做了什么关键选择（必须暴露性格，不只是解决问题）",\n'
        '    "choice_cost": "这个选择的代价（喂给下一章的债务，不能零代价；须含可复述的名词/伤势/誓言词组）",\n'
        "\n"
        "    // ── 章节结构骨架 ──\n"
        '    "opening_hook": "开篇：先写上一章 choice_cost 即时后果（须含上章代价原文≥2连续汉字），再写本章钩子（≤35字）",\n'
        '    "core_event": "核心事件：必须是 protagonist_choice 的直接后果，格式「因[choice]→[result]」（≤60字）",\n'
        '    "character_change": "谁的认知/处境/关系发生了不可逆变化（≤30字，不能只写外部变化）",\n'
        '    "end_hook": "章末钩子：读完最后一句停不下来的原因（≤30字，禁用「悬念丛生」「让读者期待」等废话，必须具体手法）",\n'
        "\n"
        "    // ── 伏笔与承诺管理 ──\n"
        '    "foreshadow": "伏笔操作：埋[伏笔内容|主题:与全书立意的关联] / 收[伏笔代号+内容] / 加热[伏笔代号+推进方式]（无则填空）",\n'
        '    "promise_fulfilled": "本章兑现了哪条读者承诺（填承诺原文片段，无则填空字符串）",\n'
        "\n"
        "    // ── 反派与配角 ──\n"
        '    "villain_action": "反派这一章在做什么（即便不在主角视角），对主角的威胁如何量化？",\n'
        '    "supporting_spotlight": "哪个配角有独立的情节推进（不只是配合主角），填姓名+做了什么",\n'
        "\n"
        "    // ── 节奏与情感标记 ──\n"
        f'    "reader_emotion_target": "本章结束时读者的目标情绪（{emo_options}）",\n'
        '    "involved_characters": ["出场人物名（只用已知人物名）"],\n'
        '    "storyline_refs": ["推进了哪条故事线（从已有故事线选）"],\n'
        '    "storyline_beat_ref": "本章主要兑现的故事线名（与导演单一致，可空）",\n'
        '    "pacing": "fast/normal/slow/climax",\n'
        f'    "emotional_tone": "{emo_options}",\n'
        '    "power_milestone": "若本章有境界突破/技能习得/法宝获得则描述，否则填空",\n'
        '    "has_face_slap": false,\n'
        '    "has_emotional_beat": false,\n'
        f'    "expected_words": {default_words}\n'
        + extra_fields
        + "  }\n"
        "]\n"
        + word_hint
        + laws
    )
