"""Bootstrap Step 7：关键道具法宝。"""

from __future__ import annotations

import logging
import uuid as _uuid_module
from typing import Any
from uuid import UUID

from app.models import Item, Project
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.power_registry import format_power_context_block
from app.services.bootstrap.power_grade_align import enrich_item_power_fields
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

logger = logging.getLogger(__name__)


def build_key_items_prompt(project: Project, ctx: dict) -> tuple[str, str]:
    """构建关键道具 prompt（供独立步骤与合并节点共用）。"""
    system = "你是网络小说世界构建专家。只返回JSON数组。"
    kit_block = get_genre_kit_block(ctx)
    char_id_hint = ", ".join(
        f"{c['name']}（id={c['id']}）" for c in ctx.get("char_id_list", [])[:8]
    ) or "（人物列表待生成）"
    prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
主角：{ctx.get('protagonist', '主角')}
{format_power_context_block(ctx)}

【器物对齐】填写 artifact_tier（从器物轴精确选名）与 required_realm（持有者须达到的主轴境界）；rarity 与器物阶应一致。
主要人物（姓名+UUID）：{char_id_hint}
主要势力：{', '.join(ctx.get('faction_names', [])[:4])}

【流派编辑手册约束】
- 道具效果与获取必须符合 genre_kit 的 satisfaction_tropes（玄幻强调升级/打脸相关法宝）

生成本小说最重要的5~8件道具/法宝，返回JSON数组：
[
  {{
    "name": "道具/法宝名称",
    "item_type": "artifact",
    "rarity": "legendary",
    "artifact_tier": "灵宝（从器物轴精确选名）",
    "required_realm": "持有人须达到的主轴境界名",
    "description": "外观与特征描述（30字内）",
    "origin": "来历（上古遗留、宗门镇宝等）",
    "effects": "核心能力效果",
    "limitations": "使用限制（境界要求、次数、副作用）",
    "story_significance": "在故事中的重要性/象征意义",
    "current_owner_id": "当前持有人UUID（优先从上面人物id列表直接填写，或留空）",
    "current_owner_name": "当前持有人姓名（可选，用于人工核对）",
    "status": "intact",
    "plot_hook": "这件道具在故事中的剧情钩子：何时会被损毁/被夺走/持有者死亡/揭露隐藏能力/成为争夺焦点？用一句话指明触发章节范围（如：「第1卷末法宝被反派势力强夺，主角踏上复夺之路」）"
  }}
]
item_type 只能是: weapon / armor / pill / artifact / material / scroll / beast / other
rarity 只能是: common / uncommon / rare / epic / legendary / mythic / unique
status 只能是: intact / damaged / destroyed / lost / unknown
选择对主线剧情影响最大的道具，包含主角核心战力道具和1~2个关键麦高芬道具。
每件道具必须填写 plot_hook，不得留空。
只返回JSON数组，不要说明文字。"""
    return system, prompt


async def gen_key_items(svc: Any, project: Project, ctx: dict):
    """独立步骤：构建 prompt → 调用 → 落库。"""
    system, prompt = build_key_items_prompt(project, ctx)
    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.items",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("items", [])
    return persist_key_items(svc, project, ctx, data)


def persist_key_items(svc: Any, project: Project, ctx: dict, data: list):
    """落库关键道具（含持有人 UUID 校验/回退映射），供独立步骤与合并节点共用。"""
    char_name_to_id: dict = ctx.get("char_name_to_id", {})
    results = []
    for i, item in enumerate(data):
        owner_uuid_str = None
        owner_id = item.get("current_owner_id")
        if owner_id and isinstance(owner_id, str):
            try:
                _uuid_module.UUID(owner_id)
                owner_uuid_str = owner_id
            except ValueError:
                logger.warning(
                    "Item '%s' current_owner_id: AI 输出 '%s' 不是有效 UUID，尝试名字映射",
                    item.get("name", "?"), owner_id,
                )
        if owner_uuid_str is None:
            owner_name = item.get("current_owner_name") or item.get("current_owner", "") or ""
            if owner_name:
                mapped = char_name_to_id.get(owner_name)
                if mapped:
                    logger.warning(
                        "Item '%s' current_owner: 已通过名字 '%s' 回退映射到 %s",
                        item.get("name", "?"), owner_name, mapped,
                    )
                    owner_uuid_str = mapped
                else:
                    logger.warning(
                        "Item '%s' current_owner: '%s' 不在人物列表，owner_id 置空",
                        item.get("name", "?"), owner_name,
                    )
        item_extra = {}
        if item.get("plot_hook"):
            item_extra["plot_hook"] = str(item["plot_hook"])[:300]
        aligned = enrich_item_power_fields(item, ctx)
        for k in ("power_ref", "artifact_tier", "required_realm"):
            if aligned.get(k) is not None:
                item_extra[k] = aligned[k]
        it = Item(
            project_id=project.id,
            name=item.get("name", f"道具{i+1}"),
            item_type=item.get("item_type", "artifact"),
            rarity=item.get("rarity", "rare"),
            description=item.get("description"),
            origin=item.get("origin"),
            effects=item.get("effects"),
            limitations=item.get("limitations"),
            story_significance=item.get("story_significance"),
            status=item.get("status", "intact"),
            current_owner_id=UUID(owner_uuid_str) if owner_uuid_str else None,
            sort_order=i,
            extra=item_extra,
        )
        svc.db.add(it)
        results.append(it)

    svc.db.commit()
    ctx["item_names"] = [it.name for it in results]
    return results
