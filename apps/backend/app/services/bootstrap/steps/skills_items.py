"""Bootstrap Step 6+7 合并：核心功法技能 + 关键道具一次 LLM 生成。

原 node_skills_items 并行两次调用（skills ∥ items）；二者输入同为境界轴 + 人物列表，
合并为一次调用省一次 LLM 请求（与 narrative_arcs 同模式）。产物仍分别落库 Skill /
Item 表，下游 ctx 键（skill_names / item_names）不变；UI 仍 emit 两个 step 事件。

复用各步已抽出的 build_*_prompt / persist_* helper，技能的 mastered_by 境界校验、
道具的持有人 UUID 回退等关键逻辑原样保留，不随合并漂移。

健壮性：合并响应缺哪部分就回退对应独立步骤——最坏退化为今天的两次调用。

红线：本文件 ≤ 600 行。
"""

from __future__ import annotations

import logging
from typing import Any

from app.models import Project
from app.services.bootstrap.narrative_arc_gen import call_json_object_with_retry
from app.services.bootstrap.steps.items import build_key_items_prompt, persist_key_items
from app.services.bootstrap.steps.skills import build_key_skills_prompt, persist_key_skills

logger = logging.getLogger(__name__)


def _build_merged_prompt(svc: Any, project: Project, ctx: dict) -> tuple[str, str]:
    """把功法 prompt 与道具 prompt 包成一次「合并返回」调用。"""
    _, sk_prompt = build_key_skills_prompt(svc, project, ctx)
    _, it_prompt = build_key_items_prompt(project, ctx)
    system = (
        "你是网络小说世界构建专家，一次完成功法技能与关键道具两项设计并合并返回。"
        "忽略下面两个子任务结尾「只返回JSON数组」的措辞，以最外层合并结构为准。"
        "只返回一个 JSON 对象，不要任何解释文字。"
    )
    prompt = f"""你要一次完成两项设计，最终合并为**一个 JSON 对象**返回。

═══════════ 子任务一：核心功法技能（输出到键 "skills"，值是数组）═══════════
{sk_prompt}

═══════════ 子任务二：关键道具法宝（输出到键 "items"，值是数组）═══════════
{it_prompt}

═══════════ 合并返回（最高优先级，覆盖以上两段的「只返回」措辞）═══════════
只返回如下结构，不要任何解释：
{{"skills": <子任务一的 JSON 数组>, "items": <子任务二的 JSON 数组>}}
功法与道具应彼此呼应：标志性功法可对应一件承载它的法宝。"""
    return system, prompt


async def gen_skills_items(svc: Any, project: Project, ctx: dict) -> tuple[list, list]:
    """一次生成功法 + 道具，分别落库；缺失部分回退独立步骤。

    Returns:
        (skills, items) 两个 ORM 列表。
    """
    system, prompt = _build_merged_prompt(svc, project, ctx)

    data: Any = {}
    try:
        data = await call_json_object_with_retry(svc, system, prompt, task="bootstrap.skills_items")
    except Exception:
        logger.warning("skills_items 合并调用失败，回退独立步骤 project=%s", project.id, exc_info=True)
        data = {}
    if not isinstance(data, dict):
        data = {}

    skills_data = data.get("skills")
    skills_data = skills_data if isinstance(skills_data, list) else []
    items_data = data.get("items")
    items_data = items_data if isinstance(items_data, list) else []

    # ── 功法（缺失则回退独立步骤）──────────────────────────────────────────
    if skills_data:
        skills = persist_key_skills(svc, project, ctx, skills_data)
    else:
        logger.warning("skills_items 合并响应缺 skills，回退独立步骤 project=%s", project.id)
        from app.services.bootstrap.steps.skills import gen_key_skills
        skills = await gen_key_skills(svc, project, ctx)

    # ── 道具（缺失则回退独立步骤）──────────────────────────────────────────
    if items_data:
        items = persist_key_items(svc, project, ctx, items_data)
    else:
        logger.warning("skills_items 合并响应缺 items，回退独立步骤 project=%s", project.id)
        from app.services.bootstrap.steps.items import gen_key_items
        items = await gen_key_items(svc, project, ctx)

    logger.info(
        "bootstrap.skills_items 完成 project=%s 功法=%d 道具=%d",
        project.id, len(skills), len(items),
    )
    return skills, items
