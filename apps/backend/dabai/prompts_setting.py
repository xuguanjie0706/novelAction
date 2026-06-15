"""设定步骤 prompt（深挖版）：benchmark / golden_finger / factions / storylines / volumes。

设计动机（2026-06-16 重规划）：按次计费 + 质量优先——单次调用不再吝惜 token，
把每个设定步的 JSON 骨架与硬规则全量铺开，让同一次推理产出「老白文主编脑子里
一整套互相咬合的设定」，而非压缩成人名+一句话。所有顶层键与 item_required 与
schemas.STEP_CONTRACT 保持一致（向后兼容 persist / linter）；新增字段一律是
JSON 列 / extra 列可吞下的增量，不破坏既有落库。

从 prompts.py 抽出以遵守 600 行红线（prompts.py 仅保留分发 + 兼容存根）。
"""

from __future__ import annotations

from dabai import ctx_rich
from dabai.config import DabaiConfig
from dabai.first_chapter_opening import first_chapter_opening_block
from dabai.naming import character_naming_prompt_block
from dabai.non_system import (
    benchmark_non_system_note,
    golden_finger_extra_block,
    golden_finger_json_fields,
    prefers_non_system,
)
from dabai.prompt_base import SYS_BASE, benchmark_block, ctx_brief, ladder_block
from dabai.realm_spine import volume_realm_pace_prompt_addendum


# ── ① 对标 + 立项定位（合并步）────────────────────────────────────────────────
def benchmark(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """一次产出『对标分析』+『立项定位』，定位须从对标推导，全量铺开。"""
    system = (
        "你是有20年经验的番茄/起点/七猫选题主编 + 数据运营，操盘过多部百万追读爽文。\n"
        "请先做深度对标分析，再据此为本书做立项定位（定位必须对齐对标特征，不要自说自话）。\n"
        "★合规要求：只描述作品可借鉴的『特征』（卖点、套路、设定母题、文笔风格、数据表现），"
        "严禁抄录任何作品的原文段落、具体情节或人物原名作为输出内容。\n"
        "★防幻觉要求：对标价值在『特征画像』而非书名——拿不准书名时 title 写题材型代称"
        "（如「系统签到流头部作品」），confidence 标 low，禁止编造书名或张冠李戴。\n"
        "不省 token：每个字段都要给具体可执行的判断，不要泛泛而谈。只返回 JSON。"
    )
    logline = ctx.get("logline") or ""
    user = (
        f"题材 / 一句话创意：{logline}\n"
        + benchmark_non_system_note(logline) + "\n"
        "返回 JSON（顶层两块 benchmark / positioning，positioning 须从 benchmark 推导）：\n"
        "{\n"
        '  "benchmark": {\n'
        '    "topic": "题材标签（如 系统流/吞噬流/赘婿打脸）",\n'
        '    "reader_pain_points": ["该题材读者最想被满足的爽 3-5 条（被轻视后翻身/越级碾压/扮猪吃虎…）"],\n'
        '    "reference_books": [\n'
        '      {"title": "书名或题材型代称", "confidence": "high|medium|low",\n'
        '       "why_comparable": "为何对标", "core_appeal": "核心卖点/爽点",\n'
        '       "setting_motif": "设定母题(金手指/世界观套路)",\n'
        '       "structure_note": "开篇怎么抓人/爽点节奏",\n'
        '       "style_note": "文笔特征(句式/节奏/腔调)",\n'
        '       "why_it_worked": "成功底层原因（情绪杠杆，不是表面套路）"}\n'
        "    ],\n"
        '    "style_profile": {"sentence_style": "句式", "pacing": "节奏",\n'
        '      "dialogue_density": "对话密度", "shuang_cadence": "爽点节奏(几章一爆)",\n'
        '      "narration_voice": "叙事腔调", "chapter_word_target": "章均字数区间"},\n'
        '    "data_signals": {"hook_window": "前几章定生死", "retention_lever": "靠什么留住追读",\n'
        '      "paywall_zone": "一般在第几章上付费墙", "collapse_risks": "数据掉读高危区"},\n'
        '    "setting_conventions": ["该题材常见设定套路 3-5 条"],\n'
        '    "tropes_to_use": ["值得用的爽点/桥段套路 4-6 条"],\n'
        '    "pitfalls_to_avoid": ["容易翻车/读者反感的点 3-5 条"]\n'
        "  },\n"
        '  "positioning": {\n'
        '    "target_audience": "目标读者画像（平台/性别/年龄/口味，对齐对标读者）",\n'
        '    "shuang_pool": ["主打爽点类型 5-7 个，从 打脸/升级/获宝/扮猪吃虎/装逼/群嘲反转/收小弟/救场/扬名 选"],\n'
        '    "face_slap_frequency": "打脸/爽点频率（呼应对标 shuang_cadence，如每章一小爽、每5章一大爆）",\n'
        '    "golden_three_strategy": "黄金三章策略：第1章蓄憋屈、第2章金手指登场、第3章第一次大打脸（逐章写清抓手）",\n'
        '    "retention_anchors": ["前10章每2-3章一个具体追读锚点（钩子事件），至少4条"],\n'
        '    "paywall_chapter": "建议付费卡点章号 + 卡点前必须给到的最大爽点",\n'
        '    "chapter_word_target": "建议章均字数（普通章/大爆点章）",\n'
        '    "emotion_curve": ["分卷情绪主色调（憋屈→反击→扬名→新危机…），按 卷数 给"],\n'
        '    "core_selling_hooks": ["本书最炸的3个卖点钩子，按强度排序（番茄首页一句话能不能抓人）"],\n'
        '    "differentiation": "与对标作品的一句话差异化（同题材凭什么选你）",\n'
        '    "pace_type": "fast",\n'
        '    "emotional_arc": "情绪闭环节律（憋屈→反击→扬名 的周期长度）",\n'
        '    "taboo_lines": ["3-5 条硬禁忌（可吸收对标 pitfalls_to_avoid，如 不许窝囊超过一章）"],\n'
        '    "writing_style": "plain"\n'
        "  }\n"
        "}\n"
        "硬规则：reference_books 给 3-5 本；retention_anchors / core_selling_hooks "
        "必须是具体事件而非抽象形容词；定位的 shuang_cadence / 字数 / 卡点要彼此自洽。"
    )
    return system, user


# ── ② 金手指 + 境界阶梯 + 反派阶梯（合并步）──────────────────────────────────
def golden_finger(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """一次产出力量体系与对立面（金手指 / 境界 / 卷级 Boss），三块同次推理对齐。"""
    artifact = prefers_non_system(ctx)
    type_hint, gf_extra_fields = golden_finger_json_fields(artifact=artifact)
    user = (
        f"{ctx_brief(ctx)}\n"
        + benchmark_block(ctx) + "\n"
        + (golden_finger_extra_block() if artifact else "")
        + "一次设计好本书的【力量体系与对立面】——金手指 + 与之匹配的境界阶梯 + 卷级反派阶梯。"
        "金手指要当章见效、能持续产出爽点；境界要清晰可数、和金手指升级机制自洽；"
        "每卷一个主要对立面（Boss），是各卷打脸高潮的靶子。不省 token，每个字段写满写实。"
        "可借鉴对标设定母题，但必须差异化。返回 JSON（三块）：\n"
        "{\n"
        '  "golden_finger": {\n'
        '    "name": "金手指名称",\n'
        f'    "type": "{type_hint}",\n'
        '    "core_ability": "核心能力（一句话）",\n'
        '    "acquisition": "开局怎么获得（认主/觉醒/捡到，第1-2章能落地的方式）",\n'
        '    "upgrade_mechanism": "怎么靠它变强（量化升级路径，呼应下方境界阶梯）",\n'
        '    "upgrade_economy": "升级资源经济：靠什么喂养它升级（吞噬/签到/积分/血祭…）+ 资源从哪来",\n'
        '    "manifestation": "呈现形态（脑海面板/古卷/纹身/吞噬具象…，写章可视化的抓手）",\n'
        '    "shuang_engine": "怎么持续产生爽点（越强越稀有越爽 在哪体现）",\n'
        '    "anti_boring": "防无敌设计：怎么在很强的同时仍有张力（信息差/资源差/规则限制）",\n'
        '    "restriction": "限制（防无敌没张力，但不能是劝退读者的长期代价）",\n'
        '    "differentiation": "与对标同类金手指的差异化一句话",\n'
        '    "first_10_shuang": ["前10章金手指能产出的具体爽点 14-20 条'
        '（每条=场景+用法+爽在哪+谁见证，是章纲的弹药库，要密、要狠、不重样）"],\n'
        '    "signature_scenes": ["最能立人设的3个金手指高光名场面（中后期，写章作高潮素材）"],\n'
        '    "tiers": [{"stage": "金手指自身阶段名", "unlock": "该阶段解锁的新用法", "trigger": "怎么进阶"}],\n'
        '    "realm_milestones": [{"rank": 1, "gf_form": "该境界档金手指的形态/阶段",'
        ' "new_ability": "该档解锁的新能力（写章按此取材）", "numeric_marker": "可量化标志（如 吞噬上限/签到天数）"}]'
        + (",\n" + gf_extra_fields if gf_extra_fields.strip() else "\n") +
        "  },\n"
        '  "power_ladder": {\n'
        '    "name": "体系名称",\n'
        '    "design_philosophy": "这套境界为本书爽点服务的逻辑一句话（如 每跨一大境如天堑、主角靠金手指越级、越级即爽点）",\n'
        '    "sub_stage_pattern": "每个大境界内的小层级划分（如 初期/中期/后期/巅峰/圆满，或 一至九重），realm_sub_rank 按此",\n'
        '    "cross_realm_gap": "大境界之间的战力级差（量化倍率）+ 为何常人无法越级（法则压制/气血碾压）——主角越级的稀有与炸裂由此而来",\n'
        '    "suppression_rule": "高境界对低境界的压制机制（气势锁定/法则镇压/神识碾压），解释正常打不过，反衬主角逆天",\n'
        '    "special_constitution": "同境界战力分化机制（特殊体质/血脉/功法品阶），让主角能同境吊打天骄、为打脸留空间",\n'
        '    "ceiling": "体系天花板与终极悬念（成仙/飞升/破碎虚空/封王/不死），指向全书结局，留白不写死",\n'
        '    "levels": [{\n'
        '      "rank": 1, "name": "大境界名（有阶梯感与逼格，禁第1境第2境式序号）", "desc": "一句话核心特征",\n'
        '      "sub_stages": ["该大境内小层级名 3-5 个（如 一重/三重/九重 或 初期/巅峰，供 realm_sub_rank）"],\n'
        '      "realm_title": "此境修士的社会称谓（散修/武者/真人/宗师/大能/老祖/地仙…）",\n'
        '      "power_benchmark": "战力标尺事件（碎石→断江→裂山→灭城→翻云覆雨，一句话让读者秒懂这一境多强）",\n'
        '      "combat_multiplier": "相对上一大境的战力倍率（量化越级难度，如 一拳十倍/百倍）",\n'
        '      "breakthrough": "突破到下一档的条件与瓶颈（卡关点：多少修士困死于此，反派常卡在此境）",\n'
        '      "tribulation": "突破时的异象/天劫/反噬（天地异象、雷劫、走火入魔——扮猪吃虎暴露实力与越级惊场的视觉装置）",\n'
        '      "lifespan": "此境寿命（长生阶梯，逐境翻倍，是反派疯狂与主角向上的根本动机）",\n'
        '      "world_scope": "此境对应的活动格局（村镇→宗门→一国→一域→一界→界外，格局逐境打开）",\n'
        '      "ascend_resource": "晋级所需稀缺资源（灵石→丹药→天材地宝→秘境机缘→法则碎片，夺宝/资源争夺爽点的根）",\n'
        '      "signature_power": "此境标志性神通/手段（御物→御空→分身→言出法随…）",\n'
        '      "mortal_view": "低境者/凡人对此境的认知（传说/活神仙/灭门只在翻手间——打脸时『你也配』逼格落差的来源）"\n'
        "    }]\n"
        "  },\n"
        '  "antagonist_ladder": [\n'
        "    {\n"
        '      "volume_number": 1, "boss_name": "Boss 姓名（2-4字具体名，禁占位）",\n'
        '      "boss_faction": "所属势力（可新设，势力步必须建档）",\n'
        '      "boss_realm": "境界名", "boss_realm_rank": 2,\n'
        '      "motive": "为何与主角过不去（具体仇怨/利益冲突，禁止单纯看不顺眼）",\n'
        '      "pressure_style": "压迫方式（资源克扣/规则刁难/当众羞辱/追杀/夺宝…）",\n'
        '      "humiliation": "对主角施加的最具体一次羞辱（打脸前的势能）",\n'
        '      "enforcers": ["手下打手/帮凶 1-2 个具体名字（章纲打脸轮换素材）"],\n'
        '      "weakness": "命门/翻盘缺口（主角靠什么破他）",\n'
        '      "first_clash": "与主角首次正面冲突的事件（落在第几章段）",\n'
        '      "fate": "卷末下场（被当众打脸/重伤遁走/伏诛/臣服…）"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "硬规则：\n"
        "1. 【境界体系】6-8 个大境界，rank 从 1 递增、命名要有阶梯感与逼格记忆点（禁「第1境」式序号）；\n"
        "   ★越级即爽点★：cross_realm_gap 必须量化大境级差（越往上倍率越夸张），并明确常态铁律"
        "——『低一大境的天骄也难撼高一大境的普通修士』；主角靠金手指打破这条铁律，越级打脸才炸裂；\n"
        "   ★三条曲线同步指数上涨★：lifespan（寿命）、ascend_resource（资源稀缺度）、world_scope（活动格局）"
        "逐境翻番式拉开，长生欲、夺宝欲、格局打开三大驱动力全靠它；\n"
        "   ★战力标尺★：每境 power_benchmark 给一句可视化标尺事件，让读者一眼感知强度差；\n"
        "   ★详略★：前 2-3 个低境界写细（开局主战场、读者停留最久），高境界可略写留神秘；\n"
        "   ★天花板留悬念★：ceiling 指向全书终局但不写死；sub_stages 必须能支撑 realm_sub_rank（同境小层）；\n"
        "   realm_milestones 必须与 levels 的 rank 一一对应（金手指形态与境界不许脱钩，"
        "金手指升级机制要解释主角为何能越级、为何升得比别人快）；\n"
        f"2. 反派阶梯共 {cfg.volume_count} 卷各一条：boss_realm_rank 用上面 levels 的数字，"
        "须略高于该卷主角预计档位（压迫感来源）、逐卷递增、不超体系最高档；\n"
        "3. 仇恨链升级：后卷 Boss 优先是前卷 Boss 的靠山/师门/家族（打倒一个引出更大的）；"
        "fate 不得连续两卷相同；禁止所有 Boss 出自同一势力；\n"
        "4. 第1卷 Boss 必须是开局就能接触到的近身压迫者（同门/管事/退婚家族级别），"
        "不要一上来就是隐世大佬；\n"
        "5. first_10_shuang 14 条起步、条条不同场景；空泛的「变强了」不算一条。"
        + character_naming_prompt_block(ctx)
    )
    return SYS_BASE, user


# ── ③ 势力 + 人物卡司（合并步）────────────────────────────────────────────────
def factions(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """一次产出势力 + 全量人物卡司（含配角池），两者咬合且接住反派阶梯 roster。"""
    user = (
        f"{ctx_brief(ctx)}\n"
        + benchmark_block(ctx)
        + ctx_rich.antagonist_block(ctx) + "\n"
        "一次设计好本书的【阵营卡司】——势力 + 人物，两者要咬合："
        "人物分属设计好的势力，打脸对象来自压迫方势力。人物档案不省 token，"
        "把心理侧写写满（写章人物不脸谱化、人人一个腔的解药）。返回 JSON（两块）：\n"
        "{\n"
        '  "factions": [\n'
        "    {\n"
        '      "name": "势力名", "stance": "主角方/压迫方/中立资源/神秘势力",\n'
        '      "role": "在爽点循环里扮演什么（谁压迫主角、谁是打脸靶子土壤）",\n'
        '      "power_tier": "最高战力档", "structure": "内部层级/规矩一句话（外门内门/长老堂…）",\n'
        '      "resource": "掌握的稀缺资源（功法/灵矿/商路，主角觊觎或争夺的）",\n'
        '      "note": "前期/后期作用 + 与其他势力的关系（盟友/世仇/上下级）",\n'
        '      "locations": ["该势力的驻地+周边场景 3-5 个（具体地名，'
        '如 万宝拍卖行/外门灵田/刑堂大殿，是章纲场景轮换池）"]\n'
        "    }\n"
        "  ],\n"
        '  "characters": [\n'
        "    {\n"
        '      "name": "姓名", "role": "主角/打脸对象/女主/导师/工具人配角",\n'
        '      "tier": "核心/配角", "faction": "所属势力名", "start_realm": "起始境界",\n'
        '      "appearance": "外貌+穿着标志（一句话，正文可视化锚点）",\n'
        '      "persona": "性格（一句话）", "speech_kit": "口癖/标志性台词 1-2 句（原话）",\n'
        '      "catchphrase": "口头禅一句", "signature_move": "标志动作/习惯（攥拳/冷笑/摸刀…）",\n'
        '      "values": "价值观/行事准则一句话", "function": "在爽点循环里的功能（打脸靶子/救场/感情锚点/埋钩子）",\n'
        '      "relation_to_protagonist": "与主角的初始关系+张力一句话",\n'
        '      "debut_scene": "首次登场场景/方式（落在哪个势力场景）"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "硬规则：\n"
        "1. 势力 4-6 个，必须涵盖【卷级反派阶梯】里出现的所有势力名；\n"
        "2. 人物必须含：1个扮猪吃虎的主角、反派阶梯前 2-3 卷的 Boss（逐个建档，"
        "名字/境界与阶梯一致）、1个女主、1个导师/贵人；\n"
        "3. 主角档案额外带 desire（最强欲望）、wound（憋屈来源）、fear（恐惧）、"
        "secret（秘密/底牌）、growth_arc（分卷成长弧 3-4 句）、golden_finger（持有的金手指名）字段；\n"
        "4. 另配【工具人配角池】10-14 人（tier=配角），每人必须有独立正名 + 身份标签"
        "（管事/师兄/商会少东/执法弟子/散修…）+ debut_scene——他们是 witnesses 逐章轮换的群演库；\n"
        "5. 反派阶梯已给出的 boss_name 须原样建档，禁止改成「执法堂甲」类序号名；"
        "每个核心 Boss 也要带 secret / fear / weakness 字段。\n"
        + character_naming_prompt_block(ctx)
    )
    return SYS_BASE, user


# ── ④ 故事线 + 剧情资产/关系 + 谜题排程（合并步）────────────────────────────
def storylines(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """一次产出叙事规划三块，三块同次推理咬合（谜题↔故事线↔资产↔关系一盘棋）。"""
    gf = ctx.get("golden_finger") or {}
    user = (
        f"{ctx_brief(ctx)}\n"
        + ctx_rich.characters_block(ctx)
        + ctx_rich.antagonist_block(ctx) + "\n"
        f"一次做好本书的【叙事规划】三块（全书 {cfg.volume_count} 卷），不省 token，返回 JSON：\n"
        "{\n"
        '  "storylines": [\n'
        "    {\n"
        '      "name": "线名", "type": "main/revenge/romance/mystery",\n'
        '      "summary": "一句话走向", "stakes": "这条线的赌注/为什么读者在意",\n'
        '      "bound_characters": ["这条线绑定的人物名（用人物档案里的名字）"],\n'
        '      "nodes": [{"planned_volume": 1, "node": "该卷关键节点（具体事件，≤26字）",\n'
        '        "beat_type": "推进/转折/回收", "emotional_payoff": "读者情绪收益一句话"}]\n'
        "    }\n"
        "  ],\n"
        '  "story_assets": {\n'
        '    "plot_assets": [\n'
        '      {"kind": "skill|item", "name": "≤10字", "plot_role": "争夺点|底牌|成长线|身世信物",\n'
        '       "owner": "开局持有者人名（未登场则留空）", "debut": "start|later", "planned_volume": 1,\n'
        '       "coveted_by": "谁觊觎它（制造争夺冲突）", "escalation": "它如何随剧情升级/解锁",\n'
        '       "ignite_hint": "何时引爆/亮出（卷或章段）", "description": "≤40字综述"}\n'
        "    ],\n"
        '    "initial_relations": [\n'
        '      {"from": "主角人名", "to": "对方人名",\n'
        '       "attitude": "敌对|轻视|忌惮|臣服|效忠|盟友|暧昧|中立",\n'
        '       "tension": "≤30字初始张力（嫉妒/退婚之恨/暗中觊觎金手指）",\n'
        '       "arc": "这段关系预计的演变轨迹（敌对→忌惮→臣服 之类，爽点曲线)"}\n'
        "    ]\n"
        "  },\n"
        '  "mystery_schedule": {\n'
        '    "mysteries": [\n'
        "      {\n"
        '        "name": "谜题名（≤10字）",\n'
        '        "essence": "真相一句话（只给作者看，正文揭底前禁止说破）",\n'
        '        "hook_question": "读者侧悬念问题（如 系统为何选中他？）",\n'
        '        "red_herring": "中途的误导/烟雾弹一句话（让揭底更反转）",\n'
        '        "reveals": [{"volume_number": 1, "reveal": "该卷透出的一小块具体信息"}],\n'
        '        "final_reveal_volume": 5, "payoff": "揭底时给读者的最大爽/震撼"\n'
        "      }\n"
        "    ]\n"
        "  }\n"
        "}\n"
        "【故事线硬规则】3-4 条，主线必须是『升级打脸』，其余可含复仇/感情/身世谜题线；"
        "每条线 3-5 个 nodes、覆盖不同卷次；感情线/身世线节点不许全堆在第1卷或最后一卷；"
        "复仇线节点须呼应上方反派阶梯的卷级 Boss。\n"
        "【资产/关系硬规则】plot_assets 4-6 件，每件绑定剧情作用"
        "（被各方觊觎的争夺点/反派底牌/主角功法升级路线/身世信物谜题）；"
        f"金手指（{gf.get('name', '')}）本身不要重复列入（已单独建账）。"
        "★debut 分流★：debut=start 仅「开局已持有」（他人持有的争夺点/底牌、主角随身身世信物）；"
        "debut=later 为第1章及之后才获得（含成长线主功法，成长线★必须★later）；"
        "initial_relations 覆盖主角与每个核心人物，要有张力 + arc。\n"
        "【谜题硬规则】2-4 个；reveals 覆盖全卷次、每卷至少一个谜题动一动；"
        "信息逐次升级（碎片→指向→反转），禁止每卷重复同一句暗示；"
        "最大谜题（金手指来历/身世）final_reveal_volume 放在全书后 1/3；"
        "谜题之间互相咬合（身世信物指向金手指来历之类），且与 storylines 的 mystery 线节点、"
        "plot_assets 的身世信物对齐——三块是一盘棋，不是三张孤表。"
    )
    return SYS_BASE, user


# ── ⑤ 卷骨架（每卷章段节拍表 + 情绪收支）──────────────────────────────────────
def volumes(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """卷骨架深挖：每卷给章段节拍表、情绪收支、新登场人物/设定、追读锚点。"""
    levels = (ctx.get("power_ladder") or {}).get("levels") or []
    max_rank = max((int(l.get("rank", 0)) for l in levels), default=cfg.volume_count + 1)
    user = (
        f"{ctx_brief(ctx)}\n"
        + ctx_rich.volume_design_context(ctx)
        + ladder_block(ctx) + "\n"
        f"把全书拆成 {cfg.volume_count} 卷，每卷 {cfg.volume_chapters} 章。"
        "每卷给出爽点大节拍、卷内章段施工图、卷末高潮、【主角境界区间】，并接住上方设计资产："
        "本卷 Boss、本卷登场的剧情资产、本卷谜题透出、各故事线节点。不省 token，返回 JSON 数组：\n"
        "[\n"
        "  {\n"
        '    "volume_number": 1, "title": "第1卷 卷名",\n'
        '    "phase": "opening/rising/turning/dark_hour/climax",\n'
        f'    "planned_chapters": {cfg.volume_chapters},\n'
        '    "opening_setup": "本卷开篇承接上卷钩子的方式（第1卷为开局蓄势）",\n'
        '    "boss": "本卷 Boss（必须用反派阶梯里该卷的名字）",\n'
        '    "big_beats": ["本卷2-4个大爆点（打脸/越级/夺宝），至少1个落在本卷 Boss 身上、'
        '至少1个兑现本卷规划登场的剧情资产"],\n'
        '    "chapter_beat_map": [{"span": "1-3", "role": "开篇蓄憋屈/金手指登场",'
        ' "key_event": "该段核心事件一句话"}],\n'
        '    "volume_climax": "卷末高潮（对本卷 Boss 的最大一次打脸或翻盘）",\n'
        '    "emotion_ledger": {"deposit": "本卷攒了什么憋屈/期待", "spend": "在哪兑现爽",'
        ' "net": "卷末读者情绪净余额"},\n'
        '    "new_characters": ["本卷新登场的重要人物名（须在人物档案里）"],\n'
        '    "new_settings": ["本卷新揭开的设定/地图/势力 1-3 条"],\n'
        '    "reader_hook": "本卷最强追读锚点（让读者必追下一卷的那根钩）",\n'
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
        "本卷 Boss 的境界档（见反派阶梯）须略高于本卷主角区间上限，压迫感由此而来。\n"
        "★章段施工图★：chapter_beat_map 覆盖全卷章数（分 4-6 段，span 用章号区间），"
        "每段标清作用与核心事件，是后续章纲展开的骨架；emotion_ledger 三项都要填实。"
        + volume_realm_pace_prompt_addendum(ctx, cfg.volume_chapters) + "\n"
        "第1卷开局须贴合本书主题定制（见下方第1章开局块），"
        "禁止默认套用退婚+踹 cliff/演武场羞辱等烂模板；"
        "结构仍是：蓄憋屈→金手指露头→留当众打脸钩子。"
        + first_chapter_opening_block(ctx)
    )
    return SYS_BASE, user
