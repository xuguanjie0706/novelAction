"""每步 JSON 导向 prompt（system + user 模板）。

统一约定：
  - system 立「大白文总编辑」人设，强调爽点循环而非因果链。
  - user 末尾给出**精确 JSON 骨架**，并强制「只返回 JSON」。
  - 章纲 prompt 是核心：要求先排爽点序列，再展开每章；显式禁止 choice_cost 思维。
ctx 为累积上下文 dict（前序步骤产物）。
"""

from __future__ import annotations

import json
from typing import Any

from dabai.config import DabaiConfig
from dabai.golden_finger_bind import chapter_outline_bind_block

_SYS_BASE = (
    "你是有15年经验的番茄/七猫大白文主编，专精移动端碎片化爽文。\n"
    "你的信条：读者要的是『情绪势能→爽点引爆→即时反馈→更强钩子』的循环，"
    "不是文学因果链。爽点要直给、要有观众、要让读者一眼看懂。\n"
    "信息密度要低，一次只讲一个新东西；金手指当章见效；主角不许窝囊超过一章。\n"
    "只返回 JSON，不要任何解释、注释或 markdown 说明文字。"
)


def _ctx_brief(ctx: dict) -> str:
    """把已生成产物压成紧凑上下文（喂给后续步骤）。"""
    parts = []
    if "logline" in ctx:
        parts.append(f"一句话创意：{ctx['logline']}")
    if "golden_finger" in ctx:
        gf = ctx["golden_finger"]
        parts.append(f"金手指：{gf.get('name')}（{gf.get('core_ability', '')[:40]}）")
    if "power_ladder" in ctx:
        lv = ctx["power_ladder"].get("levels", [])
        parts.append("境界：" + "→".join(x.get("name", "") for x in lv[:7]))
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


def _benchmark_block(ctx: dict) -> str:
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


# ── 各步 user prompt 构造 ────────────────────────────────────────────────────
def benchmark(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """合并步：一次调用同时产出『对标分析』+『立项定位』（定位须对齐对标）。

    返回 JSON 顶层含 benchmark / positioning 两个子对象，pipeline 拆成两个 ctx 键。
    """
    system = (
        "你是网文市场分析 + 选题编辑，熟悉番茄/起点/七猫各题材的热门作品与套路。\n"
        "请先做对标分析，再据此为本书做立项定位（定位必须对齐对标特征，不要自说自话）。\n"
        "★合规要求：只描述作品可借鉴的『特征』（卖点、套路、设定母题、文笔风格），"
        "严禁抄录任何作品的原文段落、具体情节或人物原名作为输出内容。\n"
        "只返回 JSON。"
    )
    user = (
        f"题材 / 一句话创意：{ctx['logline']}\n\n"
        "返回 JSON（顶层两块：benchmark 对标分析、positioning 立项定位，"
        "positioning 要从 benchmark 推导而来）：\n"
        "{\n"
        '  "benchmark": {\n'
        '    "topic": "题材标签（如 系统流/吞噬流/赘婿打脸）",\n'
        '    "reference_books": [\n'
        '      {"title": "书名", "why_comparable": "为何对标", "core_appeal": "核心卖点/爽点",\n'
        '       "setting_motif": "设定母题(金手指/世界观套路)", "style_note": "文笔特征(句式/节奏/腔调)"}\n'
        "    ],\n"
        '    "style_profile": {"sentence_style": "句式", "pacing": "节奏",\n'
        '      "dialogue_density": "对话密度", "shuang_cadence": "爽点节奏(几章一爆)",\n'
        '      "narration_voice": "叙事腔调"},\n'
        '    "setting_conventions": ["该题材常见设定套路 2-4 条"],\n'
        '    "tropes_to_use": ["值得用的爽点/桥段套路"],\n'
        '    "pitfalls_to_avoid": ["容易翻车/读者反感的点"]\n'
        "  },\n"
        '  "positioning": {\n'
        '    "target_audience": "目标读者画像（对齐对标读者）",\n'
        '    "shuang_pool": ["主打爽点类型 5-7 个，从 打脸/升级/获宝/扮猪吃虎/装逼/群嘲反转/收小弟/救场/扬名 选"],\n'
        '    "face_slap_frequency": "打脸/爽点频率（呼应对标 shuang_cadence）",\n'
        '    "golden_three_strategy": "黄金三章策略：第1章蓄憋屈、第2章金手指登场、第3章第一次大打脸",\n'
        '    "pace_type": "fast",\n'
        '    "emotional_arc": "情绪闭环节律（憋屈→反击→扬名）",\n'
        '    "taboo_lines": ["3 条硬禁忌（可吸收对标 pitfalls_to_avoid）"],\n'
        '    "writing_style": "plain"\n'
        "  }\n"
        "}"
    )
    return system, user


def positioning(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    user = (
        f"一句话创意：{ctx['logline']}\n"
        + _benchmark_block(ctx) + "\n"
        "为这本大白文做立项定位。返回 JSON 对象：\n"
        "{\n"
        '  "target_audience": "目标读者画像（平台/年龄/口味）",\n'
        '  "shuang_pool": ["本书主打的爽点类型，从 打脸/升级/获宝/扮猪吃虎/装逼/群嘲反转/收小弟/救场/扬名 中选5-7个"],\n'
        '  "face_slap_frequency": "打脸/爽点频率（如每章一次小爽点，每5章一大爆点）",\n'
        '  "golden_three_strategy": "黄金三章策略：第1章怎么蓄憋屈，第2章金手指怎么登场，第3章怎么第一次大打脸",\n'
        '  "pace_type": "fast",\n'
        '  "emotional_arc": "情绪闭环节律（憋屈→反击→扬名 的周期）",\n'
        '  "taboo_lines": ["3条硬禁忌，如 不许窝囊超过一章"],\n'
        '  "writing_style": "plain"\n'
        "}"
    )
    return _SYS_BASE, user


def golden_finger(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """合并步：一次产出 金手指 + 境界阶梯（两者同属力量体系，须自洽）。"""
    user = (
        f"{_ctx_brief(ctx)}\n"
        + _benchmark_block(ctx) + "\n"
        "一次设计好本书的【力量体系】——金手指 + 与之匹配的境界阶梯。"
        "金手指要当章见效、能持续产出爽点；境界要清晰可数、和金手指的升级机制自洽。"
        "可借鉴对标设定母题，但要差异化。返回 JSON（两块）：\n"
        "{\n"
        '  "golden_finger": {\n'
        '    "name": "金手指名称",\n'
        '    "type": "类型（系统/吞噬/重生/天赋/老爷爷/签到…可组合）",\n'
        '    "core_ability": "核心能力（一句话）",\n'
        '    "upgrade_mechanism": "怎么靠它变强（量化升级路径，且要呼应下面的境界阶梯）",\n'
        '    "shuang_engine": "怎么持续产生爽点（越强越稀有越爽 在哪体现）",\n'
        '    "restriction": "限制（防无敌没张力，但不能是劝退读者的长期代价）",\n'
        '    "signature_lines": ["1-2句标志性提示音/口头禅"]\n'
        "  },\n"
        '  "power_ladder": {\n'
        '    "name": "体系名称",\n'
        '    "levels": [{"rank": 1, "name": "境界名", "desc": "一句话特征+突破条件"}]\n'
        "  }\n"
        "}\n"
        "境界要求 6-8 个大境界，rank 从 1 递增。"
    )
    return _SYS_BASE, user


def factions(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """合并步：一次产出 势力 + 人物（阵营卡司，人物须落在势力里、关系自洽）。"""
    user = (
        f"{_ctx_brief(ctx)}\n"
        + _benchmark_block(ctx) + "\n"
        "一次设计好本书的【阵营卡司】——势力 + 人物，两者要咬合："
        "人物要分属设计好的势力，打脸对象要来自压迫方势力。返回 JSON（两块）：\n"
        "{\n"
        '  "factions": [\n'
        "    {\n"
        '      "name": "势力名", "stance": "主角方/压迫方/中立资源/神秘势力",\n'
        '      "role": "在爽点循环里扮演什么（谁压迫主角、谁是打脸靶子土壤）",\n'
        '      "power_tier": "最高战力档", "note": "前期/后期作用"\n'
        "    }\n"
        "  ],\n"
        '  "characters": [\n'
        "    {\n"
        '      "name": "姓名", "role": "主角/打脸对象/女主/导师/工具人配角",\n'
        '      "tier": "核心/配角", "start_realm": "起始境界", "persona": "性格（一句话）",\n'
        '      "function": "在爽点循环里的功能（打脸靶子/救场/感情锚点/埋钩子）"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "势力 3-5 个；人物必须含：1个扮猪吃虎的主角、≥1个前期打脸对象、1个女主、若干工具人；"
        "主角额外带 desire（最强欲望）、wound（憋屈来源）、golden_finger 字段。"
    )
    return _SYS_BASE, user


def storylines(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    user = (
        f"{_ctx_brief(ctx)}\n\n"
        "设计 3-4 条故事线。主线必须是『升级打脸』，其余可含复仇线/感情线/身世谜题线。返回 JSON 数组：\n"
        '[{"name": "线名", "type": "main/revenge/romance/mystery", "summary": "一句话走向"}]'
    )
    return _SYS_BASE, user


def story_assets(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """剧情资产 + 初始关系：台账种子，章纲与写章全程引用同一批设定。"""
    chars = ctx.get("characters") or []
    char_lines = "\n".join(
        f"  - {c.get('name', '')}（{c.get('role', '')}）：{(c.get('persona') or '')[:30]}"
        for c in chars[:8]
    )
    user = (
        f"{_ctx_brief(ctx)}\n\n"
        f"【人物清单】\n{char_lines}\n\n"
        "设计两块台账种子，只返回 JSON：\n"
        "1. plot_assets：3-6 件有剧情功能的功法/道具（不是装备列表——每件必须绑定剧情作用：\n"
        "   被各方觊觎的争夺点 / 反派底牌 / 主角功法升级路线 / 身世信物谜题）。\n"
        "2. initial_relations：主角与每个核心人物的开局关系（要有张力，是前期打脸剧情的燃料）。\n"
        "{\n"
        '  "plot_assets": [\n'
        '    {"kind": "skill|item", "name": "≤10字", "plot_role": "争夺点|底牌|成长线|身世信物",\n'
        '     "owner": "开局持有者人名（未登场则留空）", "debut": "start|later", "planned_volume": 1,\n'
        '     "description": "≤40字：谁觊觎/怎么升级/何时引爆"}\n'
        "  ],\n"
        '  "initial_relations": [\n'
        '    {"from": "主角人名", "to": "对方人名",\n'
        '     "attitude": "敌对|轻视|忌惮|臣服|效忠|盟友|暧昧|中立",\n'
        '     "tension": "≤30字初始张力（嫉妒/退婚之恨/暗中觊觎金手指）"}\n'
        "  ]\n"
        "}\n"
        "注意：金手指本身不要重复列入 plot_assets（已单独建账）。"
    )
    return _SYS_BASE, user


def _ladder_block(ctx: dict) -> str:
    """境界体系档位清单（供卷/章对齐 realm rank）。"""
    levels = (ctx.get("power_ladder") or {}).get("levels") or []
    if not levels:
        return ""
    items = "　".join(f"{l.get('rank')}={l.get('name')}" for l in levels)
    return f"\n【境界体系档位（realm_rank 必须用这里的数字）】{items}\n"


def volumes(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    levels = (ctx.get("power_ladder") or {}).get("levels") or []
    max_rank = max((int(l.get("rank", 0)) for l in levels), default=cfg.volume_count + 1)
    user = (
        f"{_ctx_brief(ctx)}\n"
        + _ladder_block(ctx) + "\n"
        f"把全书拆成 {cfg.volume_count} 卷，每卷 {cfg.volume_chapters} 章。"
        "每卷给出爽点大节拍、卷末高潮，以及【主角境界区间】。返回 JSON 数组：\n"
        "[\n"
        "  {\n"
        '    "volume_number": 1, "title": "第1卷 卷名",\n'
        '    "phase": "opening/rising/turning/dark_hour/climax",\n'
        f'    "planned_chapters": {cfg.volume_chapters},\n'
        '    "big_beats": ["本卷2-3个大爆点（打脸/越级/夺宝）"],\n'
        '    "volume_climax": "卷末高潮（最大的一次打脸或翻盘）",\n'
        '    "end_hook": "卷末钩子（勾下一卷）",\n'
        '    "realm_start_rank": 1, "realm_end_rank": 2\n'
        "  }\n"
        "]\n"
        "★境界硬规则★：realm_start_rank / realm_end_rank 用上面档位的数字；"
        f"全书从第1卷起单调上升，最高不超过 {max_rank}；"
        "每卷 realm_end_rank ≥ realm_start_rank；下一卷 realm_start_rank = 上一卷 realm_end_rank（首尾相接，禁止回退）；"
        "开局卷升幅要小（1-2 档），别一卷暴涨。\n"
        "第1卷必须是新手村开局：退婚/被辱→觉醒金手指→当众打脸扬名。"
    )
    return _SYS_BASE, user


# ── 章纲：爽点节拍器（核心 prompt）──────────────────────────────────────────────
def chapter_outlines(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    vol = ctx.get("_target_volume", {})
    n = vol.get("planned_chapters", cfg.volume_chapters)
    pool = "、".join(cfg.shuang_pool)
    chars = "、".join(c.get("name", "") for c in ctx.get("characters", []))
    # 分批信息（由 iter_chapter_batches 注入 ctx['_batch']）
    batch = ctx.get("_batch", {})
    bs = int(batch.get("batch_start", 1))
    be = int(batch.get("batch_end", n))
    # 全局章号（卷展开时 = 前卷偏移 + 卷内章号；bootstrap 第1卷两者相同）
    gbs = int(batch.get("global_start", bs))
    gbe = int(batch.get("global_end", be))
    prev_tail = (batch.get("prev_tail") or "").strip()
    batch_count = be - bs + 1
    carry = ""
    if prev_tail:
        carry = (
            f"\n【上文结尾（硬性承接）】前一章（可能是上一卷末章）的爽点收尾/钩子是："
            f"「{prev_tail[:120]}」。本批第{gbs}章 yaqu_setup 必须顺着它起，"
            "不得另起炉灶、不得回到已解决的旧危机。\n"
        )
    # 境界脊柱：本卷区间 + 本批起步 floor（禁止回退）
    vr_lo = vol.get("realm_start_rank")
    vr_hi = vol.get("realm_end_rank")
    realm_floor = batch.get("realm_floor")  # 上一批末章境界档
    realm_block = ""
    if vr_lo or vr_hi or realm_floor:
        floor = realm_floor or vr_lo or 1
        realm_block = (
            "\n【境界脊柱（硬约束，违反即判 REALM 回退）】\n"
            f"  本卷主角境界区间：第 {vr_lo or '?'} 档 → 第 {vr_hi or '?'} 档。\n"
            f"  本批起步：主角已在第 {floor} 档，本批每章 realm_rank ★只能 ≥ {floor}★、"
            "且全批单调不减、不得超过本卷 realm_end_rank。\n"
            "  境界提升要循序渐进（通常几章升一档），禁止忽高忽低、禁止写回低境界。\n"
        )
    system = _SYS_BASE + (
        "\n\n【章纲专项 · 爽点节拍器】\n"
        "本任务的核心不是『欲望-障碍-选择-代价』那套精品文链路——"
        "★明确禁止给主角的爽点强加代价/后遗症★。大白文的章是：\n"
        "憋屈势能(yaqu_setup) → 【转折拍 emotion_turn：情绪扳机】 → 爽点引爆(yinbao) → "
        "爽感反馈(shuang_payoff，必须有观众) → 强钩子(end_hook)。\n"
        "★转折拍是关键★：从憋屈到引爆之间必须有一个『扳机』——主角情绪从隐忍/被动 靠一个具体触发点"
        "（一句羞辱、一个细节、一段闪念、一声金手指提示）转到出手/反击，"
        "这样正文才不会情绪硬跳。金手指首次觉醒章还须写清『疑→证→择』绑定节拍（见下方硬约束）。"
        "先排好整卷爽点序列，再逐章展开。\n"
        "【功力要求】你是写了三十年白话网文的老作者，章纲每个字段都按可拍画面写：\n"
        "  - 标题自带钩子（冲突/反差/悬念入题），禁止『修炼』『突破』这类白开水标题；\n"
        "  - yaqu_setup 写到具体的人+具体的不公（谁、当着谁、用什么方式压主角），不写抽象处境；\n"
        "  - yinbao 写清招式/手段/场面调度，反转要有“先抑两拍再爆”的节奏感；\n"
        "  - shuang_payoff 写打脸对象的具体反应（脸色/下跪/改口/围观惊呼），爽感可量化；\n"
        "  - 全卷爽点强度要走阶梯：小爽铺垫→中爽推进→大爆点炸场，禁止平铺直叙一个调门到底；\n"
        "  - 所有人物/势力/功法/道具只能用上文给定的既有设定，禁止凭空新造核心设定。"
    )
    gf_name = (ctx.get("golden_finger") or {}).get("name", "")
    # 黄金前 N 章按★全局章号★判定：仅全书开局批注入金手指绑定节拍，卷2+不再触发
    bind_block = chapter_outline_bind_block(gf_name) if gbs <= cfg.golden_chapters else ""
    golden_rule = (
        f"1. 黄金前 {cfg.golden_chapters} 章（仅当本批含全书第1章时）："
        "第1章蓄憋屈+留金手指钩子，第2章金手指见效，第3章第一次当众大打脸。\n"
        if gbs <= cfg.golden_chapters else
        "1. 本批非全书开局：开篇承接上文钩子直接进入本卷冲突，禁止重新介绍金手指/世界观。\n"
    )
    # 前情回灌（卷展开期由 volume_expand.build_story_so_far 注入；bootstrap 期为空）
    story = (ctx.get("story_so_far") or "").strip()
    story_block = (
        "\n【前情与既定事实（全部已发生，章纲必须与之自洽；禁止矛盾、禁止重置、"
        "禁止让已死/已臣服人物无故复活/翻脸）】\n" + story + "\n"
    ) if story else ""
    user = (
        f"{_ctx_brief(ctx)}\n"
        + _benchmark_block(ctx)
        + story_block + "\n"
        f"为《{vol.get('title', '第1卷')}》（phase={vol.get('phase')}，全卷共 {n} 章）"
        f"生成全书第 {gbs}～{gbe} 章章纲（本卷第 {bs}～{be} 章，本批 {batch_count} 章）。\n"
        f"本卷大爆点：{vol.get('big_beats')}\n本卷卷末高潮：{vol.get('volume_climax')}\n"
        f"可用人物：{chars}\n可用爽点类型：{pool}\n"
        + _ladder_block(ctx)
        + carry + realm_block + bind_block +
        "硬约束：\n"
        + golden_rule +
        "2. 相邻两章 shuang_type 不得相同；每 "
        f"{cfg.big_beat_every} 章至少一个 is_big_beat=true 的大爆点。\n"
        "3. shuang_payoff 必须写明『当着谁的面、爽在哪』，witnesses 至少 1 人（爽点必须有观众）。\n"
        f"4. 每章 new_info_count ≤ {cfg.max_new_info_per_chapter}（一次只引入一个新设定/新人物/新名词）。\n"
        "5. end_hook 必须具体（更强敌人登场/更大机缘/打脸预告），禁用『悬念丛生』『让人期待』套话。\n"
        "6. 禁止给主角爽点强加 choice_cost / 后遗症 / 道德负担。\n\n"
        f"返回 JSON 数组，{batch_count} 个元素（全书第{gbs}～{gbe}章），每个：\n"
        "{\n"
        f'  "chapter_number": {gbs}, "title": "第X章 标题(≤10字)",\n'
        '  "shuang_type": "本章爽点类型(从可用类型选)",\n'
        '  "yaqu_setup": "憋屈势能：谁在压主角/什么不公",\n'
        '  "emotion_turn": "转折拍：从【情绪】→【触发】→【情绪】；金手指觉醒章须含疑→证→择（如 从恍惚→疑为鬼叫→倒计时/锁链松→赌命提取）",\n'
        '  "yinbao": "引爆：主角怎么靠金手指反转",\n'
        '  "shuang_payoff": "爽感量化：当着谁的面、爽在哪、对方什么反应",\n'
        '  "witnesses": ["见证者/被打脸者(≥1人)"],\n'
        '  "end_hook": "章末强钩子(具体)",\n'
        '  "new_info_count": 1,\n'
        '  "involved_characters": ["出场人物(用已知人物名)"],\n'
        '  "is_big_beat": false,\n'
        '  "expected_words": 2000,\n'
        '  "realm_rank": 1\n'
        "}\n"
        "★realm_rank★ = 本章结束时主角的境界档（用上面体系数字）；本批内单调不减、"
        "落在本卷区间内、不得低于本批起步档。"
    )
    return system, user


# ── 分发 ─────────────────────────────────────────────────────────────────────
_BUILDERS = {
    "benchmark": benchmark,
    # 注：positioning / power_ladder / characters 为合并步的 derived 键，
    # 由 carrier（benchmark / golden_finger / factions）一次产出，不单独 build。
    "positioning": positioning,  # 保留以兼容潜在的拆分调用，pipeline 实际不调用
    "golden_finger": golden_finger,
    "factions": factions,
    "storylines": storylines,
    "story_assets": story_assets,
    "volumes": volumes,
    "chapter_outlines": chapter_outlines,
}


def build(step: str, ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """返回 (system, user)。未知步骤抛 KeyError。"""
    return _BUILDERS[step](ctx, cfg)


def dump_ctx_json(ctx: dict) -> str:  # 调试辅助
    return json.dumps(ctx, ensure_ascii=False, indent=2)
