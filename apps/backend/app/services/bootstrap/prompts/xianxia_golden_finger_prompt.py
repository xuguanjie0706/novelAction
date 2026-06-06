"""修仙金手指 prompt：金手指必须咬合境界轴（非番茄式泛化信息差）。"""
from __future__ import annotations

_FINGER_TYPES = (
    "吞噬（吞噬战利/境界/血脉化为己用）/ 模拟器（推演人生或战斗结果）/ "
    "一键升级（资源换等级）/ 时间洞府（闭关加速）/ 词条签到（日常获取）/ "
    "功法推演（残篇补全为完整顶级功法）"
)


def build_xianxia_golden_finger_prompt(
    *, core_satisfaction: str, progression_fantasy: str,
    tension_source: str, realm_axis_name: str, realm_ladder_line: str,
) -> str:
    """返回修仙金手指 user prompt。realm_* 来自已生成的境界主轴。"""
    return f"""为一部番茄修仙直白文设计【金手指】。已知：
- 核心爽感：{core_satisfaction}
- 升级幻想：{progression_fantasy}
- 张力来源：{tension_source}
- 境界主轴「{realm_axis_name}」：{realm_ladder_line}

修仙金手指的灵魂是**咬合境界轴**——它必须直接作用于「突破/资源/功法/战力」，
而不是泛化的『信息优势/未卜先知』。同时必须有代价与天花板，否则数值爽点会失去张力。
返回 JSON：

{{
  "finger_type": "从下列选一个，照抄：{_FINGER_TYPES}",
  "finger_name": "金手指名称(有记忆点，6字内)",
  "axis_coupling": "如何咬合境界主轴：具体作用于 突破速度/资源转化/功法领悟/战力倍率 中的哪几项，必须点名境界主轴「{realm_axis_name}」",
  "activation": "开局如何获得 + 第一次如何使用(第1章可兑现)",
  "input_cost": "使用代价/限制(必须有：如消耗稀缺资源/反噬/冷却/前置条件)，确保不能无限白嫖",
  "ceiling_description": "能力天花板：到高境后金手指的边界在哪，防止后期主角失控碾压一切失去张力",
  "early_game_hook": "开局前3章用金手指打出第一个数值爽点的具体场景(40字内)",
  "evolution_stages": ["随大境提升，金手指的3-4阶进化(每阶一句，须与境界轴档位挂钩)"]
}}

铁律：
1. axis_coupling 必须显式说明对境界突破或战力数值的作用，不能只写『获得信息』。
2. input_cost 不可为空、不可形同虚设——它是维持升级张力的关键。
3. 只返回 JSON。"""
