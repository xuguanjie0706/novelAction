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
from app.services.dabai.lab_char_voice import resolve_char_realm
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
    realm_lines = [
        f"  - {c.name}：{resolve_char_realm(c)}"
        for c in project.characters
        if c.name and resolve_char_realm(c) and not (
            (c.role or "").find("主角") >= 0
        )
    ][:20]
    clue_lines = [
        f"  - id={c.id} 《{c.title}》（第{c.chapter_planted}章埋设）：{(c.description or '')[:60]}"
        for c in open_clues[:20]
    ]

    parts = [
        f"《{project.title or project.logline}》第{ch.chapter_number}章《{ch.title or ''}》复盘。",
        "【已建档人物（记忆 tags 必须用这些名字，禁止「主角」等代称；"
        "这些人勿放入 new_characters）】\n" + "、".join(names[:40]),
    ]
    if realm_lines:
        parts.append(
            "【配角档案境界（写 state/fact 记忆时须与此一致；正文若写错层数勿照抄，"
            "应按档案纠正；仅当正文明确描写该配角突破/跌境才可更新）】\n"
            + "\n".join(realm_lines)
        )
    if clue_lines:
        parts.append("【当前未回收线索（判断本章是否回收）】\n" + "\n".join(clue_lines))
    if ledger_block.strip():
        parts.append(ledger_block.strip() + "\n（对照判断本章资产/关系是否变化）")
    parts.append(f"【本章正文（开头部分）】\n{head}")
    if tail:
        parts.append(f"【本章正文（结尾部分）】\n{tail}")
    parts.append(
        "【限知记忆边界】summary/memories 只写主角合理已知（亲眼看见、亲耳听见、"
        "亲身经历或有证据可推断）的事实。若正文误含『与此同时/另一边』式幕后切镜，"
        "不得把幕后人物的内心判断、秘密决定或远程反应写成主角已知记忆；"
        "只能记录主角在现场获得的线索。"
    )
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
        '    {"title": "≤20字", "type": "hook|foreshadow|promise", "description": "≤60字",\n'
        '     "hook_category": "13式钩子之一（仅type=hook时填，见下）或null"}\n'
        '    // hook_category 取值：强敌登场|打脸预告|身份揭露|危机降临|反转钩|悬念问题|\n'
        '    //   蓄势待发|机缘出现|误会升级|倒计时|关系突变|选择困境|信息炸弹\n'
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
        '  "new_characters": [  // 本章首次登场、且后续会复现的长期角色；无则[]\n'
        '    // ⚠仅收录：新收的小弟/新登场的女主或宿敌/重要新反派/关键导师等会反复出现的角色。\n'
        '    // ⚠禁止收录：一次性工具人、被打脸即退场的炮灰、路人、群演。已建档人名也不要重复。\n'
        '    {"name": "人名", "role": "主角阵营|宿敌|女主|导师|反派|盟友", "tier": "核心|配角",\n'
        '     "start_realm": "登场时境界，无则null", "persona": "≤30字性格/说话风格",\n'
        '     "function": "≤30字在故事里的作用"}\n'
        "  ],\n"
        '  "realm_snapshot": {   // 章末主角境界精确快照（系统文核心；必填；下章开笔绝对基准）\n'
        '    "realm": "大境界名称，如炼气期（禁止只写泛称「练气」）",\n'
        '    "sub_level": 当前小境界层数（整数 1～9，须与正文末句一致；同境内未突破则与开笔相同）,\n'
        '    "max_sub": 该大境界最大层数（整数，如9），无则null,\n'
        '    "combat_power": 战力估算数值（整数，须≥上章同境面板，禁止无故暴跌）,\n'
        '    "location": "章末主角位置【系统台账坐标】，格式「地图区域·具体地点」（如 鬼市地宫·废弃矿道）；'
        '仅供后台对齐，正文应写自然地名，禁止把此串原样抄进小说",\n'
        '    "location_change_reason": "主角本章如何从此前位置到达此处（路径/方式/触发事件）；'
        '位置未变则写「本章未离开当前区域」",\n'
        '    "realm_change_reason": "主角本章境界/小层变化的正文依据（谁、做了什么、结果）；'
        '本章修为未变则写「本章修为未变，维持第N层」"\n'
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


_NEW_CHAR_ROLES = {"主角阵营", "宿敌", "女主", "导师", "反派", "盟友", "配角", "核心"}


def _persist_new_characters(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline, result: dict,
) -> list[str]:
    """写作期新长期角色建档（按名字去重，已存在则跳过，不覆盖 bootstrap 档案）。

    工具人/炮灰由复盘 prompt 约束不收录；此处再按名字与既有人物去重兜底。
    """
    from app.models.dabai import DabaiCharacter

    existing = {
        (c.name or "").strip()
        for c in db.query(DabaiCharacter.name)
        .filter(DabaiCharacter.project_id == project.id)
    }
    created: list[str] = []
    max_order = (
        db.query(DabaiCharacter.sort_order)
        .filter(DabaiCharacter.project_id == project.id)
        .order_by(DabaiCharacter.sort_order.desc())
        .limit(1)
        .scalar()
    ) or 0
    for item in list(result.get("new_characters") or [])[:6]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:100]
        if not name or name in existing:
            continue
        tier = str(item.get("tier") or "配角").strip()[:20]
        max_order += 1
        db.add(DabaiCharacter(
            project_id=project.id,
            name=name,
            role=str(item.get("role") or "")[:60],
            tier=tier if tier in ("核心", "配角") else "配角",
            start_realm=str(item.get("start_realm") or "")[:60] or None,
            persona=str(item.get("persona") or "")[:300] or None,
            function=str(item.get("function") or "")[:300] or None,
            extra={"source": "debrief", "debut_chapter": ch.chapter_number},
            sort_order=max_order,
        ))
        existing.add(name)
        created.append(name)
    return created


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
        hook_cat = str(item.get("hook_category") or "").strip()[:30] or None
        created.append(DabaiClue(
            project_id=project.id, title=title,
            clue_type=clue_type if clue_type in _CLUE_TYPES else "hook",
            hook_category=hook_cat if clue_type == "hook" else None,
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
    new_characters = _persist_new_characters(db, project, ch, result)
    asset_logs, relation_logs = apply_ledger_changes(db, project, ch, result)
    prune_noise_assets(db, project)
    realm_info = result.get("realm_snapshot") if isinstance(result.get("realm_snapshot"), dict) else None
    realm_label = sync_protagonist_realm(
        db, project, ch, memories=memories, realm_info=realm_info,
    )
    # 系统面板快照：复盘结束后立即存档，作为下章写作的数值绝对基准
    try:
        build_panel_snapshot(db, project, ch, realm_info=realm_info)
    except Exception as _snap_err:  # noqa: BLE001
        logger.warning("面板快照写入失败 ch=%s: %s", ch.id, _snap_err)

    db.commit()

    # 复盘记忆落库后异步向量化（pgvector 语义召回；未装 pgvector 自动跳过）
    try:
        from app.database import SessionLocal
        from app.services.dabai.lab_embedding import embed_dabai_memories_async
        embed_dabai_memories_async(memories, SessionLocal)
    except Exception as _embed_err:  # noqa: BLE001
        logger.warning("dabai 记忆向量化触发失败 ch=%s: %s", ch.id, _embed_err)

    payload = {
        "version": DEBRIEF_VERSION,
        "summary": str(result.get("summary") or "")[:200],
        "memory_count": len(memories),
        "new_clues": [c.title for c in created],
        "resolved_clues": [c.title for c in resolved],
        "asset_changes": asset_logs,
        "relation_changes": relation_logs,
        "new_characters": new_characters,
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
