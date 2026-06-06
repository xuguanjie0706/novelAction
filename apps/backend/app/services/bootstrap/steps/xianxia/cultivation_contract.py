"""番茄·修仙线 Step：境界轴 + 境界预算契约（replaces 通用 power_systems）。

职责
----
1. 生成修仙境界主轴（复用番茄 ``gen_cultivation_ladder``：8–12 大境 × 四小境，
   同步 PowerSystem 表，hydrate ctx 的 power_level_names / power_systems_full）。
2. 在卷生成之前，**算定全书境界预算契约**并落库为单一事实源
   （``Project.extra.cultivation_contract`` + ``ctx['cultivation_contract']``）。

与番茄线的关键区别：番茄线 ``node_power_ladder`` 按 ``is_xianxia_archetype`` 在
社会阶梯/境界轴之间分叉；本步骤**无条件走境界轴**（mode=xianxia 已由用户显式选定），
并额外产出契约，让「第一卷修满」在卷生成阶段被硬执行而非软提示。
红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models import Project
from app.services.bootstrap.cultivation_budget import contract_from_ctx
from app.services.outline_planning import words_to_plan

logger = logging.getLogger(__name__)


async def gen_cultivation_contract(svc: Any, project: Project, ctx: dict) -> dict:
    """生成境界主轴并落库境界预算契约。

    @returns 境界轴 dict（axis_kind="cultivation"，供薄壳判定步骤成功）。
    @raises BootstrapStepError: 境界轴 JSON 解析/校验失败（沿用 cultivation_ladder）。
    """
    from app.services.bootstrap.steps.fanqie.cultivation_ladder import (
        gen_cultivation_ladder,
    )

    ladder = await gen_cultivation_ladder(svc, project, ctx)

    tw = int(project.target_words or 1_200_000)
    n_volumes = words_to_plan(tw)["total_volumes"]
    contract = contract_from_ctx(ctx, n_volumes)

    if contract:
        ctx["cultivation_contract"] = contract
        extra = dict(project.extra or {})
        extra["cultivation_contract"] = contract
        project.extra = extra
        flag_modified(project, "extra")
        svc.db.commit()
        logger.info(
            "xianxia.cultivation_contract project=%s 卷数=%d 主角 rank %d→%d",
            project.id, n_volumes, contract["start_rank"], contract["end_rank"],
        )
    else:
        logger.warning(
            "xianxia.cultivation_contract 未能装配契约（缺 power_level_names）project=%s",
            project.id,
        )
    return ladder
