"""设定步骤 prompt（system + user 模板）+ 全步骤分发。

统一约定：
  - system 立「大白文总编辑」人设（prompt_base.SYS_BASE），强调爽点循环而非因果链。
  - user 末尾给出**精确 JSON 骨架**，并强制「只返回 JSON」。
  - 章纲两段式（节拍序列/五拍展开/定向修复）见 prompts_chapter；
    新增设定步（反派阶梯/谜题排程/书名简介）见 prompts_extra。
ctx 为累积上下文 dict（前序步骤产物）。
"""

from __future__ import annotations

import json

from dabai import ctx_rich, prompts_chapter, prompts_extra
from dabai.config import DabaiConfig
from dabai.first_chapter_opening import first_chapter_opening_block
from dabai.realm_spine import volume_realm_pace_prompt_addendum
from dabai.non_system import (
    benchmark_non_system_note,
    golden_finger_extra_block,
    golden_finger_json_fields,
    prefers_non_system,
)
from dabai.naming import character_naming_prompt_block
from dabai.prompt_base import SYS_BASE, benchmark_block, ctx_brief, ladder_block

# 兼容旧引用名
_SYS_BASE = SYS_BASE
_ctx_brief = ctx_brief
_benchmark_block = benchmark_block
_ladder_block = ladder_block


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
        "★防幻觉要求：对标的价值在『特征画像』而非书名——拿不准具体书名时，"
        "title 写题材型代称（如「系统升级流头部作品」），confidence 标 low，"
        "禁止编造具体书名或张冠李戴。\n"
        "只返回 JSON。"
    )
    logline = ctx.get("logline") or ""
    user = (
        f"题材 / 一句话创意：{logline}\n"
        + benchmark_non_system_note(logline) + "\n"
        "返回 JSON（顶层两块：benchmark 对标分析、positioning 立项定位，"
        "positioning 要从 benchmark 推导而来）：\n"
        "{\n"
        '  "benchmark": {\n'
        '    "topic": "题材标签（如 系统流/吞噬流/赘婿打脸）",\n'
        '    "reference_books": [\n'
        '      {"title": "书名或题材型代称", "confidence": "high|medium|low",\n'
        '       "why_comparable": "为何对标", "core_appeal": "核心卖点/爽点",\n'
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
        + benchmark_block(ctx) + "\n"
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
    return SYS_BASE, user


def golden_finger(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """合并步：一次产出 金手指 + 境界阶梯 + 卷级反派阶梯。

    三者同域（力量体系与对立面）：Boss 档与境界档同次推理生成，对齐性比拆开更好；
    按次计费下省 1 次调用。
    """
    artifact = prefers_non_system(ctx)
    type_hint, gf_extra_fields = golden_finger_json_fields(artifact=artifact)
    user = (
        f"{ctx_brief(ctx)}\n"
        + benchmark_block(ctx) + "\n"
        + (golden_finger_extra_block() if artifact else "")
        + "一次设计好本书的【力量体系与对立面】——金手指 + 与之匹配的境界阶梯 + 卷级反派阶梯。"
        "金手指要当章见效、能持续产出爽点；境界要清晰可数、和金手指的升级机制自洽；"
        "每卷一个主要对立面（Boss/压迫源），是各卷打脸高潮的靶子。"
        "可借鉴对标设定母题，但要差异化。返回 JSON（三块）：\n"
        "{\n"
        '  "golden_finger": {\n'
        '    "name": "金手指名称",\n'
        f'    "type": "{type_hint}",\n'
        '    "core_ability": "核心能力（一句话）",\n'
        '    "upgrade_mechanism": "怎么靠它变强（量化升级路径，且要呼应下面的境界阶梯）",\n'
        '    "shuang_engine": "怎么持续产生爽点（越强越稀有越爽 在哪体现）",\n'
        '    "restriction": "限制（防无敌没张力，但不能是劝退读者的长期代价）",\n'
        '    "first_10_shuang": ["前10章金手指能产出的具体爽点 8-10 条'
        '（每条=场景+用法+爽在哪，是章纲的弹药库）"],\n'
        '    "realm_milestones": [{"rank": 1, "gf_form": "该境界档金手指的形态/阶段",'
        ' "new_ability": "该档解锁的新能力（写章按此取材）"}],\n'
        + gf_extra_fields +
        "  },\n"
        '  "power_ladder": {\n'
        '    "name": "体系名称",\n'
        '    "levels": [{"rank": 1, "name": "境界名", "desc": "一句话特征+突破条件"}]\n'
        "  },\n"
        '  "antagonist_ladder": [\n'
        "    {\n"
        '      "volume_number": 1, "boss_name": "Boss 姓名",\n'
        '      "boss_faction": "所属势力（可新设，后续势力步必须建档）",\n'
        '      "boss_realm": "境界名", "boss_realm_rank": 2,\n'
        '      "motive": "为何与主角过不去（具体仇怨/利益冲突，禁止单纯看不顺眼）",\n'
        '      "pressure_style": "压迫方式（资源克扣/规则刁难/当众羞辱/追杀/夺宝…）",\n'
        '      "fate": "卷末下场（被当众打脸/重伤遁走/伏诛/臣服…）"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "硬规则：\n"
        "1. 境界 6-8 个大境界，rank 从 1 递增；realm_milestones 必须与 levels 的 rank "
        "一一对应（金手指与境界不许脱钩）；\n"
        f"2. 反派阶梯共 {cfg.volume_count} 卷各一条：boss_realm_rank 用上面 levels 的数字，"
        "须略高于该卷主角预计档位（压迫感来源）、逐卷递增、不超体系最高档；\n"
        "3. 仇恨链升级：后卷 Boss 优先是前卷 Boss 的靠山/师门/家族（打倒一个引出更大的）；"
        "fate 不得连续两卷相同；禁止所有 Boss 出自同一势力；\n"
        "4. 第1卷 Boss 必须是开局就能接触到的近身压迫者（同门/管事/退婚家族级别），"
        "不要一上来就是隐世大佬。"
    )
    return SYS_BASE, user


def factions(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """合并步：一次产出 势力 + 人物（阵营卡司）。

    须接住反派阶梯 roster（Boss 建档）、给出场景池与配角池（章纲轮换素材）。
    """
    user = (
        f"{ctx_brief(ctx)}\n"
        + benchmark_block(ctx)
        + ctx_rich.antagonist_block(ctx) + "\n"
        "一次设计好本书的【阵营卡司】——势力 + 人物，两者要咬合："
        "人物要分属设计好的势力，打脸对象要来自压迫方势力。返回 JSON（两块）：\n"
        "{\n"
        '  "factions": [\n'
        "    {\n"
        '      "name": "势力名", "stance": "主角方/压迫方/中立资源/神秘势力",\n'
        '      "role": "在爽点循环里扮演什么（谁压迫主角、谁是打脸靶子土壤）",\n'
        '      "power_tier": "最高战力档", "note": "前期/后期作用",\n'
        '      "locations": ["该势力的驻地+周边场景 3-5 个（具体地名，'
        '如 万宝拍卖行/外门灵田/刑堂大殿，是章纲场景轮换池）"]\n'
        "    }\n"
        "  ],\n"
        '  "characters": [\n'
        "    {\n"
        '      "name": "姓名", "role": "主角/打脸对象/女主/导师/工具人配角",\n'
        '      "tier": "核心/配角", "start_realm": "起始境界", "persona": "性格（一句话）",\n'
        '      "function": "在爽点循环里的功能（打脸靶子/救场/感情锚点/埋钩子）",\n'
        '      "speech_kit": "口癖/标志性台词 1-2 句（正文人人一个腔的解药）"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "硬规则：\n"
        "1. 势力 4-6 个，必须涵盖【卷级反派阶梯】里出现的所有势力名；\n"
        "2. 人物必须含：1个扮猪吃虎的主角、反派阶梯前 2-3 卷的 Boss（逐个建档，"
        "名字/境界与阶梯一致）、1个女主、1个导师/贵人；\n"
        "3. 另配【工具人配角池】8-12 人（tier=配角），每人必须有独立正名+身份标签"
        "（管事/师兄/商会少东/执法弟子/散修…）——他们是 witnesses 逐章轮换的群演库；\n"
        "4. 主角额外带 desire（最强欲望）、wound（憋屈来源）、golden_finger 字段。\n"
        + character_naming_prompt_block(ctx)
        + "\n5. 反派阶梯已给出的 boss_name 须原样建档，禁止改成「执法堂甲」类序号名。"
    )
    return SYS_BASE, user


def storylines(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """合并步：一次产出 叙事规划三块——故事线 + 剧情资产/初始关系 + 谜题排程。

    三块本是同一次叙事推理：谜题须咬合故事线与资产、资产须绑定人物关系张力，
    同次生成比拆三次注入对齐更紧；按次计费下省 2 次调用。
    """
    gf = ctx.get("golden_finger") or {}
    user = (
        f"{ctx_brief(ctx)}\n"
        + ctx_rich.characters_block(ctx)
        + ctx_rich.antagonist_block(ctx) + "\n"
        f"一次做好本书的【叙事规划】三块（全书 {cfg.volume_count} 卷），返回 JSON：\n"
        "{\n"
        '  "storylines": [\n'
        "    {\n"
        '      "name": "线名", "type": "main/revenge/romance/mystery",\n'
        '      "summary": "一句话走向",\n'
        '      "bound_characters": ["这条线绑定的人物名（用人物档案里的名字）"],\n'
        '      "nodes": [{"planned_volume": 1, "node": "该卷这条线的关键节点（具体事件，≤26字）"}]\n'
        "    }\n"
        "  ],\n"
        '  "story_assets": {\n'
        '    "plot_assets": [\n'
        '      {"kind": "skill|item", "name": "≤10字", "plot_role": "争夺点|底牌|成长线|身世信物",\n'
        '       "owner": "开局持有者人名（未登场则留空）", "debut": "start|later", "planned_volume": 1,\n'
        '       "description": "≤40字：谁觊觎/怎么升级/何时引爆"}\n'
        "    ],\n"
        '    "initial_relations": [\n'
        '      {"from": "主角人名", "to": "对方人名",\n'
        '       "attitude": "敌对|轻视|忌惮|臣服|效忠|盟友|暧昧|中立",\n'
        '       "tension": "≤30字初始张力（嫉妒/退婚之恨/暗中觊觎金手指）"}\n'
        "    ]\n"
        "  },\n"
        '  "mystery_schedule": {\n'
        '    "mysteries": [\n'
        "      {\n"
        '        "name": "谜题名（≤10字）",\n'
        '        "essence": "真相一句话（只给作者看，正文揭底前禁止说破）",\n'
        '        "hook_question": "读者侧悬念问题（如 系统为何选中他？）",\n'
        '        "reveals": [{"volume_number": 1, "reveal": "该卷透出的一小块具体信息"}],\n'
        '        "final_reveal_volume": 5\n'
        "      }\n"
        "    ]\n"
        "  }\n"
        "}\n"
        "【故事线硬规则】3-4 条，主线必须是『升级打脸』，其余可含复仇/感情/身世谜题线；"
        "每条线 3-5 个 nodes、覆盖不同卷次；感情线/身世线节点不许全堆在第1卷或最后一卷；"
        "复仇线节点须呼应上方反派阶梯的卷级 Boss。\n"
        "【资产/关系硬规则】plot_assets 3-6 件，每件必须绑定剧情作用"
        "（被各方觊觎的争夺点/反派底牌/主角功法升级路线/身世信物谜题）；"
        f"金手指（{gf.get('name', '')}）本身不要重复列入（已单独建账）。"
        "★debut 分流★：debut=start 仅「开局已持有」（他人持有的争夺点/底牌、主角随身身世信物）；"
        "debut=later 为第1章及之后才获得（含成长线主功法，成长线★必须★later）；"
        "initial_relations 覆盖主角与每个核心人物，要有张力（前期打脸剧情的燃料）。\n"
        "【谜题硬规则】2-4 个；reveals 覆盖全卷次、每卷至少一个谜题动一动；"
        "信息逐次升级（碎片→指向→反转），禁止每卷重复同一句暗示；"
        "最大谜题（金手指来历/身世）final_reveal_volume 放在全书后 1/3；"
        "谜题之间要互相咬合（身世信物指向金手指来历之类），且与上面 storylines 的"
        " mystery 线节点、plot_assets 的身世信物对齐——三块是一盘棋，不是三张孤表。"
    )
    return SYS_BASE, user


def story_assets(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """剧情资产 + 初始关系：台账种子，章纲与写章全程引用同一批设定。"""
    chars = ctx.get("characters") or []
    char_lines = "\n".join(
        f"  - {c.get('name', '')}（{c.get('role', '')}）：{(c.get('persona') or '')[:30]}"
        for c in chars[:8]
    )
    user = (
        f"{ctx_brief(ctx)}\n\n"
        f"【人物清单】\n{char_lines}\n\n"
        "设计两块台账种子，只返回 JSON：\n"
        "1. plot_assets：3-6 件有剧情功能的功法/道具（不是装备列表——每件必须绑定剧情作用：\n"
        "   被各方觊觎的争夺点 / 反派底牌 / 主角功法升级路线 / 身世信物谜题）。\n"
        "2. initial_relations：主角与每个核心人物的开局关系（要有张力，是前期打脸剧情的燃料）。\n"
        "★debut 分流（硬约束）★：\n"
        "  - debut=start：仅「开局已持有」——他人持有的争夺点/底牌、主角随身身世信物等；\n"
        "  - debut=later：第1章及之后才获得的功法/宝物（含成长线主功法、金手指配套魔经/诀）；\n"
        "  - plot_role=成长线 的功法 ★必须★ debut=later（第1章认主后才得，禁止标 start）；\n"
        "  - 主角持有的 skill 默认 debut=later，除非明确是开局就练的残缺入门诀且第1章不获得。\n"
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
    return SYS_BASE, user


def volumes(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    levels = (ctx.get("power_ladder") or {}).get("levels") or []
    max_rank = max((int(l.get("rank", 0)) for l in levels), default=cfg.volume_count + 1)
    user = (
        f"{ctx_brief(ctx)}\n"
        + ctx_rich.volume_design_context(ctx)
        + ladder_block(ctx) + "\n"
        f"把全书拆成 {cfg.volume_count} 卷，每卷 {cfg.volume_chapters} 章。"
        "每卷给出爽点大节拍、卷末高潮、【主角境界区间】，并接住上方设计资产："
        "本卷 Boss、本卷登场的剧情资产、本卷谜题透出、各故事线节点。返回 JSON 数组：\n"
        "[\n"
        "  {\n"
        '    "volume_number": 1, "title": "第1卷 卷名",\n'
        '    "phase": "opening/rising/turning/dark_hour/climax",\n'
        f'    "planned_chapters": {cfg.volume_chapters},\n'
        '    "boss": "本卷 Boss（必须用反派阶梯里该卷的名字）",\n'
        '    "big_beats": ["本卷2-4个大爆点（打脸/越级/夺宝），至少1个落在本卷 Boss 身上、'
        '至少1个兑现本卷规划登场的剧情资产"],\n'
        '    "volume_climax": "卷末高潮（对本卷 Boss 的最大一次打脸或翻盘）",\n'
        '    "end_hook": "卷末钩子（勾下一卷，优先用下一卷 Boss 或谜题透出做引）",\n'
        '    "storyline_moves": ["线名:本卷推进到哪个节点（按故事线节点表落位）"],\n'
        '    "mystery_moves": ["谜题名:本卷透出哪块信息（按谜题排程落位）"],\n'
        '    "realm_start_rank": 1, "realm_end_rank": 2\n'
        "  }\n"
        "]\n"
        "★境界硬规则★：realm_start_rank / realm_end_rank 用上面档位的数字；"
        f"全书从第1卷起单调上升，最高不超过 {max_rank}；"
        "每卷 realm_end_rank ≥ realm_start_rank；下一卷 realm_start_rank = 上一卷 realm_end_rank（首尾相接，禁止回退）；"
        "开局卷升幅要小（1-2 档），别一卷暴涨；"
        "本卷 Boss 的境界档（见反派阶梯）须略高于本卷主角区间上限，压迫感由此而来。"
        + volume_realm_pace_prompt_addendum(ctx, cfg.volume_chapters) + "\n"
        "第1卷开局须贴合本书主题定制（见下方第1章开局块），"
        "禁止默认套用退婚+踹 cliff/演武场羞辱等烂模板；"
        "结构仍是：蓄憋屈→金手指露头→留当众打脸钩子。"
        + first_chapter_opening_block(ctx)
    )
    return SYS_BASE, user


# ── 分发 ─────────────────────────────────────────────────────────────────────
_BUILDERS = {
    "benchmark": benchmark,
    # 注：positioning / power_ladder / characters 为合并步的 derived 键，
    # 由 carrier（benchmark / golden_finger / factions）一次产出，不单独 build。
    "positioning": positioning,  # 保留以兼容潜在的拆分调用，pipeline 实际不调用
    "golden_finger": golden_finger,
    "antagonist_ladder": prompts_extra.antagonist_ladder,
    "factions": factions,
    "storylines": storylines,
    "story_assets": story_assets,
    "mystery_schedule": prompts_extra.mystery_schedule,
    "title_blurb": prompts_extra.title_blurb,
    "volumes": volumes,
    "volume_chapters": prompts_chapter.volume_chapters,  # 单次整卷 beat+五拍（主路径）
    "beat_sequence": prompts_chapter.beat_sequence,      # 降级路径
    "chapter_outlines": prompts_chapter.chapter_outlines,  # 降级路径
    "chapter_repair": prompts_chapter.chapter_repair,
}


def build(step: str, ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """返回 (system, user)。未知步骤抛 KeyError。"""
    return _BUILDERS[step](ctx, cfg)


def dump_ctx_json(ctx: dict) -> str:  # 调试辅助
    return json.dumps(ctx, ensure_ascii=False, indent=2)
