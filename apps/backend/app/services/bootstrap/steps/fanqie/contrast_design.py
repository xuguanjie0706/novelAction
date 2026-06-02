"""Bootstrap Fanqie Steps 1-2：落差工程。

番茄核心公式：越惨越爽。
主角的初始耻辱感越具体、越可视化，金手指激活后的爽感就越强。

设计约束：
- 初始状态必须「一句话能说清楚」且「听完想骂人（替主角不值）」
- 触发事件必须在第一章 800 字内发生，不允许铺垫超过两页
- 落差系数 = 终态地位 / 初始状态，番茄要求视觉上 ≥ 10x
"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_contrast_design(svc: Any, project: Project, ctx: dict) -> dict:
    """
    生成落差工程：主角初始耻辱状态 + 金手指触发事件设计。

    产物写入 Project.extra['contrast_design'] 并缓存到 ctx。

    @returns contrast_design dict
    """
    system = "你是番茄小说开局设计专家。只返回 JSON，不要解释文字。"
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    archetype = fanqie_pos.get("genre_archetype", "")
    satisfaction = fanqie_pos.get("core_satisfaction", "")

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{archetype}
核心爽感：{satisfaction}
创意：{ctx['logline']}

番茄开局铁律：主角初始状态越惨越好，触发事件必须在800字内发生。

返回 JSON：
{{
  "initial_state_headline": "一句话概括主角当前处境（必须含具体身份+具体羞辱事件，如：'上门女婿，被丈母娘当众撕毁结婚证，老婆提出离婚'，禁止用'穷困潦倒'这类模糊词）",
  "humiliation_scenes": [
    "具体羞辱场景1（可发生在第1章开头，含人物+地点+羞辱方式，20字内）",
    "具体羞辱场景2（可发生在第1章中段，比场景1更狠，20字内）"
  ],
  "protagonist_pain_point": "主角最在乎的东西（亲情/爱情/尊严/家族...）被谁以什么方式伤害（20字内）",
  "trigger_event": "金手指触发的具体事件（含：发生地点+触发物/触发条件+第几章第几百字左右触发，必须具体）",
  "trigger_word_estimate": "预计触发字数位置（如：约第650字处）",
  "final_destination": "主角的终态成就（一句话，画面感越强越好，如：'站在全城最高楼顶，俯视曾经踩踏自己的所有人'）",
  "contrast_ratio_note": "落差感说明：从什么状态到什么状态，读者会有多强的「翻天覆地」感（30字内）"
}}

要求：
1. humiliation_scenes 必须是「在场景中真实发生的动作」，不是心理描写
2. trigger_event 必须在第一章 800 字内发生，若类型需要铺垫，说明怎么在800字内完成铺垫
3. final_destination 要让读者「光是想想就觉得爽」——高度要足够高，反差要足够大
4. 只返回 JSON"""

    last_err = ""
    for attempt in range(3):
        fix = f"\n【请修正：{last_err}】" if last_err else ""
        raw = await svc._call_with_retry(
            system, prompt + fix,
            max_tokens=max_tokens_bootstrap_completion(),
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
        required = {"initial_state_headline", "trigger_event", "final_destination"}
        if missing := required - data.keys():
            last_err = f"缺少字段：{missing}"
            continue
        if not data.get("initial_state_headline"):
            last_err = "initial_state_headline 不能为空"
            continue

        # 持久化到 Project.extra
        extra = dict(project.extra or {})
        extra["contrast_design"] = data
        project.extra = extra
        svc.db.commit()
        return data

    return {}
