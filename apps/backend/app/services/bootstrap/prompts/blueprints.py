"""世界设定卡蓝图常量与配套 prompt 片段。

`GEMINI_SETTING_BLUEPRINTS` 是 24 张固定标题的世界圣经卡片，用于 single-shot 与
sequential 两种 Bootstrap 路径强制生成数量与覆盖面，避免 LLM 漏卡。

数量目标常量（`CHARACTER_TARGET` / `FACTION_*` / `SKILL_*` / `ITEM_*`）参与多 step
prompt 的硬性数量规则，集中在此便于一处调参。
"""

from __future__ import annotations

import json


GEMINI_SETTING_BLUEPRINTS: list[dict] = [
    {"title": "作品立意", "category": "世界背景", "tags": ["立意", "主题"], "importance": "core", "stage": "full", "section": "core", "purpose": "锁定作品承诺、核心矛盾、读者钩子和禁忌边界。"},
    {"title": "世界底层规则", "category": "规则法则", "tags": ["规则", "法则"], "importance": "core", "stage": "full", "section": "focus", "purpose": "定义所有角色必须遵守的硬规则、代价和例外。"},
    {"title": "时代格局与阶层结构", "category": "世界背景", "tags": ["时代", "阶层"], "importance": "core", "stage": "full", "section": "focus", "purpose": "说明世界为什么不公平，主角从哪里被压迫。"},
    {"title": "主角起点生存环境", "category": "世界背景", "tags": ["起点", "生存"], "importance": "core", "stage": "early", "section": "focus", "purpose": "提供开篇十章可直接使用的生活压力、羞辱和资源限制。"},
    {"title": "大陆地图与地缘格局", "category": "地理场景", "tags": ["地图", "地理"], "importance": "core", "stage": "full", "section": "focus", "purpose": "给出大地图、路线方向、资源分布和势力边界。"},
    {"title": "开篇城镇与日常空间", "category": "地理场景", "tags": ["城镇", "开篇"], "importance": "major", "stage": "early", "section": "focus", "purpose": "沉淀主角开局活动区、街巷、家族/宗门/市集场景。"},
    {"title": "核心宗门或学院地貌", "category": "地理场景", "tags": ["宗门", "学院"], "importance": "major", "stage": "early", "section": "focus", "purpose": "给修炼、考核、冲突和师承关系提供稳定舞台。"},
    {"title": "禁地与高危秘境", "category": "地理场景", "tags": ["禁地", "秘境"], "importance": "major", "stage": "mid", "section": "focus", "purpose": "准备升级副本、伏笔揭示和关键资源争夺。"},
    {"title": "交通路径与边境关卡", "category": "地理场景", "tags": ["交通", "边境"], "importance": "major", "stage": "full", "section": "focus", "purpose": "约束角色移动速度、追杀路线和跨区域代价。"},
    {"title": "远古战争与失落真相", "category": "历史传说", "tags": ["远古", "战争"], "importance": "core", "stage": "full", "section": "focus", "purpose": "埋下全书级谜团、反派根源和世界现状成因。"},
    {"title": "被篡改的官方历史", "category": "历史传说", "tags": ["历史", "谎言"], "importance": "major", "stage": "mid", "section": "focus", "purpose": "制造信息差，让读者持续追问真相。"},
    {"title": "民间传说与危险谣言", "category": "历史传说", "tags": ["传说", "谣言"], "importance": "flavor", "stage": "early", "section": "focus", "purpose": "给路人谈资、地方恐惧和小伏笔提供素材。"},
    {"title": "禁忌人物或失踪先贤", "category": "历史传说", "tags": ["先贤", "禁忌"], "importance": "major", "stage": "full", "section": "focus", "purpose": "连接主角传承、反派阴影和后期真相。"},
    {"title": "宗门礼法与等级称谓", "category": "文化风俗", "tags": ["礼法", "称谓"], "importance": "major", "stage": "early", "section": "focus", "purpose": "让对话、羞辱、拜师和处罚有具体制度感。"},
    {"title": "民俗节庆与公共仪式", "category": "文化风俗", "tags": ["节庆", "仪式"], "importance": "flavor", "stage": "full", "section": "focus", "purpose": "提供大型场景、社交冲突和视觉记忆点。"},
    {"title": "交易习惯与黑市规矩", "category": "文化风俗", "tags": ["交易", "黑市"], "importance": "major", "stage": "full", "section": "focus", "purpose": "支撑拍卖、情报、赃物、资源兑换和风险。"},
    {"title": "婚盟血誓与家族规训", "category": "文化风俗", "tags": ["家族", "誓约"], "importance": "major", "stage": "mid", "section": "focus", "purpose": "制造人物选择、亲情束缚和势力联姻矛盾。"},
    {"title": "资源经济与稀缺机制", "category": "规则法则", "tags": ["资源", "经济"], "importance": "core", "stage": "full", "section": "focus", "purpose": "解释修炼资源如何流通、垄断和剥削。"},
    {"title": "誓约契约与违约反噬", "category": "规则法则", "tags": ["誓约", "契约"], "importance": "major", "stage": "full", "section": "focus", "purpose": "给承诺、背叛、交易和审判提供硬约束。"},
    {"title": "突破副作用与失败代价", "category": "规则法则", "tags": ["突破", "代价"], "importance": "core", "stage": "full", "section": "focus", "purpose": "防止升级廉价化，让每次变强有代价。"},
    {"title": "信息禁区与知识垄断", "category": "规则法则", "tags": ["禁区", "知识"], "importance": "major", "stage": "mid", "section": "focus", "purpose": "解释秘密为何难以公开，制造调查阻力。"},
    {"title": "妖兽生态与危险等级", "category": "其他", "tags": ["妖兽", "生态"], "importance": "major", "stage": "full", "section": "focus", "purpose": "提供野外战斗、材料来源和环境压迫。"},
    {"title": "职业体系与底层营生", "category": "其他", "tags": ["职业", "民生"], "importance": "flavor", "stage": "full", "section": "focus", "purpose": "让世界不只围着修炼者转，补足普通人的生活。"},
    {"title": "终局神话与世界边界", "category": "其他", "tags": ["终局", "边界"], "importance": "core", "stage": "late", "section": "focus", "purpose": "预埋后期地图扩展、终极敌人和结局余味。"},
]


SETTING_CARD_SCHEMA_BRIEF = """单卡 JSON 须含：title, content（每张≥180字、可落地名词/规则/代价/冲突）, tags, extra。
extra 须含 category、importance、stage（与蓝图字段一致）。
蓝图 section 为 core：extra.core 必填 core_concept, genre_position, protagonist_drive, core_conflict, reader_hook, emotional_tone, boundaries, ending_direction（各一句短句）。
蓝图 section 为 focus：extra.focus 必填 summary, story_function, conflict_seed, cost_or_risk, affected_people, exception_or_loophole, visual_anchor（各一句）。
每张 extra 还须 reveal_timing（何时以何情节揭示）、who_knows_now（须从上方已列人物名与势力名择真实名书写，禁用「主角」「反派」等泛称）。
【JSON 可解析性】字符串内禁止未转义的英文双引号 " ，对白用「」或省略引号。"""


CHARACTER_TARGET = 8
FACTION_MIN_TARGET = 4
FACTION_MAX_TARGET = 6
SKILL_MIN_TARGET = 5
SKILL_MAX_TARGET = 8
ITEM_MIN_TARGET = 5
ITEM_MAX_TARGET = 8


def setting_blueprints_for_prompt() -> str:
    """以缩进 JSON 形式输出蓝图，用于 prompt 注入。"""
    return json.dumps(GEMINI_SETTING_BLUEPRINTS, ensure_ascii=False, indent=2)


def setting_extra_with_defaults(item: dict) -> dict:
    """为单张设定卡的 extra 字段补齐 schema_version / category / 揭示节奏占位。"""
    extra = item.get("extra", {})
    if not isinstance(extra, dict):
        extra = {}
    matching = next(
        (bp for bp in GEMINI_SETTING_BLUEPRINTS if bp["title"] == item.get("title")),
        None,
    )
    if matching:
        extra = {
            "schema_version": 2,
            **extra,
            "category": matching["category"],
            "importance": matching["importance"],
            "stage": matching["stage"],
        }
    else:
        extra = {"schema_version": 2, **extra}
    # 揭示节奏字段（v3，若 AI 生成时填写则保留，否则给空字符串占位）
    extra.setdefault("reveal_timing", "")      # 本设定何时/以何种情节方式向读者/主角揭示
    extra.setdefault("who_knows_now", "")      # 故事开篇时哪些角色/势力知道这一设定
    return extra
