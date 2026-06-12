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
    "signature_lines": ["叮——吞噬成功", "你以为的杀招，是我的口粮"],
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
     "power_tier": "金丹境掌门", "note": "前期看不起主角，后期被主角扬名带飞"},
    {"name": "李家", "stance": "压迫方", "role": "天才李天骄家族，悔婚羞辱主角",
     "power_tier": "元婴境家主", "note": "贯穿前三卷的打脸对象土壤"},
    {"name": "万妖谷", "stance": "中立/资源", "role": "妖兽与天材地宝的来源地",
     "power_tier": "化神境妖王", "note": "主角吞噬升级的猎场"},
    {"name": "噬天教", "stance": "神秘势力", "role": "上古吞噬一脉残党，与系统同源",
     "power_tier": "未知", "note": "中后期身世线，先埋钩子"},
]

_CHARACTERS = [
    {"name": PROTAGONIST, "role": "主角", "tier": "核心",
     "start_realm": "炼气一层", "vol1_target_realm": "筑基初期",
     "persona": "重生废柴，扮猪吃虎，腹黑隐忍但该装逼时绝不手软",
     "desire": "变强、打脸所有看不起他的人、查明系统来历",
     "wound": "被退婚当众羞辱、母亲遗物被夺", "golden_finger": "万物吞噬系统"},
    {"name": "李天骄", "role": "打脸对象/前期反派", "tier": "核心",
     "start_realm": "炼气九层", "persona": "天之骄子，傲慢，悔婚主角",
     "function": "前期主要打脸靶子，每次找茬都被反杀"},
    {"name": "苏挽柔", "role": "女主/师妹", "tier": "核心",
     "start_realm": "炼气七层", "persona": "唯一没看不起主角的人，外冷内热",
     "function": "感情线锚点 + 关键时刻救场"},
    {"name": "周扒皮", "role": "工具人配角", "tier": "配角",
     "persona": "外门管事，势利眼，前期刁难主角后被打脸"},
    {"name": "玄阳真人", "role": "宗门掌门", "tier": "配角",
     "persona": "慧眼识珠，后期力排众议提拔主角"},
    {"name": "噬魂老人", "role": "神秘导师", "tier": "配角",
     "persona": "系统残魂化身，半遮半掩透露身世，先埋钩子"},
]

_STORYLINES = [
    {"name": "升级打脸主线", "type": "main",
     "summary": "林凡靠吞噬系统从炼气废柴一路逆袭，逐个打脸看不起他的人并扬名"},
    {"name": "退婚复仇线", "type": "revenge",
     "summary": "向李家与李天骄讨回当众羞辱之仇，夺回母亲遗物"},
    {"name": "挽柔感情线", "type": "romance",
     "summary": "与苏挽柔在患难中互相扶持，慢热升温"},
    {"name": "系统身世线", "type": "mystery",
     "summary": "吞噬系统的来历、噬天教残党、上古吞噬一脉的秘密，长线慢埋"},
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
        vols.append({
            "volume_number": i + 1,
            "title": f"第{i + 1}卷 {titles[idx]}",
            "phase": phases[min(i, len(phases) - 1)],
            "planned_chapters": cfg.volume_chapters,
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
def get(step: str, cfg: DabaiConfig, meta: dict | None = None) -> Any:
    meta = meta or {}
    if step == "chapter_outlines":
        # 分批：按 meta 的 batch_start/batch_end 切片整卷 mock 章纲
        full = _chapter_outlines(cfg)
        bs = int(meta.get("batch_start", 1))
        be = int(meta.get("batch_end", len(full)))
        return [c for c in full if bs <= c["chapter_number"] <= be]
    table = {
        # 合并步：carrier 一次返回本组两块
        "benchmark": lambda: {"benchmark": _BENCHMARK, "positioning": _POSITIONING},
        "golden_finger": lambda: {"golden_finger": _GOLDEN_FINGER, "power_ladder": _POWER_LADDER},
        "factions": lambda: {"factions": _FACTIONS, "characters": _CHARACTERS},
        "storylines": lambda: _STORYLINES,
        "story_assets": lambda: _STORY_ASSETS,
        "volumes": lambda: _volumes(cfg),
    }
    if step not in table:
        raise KeyError(f"mock 无此步骤：{step}")
    return table[step]()
