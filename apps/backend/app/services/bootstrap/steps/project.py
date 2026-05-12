"""Bootstrap Step 1：项目基础信息落库。"""

from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts import book_length_constraints_for_prompt
from app.services.genre_kit import get_genre_kit, render_kit_for_prompt


async def gen_project(svc: Any, ctx: dict):
    """生成项目基础信息并创建 ``Project`` 行。"""
    system = "你是网络小说策划专家。根据创意生成项目基础信息，只返回JSON。"
    tw = int(ctx.get("target_words") or 1_200_000)
    length_block = book_length_constraints_for_prompt(tw)
    positioning_block = ""
    positioning = ctx.get("positioning") or {}
    if isinstance(positioning, dict) and positioning:
        positioning_block = (
            "\n【立项定位（必须严格遵守）】\n"
            + json.dumps(positioning, ensure_ascii=False, indent=2)
            + "\n"
        )
    prompt = f"""创意：{ctx['logline']}
立意与类型：{ctx.get('premise')[:1500] if ctx.get('premise') else '（未填写，请自动提炼作品定位、主题命题、核心矛盾与禁忌边界）'}
{positioning_block}
{length_block}

返回JSON：
{{
  "title": "小说名（2~6个汉字，有冲击力）",
  "genre": "玄幻",
  "premise": "使用 markdown 二级标题输出完整《立意与类型（PREMISE）》，必须包含：作品定位、核心一句话、类型与篇幅、主题与命题、核心矛盾、主角概况、结局倾向、最坏会怎样（收束边界）、希望读者记住的一个画面、叙事视角与禁忌；其中「类型与篇幅」必须严格服从上方【全书字数目标（硬性约束）】",
  "world_overview": "世界观简述，300~500字，包含力量体系、势力格局、社会规则",
  "story_core": {{
    "drive": "故事驱动力（成长/复仇/守护等）",
    "conflict": "核心矛盾",
    "theme": "主题",
    "differentiation": "与同类小说的差异化"
  }}
}}
要求：
1) premise 不要空话，必须可直接作为作者创作基线
2) premise 中必须给出清晰的目标读者、禁忌边界；「类型与篇幅」仅允许使用与【全书字数目标（硬性约束）】一致的规模表述
3) theme / conflict 要与 premise 一致
4) 只返回 JSON，不要解释文字。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=settings.GEMINI_SETTING_COMPLETION_MAX_TOKENS,
        task="bootstrap.project",
    )
    data = parse_json(raw)

    story_core = data.get("story_core", {}) or {}
    positioning = ctx.get("positioning") or {}
    if isinstance(story_core, dict) and positioning:
        story_core["positioning"] = positioning

    project_kwargs = dict(
        title=data["title"],
        genre=data.get("genre", "玄幻"),
        logline=ctx["logline"],
        premise=data.get("premise") or ctx.get("premise") or "",
        world_overview=data.get("world_overview", ""),
        story_core=story_core,
        target_words=int(ctx.get("target_words") or 1_200_000),
    )
    if hasattr(Project, "extra") and positioning:
        project_kwargs["extra"] = {"positioning": positioning}
    if svc.user_id is not None:
        project_kwargs["user_id"] = svc.user_id
    project = Project(**project_kwargs)
    svc.db.add(project)
    svc.db.commit()
    svc.db.refresh(project)

    ctx["project_title"] = project.title
    ctx["genre"] = project.genre
    ctx["world_overview"] = project.world_overview
    ctx["story_core"] = story_core
    ctx["premise"] = project.premise or ctx.get("premise") or ""
    ctx["genre_kit"] = get_genre_kit(project.genre)
    ctx["genre_kit_prompt"] = render_kit_for_prompt(ctx["genre_kit"])

    return project, ctx
