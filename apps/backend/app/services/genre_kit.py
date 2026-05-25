"""
Genre Kit 系统 — 网文流派分流核心

每个流派定义独立的「编辑手册」：
- opening_beats: 开局 5 个必备节拍（顺序敏感）
- satisfaction_tropes: 核心爽点类型（密度控制）
- side_character_quota: 配角配额（主/核/反/师）
- chapter_hook_spectrum: 章末钩子谱（避免重复）
- dialogue_tone: 对白基调 + 心理描写比例
- forbidden_examples: 反例约束（这个流派最容易踩的雷）
- pacing_guide: 节奏指南
- reader_expectation: 读者期待管理要点

使用方式：
from app.services.genre_kit import get_genre_kit, render_kit_for_prompt
kit = get_genre_kit(project.genre or "玄幻")
prompt_injection = render_kit_for_prompt(kit)
"""

from __future__ import annotations

from typing import Any

GENRE_KITS: dict[str, dict[str, Any]] = {
    "玄幻": {
        "opening_beats": [
            "金手指觉醒/系统绑定/血脉觉醒（第1-2章必须完成）",
            "第一次打脸/踩人/立威（第2-3章）",
            "势力/宗门初探 + 低配角出场（第3-5章）",
            "第一次升级/突破/战斗（第4-6章）",
            "主线冲突埋设 + 章末强钩子（第6-8章）",
        ],
        "satisfaction_tropes": ["打脸", "升级", "装逼", "反转", "团宠", "收徒"],
        "side_character_quota": {"protagonist": 1, "core_allies": 3, "antagonists": 2, "mentors": 2},
        "chapter_hook_spectrum": ["反转", "信息差揭秘", "角色危机", "新金手指碎片", "敌人现身"],
        "dialogue_tone": "热血直白，少长篇心理，战斗中多短句，胜利后多嘲讽/立flag",
        "forbidden_examples": [
            "失忆开局（除非是核心设定，否则第1章就失忆属于大忌）",
            "一上来就无敌（金手指必须有代价或成长曲线）",
            "配角工具人化（每个出场角色至少有1个独立动机）",
            "跳步升级（必须有合理的资源/战斗/顿悟支撑）",
        ],
        "pacing_guide": "每3章一小爽点，每8-10章一中高潮，每卷一大反转。开局前3章必须让读者看到主角的'与众不同'。",
        "reader_expectation": "读者最想看到：主角如何从底层逆袭、打脸爽、升级细节、金手指新用法。避免：一上来就世界大战、配角无脑跪舔。",
        "power_architecture_defaults": {
            "multi_axis": True,
            "required_axes": ["primary", "path", "artifact", "sect"],
            "optional_axes": [],
            "primary_min_levels": 7,
            "paths_pool": ["combat", "beast", "array", "pill", "body"],
            "paths_pick": 2,
            "artifact_tier_names": ["凡器", "玄器", "地器", "天器", "圣器", "帝器", "神器"],
            "sect_rank_names": ["外门弟子", "内门弟子", "核心弟子", "执事", "长老", "副宗主", "宗主"],
            "breakthrough_trials_pool": ["resource", "insight", "battle", "bloodline"],
        },
    },
    "仙侠": {
        "opening_beats": [
            "修仙资格/灵根/血脉觉醒（第1章）",
            "宗门/仙门初入 + 低配角冲突（第2-4章）",
            "第一次筑基/炼气突破 + 法宝/功法获得（第3-5章）",
            "红尘/心魔/道心考验埋点（第4-6章）",
            "主线仙门/魔道冲突钩子（第6-8章）",
        ],
        "satisfaction_tropes": ["渡劫", "飞升", "法宝炼制", "道侣", "心魔炼心", "仙门大比"],
        "side_character_quota": {"protagonist": 1, "core_allies": 3, "antagonists": 2, "mentors": 2, "dao_companions": 1},
        "chapter_hook_spectrum": ["渡劫危机", "心魔诱惑", "法宝异变", "仙缘现世", "仇敌追杀"],
        "dialogue_tone": "古风雅致，少现代口语，多诗词/典故引用，内心独白偏道心/因果",
        "forbidden_examples": [
            "现代词汇入侵（手机、汽车、CEO等）",
            "一上来就飞升（必须有漫长的筑基/金丹/元婴过程）",
            "道侣工具化（感情线必须有独立弧光）",
            "跳过心魔劫（道心不稳必须被反复锤炼）",
        ],
        "pacing_guide": "节奏偏中慢，每卷一个大境界突破，每10章一次心魔/因果收束。开局前5章必须建立'仙凡之别'的压迫感。",
        "reader_expectation": "读者最想看到：境界突破细节、法宝/功法新奇用法、红尘炼心、仙门权谋。避免：纯打斗无思考、感情线突兀。",
        "power_architecture_defaults": {
            "multi_axis": True,
            "required_axes": ["primary", "path", "artifact", "sect"],
            "optional_axes": ["dao_heart"],
            "primary_min_levels": 7,
            "paths_pool": ["sword", "pill", "body", "talisman", "array", "demon"],
            "paths_pick": 2,
            "artifact_tier_names": ["凡品", "灵器", "宝器", "灵宝", "古宝", "道器", "仙器"],
            "sect_rank_names": ["外门弟子", "内门弟子", "真传弟子", "执事", "长老", "副掌门", "掌门", "老祖"],
            "breakthrough_trials_pool": ["resource", "insight", "tribulation", "heart_demon"],
        },
    },
    "都市": {
        "opening_beats": [
            "身份反差/隐藏身份暴露（第1章）",
            "第一次装逼/打脸/利益冲突（第2-3章）",
            "商业/职场/家族初探 + 配角登场（第3-5章）",
            "第一次资源/人脉/技能展现（第4-6章）",
            "主线阴谋/对手现身 + 章末钩子（第6-8章）",
        ],
        "satisfaction_tropes": ["打脸", "装逼", "逆袭", "团宠", "商业战争", "隐形富豪"],
        "side_character_quota": {"protagonist": 1, "core_allies": 3, "antagonists": 2, "mentors": 1, "love_interest": 1},
        "chapter_hook_spectrum": ["身份揭秘", "商业反转", "情敌/对手危机", "新资源到手", "家族秘密"],
        "dialogue_tone": "现代口语，带点幽默/嘲讽，心理描写偏利益计算和人性观察",
        "forbidden_examples": [
            "一上来就无敌富豪（必须有从底层爬起的过程）",
            "配角无脑跪舔（每个角色都有自己的利益算计）",
            "跳步成功（商业/职场必须有合理的谈判/布局）",
            "纯恋爱无事业（都市必须事业+感情双线）",
        ],
        "pacing_guide": "每2-3章一小打脸，每7章一中高潮，每卷一商业大战。开局前3章必须让读者看到主角的'隐藏能力'。",
        "reader_expectation": "读者最想看到：主角如何低调装逼、商业布局、打脸爽、感情线推进。避免：一上来就世界级阴谋、配角智商为0。",
    },
    "悬疑": {
        "opening_beats": [
            "反常事件/命案/失踪（第1章）",
            "嫌疑人/线索初铺 + 信息差建立（第2-3章）",
            "第一次推理/盘问/现场勘查（第3-5章）",
            "新受害者/新线索 + 嫌疑人反杀（第4-6章）",
            "主线大阴谋钩子 + 章末强反转（第6-8章）",
        ],
        "satisfaction_tropes": ["反转", "信息差", "嫌疑人互咬", "隐藏身份", "时限压力"],
        "side_character_quota": {"protagonist": 1, "core_allies": 2, "suspects": 4, "victims": 2, "mentor_detective": 1},
        "chapter_hook_spectrum": ["新尸体出现", "嫌疑人死亡", "关键证据反转", "凶手视角切换", "倒计时逼近"],
        "dialogue_tone": "克制、留白，多问句少陈述，心理描写偏信息筛选和逻辑推演",
        "forbidden_examples": [
            "一上来就凶手自白（必须保持信息差到中后期）",
            "配角无脑作死（每个嫌疑人都要有合理动机和反侦察能力）",
            "跳步推理（必须有证据链支撑，不能靠'直觉'）",
            "纯惊悚无逻辑（悬疑必须有可验证的真相）",
        ],
        "pacing_guide": "每章必须有新信息或新反转，节奏偏快但留白。开局前3章必须让读者产生'到底谁是凶手'的强烈好奇。",
        "reader_expectation": "读者最想看到：层层反转、证据链闭环、凶手视角的惊悚、主角的逻辑碾压。避免：跳步推理、凶手太早暴露。",
    },
    "言情": {
        "opening_beats": [
            "怦然心动/初遇/误会（第1章）",
            "第一次靠近/身体接触/暧昧（第2-3章）",
            "误会加深/情敌/障碍出现（第3-5章）",
            "第一次表白/吻/冲突高潮（第4-6章）",
            "感情线主线钩子 + 章末甜/虐钩子（第6-8章）",
        ],
        "satisfaction_tropes": ["误会", "追妻火葬场", "甜宠", "虐后反转", "三角恋", "身份反差"],
        "side_character_quota": {"protagonist": 1, "love_interest": 1, "rivals": 2, "best_friends": 2, "family_obstacles": 2},
        "chapter_hook_spectrum": ["误会加深", "情敌挑衅", "甜蜜时刻", "身份揭秘", "分离危机"],
        "dialogue_tone": "细腻、情绪化，多内心独白，少直白表白，多'他/她怎么了'的观察",
        "forbidden_examples": [
            "一上来就强吻/强上（必须有铺垫和双方意愿）",
            "女主工具化（女主必须有独立事业/性格弧光）",
            "三角恋无脑（每个角色的感情都要有合理动机）",
            "跳步感情（必须有误会-和解-新误会的节奏）",
        ],
        "pacing_guide": "每3章一小暧昧/甜点，每8章一感情高潮/误会。开局前3章必须让读者看到'他们之间有火花'。",
        "reader_expectation": "读者最想看到：男主追妻、女主傲娇、甜宠细节、身份反差甜。避免：一上来就HE、女主无脑恋爱脑。",
    },
}

CANONICAL_GENRES = list(GENRE_KITS.keys())

def normalize_genre(raw: str | None) -> str:
    """把用户输入的 genre 归一化到标准流派名"""
    if not raw:
        return "玄幻"
    g = raw.strip().lower()
    mapping = {
        "xuanhuan": "玄幻", "xuan huan": "玄幻", "fantasy": "玄幻",
        "xianxia": "仙侠", "xian xia": "仙侠", "immortal": "仙侠",
        "urban": "都市", "modern": "都市", "city": "都市",
        "mystery": "悬疑", "detective": "悬疑", "thriller": "悬疑",
        "romance": "言情", "love": "言情", "qing": "言情",
        "scifi": "科幻", "sci-fi": "科幻", "science": "科幻",
        "wuxia": "武侠", "martial": "武侠",
    }
    for k, v in mapping.items():
        if k in g:
            return v
    # 如果已经是中国标准名
    for cg in CANONICAL_GENRES:
        if cg in raw:
            return cg
    return "玄幻"  # 默认兜底

def get_genre_kit(genre: str | None) -> dict[str, Any]:
    """返回对应流派的完整 kit，若不存在则返回玄幻兜底"""
    normalized = normalize_genre(genre)
    return GENRE_KITS.get(normalized, GENRE_KITS["玄幻"]).copy()

def render_kit_for_prompt(kit: dict[str, Any]) -> str:
    """把 kit 渲染成可直接注入 prompt 的结构化文本"""
    lines = []
    lines.append("【流派编辑手册（必须严格遵守）】")
    lines.append(f"开局必备节拍（前8章必须覆盖）：\n- " + "\n- ".join(kit.get("opening_beats", [])))
    lines.append(f"核心爽点类型（每章至少命中1-2个）：{', '.join(kit.get('satisfaction_tropes', []))}")
    lines.append(f"配角配额（本章在场角色不得超过）：{kit.get('side_character_quota', {})}")
    lines.append(f"章末钩子谱（优先从以下类型选择，避免重复）：{', '.join(kit.get('chapter_hook_spectrum', []))}")
    lines.append(f"对白与心理基调：{kit.get('dialogue_tone', '')}")
    lines.append("禁忌反例（本流派严禁出现）：\n- " + "\n- ".join(kit.get("forbidden_examples", [])))
    lines.append(f"节奏指南：{kit.get('pacing_guide', '')}")
    lines.append(f"读者期待管理：{kit.get('reader_expectation', '')}")
    return "\n".join(lines)

def get_genre_guardrail(genre: str | None) -> str:
    """返回流派专属的 guardrail 文本（可直接追加到 system prompt）"""
    kit = get_genre_kit(genre)
    return render_kit_for_prompt(kit)
