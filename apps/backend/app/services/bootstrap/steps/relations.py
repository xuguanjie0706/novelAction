"""Bootstrap Step 11：人物关系。"""

from __future__ import annotations

from typing import Any

from app.models import CharacterRelationship, Project
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_relations(svc: Any, project: Project, chars: list, ctx: dict):
    if len(chars) < 2:
        return []

    core_names = set(ctx.get("core_char_names", [c.name for c in chars]))
    relation_chars = [c for c in chars if c.name in core_names]
    if len(relation_chars) < 2:
        relation_chars = chars

    name_map = {c.name: c for c in chars}
    debt_summary = "; ".join(
        f"{c.name}→欠债:{c.extra.get('debt_to','')}(第{c.extra.get('detonation_vol',0)}卷引爆)"
        for c in relation_chars
        if c.extra and c.extra.get("debt_to", "").strip()
    )
    system = "你是人物关系设计专家。只返回JSON数组。"
    prompt = f"""人物列表：{', '.join(c.name for c in relation_chars)}
创意：{ctx['logline']}
已知欠债关系（请让关系设计与欠债相互呼应）：{debt_summary or '（无）'}

生成人物关系（覆盖所有核心人物，每对关系1条），返回JSON数组：
[
  {{
    "from_name": "人物A", "to_name": "人物B",
    "relation_type": "师徒",
    "description": "关系现状描述（15字内）",
    "intensity": 8,
    "unresolved_tension": "这段关系中悬而未决的张力/恩怨/信息差（20字内；若纯粹积极关系，写潜在的分歧或考验）",
    "trigger_event": "什么事件会让这段关系发生质变？（15字内，要具体）"
  }}
]
intensity 为 1~10 的整数，只能使用上面列出的人物名。
unresolved_tension 和 trigger_event 为必填，不能为空或敷衍。"""

    try:
        raw = await svc._call_with_retry(
            system,
            prompt,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.relations",
        )
        data = parse_json(raw)
        if not isinstance(data, list):
            data = data.get("relations", [])
    except Exception:
        return []

    results = []
    for item in data:
        from_char = name_map.get(item.get("from_name", ""))
        to_char = name_map.get(item.get("to_name", ""))
        if not from_char or not to_char:
            continue
        tension = (item.get("unresolved_tension") or "").strip()
        trigger = (item.get("trigger_event") or "").strip()
        evolution_note_parts = []
        if tension:
            evolution_note_parts.append(f"[张力]{tension}")
        if trigger:
            evolution_note_parts.append(f"[引爆事件]{trigger}")
        evolution_note = "；".join(evolution_note_parts) or None
        rel = CharacterRelationship(
            project_id=project.id,
            from_character_id=from_char.id,
            to_character_id=to_char.id,
            relation_type=item.get("relation_type", "认识"),
            description=item.get("description"),
            intensity=int(item.get("intensity", 5)),
            evolution_note=evolution_note,
        )
        svc.db.add(rel)
        results.append(rel)

    svc.db.commit()

    ctx["relation_triggers"] = "; ".join(
        f"{item.get('from_name','?')}↔{item.get('to_name','?')}[{item.get('trigger_event','')}]"
        for item in data
        if item.get("trigger_event", "").strip()
    )

    return results
