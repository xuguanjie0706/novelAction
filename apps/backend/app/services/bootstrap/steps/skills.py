"""Bootstrap Step 6：核心功法技能。"""

from __future__ import annotations

import logging
import uuid as _uuid_module
from typing import Any

from app.models import Project, Skill
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

logger = logging.getLogger(__name__)


async def gen_key_skills(svc: Any, project: Project, ctx: dict):
    system = "你是网络小说世界构建专家。只返回JSON数组。"
    kit_block = get_genre_kit_block(ctx)
    char_id_hint = ", ".join(
        f"{c['name']}（id={c['id']}）" for c in ctx.get("char_id_list", [])[:8]
    ) or "（人物列表待生成）"
    prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
主角：{ctx.get('protagonist', '主角')}
境界体系：{ctx.get('power_summary', '（未设定）')}
主要人物（姓名+UUID）：{char_id_hint}

【流派编辑手册约束】
- 技能效果与获取方式必须符合 genre_kit 的 satisfaction_tropes（玄幻强调金手指新用法，仙侠强调心魔/渡劫相关）

生成本小说最关键的5~8个功法/技能，返回JSON数组：
[
  {{
    "name": "功法/技能名称",
    "skill_type": "combat",
    "grade": "earth",
    "source": "来源（如：上古秘典、宗门传承）",
    "level_required": "修炼要求（境界，如：斗者三星以上）",
    "description": "功法/技能描述（40字内）",
    "effects": "使用效果",
    "limitations": "使用限制或副作用",
    "mastered_by_character_ids": ["直接填写上面人物的UUID字符串列表，优先使用id字段"],
    "mastered_by_names": ["对应的人物姓名（可选，用于人工核对）"],
    "plot_hook": "这个技能/功法在故事中的剧情钩子：何时会被损毁/被夺走/被超越/失效/揭露禁忌代价？用一句话指明触发章节范围（如：「第2卷高潮时主角核心功法被反派破解，被迫觉醒隐藏传承」）"
  }}
]
skill_type 只能是: combat / defense / movement / support / bloodline / special
grade 只能是: mortal / earth / sky / profound / saint / divine / supreme
选择对故事最重要的技能，包含主角核心战技和1~2个反派标志性技能。
每个技能必须填写 plot_hook，不得留空。
只返回JSON数组，不要说明文字。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.skills",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("skills", [])

    char_name_to_id: dict = ctx.get("char_name_to_id", {})
    results = []
    for i, item in enumerate(data):
        raw_ids = item.get("mastered_by_character_ids") or item.get("mastered_by", [])
        mastered_ids = []
        for val in raw_ids:
            if isinstance(val, str):
                try:
                    _uuid_module.UUID(val)
                    mastered_ids.append(val)
                except ValueError:
                    mapped = char_name_to_id.get(val)
                    if mapped:
                        logger.warning(
                            "Skill '%s' mastered_by: AI 输出名字 '%s' 而非 UUID，已回退映射到 %s",
                            item.get("name", "?"), val, mapped,
                        )
                        mastered_ids.append(mapped)
                    else:
                        logger.warning(
                            "Skill '%s' mastered_by: AI 输出 '%s' 既非 UUID 也不在人物列表，已丢弃",
                            item.get("name", "?"), val,
                        )
        skill_extra = {}
        if item.get("plot_hook"):
            skill_extra["plot_hook"] = str(item["plot_hook"])[:300]
        sk = Skill(
            project_id=project.id,
            name=item.get("name", f"功法{i+1}"),
            skill_type=item.get("skill_type", "combat"),
            grade=item.get("grade", "earth"),
            source=item.get("source"),
            level_required=item.get("level_required"),
            description=item.get("description"),
            effects=item.get("effects"),
            limitations=item.get("limitations"),
            mastered_by_character_ids=mastered_ids,
            sort_order=i,
            extra=skill_extra,
        )
        svc.db.add(sk)
        results.append(sk)

    svc.db.commit()
    ctx["skill_names"] = [sk.name for sk in results]
    return results
