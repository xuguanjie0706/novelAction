"""Bootstrap Fanqie Phase B：爽文公式（合并步骤）。

原三步（contrast_design → golden_finger → face_slap_map）合并为一次 LLM 调用。

设计动机
--------
这三个设计本质上是同一个创意单元：落差决定出发点，金手指在落差中激活，
打脸地图是金手指升级阶段的镜像。分三次调用时每一步都要把前一步的结果
作为上下文传入，等于让 AI 在三次对话中做了一件事，且一致性依赖 ctx 传递。
合并为一次调用后 AI 可以同时对齐三者，产物更内聚，节省 2 次 LLM 调用。

产物（与原三步完全兼容）
-----------------------
- Project.extra['contrast_design']
- Project.extra['golden_finger']
- Project.extra['face_slap_map']
- ctx['protagonist'], ctx['golden_finger'], ctx['face_slap_map'], ctx['contrast_design']
"""
from __future__ import annotations

import re
from typing import Any

from app.models import Project
from app.services.bootstrap.steps.fanqie._json_once import call_fanqie_json_once

_STEP = "fanqie_formula"

_FINGER_TYPES = (
    "系统面板（属性/技能/任务）/ 空间戒指（储物/种植/炼丹）/ "
    "前世记忆（战神/大佬/修仙者）/ 传承血脉（觉醒特殊体质）/ "
    "神级师父（隐世高手收徒）/ 重生预知（知道未来剧情）/ "
    "签到系统 / 鉴宝能力 / 医术天赋觉醒 / 特殊瞳术"
)


def _validate_formula(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "须为 JSON 对象"
    # contrast 必填
    if not (data.get("protagonist_name") or "").strip():
        return "protagonist_name 不能为空"
    if not data.get("initial_state_headline"):
        return "initial_state_headline 不能为空"
    # golden_finger 必填
    gf = data.get("golden_finger")
    if not isinstance(gf, dict):
        return "golden_finger 须为对象"
    stages = gf.get("upgrade_stages")
    if not isinstance(stages, list) or len(stages) < 3:
        return "golden_finger.upgrade_stages 至少需要 3 个阶段"
    # face_slap 必填
    fsm = data.get("face_slap_map")
    if not isinstance(fsm, dict):
        return "face_slap_map 须为对象"
    targets = fsm.get("targets")
    if not isinstance(targets, list) or len(targets) < 3:
        return "face_slap_map.targets 至少需要 3 个打脸对象"
    first_ch = fsm.get("first_slap_chapter")
    if isinstance(first_ch, int) and first_ch > 5:
        return "face_slap_map.first_slap_chapter 必须 ≤ 5"
    return None


async def gen_fanqie_formula(svc: Any, project: Project, ctx: dict) -> dict:
    """
    一次调用生成落差工程 + 金手指工程 + 打脸地图。

    @returns formula dict（含 contrast_design / golden_finger / face_slap_map 三个子结构）
    """
    system = (
        "你是番茄小说开局设计专家，精通落差工程、金手指设计、打脸节奏三位一体的设计方法。"
        "只返回 JSON，不要解释文字。"
    )
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    archetype = fanqie_pos.get("genre_archetype", "")
    satisfaction = fanqie_pos.get("core_satisfaction", "")

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{archetype}
核心爽感：{satisfaction}
创意：{ctx['logline']}

番茄开局铁律：主角初始状态越惨越好，金手指触发必须在800字内，首次打脸不超过第5章。

请一次性设计完整的「爽文公式」，返回 JSON：
{{
  "protagonist_name": "全书POV主角姓名（2~4字，禁止用萧凡/萧炎式替身名，后文所有步骤沿用此名）",
  "initial_state_headline": "一句话概括主角当前处境（必须含具体身份+具体羞辱事件，如：'上门女婿，被丈母娘当众撕毁结婚证，老婆提出离婚'，禁止用'穷困潦倒'这类模糊词）",
  "humiliation_scenes": [
    "具体羞辱场景1（可发生在第1章开头，含人物+地点+羞辱方式，20字内）",
    "具体羞辱场景2（可发生在第1章中段，比场景1更狠，20字内）"
  ],
  "protagonist_pain_point": "主角最在乎的东西被谁以什么方式伤害（20字内）",
  "trigger_event": "金手指触发的具体事件（含：发生地点+触发物/触发条件+预计字数位置）",
  "trigger_word_estimate": "预计触发字数位置（如：约第650字处）",
  "final_destination": "主角的终态成就（一句话，画面感强，如：'站在全城最高楼顶，俯视曾经踩踏自己的所有人'）",
  "contrast_ratio_note": "落差说明：从什么状态到什么状态（30字内）",

  "golden_finger": {{
    "finger_type": "从以下选一种：{_FINGER_TYPES}",
    "finger_name": "金手指的具体称呼（如：「战神传承」「至尊系统」「神农空间」）",
    "mechanism": "核心机制：怎么运作，触发条件，升级规则（2-3句话）",
    "activation_trigger": "第一次激活的精确触发条件（必须与上方 trigger_event 一致）",
    "constraint": "金手指的限制/代价（不能让主角纯无敌，要有张力，1句话）",
    "visualization_style": "爽感可视化方式（读者如何「看到」效果）",
    "upgrade_stages": [
      {{"stage": 1, "name": "阶段名", "unlock_ability": "解锁的核心能力（具体，一句话）", "visualization": "爽感画面（20字内）", "face_slap_target": "这阶段主要打脸谁", "chapter_range": "约第几章到第几章"}},
      {{"stage": 2, "name": "...", "unlock_ability": "...", "visualization": "...", "face_slap_target": "...", "chapter_range": "..."}},
      {{"stage": 3, "name": "...", "unlock_ability": "...", "visualization": "...", "face_slap_target": "...", "chapter_range": "..."}},
      {{"stage": 4, "name": "...", "unlock_ability": "...", "visualization": "...", "face_slap_target": "...", "chapter_range": "..."}},
      {{"stage": 5, "name": "...", "unlock_ability": "...", "visualization": "...", "face_slap_target": "...", "chapter_range": "..."}}
    ],
    "ceiling_description": "金手指的终极上限（成为什么级别的存在，一句话）"
  }},

  "face_slap_map": {{
    "targets": [
      {{"order": 1, "name": "角色名或类型", "relation": "与主角的关系", "initial_attitude": "初始如何对待主角（具体，一句话）", "slap_type": "财富碾压/武力碾压/身份碾压/感情反转/当众揭穿（选一种）", "slap_scene": "打脸具体场景（谁在场+发生什么+主角如何碾压，25字内）", "chapter_estimate": "大约第几章"}},
      {{"order": 2, "name": "...", "relation": "...", "initial_attitude": "...", "slap_type": "...", "slap_scene": "...", "chapter_estimate": "..."}},
      {{"order": 3, "name": "...", "relation": "...", "initial_attitude": "...", "slap_type": "...", "slap_scene": "...", "chapter_estimate": "..."}},
      {{"order": 4, "name": "...", "relation": "...", "initial_attitude": "...", "slap_type": "...", "slap_scene": "...", "chapter_estimate": "..."}},
      {{"order": 5, "name": "...", "relation": "...", "initial_attitude": "...", "slap_type": "...", "slap_scene": "...", "chapter_estimate": "..."}}
    ],
    "first_slap_chapter": 3,
    "first_slap_preview": "第一次打脸的具体画面（必须是「看得见」的场面，一句话）",
    "slap_rhythm": "打脸节奏（如：每3章一小打，每10章一大打，每卷一个震撼大打脸）",
    "type_diversity_plan": ["本书将用到的所有打脸类型，至少3种"],
    "escalation_path": "打脸对象升级路径（从家庭→公司→城市→...，一句话概括）"
  }}
}}

硬约束：
1. humiliation_scenes 是「在场景中真实发生的动作」，不是心理描写
2. trigger_word_estimate 必须 ≤ 800字
3. face_slap_map.first_slap_chapter 必须 ≤ 5
4. face_slap_map.targets 必须恰好 5 个，按从弱到强排列
5. face_slap_map.slap_type 在 5 个 target 中至少出现 3 种不同类型
6. golden_finger.upgrade_stages 必须恰好 5 个，与 face_slap_map.targets 的打脸层级一一呼应
7. golden_finger.visualization 必须是「画面」（错误：「力量大增」；正确：「单手折断对方手腕」）
8. 只返回 JSON"""

    data = await call_fanqie_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate_formula,
    )

    # 拆分产物，兼容下游依赖各子结构键的步骤
    contrast = {
        "protagonist_name": data.get("protagonist_name", ""),
        "initial_state_headline": data.get("initial_state_headline", ""),
        "humiliation_scenes": data.get("humiliation_scenes", []),
        "protagonist_pain_point": data.get("protagonist_pain_point", ""),
        "trigger_event": data.get("trigger_event", ""),
        "trigger_word_estimate": data.get("trigger_word_estimate", ""),
        "final_destination": data.get("final_destination", ""),
        "contrast_ratio_note": data.get("contrast_ratio_note", ""),
    }
    golden_finger = data.get("golden_finger") or {}
    face_slap_map = data.get("face_slap_map") or {}

    ctx["protagonist"] = str(contrast["protagonist_name"]).strip()
    ctx["contrast_design"] = contrast
    ctx["golden_finger"] = golden_finger
    ctx["face_slap_map"] = face_slap_map

    extra = dict(project.extra or {})
    extra["contrast_design"] = contrast
    extra["golden_finger"] = golden_finger
    extra["face_slap_map"] = face_slap_map
    project.extra = extra
    svc.db.commit()

    return data


def extract_chapter_num(s: str) -> int | None:
    """从 '约第3章' / '3-5章' 等字符串提取首个章节号。"""
    m = re.search(r"\d+", str(s))
    return int(m.group()) if m else None
