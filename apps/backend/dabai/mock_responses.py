"""离线 mock：一份连贯的「吞噬流」大白文样本。

每步返回与真实 LLM 同形态的 JSON（直接返回 Python 对象，解析层会透传）。
章纲用确定性生成器排满整卷，遵守爽点节拍器约束，保证 linter 能跑出干净报告。
样本设定：废柴林凡觉醒吞噬系统，吞噬万物逆袭打脸天才李天骄。
"""

from __future__ import annotations

from typing import Any

from dabai.config import DabaiConfig
from dabai.golden_finger_bind import bind_ladder_emotion_turn_hint

PROTAGONIST = "林凡"

_BENCHMARK = {
    "topic": "系统流 / 吞噬流升级打脸",
    "reference_books": [
        {"title": "（对标·系统升级流代表作）", "why_comparable": "同为系统外挂+越级打脸",
         "core_appeal": "数值化升级、当众打脸、扮猪吃虎", "setting_motif": "签到/吞噬式金手指 + 清晰境界阶梯",
         "style_note": "短句多、对话密、节奏极快、解释直给"},
        {"title": "（对标·吞噬流代表作）", "why_comparable": "吞噬万物获得力量的爽感引擎相同",
         "core_appeal": "越强越稀有越爽、当众吞掉对手依仗", "setting_motif": "吞噬转化 + 反噬限制",
         "style_note": "爽点前置、章末强钩子、口语化"},
        {"title": "（对标·废柴逆袭流代表作）", "why_comparable": "开局退婚/被辱蓄憋屈再逆袭",
         "core_appeal": "黄金三章打脸、扬名立威", "setting_motif": "宗门外门白眼 + 天才反派土壤",
         "style_note": "憋屈—反击—扬名的三章情绪闭环"},
    ],
    "style_profile": {
        "sentence_style": "短句为主、口语化、少环境描写",
        "pacing": "极快，憋屈不拖、爽点前置",
        "dialogue_density": "高，靠对话推进冲突",
        "shuang_cadence": "每章一小爽点，每5章一大爆点",
        "narration_voice": "贴主角的爽感视角，解释直给、不留白",
    },
    "setting_conventions": [
        "金手指当章见效、可量化升级", "境界阶梯清晰可数(炼气→…)",
        "开局退婚/被逐/被夺资源蓄憋屈", "天才反派当打脸靶子",
    ],
    "tropes_to_use": ["当众打脸", "扮猪吃虎", "越级吞噬碾压", "夺回遗物立威", "黄金三章定调"],
    "pitfalls_to_avoid": ["主角窝囊超过一章", "金手指迟迟不见效", "一章塞太多新设定", "情绪硬跳无铺垫"],
}

_POSITIONING = {
    "target_audience": "16-28 岁男性，番茄/七猫移动端碎片化读者，偏好升级打脸爽文",
    "shuang_pool": ["打脸", "升级", "获宝", "扮猪吃虎", "装逼", "群嘲反转", "收小弟"],
    "face_slap_frequency": "每章至少一次小爽点，每 5 章一个大爆点",
    "golden_three_strategy": "第1章被退婚+当众羞辱蓄憋屈，第2章觉醒吞噬系统，第3章当众打脸退婚者",
    "pace_type": "fast",
    "emotional_arc": "憋屈→反击→扬名，三章一个完整爽感闭环",
    "taboo_lines": ["主角不许窝囊超过一章", "不许长篇世界观说明", "金手指当章见效"],
    "writing_style": "plain",
}

_GOLDEN_FINGER = {
    "name": "万物吞噬系统",
    "type": "系统流 + 吞噬流",
    "core_ability": "吞噬任意天材地宝、功法、妖兽甚至敌人修为，转化为自身力量与属性",
    "upgrade_mechanism": "吞噬量化为「噬力值」，攒满即可突破境界，越级吞噬有额外暴击",
    "shuang_engine": "敌人越强、宝物越稀有，吞噬反馈越爽；打脸时可当众吞掉对方依仗",
    "restriction": "吞噬有冷却且初期会反噬，强行越级吞噬需承受灼烧之痛（防无敌没张力，但不构成长期代价）",
    "first_10_shuang": [
        "杂役房吞掉发霉灵米，噬力值首涨，当晚突破炼气二层",
        "演武场吞掉李天骄掷来的灵火弹，反手原样奉还",
        "藏经阁吞掉残页功法，三息学会旁人三年的引气诀",
        "坊市被压价时当众吞掉鉴宝师的灵识探针，店主脸色骤变",
        "试炼塔吞掉阵法灵气，逼出隐藏第七层",
        "夜袭者的飞剑半路被吞，凶手顺着空气波动被揪出",
        "丹房吞掉废丹毒烟救下同门，反提纯出三枚上品丹",
        "外门大比吞掉对手护体罡气，一拳定胜负",
    ],
    "realm_milestones": [
        {"rank": 1, "gf_form": "吞噬初醒：只能吞死物/低阶灵气", "new_ability": "噬力值面板+基础转化"},
        {"rank": 2, "gf_form": "吞灵阶段：可吞功法残页与灵器", "new_ability": "功法秒学+灵器转化"},
        {"rank": 3, "gf_form": "吞丹阶段：可吞妖丹与活物修为", "new_ability": "越级吞噬暴击"},
        {"rank": 4, "gf_form": "吞魂阶段：可吞神识攻击", "new_ability": "反噬回敬+魂力护体"},
        {"rank": 5, "gf_form": "吞域阶段：可吞一域灵脉", "new_ability": "领域压制"},
        {"rank": 6, "gf_form": "吞虚阶段：可吞空间裂隙", "new_ability": "短距吞空挪移"},
        {"rank": 7, "gf_form": "噬道大成：万物皆可吞", "new_ability": "法则吞噬"},
    ],
    "signature_lines": ["叮——吞噬成功", "你以为的杀招，是我的口粮"],
}

_ANTAGONIST_LADDER = [
    {"volume_number": 1, "boss_name": "李天骄", "boss_faction": "李家",
     "boss_realm": "炼气九层", "boss_realm_rank": 2,
     "motive": "悔婚后仍觊觎林家玉佩另一半，要把林凡彻底踩死以绝后患",
     "pressure_style": "当众羞辱+资源克扣+怂恿管事刁难", "fate": "外门大比被当众打脸，本命法宝被吞"},
    {"volume_number": 2, "boss_name": "李铁山", "boss_faction": "李家",
     "boss_realm": "金丹境", "boss_realm_rank": 3,
     "motive": "侄子李天骄丢尽李家脸面，亲自出手清理门户", "pressure_style": "规则刁难+买凶截杀",
     "fate": "宗门大比越级败北，重伤遁走"},
    {"volume_number": 3, "boss_name": "血手人屠", "boss_faction": "万妖谷雇佣客卿",
     "boss_realm": "金丹巅峰", "boss_realm_rank": 4,
     "motive": "受李家重金雇佣，又贪图吞噬功法", "pressure_style": "秘境围杀+挟持人质",
     "fate": "反被吞掉本命妖丹，伏诛"},
    {"volume_number": 4, "boss_name": "李家家主李擎渊", "boss_faction": "李家",
     "boss_realm": "元婴境", "boss_realm_rank": 5,
     "motive": "家族连损三阵，玉佩秘密濒临暴露，倾族之力清算林凡",
     "pressure_style": "勾结执法堂构陷+灭门追杀", "fate": "至暗反击中被废修为，李家除名"},
    {"volume_number": 5, "boss_name": "噬天教右使", "boss_faction": "噬天教",
     "boss_realm": "化神境", "boss_realm_rank": 6,
     "motive": "察觉林凡身怀本教失落至宝（系统），要夺舍取宝", "pressure_style": "暗中布局+夺舍偷袭",
     "fate": "夺舍反被吞，身份线索浮出"},
    {"volume_number": 6, "boss_name": "噬天教主", "boss_faction": "噬天教",
     "boss_realm": "炼虚境", "boss_realm_rank": 7,
     "motive": "系统本是其师尊遗物，视林凡为窃贼与道统之争", "pressure_style": "倾教围剿+道心拷问",
     "fate": "终战被噬道反吞，身世真相大白"},
]

_MYSTERY_SCHEDULE = {
    "mysteries": [
        {"name": "系统来历", "essence": "吞噬系统是噬天教开派祖师陨落前封存的本命道果",
         "hook_question": "系统为什么偏偏选中废柴林凡？",
         "reveals": [
             {"volume_number": 1, "reveal": "噬魂老人现身：『你的系统来历不简单』"},
             {"volume_number": 3, "reveal": "血手人屠死前认出噬灵诀是『那一脉』的东西"},
             {"volume_number": 5, "reveal": "右使夺舍失败，吐出『祖师道果』四字"},
             {"volume_number": 6, "reveal": "终战揭底：系统认主与林凡血脉同源"},
         ],
         "final_reveal_volume": 6},
        {"name": "玉佩身世", "essence": "玉佩是上界林氏的传承钥匙，母亲是流放下界的林氏旁支",
         "hook_question": "李家为什么死咬着半块破玉佩不放？",
         "reveals": [
             {"volume_number": 1, "reveal": "李家夺走半块玉佩，态度反常地志在必得"},
             {"volume_number": 2, "reveal": "玉佩遇噬力微烫，浮出半个古篆"},
             {"volume_number": 4, "reveal": "李家密室搜出与玉佩同纹的上界舆图残角"},
             {"volume_number": 5, "reveal": "双佩合一，指向上界坐标"},
         ],
         "final_reveal_volume": 5},
        {"name": "噬魂老人正身", "essence": "噬魂老人是祖师残魂，既是导师也是终局变数",
         "hook_question": "半遮半掩的神秘老人到底想要什么？",
         "reveals": [
             {"volume_number": 2, "reveal": "老人指点功法却拒答来历，袖口绣噬天教旧纹"},
             {"volume_number": 4, "reveal": "危急时刻出手，被右使惊呼『不可能，你早死了』"},
             {"volume_number": 6, "reveal": "终战揭底：以残魂补全系统，托道统于林凡"},
         ],
         "final_reveal_volume": 6},
    ],
}

_TITLE_BLURB = {
    "title_candidates": [
        {"title": "开局吞了退婚书", "strategy": "金手指直给", "score": 92, "reason": "金手指+爽点事件直给"},
        {"title": "我吞万物镇天骄", "strategy": "境界宣言", "score": 88, "reason": "能力+靶子一句看懂"},
        {"title": "就凭你也配退婚？", "strategy": "台词式", "score": 86, "reason": "冲突台词入题"},
        {"title": "废柴的我吞穿修仙界", "strategy": "反差装逼", "score": 85, "reason": "废柴反差"},
        {"title": "谁在吞我的杀招", "strategy": "悬念式", "score": 80, "reason": "对手视角悬念"},
        {"title": "杂役弟子竟是噬道传人", "strategy": "身份反转", "score": 83, "reason": "身份钩子"},
        {"title": "三息吞一城", "strategy": "数字式", "score": 78, "reason": "数字夸张"},
        {"title": "吞噬成瘾", "strategy": "金手指直给", "score": 70, "reason": "偏短缺场景"},
        {"title": "退婚夜我觉醒吞噬系统", "strategy": "金手指直给", "score": 90, "reason": "黄金三章浓缩"},
        {"title": "你的底牌是我的口粮", "strategy": "台词式", "score": 84, "reason": "标志性台词"},
        {"title": "吞天骄的一百种方法", "strategy": "数字式", "score": 75, "reason": "数字+靶子"},
        {"title": "我以吞噬证道", "strategy": "境界宣言", "score": 72, "reason": "稍文" },
    ],
    "chosen_title": "开局吞了退婚书",
    "blurb": "被退婚、被夺玉佩、被全宗门当废物——林凡的人生烂到家了。"
             "直到那晚，脑海里响起一声：叮——万物吞噬系统觉醒。"
             "灵草？吞。功法？吞。天骄的杀招？也是口粮。"
             "三个月后，李家跪在山门前求他退回那纸退婚书。",
}

_POWER_LADDER = {
    "name": "噬道修行体系",
    "levels": [
        {"rank": 1, "name": "炼气境", "desc": "感应灵气，九层圆满可筑基"},
        {"rank": 2, "name": "筑基境", "desc": "灵气化液，寿元二百载"},
        {"rank": 3, "name": "金丹境", "desc": "结丹成婴之基，一方豪强"},
        {"rank": 4, "name": "元婴境", "desc": "元婴出窍，宗门长老级"},
        {"rank": 5, "name": "化神境", "desc": "神识通天，一州霸主"},
        {"rank": 6, "name": "炼虚境", "desc": "虚空显化，传说级强者"},
        {"rank": 7, "name": "合体境", "desc": "法则加身，大陆巅峰"},
    ],
}

_FACTIONS = [
    {"name": "玄阳宗", "stance": "主角方", "role": "主角所在宗门，外门弟子受尽白眼",
     "power_tier": "金丹境掌门", "note": "前期看不起主角，后期被主角扬名带飞",
     "locations": ["外门演武场", "藏经阁", "杂役房灵田", "试炼塔", "刑堂大殿"]},
    {"name": "李家", "stance": "压迫方", "role": "天才李天骄家族，悔婚羞辱主角",
     "power_tier": "元婴境家主", "note": "贯穿前三卷的打脸对象土壤",
     "locations": ["李府正厅", "城南拍卖行", "李家祠堂密室"]},
    {"name": "万妖谷", "stance": "中立/资源", "role": "妖兽与天材地宝的来源地",
     "power_tier": "化神境妖王", "note": "主角吞噬升级的猎场",
     "locations": ["谷口集市", "黑雾妖林", "妖王祭坛"]},
    {"name": "噬天教", "stance": "神秘势力", "role": "上古吞噬一脉残党，与系统同源",
     "power_tier": "未知", "note": "中后期身世线，先埋钩子",
     "locations": ["废弃血池禁地", "噬天古殿"]},
]

_CHARACTERS = [
    {"name": PROTAGONIST, "role": "主角", "tier": "核心",
     "start_realm": "炼气一层", "vol1_target_realm": "筑基初期",
     "persona": "重生废柴，扮猪吃虎，腹黑隐忍但该装逼时绝不手软",
     "desire": "变强、打脸所有看不起他的人、查明系统来历",
     "wound": "被退婚当众羞辱、母亲遗物被夺", "golden_finger": "万物吞噬系统",
     "speech_kit": "口头禅『口粮罢了』；装逼时惜字如金，打脸后只补一句短的"},
    {"name": "李天骄", "role": "打脸对象/前期反派", "tier": "核心",
     "start_realm": "炼气九层", "persona": "天之骄子，傲慢，悔婚主角",
     "function": "前期主要打脸靶子，每次找茬都被反杀",
     "speech_kit": "开口必带『就凭你？』，败时改口结巴"},
    {"name": "苏挽柔", "role": "女主/师妹", "tier": "核心",
     "start_realm": "炼气七层", "persona": "唯一没看不起主角的人，外冷内热",
     "function": "感情线锚点 + 关键时刻救场",
     "speech_kit": "话少，关心人时先递东西再低声一句"},
    {"name": "周扒皮", "role": "工具人配角", "tier": "配角",
     "persona": "外门管事，势利眼，前期刁难主角后被打脸",
     "speech_kit": "满口『规矩就是规矩』，见势不妙立刻改称『林师弟』"},
    {"name": "玄阳真人", "role": "宗门掌门", "tier": "配角",
     "persona": "慧眼识珠，后期力排众议提拔主角"},
    {"name": "噬魂老人", "role": "神秘导师", "tier": "配角",
     "persona": "系统残魂化身，半遮半掩透露身世，先埋钩子"},
    {"name": "赵铁柱", "role": "工具人配角", "tier": "配角",
     "persona": "同寝杂役，嘴碎胆小，主角第一个小弟兼消息源"},
    {"name": "钱多宝", "role": "工具人配角", "tier": "配角",
     "persona": "城南拍卖行少东家，逐利精明，后期主角的钱袋盟友"},
    {"name": "孙长老", "role": "工具人配角", "tier": "配角",
     "persona": "执法堂长老，古板认死理，被李家利用又反水作证"},
    {"name": "王雪鸢", "role": "工具人配角", "tier": "配角",
     "persona": "内门天才师姐，毒舌看戏党，最早注意到主角不对劲"},
]

_STORYLINES = [
    {"name": "升级打脸主线", "type": "main",
     "summary": "林凡靠吞噬系统从炼气废柴一路逆袭，逐个打脸看不起他的人并扬名",
     "bound_characters": [PROTAGONIST, "李天骄"],
     "nodes": [{"planned_volume": 1, "node": "外门大比夺魁打脸李天骄"},
               {"planned_volume": 2, "node": "宗门大比越级胜金丹李铁山"},
               {"planned_volume": 4, "node": "至暗反击废李家家主"},
               {"planned_volume": 6, "node": "终战吞噬教主证道"}]},
    {"name": "退婚复仇线", "type": "revenge",
     "summary": "向李家与李天骄讨回当众羞辱之仇，夺回母亲遗物",
     "bound_characters": [PROTAGONIST, "李天骄"],
     "nodes": [{"planned_volume": 1, "node": "夺回玉佩半块立威"},
               {"planned_volume": 2, "node": "李家长老亲自下场"},
               {"planned_volume": 4, "node": "李家清算清盘，复仇兑现"}]},
    {"name": "挽柔感情线", "type": "romance",
     "summary": "与苏挽柔在患难中互相扶持，慢热升温",
     "bound_characters": [PROTAGONIST, "苏挽柔"],
     "nodes": [{"planned_volume": 1, "node": "雪夜递药结情"},
               {"planned_volume": 3, "node": "秘境舍命相护"},
               {"planned_volume": 5, "node": "夺舍危机互表心迹"}]},
    {"name": "系统身世线", "type": "mystery",
     "summary": "吞噬系统的来历、噬天教残党、上古吞噬一脉的秘密，长线慢埋",
     "bound_characters": [PROTAGONIST, "噬魂老人"],
     "nodes": [{"planned_volume": 1, "node": "噬魂老人首次现身留谜"},
               {"planned_volume": 3, "node": "噬灵诀被认出师承"},
               {"planned_volume": 5, "node": "右使夺舍揭祖师道果"},
               {"planned_volume": 6, "node": "身世真相大白"}]},
]


def _volumes(cfg: DabaiConfig) -> list[dict]:
    phases = ["opening", "rising", "rising", "turning", "dark_hour", "climax"]
    titles = ["新手村·退婚打脸", "外门崛起·吞噬扬名", "宗门大比·一鸣惊人",
              "万妖谷·猎宝结仇", "李家清算·至暗反击", "噬天惊变·身世揭晓"]
    max_rank = len(_POWER_LADDER["levels"])  # 7
    vols = []
    for i in range(cfg.volume_count):
        idx = min(i, len(titles) - 1)
        # 境界区间：跨卷单调、首尾相接、封顶 max_rank
        rs = min(i + 1, max_rank)
        re_ = min(i + 2, max_rank)
        boss = next((b["boss_name"] for b in _ANTAGONIST_LADDER
                     if b["volume_number"] == i + 1), "更强敌人")
        vols.append({
            "volume_number": i + 1,
            "title": f"第{i + 1}卷 {titles[idx]}",
            "phase": phases[min(i, len(phases) - 1)],
            "planned_chapters": cfg.volume_chapters,
            "boss": boss,
            "storyline_moves": [f"升级打脸主线:第{i + 1}卷节点推进"],
            "mystery_moves": [f"系统来历:第{i + 1}卷透出一块"] if i % 2 == 0 else [],
            "realm_start_rank": rs,
            "realm_end_rank": re_,
            "big_beats": [
                "当众打脸悔婚的李天骄，一战扬名",
                "吞噬稀有妖丹越级突破，震惊外门",
                "夺回母亲遗物，立威外门",
            ] if i == 0 else [
                f"第{i + 1}卷大爆点A：越级吞噬碾压强敌",
                f"第{i + 1}卷大爆点B：当众揭穿并打脸高位者",
            ],
            "volume_climax": "外门大比夺魁，当众吞掉李天骄的本命法宝，李家颜面扫地"
            if i == 0 else f"第{i + 1}卷卷末高潮：更强敌人登场，主角越级翻盘",
            "end_hook": "噬魂老人现身，留下一句『你的系统，来历不简单』便消失"
            if i == 0 else "更大的势力注意到主角，下一卷危机降临",
        })
    return vols


# ── 章纲：确定性爽点节拍器生成器（遵守 linter 全部规则）──────────────────────────
def _chapter_outlines(cfg: DabaiConfig) -> list[dict]:
    pool = cfg.shuang_pool
    witnesses_cycle = [
        ["李天骄", "周扒皮"], ["外门弟子众"], ["李家管事"], ["苏挽柔"],
        ["玄阳真人", "众长老"], ["万妖谷散修"], ["李天骄"], ["内门弟子众"],
    ]
    setups = [
        "被周扒皮克扣月例、当众讥讽是废物",
        "李天骄带人堵门挑衅，扬言要废了主角",
        "外门弟子起哄看主角笑话，赌他过不了试炼",
        "管事故意分配最差洞府与灵田，断主角资源",
        "对手亮出稀有法宝当众炫耀，碾压式羞辱",
        "李家放话三日内让主角滚出玄阳宗",
    ]
    chapters: list[dict] = []
    n = cfg.volume_chapters
    prev_type = ""
    prev_prev = ""
    for i in range(n):
        ch = i + 1
        is_golden = ch <= cfg.golden_chapters
        is_big = is_golden or (ch % cfg.big_beat_every == 0)
        # 选爽点类型：避免与前两章重复
        st = next((t for t in pool[(ch % len(pool)):] + pool
                   if t != prev_type and t != prev_prev), pool[ch % len(pool)])
        if ch == 1:
            st, is_big = "群嘲反转", False   # 第1章先蓄憋屈，给一个小反转钩子
        elif ch == 3:
            st, is_big = "打脸", True         # 黄金第3章大打脸
        setup = setups[i % len(setups)]
        wit = witnesses_cycle[i % len(witnesses_cycle)]
        payoff = _payoff_for(st, wit, ch)
        emotion_turn = (
            bind_ladder_emotion_turn_hint("万物吞噬系统")
            if ch <= 2 else
            "从隐忍咽气→对方一句更狠的羞辱戳中底线（触发）→眼神冷下、动了真火"
        )
        chapters.append({
            "chapter_number": ch,
            "title": _title_for(st, ch),
            "shuang_type": st,
            "yaqu_setup": setup,
            "emotion_turn": emotion_turn,
            "yinbao": f"林凡借吞噬系统{_yinbao_for(st)}，瞬间扭转局面",
            "shuang_payoff": payoff,
            "witnesses": wit,
            "end_hook": _hook_for(ch, n),
            "new_info_count": 1 if ch > cfg.golden_chapters else 2,
            "involved_characters": [PROTAGONIST] + wit,
            "is_big_beat": is_big,
            "expected_words": 2300 if is_big else 2000,
            # 第1卷境界区间[1,2]：前 2/3 在第1档，后段升到第2档（单调不减）
            "realm_rank": 1 if ch <= (n * 2) // 3 else 2,
        })
        prev_prev, prev_type = prev_type, st
    return chapters


def _title_for(st: str, ch: int) -> str:
    table = {
        "打脸": f"第{ch}章 当众打脸", "升级": f"第{ch}章 一夜越境",
        "获宝": f"第{ch}章 吞宝得机缘", "扮猪吃虎": f"第{ch}章 深藏不露",
        "装逼": f"第{ch}章 锋芒乍现", "群嘲反转": f"第{ch}章 笑到最后",
        "收小弟": f"第{ch}章 强者归心", "救场": f"第{ch}章 力挽狂澜",
        "扬名": f"第{ch}章 名动外门",
    }
    return table.get(st, f"第{ch}章 逆袭时刻")


def _yinbao_for(st: str) -> str:
    return {
        "打脸": "当众吞掉对方的杀招与依仗", "升级": "吞噬妖丹噬力暴涨、当场破境",
        "获宝": "一口吞下旁人抢不到的天材地宝", "扮猪吃虎": "故意示弱诱敌再一击反杀",
        "装逼": "随手露出碾压级手段", "群嘲反转": "把嘲讽原样奉还",
        "收小弟": "实力震慑令对手俯首", "救场": "危急关头吞噬强援之力",
        "扬名": "一战打出名号",
    }.get(st, "反手碾压")


def _payoff_for(st: str, wit: list[str], ch: int) -> str:
    who = "、".join(wit) or "围观众人"
    return f"林凡当着{who}的面{_yinbao_for(st)}，{who}从讥讽到惊骇失语，外门哗然"


def _hook_for(ch: int, n: int) -> str:
    if ch == 1:
        return "退婚书还在桌上，林凡脑海里却响起一声『叮——吞噬系统觉醒』"
    if ch >= n:
        return "外门大比落幕，噬魂老人现身丢下一句『你的系统来历不简单』便消失"
    return f"刚平一事，更强的敌人已盯上林凡——第{ch + 1}章危机扑面而来"


_STORY_ASSETS = {
    "plot_assets": [
        {"kind": "skill", "name": "噬灵诀", "plot_role": "成长线",
         "owner": PROTAGONIST, "debut": "later", "planned_volume": 1,
         "description": "随吞噬次数进化的功法，每卷解锁新形态，宗门长老暗中觊觎"},
        {"kind": "item", "name": "母亲的玉佩", "plot_role": "身世信物",
         "owner": PROTAGONIST, "debut": "start", "planned_volume": 1,
         "description": "被李家夺走一半，藏着主角身世与上界坐标"},
        {"kind": "item", "name": "玄阴火种", "plot_role": "争夺点",
         "owner": "", "debut": "later", "planned_volume": 2,
         "description": "秘境至宝，各宗争夺，主角吞噬后境界跃迁的关键"},
        {"kind": "skill", "name": "灭魂印", "plot_role": "底牌",
         "owner": "噬魂老人", "debut": "later", "planned_volume": 3,
         "description": "幕后反派杀器，与主角系统同源，揭示金手指来历"},
    ],
    "initial_relations": [
        {"from": PROTAGONIST, "to": "李天骄", "attitude": "敌对",
         "tension": "悔婚当众羞辱，且其家族夺走玉佩另一半"},
        {"from": PROTAGONIST, "to": "苏挽柔", "attitude": "暧昧",
         "tension": "唯一未落井下石之人，暗中递过疗伤药"},
        {"from": PROTAGONIST, "to": "周扒皮", "attitude": "轻视",
         "tension": "克扣主角杂役月例，狗眼看人低"},
        {"from": PROTAGONIST, "to": "玄阳真人", "attitude": "中立",
         "tension": "掌门看似公允，实则注意到主角功法异常"},
    ],
}


# ── 分发表 ──────────────────────────────────────────────────────────────────
def _beat_rows(cfg: DabaiConfig, bs: int, be: int) -> list[dict]:
    """节拍序列 mock：从整卷章纲推导每章一行节拍。"""
    rows = []
    for c in _chapter_outlines(cfg):
        if bs <= c["chapter_number"] <= be:
            rows.append({
                "chapter_number": c["chapter_number"], "title": c["title"],
                "shuang_type": c["shuang_type"],
                "location": ["外门演武场", "藏经阁", "城南拍卖行", "黑雾妖林",
                             "试炼塔", "杂役房灵田"][c["chapter_number"] % 6],
                "slap_target": (c["witnesses"] or ["李天骄"])[0],
                "realm_rank": c["realm_rank"], "is_big_beat": c["is_big_beat"],
                "one_line": c["yaqu_setup"][:20] + "→" + c["yinbao"][:18],
            })
    return rows


def get(step: str, cfg: DabaiConfig, meta: dict | None = None) -> Any:
    meta = meta or {}
    if step == "chapter_outlines":
        # 分批：按 meta 的 batch_start/batch_end 切片整卷 mock 章纲
        full = _chapter_outlines(cfg)
        bs = int(meta.get("batch_start", 1))
        be = int(meta.get("batch_end", len(full)))
        return [c for c in full if bs <= c["chapter_number"] <= be]
    if step == "beat_sequence":
        return _beat_rows(cfg, int(meta.get("batch_start", 1)),
                          int(meta.get("batch_end", cfg.volume_chapters)))
    if step == "volume_chapters":
        # 单次整卷：beat + 五拍两块同返
        bs = int(meta.get("batch_start", 1))
        be = int(meta.get("batch_end", cfg.volume_chapters))
        full = _chapter_outlines(cfg)
        return {
            "beat_sequence": _beat_rows(cfg, bs, be),
            "chapter_outlines": [c for c in full if bs <= c["chapter_number"] <= be],
        }
    if step == "chapter_repair":
        return []  # mock 章纲本就 lint 干净；空数组=保留原批
    table = {
        # 合并步：carrier 一次返回本组所有键
        "benchmark": lambda: {"benchmark": _BENCHMARK, "positioning": _POSITIONING},
        "golden_finger": lambda: {
            "golden_finger": _GOLDEN_FINGER, "power_ladder": _POWER_LADDER,
            "antagonist_ladder": _ANTAGONIST_LADDER[: cfg.volume_count],
        },
        "antagonist_ladder": lambda: _ANTAGONIST_LADDER[: cfg.volume_count],
        "factions": lambda: {"factions": _FACTIONS, "characters": _CHARACTERS},
        "storylines": lambda: {
            "storylines": _STORYLINES, "story_assets": _STORY_ASSETS,
            "mystery_schedule": _MYSTERY_SCHEDULE,
        },
        "story_assets": lambda: _STORY_ASSETS,
        "mystery_schedule": lambda: _MYSTERY_SCHEDULE,
        "title_blurb": lambda: _TITLE_BLURB,
        "volumes": lambda: _volumes(cfg),
    }
    if step not in table:
        raise KeyError(f"mock 无此步骤：{step}")
    return table[step]()
