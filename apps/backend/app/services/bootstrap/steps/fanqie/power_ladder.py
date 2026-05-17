"""Bootstrap Fanqie Step 9：权力阶梯（最小化世界观）。

番茄世界观设计原则：只建「支撑金手指运转所需的最小基础设施」。
- 禁止大篇幅历史设定（读者跳过）
- 禁止复杂地理/文化描写（浪费字数）
- 必须明确财富和武力的「外在可视化」方式——读者要能「看到」权力差距

产物主要供 character_functions 和 opening_5chapters 使用。
"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json


async def gen_power_ladder(svc: Any, project: Project, ctx: dict) -> dict:
    """
    生成权力阶梯：社会/武力/财富层级 + 外在可视化方式。

    产物写入 Project.extra['power_ladder'] 并缓存到 ctx。
    不创建 PowerSystem 记录（番茄模式下以 extra 存储为主）。

    @returns power_ladder dict
    """
    system = "你是番茄小说世界架构设计师。只返回 JSON，不要解释文字。"
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    gf = ctx.get("golden_finger") or {}
    fsm = ctx.get("face_slap_map") or {}

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{fanqie_pos.get('genre_archetype', '')}
金手指：{gf.get('finger_name', '')}
金手指天花板：{gf.get('ceiling_description', '')}
打脸升级路径：{fsm.get('escalation_path', '')}
创意：{ctx['logline']}

番茄铁律：世界观只需支撑打脸路径，禁止过度设定。每段背景描写不超过3行。

设计权力阶梯，返回 JSON：
{{
  "world_core_rule": "这个世界运行的一条核心规则（必须是让打脸有意义的那条规则，20字内，如：'古武高手掌控一切商业资源，战力即话语权'）",
  "social_ladder": [
    {{"tier": 1, "name": "阶层名", "description": "这个阶层的人有什么资源/地位（15字内）", "representative": "典型代表（主角/某角色）"}},
    {{"tier": 2, "name": "...", "description": "...", "representative": "..."}},
    {{"tier": 3, "name": "...", "description": "...", "representative": "..."}},
    {{"tier": 4, "name": "...", "description": "...", "representative": "..."}},
    {{"tier": 5, "name": "...", "description": "...", "representative": "..."}}
  ],
  "protagonist_start_tier": 1,
  "protagonist_end_tier": 5,
  "wealth_visualization": "财富差距在场景中如何体现（一句话，必须是画面：如'豪车+私人司机，酒店包场，随手打赏百万'）",
  "power_visualization": "战力差距在场景中如何体现（一句话，必须是画面：如'单手接住刀，对方骨折，旁观者失声'）",
  "setting_vibe": "故事发生的整体氛围（都市/古代/现代都市+隐藏古武，10字内）"
}}

要求：
1. social_ladder 必须恰好 5 层，主角从第1层打到第5层
2. world_core_rule 必须是「读者立刻就能理解」的规则，不能是需要解释的世界观
3. wealth_visualization 和 power_visualization 必须是「第一章就能出现」的画面
4. 禁止输出超过5行的背景介绍（这是世界架构，不是世界观章节）
5. 只返回 JSON"""

    last_err = ""
    for attempt in range(3):
        fix = f"\n【请修正：{last_err}】" if last_err else ""
        raw = await svc._call_with_retry(
            system, prompt + fix,
            max_tokens=1024,
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
        if not data.get("world_core_rule"):
            last_err = "world_core_rule 不能为空"
            continue
        ladder = data.get("social_ladder")
        if not isinstance(ladder, list) or len(ladder) < 3:
            last_err = "social_ladder 至少需要 3 层"
            continue

        extra = dict(project.extra or {})
        extra["power_ladder"] = data
        # 兼容：把 world_core_rule 写入 world_overview，供通用步骤读取
        if not project.world_overview:
            project.world_overview = data.get("world_core_rule", "")
        project.extra = extra
        svc.db.commit()

        ctx["power_ladder"] = data
        ctx["world_overview"] = project.world_overview
        return data

    return {}
