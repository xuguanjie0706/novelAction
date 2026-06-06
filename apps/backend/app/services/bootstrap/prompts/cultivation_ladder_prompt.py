"""Bootstrap Fanqie 修仙线境界主轴 prompt（抽离自 cultivation_ladder.py）。

设计动机
--------
番茄通用线 power_ladder 生成「社会五阶」，对修仙打脸流是结构性错配：
修仙的爽感引擎是境界体系本身。本 prompt 生成一条命名自创、读者一眼能懂、
又有正统修仙感的「单主轴 + 小境」境界阶梯，产物填入与 power_ladder 完全相同的
ctx 键（social_ladder 复用为大境数组），下游 hydrate / normalize 零改即复用。

红线：本文件仅承载 prompt 字符串与组装函数，无业务逻辑。
"""
from __future__ import annotations

# 公版套话境名（大境名禁止整词照搬，可借语感换字）
_PUBLIC_REALM_WORDS = (
    "练气 / 炼气 / 筑基 / 金丹 / 结丹 / 元婴 / 化神 / 炼虚 / 合体 / 大乘 / 渡劫 / 飞升 / "
    "斗者 / 斗师 / 斗灵 / 斗王 / 斗皇 / 斗宗 / 斗尊 / 斗圣 / 斗帝"
)

# 修仙金手指脉络（与都市系金手指区分，供 fanqie_formula 复用提示）
FINGER_TYPES_XIANXIA = (
    "吞噬/炼化体质 / 万界功法图书馆 / 极品灵根觉醒 / 上古传承（剑修·丹尊·体修） / "
    "随身丹炉灵田空间 / 重生归来（知天材地宝与秘境） / "
    "神识天眼（鉴宝·看穿境界·破阵） / 时间加速闭关 / 杀伐证道（斩敌爆修为）"
)


def build_cultivation_ladder_prompt(
    *,
    project_title: str,
    genre_archetype: str,
    finger_name: str,
    ceiling_description: str,
    escalation_path: str,
    logline: str,
) -> str:
    """组装修仙境界主轴生成 prompt（单主轴 8-12 大境 × 四小境）。"""
    return f"""小说：《{project_title}》
类型公式：{genre_archetype}
金手指：{finger_name}
金手指天花板：{ceiling_description}
打脸升级路径：{escalation_path}
创意：{logline}

番茄修仙铁律：境界即一切话语权，低境者在高境者面前连呼吸都被压制；
世界观只为「境界差能成立打脸」服务，禁止大段历史/地理掌故，每段背景 ≤3 行。

设计本书唯一的「境界主轴」（单主轴 + 小境），返回 JSON：
{{
  "axis_kind": "cultivation",
  "realm_axis_name": "主轴总称（自创，如「九转归元道」「淬灵九重天」，禁止照搬公版词）",
  "world_core_rule": "一条让境界差有意义的核心规则（20字内，读者立刻懂，如：'灵气复苏，境界压制一切，高一境即可碾压')",
  "social_ladder": [
    {{"tier": 1, "name": "<大境1自创名>", "description": "<这一境的体感/能做到什么，15字内>", "representative": "主角起点"}},
    {{"tier": 2, "name": "<大境2>", "description": "...", "representative": "..."}},
    {{"tier": 3, "name": "<大境3>", "description": "...", "representative": "..."}},
    {{"tier": 4, "name": "<大境4>", "description": "...", "representative": "..."}},
    {{"tier": 5, "name": "<大境5>", "description": "...", "representative": "..."}},
    {{"tier": 6, "name": "<大境6>", "description": "...", "representative": "..."}},
    {{"tier": 7, "name": "<大境7>", "description": "...", "representative": "..."}},
    {{"tier": 8, "name": "<大境8>", "description": "...", "representative": "..."}},
    {{"tier": 9, "name": "<顶境名>", "description": "...", "representative": "终极对手/主角终态"}}
  ],
  "sub_realm_segments": ["初期", "中期", "后期", "圆满"],
  "protagonist_start_tier": 1,
  "protagonist_end_tier": 9,
  "power_visualization": "境界压制的画面（第1章就能出现，必须是看得见的场面，如：'高一境者一念之间，低境者灵力溃散、跪伏吐血')",
  "wealth_visualization": "修炼资源差距的画面（如：'世家子弟灵石如雨、丹药管够；主角连一块下品灵石都凑不齐')",
  "breakthrough_signature": "破境的统一外显（如：'天降灵潮、异象垂世、心魔劫临')，供卷纲反复制造破境爽点",
  "setting_vibe": "整体氛围（灵气复苏现代 / 古典仙门 / 星际修真，10字内）"
}}

硬约束：
1. social_ladder 必须 8-12 个大境，tier 从 1 递增，主角 start_tier=1 打到 end_tier=顶档或次顶档
2. 每个大境 name 必须自创：禁止整词照搬以下公版套话作为大境名 —— {_PUBLIC_REALM_WORDS}；可借语感但要换字
3. world_core_rule 必须「读者立刻懂」，不能是需要解释的世界观
4. power_visualization 必须是「境界压制」画面，不是财富对比
5. description 写「这一境能做到什么」的体感，禁止写历史掌故
6. 只返回 JSON，不要任何解释文字"""
