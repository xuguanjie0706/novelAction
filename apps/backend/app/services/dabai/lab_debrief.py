"""dabai 实验书架章节复盘 — 低温提取记忆条目 + 线索埋设/回收，落库幂等。

记忆写 ``dabai_memories``（重跑先删同章旧记忆）；线索写 ``dabai_clues``
（新线索按标题去重，回收按 id 精确标记）。与精品文 MemoryChunk/Foreshadow
链路完全隔离，不依赖 pgvector/图谱。
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiClue, DabaiMemory
from app.services.dabai.lab_ledger import (
    apply_ledger_changes, build_ledger_block, build_panel_snapshot,
    prune_noise_assets, seed_ledgers, sync_protagonist_realm,
)

logger = logging.getLogger(__name__)

DEBRIEF_VERSION = "dabai-lab-debrief-v1"

_MEM_TYPES = {"fact", "event", "state", "relation", "summary"}
_CLUE_TYPES = {"hook", "foreshadow", "promise"}

_DEBRIEF_SYSTEM = (
    "你是网文责编助理，负责章末复盘：从正文中提取后续写作必须记住的事实，"
    "并维护线索台账。只提取正文中**实际发生**的内容，禁止臆测未写剧情。只返回 JSON。"
)


def _build_debrief_prompt(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    open_clues: list[DabaiClue],
    ledger_block: str = "",
) -> tuple[str, str]:
    """构造复盘提取 (system, user)。ledger_block 为当前台账，供 LLM 判断变更。"""
    content = re.sub(r"<[^>]+>", "", ch.content or "").strip()
    head = content[:5000]
    tail = content[-1500:] if len(content) > 6500 else ""

    names = [c.name for c in project.characters if c.name]
    clue_lines = [
        f"  - id={c.id} 《{c.title}》（第{c.chapter_planted}章埋设）：{(c.description or '')[:60]}"
        for c in open_clues[:20]
    ]

    parts = [
        f"《{project.title or project.logline}》第{ch.chapter_number}章《{ch.title or ''}》复盘。",
        "【标准人名清单（记忆 tags 必须用以下名字，禁止「主角」等代称）】\n" + "、".join(names[:30]),
    ]
    if clue_lines:
        parts.append("【当前未回收线索（判断本章是否回收）】\n" + "\n".join(clue_lines))
    if ledger_block.strip():
        parts.append(ledger_block.strip() + "\n（对照判断本章资产/关系是否变化）")
    parts.append(f"【本章正文（开头部分）】\n{head}")
    if tail:
        parts.append(f"【本章正文（结尾部分）】\n{tail}")
    parts.append(
        "【资产变更约束】asset_changes 禁止写入修为点/修为/经验点等系统内部计数；"
        "golden_finger 仅限全书金手指本名（非系统面板词）。"
    )
    parts.append(
        "提取后只返回 JSON：\n"
        "{\n"
        '  "summary": "本章一句话事实摘要（谁在哪做了什么、结果如何），≤60字",\n'
        '  "memories": [  // 3-8条，后续章节写作必须记住的事实\n'
        '    {"type": "fact|event|state|relation", "content": "≤60字陈述句",\n'
        '     "importance": 1-5, "tags": ["涉及人名"]}\n'
        "  ],\n"
        '  "new_clues": [  // 本章新埋设的钩子/伏笔/对读者的承诺（章末钩子必收录为 hook）\n'
        '    {"title": "≤20字", "type": "hook|foreshadow|promise", "description": "≤60字"}\n'
        "  ],\n"
        '  "resolved_clue_ids": ["上方未回收线索中，本章已明确回收的 id；无则[]"],\n'
        '  "asset_changes": [  // 本章功法/道具/金手指的实际变化；无则[]\n'
        '    {"action": "gain|use|consume|lose|upgrade", "kind": "skill|item|golden_finger",\n'
        '     "name": "≤20字", "owner": "持有者人名", "note": "≤40字",\n'
        '     "grade": 0-4或null, "base_stat": {"atk":数值,...}或null,\n'
        '     "cooldown_chapters": 技能冷却章数或null}\n'
        '  // action=use：本章主动施展了某技能（更新冷却计时，技能仍active）\n'
        "  ],\n"
        '  "relation_changes": [  // 人物对主角态度的实际变化（如打脸后跪服）；无则[]\n'
        '    {"from": "主角人名", "to": "对方人名", "attitude": "敌对|轻视|忌惮|臣服|效忠|盟友|暧昧|中立",\n'
        '     "reason": "≤30字变化原因"}\n'
        "  ],\n"
        '  "realm_snapshot": {   // 章末主角境界精确快照（系统文核心；必填）\n'
        '    "realm": "大境界名称，如筑基期",\n'
        '    "sub_level": 当前小境界层数（整数，如3），无则null,\n'
        '    "max_sub": 该大境界最大层数（整数，如9），无则null,\n'
        '    "combat_power": 战力估算数值（整数，参考境界档位合理估算），无则null,\n'
        '    "location": "章末主角所在的具体地点，≤15字（下一章开笔位置基准）"，无法判断则null\n'
        "  }\n"
        "}"
    )
    return _DEBRIEF_SYSTEM, "\n\n".join(parts)


def _persist_memories(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline, result: dict,
) -> list[DabaiMemory]:
    """同章旧记忆先删（幂等），summary 也作为一条 summary 类型记忆落库。"""
    db.query(DabaiMemory).filter(DabaiMemory.chapter_id == ch.id).delete(
        synchronize_session=False,
    )
    rows: list[DabaiMemory] = []
    items = list(result.get("memories") or [])[:10]
    summary = str(result.get("summary") or "").strip()
    if summary:
        items.insert(0, {"type": "summary", "content": summary, "importance": 4, "tags": []})
    for item in items:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        mem_type = str(item.get("type") or "event").lower()
        try:
            importance = max(1, min(5, int(item.get("importance") or 3)))
        except (TypeError, ValueError):
            importance = 3
        rows.append(DabaiMemory(
            project_id=project.id, chapter_id=ch.id,
            chapter_number=ch.chapter_number,
            mem_type=mem_type if mem_type in _MEM_TYPES else "event",
            content=content[:300], importance=importance,
            tags=[str(t)[:40] for t in (item.get("tags") or [])][:6],
        ))
    db.add_all(rows)
    return rows


def _persist_clues(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline,
    result: dict, open_clues: list[DabaiClue],
) -> tuple[list[DabaiClue], list[DabaiClue]]:
    """新线索按标题去重；回收按 id 精确匹配 open 线索。"""
    existing_titles = {
        t for (t,) in db.query(DabaiClue.title).filter(DabaiClue.project_id == project.id)
    }
    created: list[DabaiClue] = []
    for item in list(result.get("new_clues") or [])[:6]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:60]
        if not title or title in existing_titles:
            continue
        clue_type = str(item.get("type") or "hook").lower()
        created.append(DabaiClue(
            project_id=project.id, title=title,
            clue_type=clue_type if clue_type in _CLUE_TYPES else "hook",
            description=str(item.get("description") or "")[:300],
            chapter_planted=ch.chapter_number, status="open", source="debrief",
        ))
        existing_titles.add(title)
    db.add_all(created)

    open_by_id = {str(c.id): c for c in open_clues}
    resolved: list[DabaiClue] = []
    for raw_id in list(result.get("resolved_clue_ids") or [])[:10]:
        clue = open_by_id.get(str(raw_id).strip())
        if clue and clue.status == "open":
            clue.status = "resolved"
            clue.chapter_resolved = ch.chapter_number
            resolved.append(clue)
    return created, resolved


async def run_lab_debrief(
    svc,
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
) -> dict:
    """lab 复盘入口：提取 + 落库，幂等可重跑。"""
    if not (ch.content or "").strip():
        raise ValueError("本章尚无正文，无法复盘")

    seed_ledgers(db, project)
    open_clues = (
        db.query(DabaiClue)
        .filter(DabaiClue.project_id == project.id, DabaiClue.status == "open")
        .order_by(DabaiClue.chapter_planted)
        .all()
    )

    from app.services.bootstrap.parse import parse_json
    from app.services.bootstrap.retry import call_with_retry

    ledger_block = build_ledger_block(db, project, ch)
    system, user = _build_debrief_prompt(project, ch, open_clues, ledger_block)
    raw = await call_with_retry(
        svc, system, user, max_tokens=2200, task="dabai.debrief",
    )
    result = parse_json(raw)
    if not isinstance(result, dict):
        raise ValueError("复盘 JSON 解析失败")

    memories = _persist_memories(db, project, ch, result)
    created, resolved = _persist_clues(db, project, ch, result, open_clues)
    asset_logs, relation_logs = apply_ledger_changes(db, project, ch, result)
    prune_noise_assets(db, project)
    realm_label = sync_protagonist_realm(db, project, ch, memories=memories)

    # 系统面板快照：复盘结束后立即存档，作为下章写作的数值绝对基准
    realm_info = result.get("realm_snapshot") if isinstance(result.get("realm_snapshot"), dict) else None
    try:
        build_panel_snapshot(db, project, ch, realm_info=realm_info)
    except Exception as _snap_err:  # noqa: BLE001
        logger.warning("面板快照写入失败 ch=%s: %s", ch.id, _snap_err)

    db.commit()
    payload = {
        "version": DEBRIEF_VERSION,
        "summary": str(result.get("summary") or "")[:200],
        "memory_count": len(memories),
        "new_clues": [c.title for c in created],
        "resolved_clues": [c.title for c in resolved],
        "asset_changes": asset_logs,
        "relation_changes": relation_logs,
    }
    if realm_label:
        payload["protagonist_realm"] = realm_label
    if realm_info:
        payload["realm_snapshot"] = {
            "sub_level": realm_info.get("sub_level"),
            "max_sub": realm_info.get("max_sub"),
            "combat_power": realm_info.get("combat_power"),
        }
    return payload
