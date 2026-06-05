"""Bootstrap Fanqie Steps 6-8：打脸地图。

打脸地图是番茄留存率的核心驱动。设计原则：
- 对象谱系：从近到远、从小到大分层，主角逐层碾压（不能一开始就打最强的）
- 首次打脸：硬约束第 3-5 章内发生，且必须「看得见」（不能是旁白叙述）
- 类型多样性：财富/武力/身份/感情/当众揭穿，混用，不能全是同一种
"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.steps.fanqie._json_once import call_fanqie_json_once

_STEP = "face_slap_map"


async def gen_face_slap_map(svc: Any, project: Project, ctx: dict) -> dict:
    """
    生成打脸地图：对象谱系 + 首次打脸规划 + 爽点类型多样性分配。

    产物写入 Project.extra['face_slap_map'] 并缓存到 ctx。
    character_functions 步骤将据此分配角色的「打脸靶」功能标签。

    @returns face_slap_map dict
    """
    system = "你是番茄小说打脸节奏设计专家。只返回 JSON，不要解释文字。"
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    contrast = ctx.get("contrast_design") or {}
    gf = ctx.get("golden_finger") or {}

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{fanqie_pos.get('genre_archetype', '')}
主角初始状态：{contrast.get('initial_state_headline', '')}
金手指：{gf.get('finger_name', '')}（{gf.get('mechanism', '')[:80]}）
金手指升级阶段对应的打脸目标：
{_format_stages(gf.get('upgrade_stages', []))}
创意：{ctx['logline']}

设计打脸地图，返回 JSON：
{{
  "targets": [
    {{
      "order": 1,
      "name": "角色名或类型（如：丈母娘/公司小混混）",
      "relation": "与主角的关系",
      "initial_attitude": "初始如何对待主角（一句话，必须具体）",
      "slap_type": "打脸类型（财富碾压/武力碾压/身份碾压/感情反转/当众揭穿，选一种）",
      "slap_scene": "打脸的具体场景（谁在场+发生什么+主角如何碾压，25字内）",
      "chapter_estimate": "大约第几章"
    }},
    {{"order": 2, "name": "...", "relation": "...", "initial_attitude": "...", "slap_type": "...", "slap_scene": "...", "chapter_estimate": "..."}},
    {{"order": 3, "name": "...", "relation": "...", "initial_attitude": "...", "slap_type": "...", "slap_scene": "...", "chapter_estimate": "..."}},
    {{"order": 4, "name": "...", "relation": "...", "initial_attitude": "...", "slap_type": "...", "slap_scene": "...", "chapter_estimate": "..."}},
    {{"order": 5, "name": "...", "relation": "...", "initial_attitude": "...", "slap_type": "...", "slap_scene": "...", "chapter_estimate": "..."}}
  ],
  "first_slap_chapter": 3,
  "first_slap_preview": "第一次打脸的具体画面（一句话，必须是「看得见」的场面，不能是旁白叙述）",
  "slap_rhythm": "打脸节奏（如：每3章一小打，每10章一大打，每卷一个震撼全场的大打脸）",
  "type_diversity_plan": ["本书将用到的所有打脸类型，至少3种"],
  "escalation_path": "打脸对象的升级路径（从家庭→公司→城市→...，一句话概括整体路线）"
}}

硬约束：
1. targets 必须恰好 5 个，按照从弱到强排列
2. first_slap_chapter 必须 ≤ 5（番茄算法要求）
3. slap_type 在 5 个 target 中至少出现 3 种不同类型
4. slap_scene 必须是「动作」而非「结果」（错误：'主角赢了'；正确：'主角当众把支票摔在对方脸上'）
5. 只返回 JSON"""

    def _validate(data: Any) -> str | None:
        if not isinstance(data, dict):
            return "须为 JSON 对象"
        targets = data.get("targets")
        if not isinstance(targets, list) or len(targets) < 3:
            return "targets 至少需要 3 个打脸对象"
        first_ch = data.get("first_slap_chapter")
        if isinstance(first_ch, int) and first_ch > 5:
            return "first_slap_chapter 必须 ≤ 5"
        return None

    data = await call_fanqie_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate,
    )

    extra = dict(project.extra or {})
    extra["face_slap_map"] = data
    project.extra = extra
    svc.db.commit()
    ctx["face_slap_map"] = data
    return data


def _format_stages(stages: list) -> str:
    """格式化金手指阶段列表为 prompt 可读文本。"""
    if not stages:
        return "（未设定）"
    lines = []
    for s in stages:
        if isinstance(s, dict):
            lines.append(
                f"  阶段{s.get('stage', '?')} {s.get('name', '')}："
                f"打脸对象={s.get('face_slap_target', '')}，"
                f"约{s.get('chapter_range', '?')}章"
            )
    return "\n".join(lines) or "（未设定）"
