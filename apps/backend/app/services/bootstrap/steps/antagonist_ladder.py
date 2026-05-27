"""Bootstrap Step 4.5：卷级对立面登记表（antagonist_ladder）。"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models import Project
from app.services.bootstrap.antagonist_roster import (
    LADDER_EXTRA_KEY,
    format_ladder_summary,
    normalize_antagonist_ladder,
)
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.power_registry import format_power_context_block
from app.services.bootstrap.protagonist_progression import build_protagonist_progression_prompt_block
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan

logger = logging.getLogger(__name__)


async def gen_antagonist_ladder(svc: Any, project: Project, ctx: dict) -> list[dict]:
    """生成每卷核心对立面 roster，持久化到 Project.extra 并写入 ctx。"""
    tw = int(project.target_words or ctx.get("target_words") or 1_200_000)
    plan = words_to_plan(tw)
    n_volumes = plan["total_volumes"]

    kit_block = get_genre_kit_block(ctx)
    power_block = format_power_context_block(ctx)
    progression_block = build_protagonist_progression_prompt_block(ctx, n_volumes)

    faction_hint = ctx.get("faction_summary") or "（未设定）"
    storyline_hint = ctx.get("storyline_summary") or "（未设定）"
    villain_tl = "；".join(ctx.get("villain_timelines") or []) or "（见势力 villain_timeline）"

    system = (
        "你是有30年经验的网络小说结构策划，负责规划全书「卷级对立面阶梯」。"
        "只返回 JSON 数组，不要任何说明文字。"
    )
    prompt = f"""{kit_block}小说：《{ctx.get('project_title')}》({ctx.get('genre')})
创意：{ctx.get('logline')}
立意：{(ctx.get('premise') or '')[:600]}
{power_block}
{progression_block}
【势力摘要】{faction_hint}
【故事线】{storyline_hint}
【反派势力时间线线索】{villain_tl}

任务：为全书 **{n_volumes} 卷** 各指定 1 名「当卷核心对立角色」（卷级大 Boss）。
这是后续人物库与卷骨架的唯一 Boss 名单，禁止后续步骤另起新名。

返回 JSON 数组，**必须恰好 {n_volumes} 条**，按 vol_index 0→{n_volumes - 1} 排序：
[
  {{
    "vol_index": 0,
    "boss_name": "姓名（2~4字，全书唯一）",
    "faction": "所属势力（须用已生成势力名）",
    "realm_at_debut": "本卷初 Boss 有效境界（可带小境，如「筑基境中期」）",
    "realm_at_climax": "卷末对决境界（可带小境，如「破虚境圆满」）",
    "narrative_function": "本卷叙事功能（40字内，须具体）",
    "boss_kind": "arc_boss"
  }}
]

【铁律】
1. boss_name 全书不重复；后卷 realm_at_climax rank 严格高于前卷
2. realm_at_climax rank ≤ 同卷主角卷末预期 rank + 2（见上方主角成长路线）
3. 须标注小境：如「破虚境初期」「破虚境圆满」；同大境递进靠小境，不要求每卷换大境
4. 终局卷 Boss 须处体系次高档或最高档
只返回 JSON 数组。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.antagonist_ladder",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("antagonist_ladder", data.get("ladder", []))

    ladder = normalize_antagonist_ladder(data, ctx, n_volumes)

    try:
        base = project.extra if isinstance(project.extra, dict) else {}
        project.extra = {**base, LADDER_EXTRA_KEY: ladder}
        flag_modified(project, "extra")
        svc.db.commit()
    except Exception:
        logger.exception("antagonist_ladder 写库失败 project=%s", project.id)

    ctx[LADDER_EXTRA_KEY] = ladder
    ctx["antagonist_ladder_summary"] = format_ladder_summary(ladder)
    ctx["volume_boss_names"] = [row.get("boss_name") for row in ladder if row.get("boss_name")]

    logger.info(
        "bootstrap.antagonist_ladder 完成 project=%s 卷数=%d bosses=%s",
        project.id,
        len(ladder),
        ctx["volume_boss_names"],
    )
    return ladder
