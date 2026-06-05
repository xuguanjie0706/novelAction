"""Bootstrap Fanqie Steps 15-16：爽点节奏图 + 剧情储量池。

爽点节奏图：前50章每章打标（大爽/小爽/推进/过渡），连续过渡超3章自动标红。
剧情储量池：预备 3-5 个可插入的自洽支线弧，供主线卡壳或冲字数时调用。

产物写入 Project.extra['rhythm_map']。
"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.steps.fanqie._json_once import call_fanqie_json_once

_STEP = "rhythm_map"


async def gen_rhythm_map(svc: Any, project: Project, ctx: dict) -> dict:
    """
    生成爽点节奏图（前50章）+ 剧情储量池（3-5个备用弧）。

    @returns rhythm_map dict；包含 chapter_tags 列表和 story_buffer 列表
    """
    system = "你是番茄小说节奏规划专家，熟知番茄读者的注意力阈值。只返回 JSON，不要解释文字。"
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    fsm = ctx.get("face_slap_map") or {}
    gf = ctx.get("golden_finger") or {}
    contrast = ctx.get("contrast_design") or {}

    slap_rhythm = fsm.get("slap_rhythm", "每3章一小打，每10章一大打")
    stages = gf.get("upgrade_stages") or []

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{fanqie_pos.get('genre_archetype', '')}
核心爽感：{fanqie_pos.get('core_satisfaction', '')}
打脸节奏：{slap_rhythm}
金手指阶段：{len(stages)}个升级阶段
开局约束：触发约{contrast.get('trigger_word_estimate', '800字内')}；首次打脸≤第{fsm.get('first_slap_chapter', 3)}章
打脸升级路径：{fsm.get('escalation_path', '')}

番茄留存铁律：连续3章没有明显爽感，读者流失率+30%。

第一部分：生成前50章爽点节奏图。章节类型只能用：
- big_win（大爽点：打脸/重大升级/震撼全场）
- small_win（小爽点：小胜利/展示实力/小秘密揭露）
- progress（推进：剧情发展，有信息量但无爽点）
- transition（过渡：连接性章节，尽量少用）

硬约束：连续 transition 不超过2章；big_win 间隔不超过15章。

第二部分：生成3-5个剧情储量池弧线（备用支线，主线卡壳时可插入）。

返回 JSON：
{{
  "chapter_tags": [
    {{"ch": 1, "type": "progress", "note": "开局建立处境"}},
    {{"ch": 2, "type": "small_win", "note": "金手指首次效果"}},
    {{"ch": 3, "type": "big_win", "note": "首次打脸丈母娘"}},
    ... （共50条，必须包含第1-50章）
  ],
  "dry_spell_warnings": ["节奏图中连续过渡超2章的位置（如：第X-Y章需要加爽点）"],
  "major_payoff_chapters": [3, 10, 20, 35, 50],
  "story_buffer": [
    {{
      "name": "支线弧名称（5字内）",
      "chapter_count": 15,
      "trigger_condition": "什么情况下插入（主线推进过快/需要拖字数/读者追完某个打脸后给喘息）",
      "core_conflict": "支线核心矛盾（一句话）",
      "satisfaction_type": "爽感类型（武力展示/财富碾压/感情线/悬疑揭秘）",
      "insertion_point": "建议插入的章节位置（如：第15-20章之间）"
    }},
    {{"name": "...", "chapter_count": 10, "trigger_condition": "...", "core_conflict": "...", "satisfaction_type": "...", "insertion_point": "..."}},
    {{"name": "...", "chapter_count": 12, "trigger_condition": "...", "core_conflict": "...", "satisfaction_type": "...", "insertion_point": "..."}}
  ]
}}

要求：
1. chapter_tags 必须有且只有50条，ch 从1到50顺序排列
2. story_buffer 必须有3-5个弧线，每个都是「可独立成章」的完整支线
3. major_payoff_chapters 标出5个最重要的大爽点章节
4. 只返回 JSON"""

    def _validate(data: Any) -> str | None:
        if not isinstance(data, dict):
            return "须为 JSON 对象"
        tags = data.get("chapter_tags")
        if not isinstance(tags, list) or len(tags) < 30:
            return "chapter_tags 至少需要30条"
        buffer = data.get("story_buffer")
        if not isinstance(buffer, list) or len(buffer) < 2:
            return "story_buffer 至少需要2个支线弧"
        return None

    data = await call_fanqie_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.opening_contract",
        validate=_validate,
    )

    data["auto_dry_spells"] = _detect_dry_spells(data.get("chapter_tags") or [])

    extra = dict(project.extra or {})
    extra["rhythm_map"] = data
    project.extra = extra
    svc.db.commit()
    ctx["rhythm_map"] = data

    from app.services.bootstrap.fanqie_normalize import converge_fanqie_project

    converge_fanqie_project(svc.db, project, ctx)
    return data


def _detect_dry_spells(tags: list) -> list[str]:
    """检测连续 transition 超2章的区间，返回警告列表。"""
    warnings = []
    streak = 0
    streak_start = 0
    for item in tags:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "transition":
            if streak == 0:
                streak_start = item.get("ch", 0)
            streak += 1
            if streak > 2:
                warnings.append(
                    f"第{streak_start}-{item.get('ch', '?')}章连续过渡{streak}章，需补充爽点"
                )
        else:
            streak = 0
    return warnings
