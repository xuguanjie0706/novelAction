"""合并 prompt：势力体系 + 卷级对立面 roster 一次生成。

设计动机
--------
原 Step 3（factions）与 Step 4.5（antagonist_ladder）是两次独立 LLM 调用，卷级 Boss
与势力分两次生成，Boss 与势力的归属只能靠"事后引用势力摘要"软绑定，易漂移。本 prompt
让势力与每卷 Boss **在同一次调用、同一份 JSON 内共同生成**，强制每个 Boss 的 faction
取自同一响应里刚生成的势力——从结构上消除"Boss 挂靠不存在的势力"这类设定冲突，
同时省一次 LLM 调用。

红线：本文件 ≤ 600 行；本 prompt 字面量较长，已独立成模块（符合 prompt 抽离规范）。
"""

from __future__ import annotations

from typing import Any

from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.power_registry import format_power_context_block
from app.services.bootstrap.prompts.character_naming import (
    character_naming_constraints_for_prompt,
)
from app.services.bootstrap.protagonist_progression import (
    build_protagonist_progression_prompt_block,
)


def build_factions_antagonist_prompt(ctx: dict, n_volumes: int) -> tuple[str, str]:
    """构建「势力 + 卷级对立面」合并生成的 system + user prompt。"""
    kit_block = get_genre_kit_block(ctx)
    power_block = format_power_context_block(ctx)
    progression_block = build_protagonist_progression_prompt_block(ctx, n_volumes)

    story_core = ctx.get("story_core") or {}
    naming_block = character_naming_constraints_for_prompt(
        ctx.get("genre"),
        project_title=ctx.get("project_title"),
        theme=story_core.get("theme"),
        logline=ctx.get("logline"),
        require_name_meaning=True,
    )

    system = (
        "你是网络小说世界构建与结构策划专家，一次性产出势力体系与卷级对立面阶梯。"
        "你深知：卷级 Boss 必须归属于真实存在的势力，二者同时设计才不会脱节。"
        "只返回一个 JSON 对象，不要任何说明文字。"
    )

    prompt = f"""{kit_block}小说：《{ctx.get('project_title')}》（{ctx.get('genre')}）
创意：{ctx.get('logline')}
立意：{(ctx.get('premise') or '')[:500]}
世界观：{(ctx.get('world_overview') or '')[:300]}
{power_block}
{progression_block}

{naming_block}

任务：一次生成两部分，并让二者严格咬合——
A. 主要势力/组织 4~6 个（涵盖主角阵营、核心反派、中立各至少 1 个）；
B. 全书 **{n_volumes} 卷** 各 1 名「当卷核心对立角色」（卷级大 Boss），
   每个 Boss 的 faction **必须**取自 A 中刚生成的某个势力名。

返回 JSON 对象（恰好两个键）：
{{
  "factions": [
    {{
      "name": "势力名称",
      "faction_type": "sect/kingdom/family/guild/evil/race/other 之一",
      "alignment": "protagonist/neutral/antagonist/unknown 之一",
      "active_period": "early/mid/late/full 之一",
      "description": "势力特色与定位（60字内）",
      "territory": "领地/活动范围",
      "strength_level": "实力级别（如：顶级宗门，坐镇一名斗宗）",
      "member_count": "成员规模",
      "top_power": "最强战力描述",
      "goals": "势力目标与图谋",
      "resources": "核心资源/特产",
      "history": "历史背景（30字）",
      "secrets": "不为人知的秘密/隐藏阴谋（供作者参考）",
      "rivals": ["竞争势力名"],
      "allies": ["盟友势力名"],
      "attitude_to_protagonist": "friendly/hostile/neutral/subordinate/superior 之一",
      "internal_factions": "内部派系博弈（至少2派，各有代表人物与目标差异，50字内；各阵营都要填）",
      "villain_timeline": "【仅 antagonist 阵营填，其余空串】主角不干预时此势力第几卷完成什么阴谋？被打断后的应对？（70字内，具体到卷号）"
    }}
  ],
  "antagonist_ladder": [
    {{
      "vol_index": 0,
      "boss_name": "姓名（2~4字，全书唯一；须有寓意，禁止灵儿/婉儿式随意名）",
      "name_meaning": "姓名寓意与卷级冲突暗线（15~40字）",
      "faction": "所属势力（**必须**等于上方 factions 里某个 name）",
      "realm_at_debut": "本卷初 Boss 有效境界（可带小境，如「筑基境中期」）",
      "realm_at_climax": "卷末对决境界（可带小境，如「破虚境圆满」）",
      "narrative_function": "本卷叙事功能（40字内，须具体）",
      "boss_kind": "arc_boss"
    }}
  ]
}}

【铁律】
1. antagonist_ladder 必须恰好 {n_volumes} 条，按 vol_index 0→{n_volumes - 1} 排序；
   这是后续人物库与卷骨架的唯一 Boss 名单，禁止后续步骤另起新名。
2. 每个 Boss 的 faction 必须命中 factions 里的某个 name（大小写/全称一致），禁止凭空捏造势力。
3. boss_name 全书不重复；后卷 realm_at_climax rank 严格高于前卷。
4. realm_at_climax rank ≤ 同卷主角卷末预期 rank + 2（见主角成长路线）；须标注小境。
5. 终局卷 Boss 须处体系次高档或最高档。
6. 势力必须涵盖主角阵营、核心反派、中立各至少 1 个；antagonist 类势力 villain_timeline 必填。
只返回该 JSON 对象。"""

    return system, prompt


def split_factions_antagonist_payload(data: Any) -> tuple[list, list]:
    """从合并响应里安全拆出 (factions_list, ladder_list)。"""
    if isinstance(data, dict):
        factions = data.get("factions")
        ladder = data.get("antagonist_ladder", data.get("ladder"))
        return (
            factions if isinstance(factions, list) else [],
            ladder if isinstance(ladder, list) else [],
        )
    # 容错：模型只回了势力数组
    if isinstance(data, list):
        return data, []
    return [], []
