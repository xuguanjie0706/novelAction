"""Bootstrap Fanqie Steps 3-5：金手指工程。

金手指是番茄故事引擎，先于世界观设计。核心设计原则：
1. 爽感必须「可视化」：读者要能在脑海中「看到」每次升级的效果
2. 成长路线图必须与打脸对象一一对应：每个阶段解锁什么能力，能打败谁
3. 代价/限制是剧情张力的来源，不是纯无敌外挂
"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json

_FINGER_TYPES = (
    "系统面板（属性/技能/任务）/ 空间戒指（储物/种植/炼丹）/ "
    "前世记忆（战神/大佬/修仙者）/ 传承血脉（觉醒特殊体质）/ "
    "神级师父（隐世高手收徒）/ 重生预知（知道未来剧情）/ "
    "签到系统 / 鉴宝能力 / 医术天赋觉醒 / 特殊瞳术"
)


async def gen_golden_finger(svc: Any, project: Project, ctx: dict) -> dict:
    """
    设计金手指：类型选择 + 爽感可视化 + 阶段成长路线图。

    产物写入 Project.extra['golden_finger'] 并缓存到 ctx。
    后续 power_ladder / character_functions / opening_5chapters 均依赖此产物。

    @returns golden_finger dict
    """
    system = "你是番茄小说金手指设计专家。只返回 JSON，不要解释文字。"
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    contrast = ctx.get("contrast_design") or {}

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{fanqie_pos.get('genre_archetype', '')}
核心爽感：{fanqie_pos.get('core_satisfaction', '')}
主角初始状态：{contrast.get('initial_state_headline', '')}
触发事件：{contrast.get('trigger_event', '')}
创意：{ctx['logline']}

可选金手指类型（从下列中选一种或组合，禁止自创全新类型）：
{_FINGER_TYPES}

设计金手指，返回 JSON：
{{
  "finger_type": "从上列选一种，照抄原文",
  "finger_name": "金手指的具体称呼（如：「战神传承」「至尊系统」「神农空间」）",
  "mechanism": "核心机制（金手指怎么运作，触发条件，升级规则，2-3句话）",
  "activation_trigger": "第一次激活的精确触发条件（必须与 contrast_design 的 trigger_event 一致）",
  "constraint": "金手指的限制/代价（不能让主角纯无敌，要有张力，1句话）",
  "visualization_style": "爽感可视化方式（读者如何「看到」效果，如：蓝色数字面板弹出/周围人的惊愕反应/属性条跳变/...）",
  "upgrade_stages": [
    {{
      "stage": 1,
      "name": "阶段名（如：初阶/觉醒/小成）",
      "unlock_ability": "解锁的核心能力（一句话，必须具体）",
      "visualization": "这个阶段爽感的视觉化描述（读者脑海中的画面，20字内）",
      "face_slap_target": "这个阶段主要打脸谁（对应打脸地图中的层级）",
      "chapter_range": "大约在第几章到第几章展现此阶段"
    }},
    {{"stage": 2, "name": "...", "unlock_ability": "...", "visualization": "...", "face_slap_target": "...", "chapter_range": "..."}},
    {{"stage": 3, "name": "...", "unlock_ability": "...", "visualization": "...", "face_slap_target": "...", "chapter_range": "..."}},
    {{"stage": 4, "name": "...", "unlock_ability": "...", "visualization": "...", "face_slap_target": "...", "chapter_range": "..."}},
    {{"stage": 5, "name": "...", "unlock_ability": "...", "visualization": "...", "face_slap_target": "...", "chapter_range": "..."}}
  ],
  "ceiling_description": "金手指的终极上限（成为什么级别的存在，一句话）"
}}

要求：
1. upgrade_stages 必须恰好 5 个，对应 5 个打脸层级
2. visualization 必须是「画面」，不是「能力描述」（错误示例：「力量大增」；正确：「单手折断对方手腕，对方当场跪地」）
3. constraint 必须真实有效，不能是「偶尔疲劳」这种无效限制
4. 只返回 JSON"""

    last_err = ""
    for attempt in range(3):
        fix = f"\n【请修正：{last_err}】" if last_err else ""
        raw = await svc._call_with_retry(
            system, prompt + fix,
            max_tokens=1536,
            task="bootstrap.positioning",
        )
        try:
            data = parse_json(raw)
        except Exception:
            last_err = "JSON 解析失败"
            continue
        if not isinstance(data, dict):
            last_err = "须为 JSON 对象"
            continue
        stages = data.get("upgrade_stages")
        if not isinstance(stages, list) or len(stages) < 3:
            last_err = "upgrade_stages 至少需要 3 个阶段"
            continue
        required = {"finger_type", "finger_name", "mechanism", "visualization_style"}
        if missing := required - data.keys():
            last_err = f"缺少字段：{missing}"
            continue

        extra = dict(project.extra or {})
        extra["golden_finger"] = data
        project.extra = extra
        svc.db.commit()

        # 写入 ctx 供后续步骤使用
        ctx["golden_finger"] = data
        return data

    return {}
