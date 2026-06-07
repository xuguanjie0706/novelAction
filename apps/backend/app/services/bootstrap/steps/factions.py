"""Bootstrap Step 3：势力体系。"""

from __future__ import annotations

from typing import Any

from app.models import Faction, Project
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.power_registry import format_power_context_block
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_factions(svc: Any, project: Project, ctx: dict):
    system = "你是网络小说世界构建专家。只返回JSON数组。"
    kit_block = get_genre_kit_block(ctx)
    prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
世界观：{ctx['world_overview'][:300]}
{format_power_context_block(ctx)}

【流派编辑手册约束】
- 势力定位与冲突必须符合 genre_kit 的 satisfaction_tropes（玄幻多宗门/打脸、悬疑多嫌疑人互咬、言情多家族/情敌）

生成本小说的主要势力/组织（4~6个），返回JSON数组：
[
  {{
    "name": "势力名称",
    "faction_type": "sect",
    "alignment": "antagonist",
    "active_period": "early",
    "description": "势力特色与定位（60字内）",
    "territory": "领地/活动范围",
    "strength_level": "实力级别（如：顶级宗门，坐镇一名斗宗）",
    "member_count": "成员规模",
    "top_power": "最强战力描述",
    "goals": "势力目标与图谋",
    "resources": "势力核心资源/特产",
    "history": "势力历史背景（30字）",
    "secrets": "势力不为人知的秘密/隐藏阴谋（供作者参考）",
    "rivals": ["竞争势力名"],
    "allies": ["盟友势力名"],
    "attitude_to_protagonist": "hostile",
    "internal_factions": "势力内部的派系博弈（至少2派，各有代表人物与目标差异，50字内；protagonist阵营与neutral阵营也必须填写，写'改革派vs保守派'等内部张力）",
    "villain_timeline": "【仅 antagonist 阵营填写，其余填空字符串】若主角什么都不做，这股势力会在第几卷完成什么阴谋？被主角打断后的应对策略是什么？（70字内，具体到卷号）"
  }}
]
faction_type 只能是: sect / kingdom / family / guild / evil / race / other
alignment 只能是: protagonist / neutral / antagonist / unknown
active_period 只能是: early / mid / late / full
attitude_to_protagonist 只能是: friendly / hostile / neutral / subordinate / superior
必须涵盖主角阵营势力、核心反派势力、中立势力各至少1个。
villain_timeline 对 antagonist 类势力为必填，要求具体到"第X卷前完成xxx，主角若干预则转为yyy策略"。
只返回JSON数组，不要说明文字。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.factions",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("factions", [])

    results = persist_factions(svc, project, data)
    set_faction_ctx(ctx, results)
    return results


def persist_factions(svc: Any, project: Project, data: list) -> list:
    """把势力 JSON 列表落库为 Faction 行（供独立步骤与合并节点共用）。"""
    results = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        f = Faction(
            project_id=project.id,
            name=item.get("name", f"势力{i+1}"),
            faction_type=item.get("faction_type", "sect"),
            alignment=item.get("alignment", "neutral"),
            description=item.get("description"),
            territory=item.get("territory"),
            strength_level=item.get("strength_level"),
            member_count=item.get("member_count"),
            top_power=item.get("top_power"),
            goals=item.get("goals"),
            resources=item.get("resources"),
            history=item.get("history"),
            secrets=item.get("secrets"),
            rivals=item.get("rivals", []),
            allies=item.get("allies", []),
            attitude_to_protagonist=item.get("attitude_to_protagonist", "neutral"),
            sort_order=i,
            extra={
                "active_period": item.get("active_period", ""),
                "internal_factions": item.get("internal_factions", ""),
                "villain_timeline": item.get("villain_timeline", ""),
            },
        )
        svc.db.add(f)
        results.append(f)

    svc.db.commit()
    return results


def set_faction_ctx(ctx: dict, results: list) -> None:
    """把势力结果写入 ctx（faction_summary / names / id 映射 / villain_timelines）。"""
    ctx["faction_summary"] = "、".join(
        f"{f.name}（{f.alignment}，{f.extra.get('active_period','')}期）"
        for f in results
    )
    ctx["faction_names"] = [f.name for f in results]
    ctx["faction_name_to_id"] = {f.name: str(f.id) for f in results}
    ctx["villain_timelines"] = [
        f"{f.name}：{f.extra.get('villain_timeline', '')}"
        for f in results
        if f.alignment == "antagonist" and f.extra.get("villain_timeline", "").strip()
    ]
