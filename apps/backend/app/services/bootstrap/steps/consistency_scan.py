"""Bootstrap Step 14：全局一致性扫描。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.services.bootstrap.parse import parse_json


async def gen_consistency_scan(svc: Any, project, ctx: dict) -> list:
    system = (
        "你是有30年经验的网络小说总编辑，专门做稿件前置审核。"
        "只返回 JSON 数组，不要任何解释文字。"
    )

    power_summary = ctx.get("power_summary", "（未设定）")
    faction_summary = ctx.get("faction_summary", "（未设定）")
    char_realms = ctx.get("char_realms", {})
    char_names = ctx.get("char_names", [])
    skill_names = ctx.get("skill_names", [])
    item_names = ctx.get("item_names", [])
    storyline_summary = ctx.get("storyline_summary", "（未设定）")
    volumes_summary = ctx.get("volumes_summary", "（未设定）")
    protagonist = ctx.get("protagonist", "主角")

    char_realm_lines = "\n".join(
        f"- {name}：境界={realm}" for name, realm in char_realms.items()
    )

    prompt = f"""小说：《{ctx.get('project_title', '未命名')}》（{ctx.get('genre', '')}）

【境界体系】
{power_summary}

【势力档案摘要】
{faction_summary}

【人物+当前境界】
{char_realm_lines or '（未设定）'}

【人物列表】{', '.join(char_names)}
主角：{protagonist}
主角起点境界（power_systems 中 protagonist_start_rank 对应名称）：{ctx.get('power_level_names', ['（未知）'])[0] if ctx.get('power_level_names') else '（未知）'}

【已生成技能】{', '.join(skill_names) or '（无）'}
【已生成道具】{', '.join(item_names) or '（无）'}

【故事线】
{storyline_summary}

【卷级骨架】
{volumes_summary}

请对以上信息做「交叉核验」，找出所有显著矛盾或风险项，返回JSON数组：
[
  {{
    "severity": "high/medium/low",
    "type": "realm_mismatch/faction_mismatch/skill_requirement/storyline_gap/timeline_conflict/other",
    "description": "具体矛盾描述，举例说明哪里和哪里不一致（30字内）",
    "suggestion": "最简单的修复建议（20字内）"
  }}
]

检查重点：
1. 人物卡中 current_realm 是否在境界体系 levels 的合法名称里？
2. 主角和重要人物的 faction 是否与势力档案中的势力名吻合（允许模糊匹配）？
3. 故事线类型（main/sub/romance等）与卷骨架描述的冲突走向是否吻合？
4. 若有多条故事线，是否都能在卷骨架中找到对应的推进节点？
5. 境界体系 protagonist_start_rank 与主角人物卡 current_realm 是否对应同一境界？
如果没有发现矛盾，返回空数组 []。只返回JSON数组，不要任何解释。"""

    try:
        raw = await svc._call_with_retry(
            system, prompt, max_tokens=2048, task="bootstrap.consistency_scan"
        )
        issues = parse_json(raw)
        if not isinstance(issues, list):
            issues = []
    except Exception:
        issues = []

    try:
        # 必须换新 dict 并 flag_modified：原地改 JSON 列同一对象时 SQLAlchemy 可能不刷盘，
        # 会导致 SSE count 与 getInsights 读到的 extra 不一致。
        base = project.extra if isinstance(project.extra, dict) else {}
        project.extra = {**base, "consistency_issues": issues}
        flag_modified(project, "extra")
        svc.db.commit()
    except Exception:
        pass

    return issues
