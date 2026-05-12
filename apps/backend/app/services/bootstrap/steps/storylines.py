"""Bootstrap Step 4：故事线。"""

from __future__ import annotations

from typing import Any

from app.models import Project, StoryLine
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_storylines(svc: Any, project: Project, ctx: dict):
    system = "你是网络小说叙事结构专家。只返回JSON数组。"
    kit_block = get_genre_kit_block(ctx)
    prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
故事核：{ctx['story_core'].get('conflict', '')} | 主题：{ctx['story_core'].get('theme', '')}
境界体系：{ctx.get('power_summary', '（未设定）')}

【流派编辑手册约束】
- 每条故事线的 core_conflict 和 resolution_direction 必须符合 genre_kit 的 satisfaction_tropes 和 pacing_guide
- 主线冲突类型必须贴合流派（玄幻打脸/升级、悬疑信息差/嫌疑人、言情误会/追妻等）

生成3~5条主要故事线，返回JSON数组：
[
  {{
    "name": "主线：（简短有力的线名）",
    "line_type": "main",
    "description": "故事线简述（40字内）",
    "core_conflict": "这条线的核心矛盾是什么",
    "resolution_direction": "预计如何收束",
    "status": "active",
    "start_chapter": 1
  }}
]
line_type 只能是: main / sub / romance / growth / mystery / faction / antagonist
status 只能是: planned / active
必须有且只有1条 main，其余为其他类型。
只返回JSON数组，不要说明文字。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.storylines",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("storylines", [])

    results = []
    for i, item in enumerate(data):
        sl = StoryLine(
            project_id=project.id,
            name=item.get("name", f"故事线{i+1}"),
            line_type=item.get("line_type", "sub"),
            description=item.get("description"),
            core_conflict=item.get("core_conflict"),
            resolution_direction=item.get("resolution_direction"),
            status=item.get("status", "planned"),
            start_chapter=item.get("start_chapter"),
            sort_order=i,
        )
        svc.db.add(sl)
        results.append(sl)

    svc.db.commit()

    ctx["storyline_summary"] = " | ".join(
        f"{sl.name}（{sl.line_type}）" for sl in results
    )
    ctx["storyline_ids"] = {sl.name: str(sl.id) for sl in results}

    return results
