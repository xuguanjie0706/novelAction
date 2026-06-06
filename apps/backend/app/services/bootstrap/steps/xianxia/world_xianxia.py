"""修仙直白线 Step：世界设定卡（replaces 通用/番茄 settings）。

设计：复用通用 ``gen_settings`` 的持久化与蓝图引擎（零 schema 漂移），但
1. 只选修仙直白文最核心的世界蓝图子集（灵气根基/突破代价/资源经济/秘境/妖兽/上古秘辛）；
2. 注入修仙 prompt_addon，强制以灵气-灵根-天劫-丹器阵符为底层语义，且与境界主轴/金手指咬合。
红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.prompts import GEMINI_SETTING_BLUEPRINTS
from app.services.bootstrap.steps.settings import gen_settings

# 修仙直白文核心世界蓝图（按 title 从通用蓝图精选，保证 schema 一致）
_XIANXIA_BLUEPRINT_TITLES = (
    "世界底层规则",            # 灵气/修炼根基
    "突破副作用与失败代价",    # 核心：防升级廉价化（与境界契约张力呼应）
    "资源经济与稀缺机制",      # 灵石/灵药/灵脉
    "大陆地图与地缘格局",      # 洲-域地缘
    "核心宗门或学院地貌",      # 宗门舞台
    "禁地与高危秘境",          # 夺宝/副本
    "妖兽生态与危险等级",      # 野外战斗/材料
    "远古战争与失落真相",      # 上古秘辛/主角传承根源
)

_XIANXIA_ADDON = (
    "【修仙直白文世界语义铁律】\n"
    "1. 底层力量统一以『灵气/灵根/经脉/神识』为根基；修炼=吸纳灵气淬炼己身，"
    "境界名必须与本书境界主轴一致，禁止另造平行体系。\n"
    "2. 『突破副作用与失败代价』卡须写清：每次大境突破要渡何种劫/瓶颈/反噬，"
    "与境界预算契约『慢爬』节奏呼应——变强必须有阻力与代价。\n"
    "3. 『资源经济』卡须落地灵石/灵药/灵脉/天材地宝的获取-垄断-争夺链，"
    "它是数值爽点（夺宝/暴富突破）的燃料。\n"
    "4. 与金手指咬合：若某设定能被金手指利用或制约，请在 content 中点明。\n"
    "5. 白话直给，禁止意境化堆砌；每张卡要有可直接写进正文的名词、规则、代价、冲突。"
)


def _xianxia_blueprints() -> list:
    by_title = {bp.get("title"): bp for bp in GEMINI_SETTING_BLUEPRINTS}
    picked = [by_title[t] for t in _XIANXIA_BLUEPRINT_TITLES if t in by_title]
    return picked or GEMINI_SETTING_BLUEPRINTS[:8]


async def gen_world_xianxia(svc: Any, project: Project, ctx: dict):
    """生成修仙世界设定卡（精选蓝图 + 修仙语义 addon）。"""
    return await gen_settings(
        svc, project, ctx,
        blueprints=_xianxia_blueprints(),
        prompt_addon=_XIANXIA_ADDON,
    )
