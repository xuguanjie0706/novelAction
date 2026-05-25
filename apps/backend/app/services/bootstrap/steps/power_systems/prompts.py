"""Step 2 境界体系 prompt 构建。"""

from __future__ import annotations

from typing import Any

from app.services.bootstrap.context import get_genre_kit_block


def build_legacy_power_prompt(ctx: dict) -> str:
    """非多轴题材：沿用单轨 JSON 数组 prompt。"""
    kit_block = get_genre_kit_block(ctx)
    return f"""{kit_block}小说：《{ctx['project_title']}》({ctx.get('genre', '')})
创意：{ctx['logline']}
世界观：{ctx.get('world_overview', '')[:500]}

生成本小说的力量/境界体系，返回JSON数组（通常1~2套）：
[
  {{
    "name": "体系名称",
    "system_type": "cultivation",
    "description": "体系在世界观中的地位（50字内）",
    "cultivation_method": "修炼方式",
    "breakthrough_condition": "突破通用条件",
    "special_rules": "特殊规则",
    "protagonist_start_rank": 1,
    "protagonist_end_rank": 9,
    "levels": [
      {{
        "rank": 1,
        "name": "境界名",
        "description": "简述",
        "abilities": ["能力1"],
        "chapter_budget": 20,
        "gatekeeper": "卡点（10字内）",
        "leap_type": "spatial",
        "leap_description": "本层质变（15字内）"
      }}
    ]
  }}
]
system_type 只能是: cultivation / magic / ability / tech / hybrid
levels 至少 6 层；相邻层 leap_type 不得连续 3 层相同。
只返回JSON数组。"""


def build_xianxia_power_prompt(ctx: dict, arch: dict[str, Any]) -> str:
    """修仙多轴：单 JSON 对象含 cultivation_laws + systems[]。"""
    kit_block = get_genre_kit_block(ctx)
    paths = arch.get("selected_paths") or ["sword", "pill"]
    path_labels = arch.get("path_labels") or {}
    path_desc = "、".join(path_labels.get(p, p) for p in paths)
    artifact_names = " → ".join(arch.get("artifact_tier_names") or [])
    sect_names = " → ".join(arch.get("sect_rank_names") or [])
    total_ch = arch.get("total_chapters") or 300
    vols = arch.get("volume_count") or 10
    min_levels = arch.get("primary_min_levels") or 7

    return f"""{kit_block}小说：《{ctx['project_title']}》({arch.get('genre', '仙侠')})
创意：{ctx['logline']}
世界观：{ctx.get('world_overview', '')[:600]}
全书约 {total_ch} 章 / {vols} 卷

你是修仙世界观总架构师。禁止只输出一条「炼气→筑基→金丹」数字 ladder。
必须构建**多轴力量体系**，返回单个 JSON 对象（不要数组包裹根）：

{{
  "cultivation_laws": {{
    "spirit_root_rule": "灵根/资质铁律",
    "breakthrough_law": "渡劫/心魔/突破铁律",
    "ascension_rule": "飞升或位面上限",
    "golden_finger_cost": "金手指代价"
  }},
  "dao_heart": {{
    "dao_heart_stages": ["道心初种", "..."],
    "heart_demon_triggers": ["执念", "情劫", "..."],
    "tribulation_map": {{"3": {{"type": "金丹劫", "failure_cost": "跌境"}}}}
  }},
  "systems": [
    {{
      "name": "修行境界",
      "axis_role": "primary",
      "system_type": "cultivation",
      "description": "主轴简介",
      "cultivation_method": "修炼方式",
      "breakthrough_condition": "突破条件",
      "special_rules": "特殊规则",
      "visualization": "战力差距画面（一句话）",
      "protagonist_start_rank": 1,
      "protagonist_end_rank": 8,
      "levels": [
        {{
          "rank": 1,
          "name": "炼气境",
          "description": "简述",
          "abilities": ["神识初开"],
          "chapter_budget": 25,
          "gatekeeper": "具体卡点",
          "leap_type": "spatial|soul|rule|social|craft|combat",
          "leap_description": "比上一层多能做什么",
          "sub_levels": ["初期","中期","后期","圆满"],
          "breakthrough_trials": ["resource","insight","tribulation","heart_demon"]
        }}
      ]
    }},
    {{
      "name": "{path_labels.get(paths[0], '剑修')}道途",
      "axis_role": "path",
      "path_id": "{paths[0]}",
      "system_type": "cultivation",
      "description": "道途说明",
      "visualization": "道途差距画面",
      "levels": [{{"rank":1,"name":"一重","description":"","abilities":[]}}],
      "cross_system_rules": [
        {{"primary_rank":3,"path_rank":2,"unlocks":"可领悟本命神通"}}
      ]
    }},
    {{
      "name": "法宝器物阶",
      "axis_role": "artifact",
      "system_type": "hybrid",
      "visualization": "法宝光晕/丹纹画面",
      "levels": [按品阶 {artifact_names} 各一层，含 rank/name/abilities]
    }},
    {{
      "name": "宗门位阶",
      "axis_role": "sect",
      "system_type": "hybrid",
      "visualization": "令牌/洞府/秘境权限画面",
      "levels": [按 {sect_names} 各一层，含 rank/name/description]
    }}
  ]
}}

硬性要求：
1. systems 至少 4 条，且 axis_role 必须含 primary、path、artifact、sect。
2. 本书须落库道途：{path_desc}（各一条 path，path_id 对应 sword/pill/body 等）。
3. 主轴 levels ≥ {min_levels} 层，推荐炼气→筑基→金丹→元婴→化神→合体→渡劫→大乘（可改名但须有质变）。
4. 相邻两层 abilities 不得雷同；leap_type 不得连续 3 层相同。
5. 主轴 chapter_budget 之和约在全书章数 {total_ch} 的 60%~80%。
6. protagonist_end_rank - protagonist_start_rank ≥ 卷数 {vols}。
7. 至少 2 个主轴层 breakthrough_trials 含 tribulation；至少 2 层含 heart_demon。
8. 只返回 JSON 对象，不要 markdown 说明。"""
