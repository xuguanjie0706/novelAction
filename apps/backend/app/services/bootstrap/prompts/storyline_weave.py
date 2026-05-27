"""Bootstrap Step 4：故事线身份 + 织网矩阵 prompt 构建。"""

from __future__ import annotations

import json
from typing import Any


def default_volume_phases(n_volumes: int) -> list[str]:
    """Step 9 之前的默认卷 phase 分布（与 volumes.py 回退逻辑一致）。"""
    valid = ("opening", "rising", "turning", "dark_hour", "climax", "ending")
    if n_volumes <= 0:
        return []
    if n_volumes == 1:
        return ["opening"]
    if n_volumes == 2:
        return ["opening", "ending"]
    phases: list[str] = ["opening"]
    mid_count = max(0, n_volumes - 2)
    mid_template = ["rising", "turning", "dark_hour", "climax"]
    for i in range(mid_count):
        phases.append(mid_template[min(i, len(mid_template) - 1)])
    phases.append("ending")
    return phases[:n_volumes]


def build_storyline_identity_prompt(ctx: dict, kit_block: str, power_block: str) -> str:
    """第一次 LLM：故事线身份（含 weight / theme_link）。"""
    theme = (ctx.get("story_core") or {}).get("theme", "")
    premise = ctx.get("premise") or (ctx.get("story_core") or {}).get("conflict", "")
    return f"""{kit_block}小说：《{ctx.get('project_title')}》({ctx.get('genre')})
创意：{ctx.get('logline')}
故事核：{premise} | 主题：{theme}
{power_block}

【流派编辑手册约束】
- 每条故事线的 core_conflict / resolution_direction 须贴合 genre_kit
- theme_link 必须说明该线如何服务全书主题「{theme[:80]}」

生成 3~6 条故事线，返回 JSON 数组：
[
  {{
    "name": "主线：（简短有力的线名）",
    "line_type": "main",
    "description": "故事线简述（40字内）",
    "core_conflict": "核心矛盾",
    "resolution_direction": "收束方向",
    "theme_link": "与全书主题的因果关系（30字内）",
    "weight": 0.35,
    "related_character_names": ["主角名"],
    "resolution_volume_hint": 5,
    "status": "planned",
    "start_chapter": 1
  }}
]

line_type: main / sub / romance / growth / mystery / faction / antagonist
status: planned / active

【铁律】
1. 有且只有 1 条 main，weight ≥ 0.30
2. 所有 weight 之和须在 0.95~1.05
3. resolution_volume_hint 按重要性反序收束（支线先于主线）
4. 禁止与流派不符的孤儿线（如硬核玄幻的日常校园线）

只返回 JSON 数组。"""


def build_storyline_weave_prompt(
    ctx: dict,
    identity_lines: list[dict],
    n_volumes: int,
    volume_phases: list[str],
    kit_block: str,
) -> str:
    """第二次 LLM：故事线 × 卷织网矩阵。"""
    lines_json = json.dumps(identity_lines, ensure_ascii=False, indent=2)
    phases_json = json.dumps(
        [{"vol_index": i, "phase": volume_phases[i] if i < len(volume_phases) else "rising"}
         for i in range(n_volumes)],
        ensure_ascii=False,
    )
    tw = int(ctx.get("target_words") or 1_200_000)
    return f"""{kit_block}小说：《{ctx.get('project_title')}》({ctx.get('genre')})
全书约 {tw:,} 字，**{n_volumes} 卷**（vol_index 从 0 起）。

【已生成故事线身份】
{lines_json}

【各卷默认 phase】
{phases_json}

任务：为每条故事线生成「卷级导演节拍」，并规划线间交叉。返回单个 JSON 对象：

{{
  "weave_matrix": {{
    "故事线名称（与身份 name 完全一致）": [
      {{
        "vol_index": 0,
        "beat": "本卷关键动作（40字内）",
        "tension": 25,
        "is_active": true,
        "chapter_hint_start": 3,
        "chapter_hint_peak": 18,
        "crossover_with": ["另一条线名"]
      }}
    ]
  }},
  "crossover_nodes": [
    {{
      "line_a": "线A名",
      "line_b": "线B名",
      "at_vol": 1,
      "trigger": "交叉触发条件（具体）",
      "effect_on_both": "对两条线轨迹的改变（各一句）"
    }}
  ]
}}

【织网铁律】
1. 每条线 weave_matrix 内必须有恰好 {n_volumes} 个 vol_index（0~{n_volumes - 1}）
2. 每卷至少 2 条线 is_active=true
3. 任何线不得连续超过 2 卷 is_active=false
4. 每卷至少 1 个 crossover_nodes（at_vol 对齐）
5. 同卷内 tension≥75 的线不超过 2 条
6. 主线 tension 须在 phase=climax 的卷达到全书最高
7. tension 使用 0/25/50/75/100 五档，减少模糊数值
8. crossover 必须含非空 trigger 与 effect_on_both

只返回 JSON 对象。"""
