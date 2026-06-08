"""斗破线 Step 8：精简斗气大陆世界设定卡（replaces 通用 settings）。

「设定内容减少」：复用通用 ``gen_settings`` 的持久化与蓝图引擎（零 schema 漂移），但
1. 只选斗气大陆纯爽文最必要的 6 张世界蓝图（通用线默认 ~10+ 张）；
2. 注入斗破 addon，强制以『斗气/斗技品阶/丹药/异火/炼药师』为底层语义，
   严禁修仙灵气/天劫/飞剑设定，且与斗气主轴 / 金手指咬合、全程白话直给。
红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.prompts import GEMINI_SETTING_BLUEPRINTS
from app.services.bootstrap.prompts.doupo_prompts import (
    DOUPO_BLUEPRINT_TITLES,
    DOUPO_SETTINGS_ADDON,
)
from app.services.bootstrap.steps.settings import gen_settings


def _doupo_blueprints() -> list:
    by_title = {bp.get("title"): bp for bp in GEMINI_SETTING_BLUEPRINTS}
    picked = [by_title[t] for t in DOUPO_BLUEPRINT_TITLES if t in by_title]
    # 精选不到则退回通用前 6 张（仍比默认精简）
    return picked or GEMINI_SETTING_BLUEPRINTS[:6]


async def gen_world_doupo(svc: Any, project: Project, ctx: dict):
    """生成精简斗气大陆世界设定卡（6张蓝图 + 斗破语义 addon）。"""
    return await gen_settings(
        svc, project, ctx,
        blueprints=_doupo_blueprints(),
        prompt_addon=DOUPO_SETTINGS_ADDON,
    )
