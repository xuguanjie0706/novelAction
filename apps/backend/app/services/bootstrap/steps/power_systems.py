"""Bootstrap Step 2：境界体系。"""

from __future__ import annotations

from typing import Any

from app.models import PowerSystem, Project
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import coerce_power_system_rank, parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_power_systems(svc: Any, project: Project, ctx: dict):
    system = "你是网络小说世界构建专家。只返回JSON数组。"
    kit_block = get_genre_kit_block(ctx)
    prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
世界观：{ctx['world_overview'][:300]}

【流派编辑手册约束】
- 境界体系必须符合 genre_kit 的 pacing_guide（玄幻要强调升级仪式与金手指代价，仙侠要强调心魔与渡劫）

生成本小说的力量/境界体系，返回JSON数组（通常1~2套）：
[
  {{
    "name": "体系名称，如「修炼境界」",
    "system_type": "cultivation",
    "description": "体系在世界观中的地位与简介（50字内）",
    "cultivation_method": "修炼方式（如：吸纳天地灵气，淬炼丹田）",
    "breakthrough_condition": "突破通用条件（如：灵气积累满溢+感悟）",
    "special_rules": "特殊规则（如：天才/废柴判定，天花板原因）",
    "protagonist_start_rank": 1,
    "protagonist_end_rank": 9,
    "levels": [
      {{
        "rank": 1,
        "name": "境界名",
        "description": "简述",
        "abilities": ["能力1"],
        "chapter_budget": 20,
        "gatekeeper": "守在这一境界卡点的核心障碍（强敌名/事件类型/资源缺口，10字内）"
      }},
      {{
        "rank": 2,
        "name": "境界名",
        "description": "简述",
        "abilities": ["能力1"],
        "chapter_budget": 30,
        "gatekeeper": "守在这一境界卡点的核心障碍"
      }}
    ]
  }}
]
system_type 只能是: cultivation / magic / ability / tech / hybrid
levels 至少包含 6 个境界，按强弱从低到高排列。
protagonist_start_rank、protagonist_end_rank 必须是整数，且等于 levels 中某一层的 rank，禁止填境界中文名。
chapter_budget 为主角在该境界停留的预计章数（整数）；所有境界 chapter_budget 之和建议在目标总章数 70% 左右（其余 30% 用于横向扩展剧情）。
gatekeeper 必须具体（如"宗门首席×××"或"突破所需天材地宝被反派势力垄断"），不要空泛写"强敌"。
只返回JSON数组，不要说明文字。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.power_systems",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("power_systems", [])

    results = []
    for i, item in enumerate(data):
        levels = item.get("levels", [])
        start_raw = item.get("protagonist_start_rank")
        if start_raw is None:
            start_raw = item.get("protagonist_current_rank")
        end_raw = item.get("protagonist_end_rank")
        ps = PowerSystem(
            project_id=project.id,
            name=item.get("name", "修炼体系"),
            system_type=item.get("system_type", "cultivation"),
            description=item.get("description"),
            cultivation_method=item.get("cultivation_method"),
            breakthrough_condition=item.get("breakthrough_condition"),
            special_rules=item.get("special_rules"),
            levels=levels,
            protagonist_current_rank=coerce_power_system_rank(start_raw, levels, 1),
            protagonist_end_rank=coerce_power_system_rank(end_raw, levels, None),
            sort_order=i,
        )
        svc.db.add(ps)
        results.append(ps)

    svc.db.commit()

    if results:
        main_ps = results[0]
        level_names = [lv.get("name", "") for lv in (main_ps.levels or []) if lv.get("name")]
        ctx["power_level_names"] = level_names
        ctx["power_system_name"] = main_ps.name
        ctx["power_summary"] = (
            f"{main_ps.name}：" + " → ".join(level_names[:8])
        )
    else:
        ctx["power_level_names"] = []
        ctx["power_system_name"] = ""
        ctx["power_summary"] = ""

    return results
