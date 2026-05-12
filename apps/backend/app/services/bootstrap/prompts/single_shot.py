"""方案 B 单次全量 prompt（Bootstrap single_shot 模式）。

一次性要求 LLM 输出顶层 11 个数组（project / power_systems / factions / storylines /
skills / items / characters / settings / outline / memory / relations）。

设计动机：远程 Gemini 等大上下文模型一次给完最一致；但模型不一定遵守，因此 prompt 内
显式列出每个数组字段、硬性数量规则与 settings 蓝图。失败由 `_complete_*` 路径补齐。
"""

from __future__ import annotations

from .blueprints import (
    GEMINI_SETTING_BLUEPRINTS,
    CHARACTER_TARGET,
    FACTION_MIN_TARGET,
    FACTION_MAX_TARGET,
    SKILL_MIN_TARGET,
    SKILL_MAX_TARGET,
    ITEM_MIN_TARGET,
    ITEM_MAX_TARGET,
    setting_blueprints_for_prompt,
)
from .word_budget import book_length_constraints_for_prompt


def single_shot_prompt(logline: str, premise: str = "", target_words: int = 1_200_000) -> str:
    """构造 single_shot 模式的 prompt 字符串。"""
    from app.services.outline_planning import words_to_plan
    plan = words_to_plan(target_words)
    n_volumes = plan["total_volumes"]
    total_chapters_hint = plan["total_chapters"]
    setting_blueprints = setting_blueprints_for_prompt()
    return f"""根据以下创意，生成完整的小说初始化数据：

创意：{logline}
立意与类型（作品基本面）：{premise[:2000] or '（未填写，请根据创意自动提炼作品定位、主题命题、核心矛盾与禁忌边界）'}
【全书字数目标】{target_words:,}字，折合约{total_chapters_hint}章
{book_length_constraints_for_prompt(target_words)}

返回一个 JSON 对象，顶层字段固定为：
project, power_systems, factions, storylines, skills, items, characters, settings, outline, memory, relations。

下面是字段结构说明，不代表数组数量；数组数量必须遵守后面的硬性数量规则。

project 字段结构：
{{
  "title": "小说名称",
  "genre": "玄幻",
  "logline": "{logline}",
  "premise": "立意与类型（含作品定位、主题命题、核心矛盾、禁忌边界，可落地，至少200字）；其中「类型与篇幅」必须严格服从上方【全书字数目标（硬性约束）】",
  "world_overview": "世界观简述（300~500字）",
  "story_core": {{"drive": "故事驱动力", "conflict": "核心矛盾", "theme": "主题", "differentiation": "差异化"}}
}}

power_systems 每个元素字段：
name, system_type, description, cultivation_method, breakthrough_condition, special_rules,
protagonist_start_rank, protagonist_end_rank, levels。
protagonist_start_rank 与 protagonist_end_rank 必须是整数（与 levels 中某一层的 rank 一致），禁止写境界中文名。
levels 至少 6 个层级，每层包含 rank, name, description, requirements, abilities, sub_level_count。

factions 每个元素字段：
name, faction_type, alignment, active_period, description, territory, strength_level,
member_count, top_power, goals, resources, history, secrets, rivals, allies, attitude_to_protagonist。

storylines 每个元素字段：
name, line_type, description, core_conflict, resolution_direction, status, start_chapter。

skills 每个元素字段：
name, skill_type, grade, source, level_required, prerequisites, description, effects, limitations, mastered_by。

items 每个元素字段：
name, item_type, rarity, description, origin, effects, limitations, story_significance, current_owner, status。

characters 每个元素字段：
name, role, character_tier, gender, age, faction, personality, background, motivation, arc, current_realm,
speech_style, values, fear, secrets, strengths, weaknesses, special_traits。
role 只能是: protagonist / supporting / antagonist
character_tier 代表该人物在全书中的叙事层级，只能是以下4个值之一：
core=核心长线（贯穿全书，驱动主线，如主角/主反派/固定伙伴）；
arc=弧线支柱（某卷/某段主导剧情，随弧线结束淡出）；
plot=剧情推手（短期推进特定情节后退场）；
background=背景填充（丰富世界氛围，无强情节绑定）。
请根据每个人物实际定位严格判断，不要全部填 core。

settings 每个元素字段：
title, content, tags, extra。
"作品立意" 必须填写 extra.core 全字段；其他设定卡必须填写 extra.focus 全字段。
所有 settings 都必须写入 extra.schema_version=2、extra.category、extra.importance、extra.stage。

outline 每个元素字段：
title, sort_order, summary, hook, conflict, planned_chapters。planned_chapters 只能是 30 或 60。

memory 每个元素字段：
memory_type, title, content, tags。

relations 每个元素字段：
from_name, to_name, relation_type, description, intensity。

硬性数量规则：
- factions 必须生成 {FACTION_MIN_TARGET}~{FACTION_MAX_TARGET} 个，涵盖主角阵营、反派阵营、中立阵营；active_period 只能是 early/mid/late/full。
- storylines 必须生成 3~5 条，必须有且只有 1 条 main。
- skills 必须生成 {SKILL_MIN_TARGET}~{SKILL_MAX_TARGET} 个关键技能。
- items 必须生成 {ITEM_MIN_TARGET}~{ITEM_MAX_TARGET} 个关键道具。
- characters 必须生成 {CHARACTER_TARGET} 个：1 主角、3 核心配角、2 反派、2 师长/势力角色。
- settings 必须生成 {len(GEMINI_SETTING_BLUEPRINTS)} 张，严格按以下【世界设定蓝图】顺序生成，不要少卡，不要合并卡。
- outline 必须恰好生成 {n_volumes} 卷（由目标字数推算，不得增减），所有卷 planned_chapters 之和须尽量接近{total_chapters_hint}章。
- memory 必须生成 10 条初始记忆库种子。

世界设定蓝图：
{setting_blueprints}

settings 规则：
1) 每张卡 title/category/tags/importance/stage 必须与蓝图一致，写入 extra。
2) 每张卡 content 至少180字，要有可写进正文的名词、地点、制度、代价、例外或冲突。
3) WorldSetting 只写没有专属表承载的叙事世界圣经；不要把势力档案、功法、道具整段重复进 settings。

只返回 JSON，不要解释，不要 markdown fence。"""
