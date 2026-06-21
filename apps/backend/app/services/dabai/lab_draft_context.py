"""dabai 实验书架（dabai_* 表）写章上下文 — 前情/上章正文/记忆回灌/线索回灌。

与精品文 ``draft_context`` 隔离：只读 dabai_* 表，不依赖 Project/Chapter/图谱/pgvector。
记忆与线索回灌是复盘台账的「读端」：没有回灌，复盘提取的事实对写作模型不可见。

衔接断层修复（2026-06-12 四批，正文质量优先、token 不设限）：
- ``prev_full_block``：上一章完整正文整体注入（事实最高基准），不再只给 800 字尾巴；
- ``recent_plot_block``：改读复盘提取的「实际事实摘要」+ 正文实际收束，
  章纲 ``end_hook``（计划值）只作兜底并明确标注，消除「承接假钩子」；
- ``memory_block`` 双轨：近 ``_RECENT_WINDOW`` 章复盘事实无条件全量注入（时序锚定）
  + 更早章节按重要度选注 + 全书章级摘要链，消除中期剧情盲区；
- ``prev_hook_block``：上章末钩（复盘实际提取的 hook 线索优先）单列硬约束，
  不再淹没在「埋设越久越优先」的线索池里；
- ``prev_content_hash``：上章正文指纹，供导演单/分场的陈旧失效检测。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiClue, DabaiMemory, DabaiPanelSnapshot
from app.services.dabai.lab_char_voice import build_char_voice_block
from app.services.dabai.lab_realm_baseline import (
    build_writing_realm_block,
    load_opening_realm_baseline,
)

_MEM_LABELS = {
    "summary": "摘要", "fact": "事实", "event": "事件",
    "state": "状态", "relation": "关系",
}

# 近期窗口：最近 N 章的复盘事实无条件全量注入（时序锚定）
_RECENT_WINDOW = 6
# 前情提要回看章数
_RECENT_PLOT_CHAPTERS = 5
# 全书章级摘要链最多注入的章数（取最近的）
_SUMMARY_CHAIN_MAX = 40
# 上一章完整正文注入上限：正文质量优先、token 不设限——正常章（含大爆点章 3000 字）
# 全量进入，仅极端超长章（>2 万字，通常是异常合并）才做中段省略兜底。
_PREV_FULL_MAX = 20000


@dataclass
class LabDraftContext:
    """实验书架写章前置上下文。"""

    prev_tail: str
    recent_plot_block: str
    memory_block: str = ""        # 复盘记忆回灌（双轨：近期全量 + 早期重要 + 摘要链）
    clue_block: str = ""          # 未回收线索回灌（埋设越久越优先；上章末钩单列不在此）
    panel_block: str = ""         # 系统面板快照块（上章末精确数值基准）
    prev_full_block: str = ""     # 上一章完整正文（已发生事实的最高基准）
    prev_hook_block: str = ""     # 上章末钩硬约束（复盘实际钩子优先，章纲计划兜底）
    prev_content_hash: str = ""   # 上章正文指纹（导演单/分场陈旧失效检测）
    narrative_state_block: str = ""  # Layer 2 情节时间轴+世界快照（与章纲 prompt 同源）
    char_voice_block: str = ""    # 本章出场人物声音档案（性格/说话风格/欲望/憋屈/与主角关系）
    realm_writing_block: str = ""   # 开笔/章末境界衔接（情节基准，非章纲硬锁）


def content_fingerprint(text: str) -> str:
    """正文内容指纹（sha1 前 16 位）；空文本返回空串。"""
    t = (text or "").strip()
    if not t:
        return ""
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]


def _tail_of_content(content: str, max_len: int = 800) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    return text[-max_len:] if len(text) > max_len else text


def _chapter_summaries(
    db: Session, project: DabaiProject, before_chapter: int,
) -> dict[int, str]:
    """各章复盘事实摘要（mem_type=summary），chapter_number → 摘要文本。"""
    rows = (
        db.query(DabaiMemory)
        .filter(
            DabaiMemory.project_id == project.id,
            DabaiMemory.mem_type == "summary",
            DabaiMemory.chapter_number < before_chapter,
        )
        .order_by(DabaiMemory.chapter_number)
        .all()
    )
    return {int(m.chapter_number or 0): (m.content or "").strip() for m in rows}


def _actual_hooks(
    db: Session, project: DabaiProject, before_chapter: int,
) -> dict[int, tuple[str, str]]:
    """复盘实际提取的章末钩子（clue_type=hook），chapter_planted → (钩子文本, hook_category)。"""
    rows = (
        db.query(DabaiClue)
        .filter(
            DabaiClue.project_id == project.id,
            DabaiClue.clue_type == "hook",
            DabaiClue.chapter_planted < before_chapter,
        )
        .order_by(DabaiClue.chapter_planted, DabaiClue.created_at)
        .all()
    )
    hooks: dict[int, tuple[str, str]] = {}
    for c in rows:
        num = int(c.chapter_planted or 0)
        desc = (c.description or "").strip()
        text = f"{(c.title or '').strip()}{('：' + desc) if desc else ''}"
        hooks[num] = (text, (c.hook_category or "").strip())
    return hooks


def _build_recent_plot_block(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    summaries: dict[int, str],
    hooks: dict[int, tuple[str, str]],
) -> str:
    """前情提要：实际事实摘要 + 正文实际收束 + 实际末钩（计划钩子仅兜底并标注）。"""
    written = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project.id,
            DabaiChapterOutline.chapter_number < ch.chapter_number,
            DabaiChapterOutline.content.isnot(None),
        )
        .order_by(DabaiChapterOutline.chapter_number.desc())
        .limit(_RECENT_PLOT_CHAPTERS)
        .all()
    )
    lines: list[str] = []
    for row in reversed(written):
        num = int(row.chapter_number or 0)
        line = f"  第{num}章《{row.title or ''}》"
        summary = summaries.get(num, "")
        if summary:
            line += f"；事实摘要：{summary}"
        hook_info = hooks.get(num)
        if hook_info:
            hook_text, _ = hook_info
            line += f"；实际末钩：{hook_text}"
        elif (row.end_hook or "").strip():
            line += f"；计划末钩（章纲值，以正文实际结尾为准）：{row.end_hook.strip()}"
        snippet = _tail_of_content(row.content or "", 200)
        if snippet:
            line += f"；正文收束：…{snippet}"
        lines.append(line)
    if not lines:
        return ""
    return "【前情提要（已发生事实，不可推翻）】\n" + "\n".join(lines)


def _build_memory_block(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    summaries: dict[int, str],
) -> str:
    """双轨记忆回灌：全书摘要链 + 近期窗口全量 + 早期重要事实。

    旧实现按 importance desc 全书 Top-8，写到几十章后名额被早期高分事实
    占满，近期状态变化对模型不可见——中期剧情盲区是衔接断层主因之一。
    """
    cur = ch.chapter_number or 0
    recent_from = cur - _RECENT_WINDOW

    sections: list[str] = []

    # ── 轨一：全书章级摘要链（时序骨架，最近 _SUMMARY_CHAIN_MAX 章）─────────
    if summaries:
        nums = sorted(summaries)[-_SUMMARY_CHAIN_MAX:]
        chain = [f"  - 第{n}章：{summaries[n]}" for n in nums if summaries[n]]
        if chain:
            sections.append("▸全书剧情脉络（各章事实摘要）：\n" + "\n".join(chain))

    # ── 轨二：近期窗口全量事实（时序锚定，无条件注入）────────────────────────
    recent_rows = (
        db.query(DabaiMemory)
        .filter(
            DabaiMemory.project_id == project.id,
            DabaiMemory.mem_type != "summary",
            DabaiMemory.chapter_number < cur,
            DabaiMemory.chapter_number >= recent_from,
        )
        .order_by(DabaiMemory.chapter_number, DabaiMemory.importance.desc())
        .limit(40)
        .all()
    )
    if recent_rows:
        lines = [
            f"  - 第{m.chapter_number}章[{_MEM_LABELS.get(m.mem_type, m.mem_type)}] {m.content}"
            for m in recent_rows
        ]
        sections.append(f"▸近{_RECENT_WINDOW}章全部事实（最新状态以此为准）：\n" + "\n".join(lines))

    # ── 轨三：更早章节按重要度选注 ───────────────────────────────────────────
    older_rows = (
        db.query(DabaiMemory)
        .filter(
            DabaiMemory.project_id == project.id,
            DabaiMemory.mem_type != "summary",
            DabaiMemory.chapter_number < recent_from,
        )
        .order_by(DabaiMemory.importance.desc(), DabaiMemory.chapter_number.desc())
        .limit(12)
        .all()
    )
    if older_rows:
        lines = [
            f"  - 第{m.chapter_number}章[{_MEM_LABELS.get(m.mem_type, m.mem_type)}] {m.content}"
            for m in sorted(older_rows, key=lambda m: (m.chapter_number or 0))
        ]
        sections.append("▸早期重要事实：\n" + "\n".join(lines))

    if not sections:
        return ""
    return "【既定事实记忆（复盘提取，不可违背）】\n" + "\n".join(sections)


# 实体召回：本章出场人物的历史关键事实最多注入条数
_ENTITY_RECALL_MAX = 10
# 实体召回候选扫描上限（窗口外老记忆按章倒序取这么多再按人名过滤）
_ENTITY_SCAN_LIMIT = 500


def _chapter_stage_names(ch: DabaiChapterOutline) -> list[str]:
    """本章出场人物名（involved_characters + witnesses，去重去空）。"""
    seen: dict[str, None] = {}
    for raw in list(ch.involved_characters or []) + list(ch.witnesses or []):
        name = str(raw or "").strip()
        if name and name not in seen:
            seen[name] = None
    return list(seen)


def _build_entity_recall_block(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline,
) -> str:
    """实体召回：按本章出场人物的 tags，捞回「窗口外」的历史关键事实。

    解决「老的低重要度事实掉出近期窗口 + dabai 无语义检索 → 旧角色再登场时
    其身份/恩怨无法被召回」的长篇衔接断层。只召回 chapter < 近期窗口 的记忆，
    避免与 ``_build_memory_block`` 的近期全量轨重复。
    """
    names = _chapter_stage_names(ch)
    if not names:
        return ""
    cur = ch.chapter_number or 0
    recent_from = cur - _RECENT_WINDOW
    if recent_from <= 1:
        return ""  # 开篇阶段没有「窗口外」历史，跳过
    name_set = set(names)
    rows = (
        db.query(DabaiMemory)
        .filter(
            DabaiMemory.project_id == project.id,
            DabaiMemory.mem_type != "summary",
            DabaiMemory.chapter_number < recent_from,
        )
        .order_by(DabaiMemory.chapter_number.desc())
        .limit(_ENTITY_SCAN_LIMIT)
        .all()
    )
    matched = [m for m in rows if name_set & {str(t).strip() for t in (m.tags or [])}]
    if not matched:
        return ""
    matched.sort(key=lambda m: (m.importance or 0, m.chapter_number or 0), reverse=True)
    top = sorted(matched[:_ENTITY_RECALL_MAX], key=lambda m: m.chapter_number or 0)
    lines = [
        f"  - 第{m.chapter_number}章[{_MEM_LABELS.get(m.mem_type, m.mem_type)}] {m.content}"
        for m in top
    ]
    who = "、".join(names[:8])
    return (
        f"▸本章出场人物（{who}）的既往关键事实（防遗忘，须与之衔接）：\n"
        + "\n".join(lines)
    )


def _build_clue_block(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline, top_k: int = 12,
) -> str:
    """未回收线索按埋设章号升序（埋得越久越优先提醒回收）。

    上章末钩（chapter_planted == N-1 的 hook）不在此列——它有单独的
    ``prev_hook_block`` 硬约束位，避免被「越久越优先」排序挤到末尾。
    """
    prev_num = (ch.chapter_number or 0) - 1
    rows = (
        db.query(DabaiClue)
        .filter(
            DabaiClue.project_id == project.id,
            DabaiClue.status == "open",
            DabaiClue.chapter_planted < ch.chapter_number,
        )
        .order_by(DabaiClue.chapter_planted)
        .limit(top_k + 2)
        .all()
    )
    rows = [
        c for c in rows
        if not (c.clue_type == "hook" and int(c.chapter_planted or 0) == prev_num)
    ][:top_k]
    if not rows:
        return ""
    lines = [
        f"  - 《{c.title}》第{c.chapter_planted}章埋设：{(c.description or '')[:60]}"
        for c in rows
    ]
    return (
        "【未回收线索（埋设越久越优先；本章可自然推进或回收，禁止凭空冒出与之矛盾的设定）】\n"
        + "\n".join(lines)
    )


def _build_prev_full_block(prev_content: str) -> str:
    """上一章完整正文注入块（已发生事实的最高基准）。"""
    text = (prev_content or "").strip()
    if not text:
        return ""
    if len(text) > _PREV_FULL_MAX:
        head = text[: _PREV_FULL_MAX - 3000]
        tail = text[-2800:]
        text = f"{head}\n……（中段略）……\n{tail}"
    return (
        "【上一章完整正文（已发生事实的最高基准：人物状态/所在位置/对话承诺/"
        "情绪走向以此为准，禁止推翻、禁止重演已写过的桥段）】\n" + text
    )


def _build_prev_hook_block(
    prev: DabaiChapterOutline | None, hooks: dict[int, tuple[str, str]],
) -> str:
    """上章末钩单列硬约束：复盘实际提取的钩子优先，章纲计划值兜底并标注。

    若上章钩子已提取 hook_category，则注入「本章须换招」提示，强化钩子轮换。
    """
    if not prev:
        return ""
    num = int(prev.chapter_number or 0)
    hook_info = hooks.get(num)
    if hook_info:
        actual_text, hook_cat = hook_info
        lines = [
            "【上章末钩（已写入正文的对读者承诺，本章开篇必须正面回应，"
            "禁止无视或悄悄推翻）】",
            f"  {actual_text}",
        ]
        if hook_cat:
            lines.append(
                f"  ★上章钩子类型=「{hook_cat}」→ 本章 end_hook 须换 13 式中另一招★"
            )
        return "\n".join(lines)
    planned = (prev.end_hook or "").strip()
    if planned:
        return (
            "【上章末钩（章纲计划值，正文实际结尾可能略有出入，"
            "以【上一章完整正文】结尾为准）】\n  " + planned
        )
    return ""


def _build_panel_block(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline,
) -> str:
    """从最新一条面板快照生成「系统面板」注入块。

    找不到快照时返回空串（降级到旧台账块），不阻塞写章。
    """
    snap = (
        db.query(DabaiPanelSnapshot)
        .filter(
            DabaiPanelSnapshot.project_id == project.id,
            DabaiPanelSnapshot.chapter_number < ch.chapter_number,
        )
        .order_by(DabaiPanelSnapshot.chapter_number.desc())
        .first()
    )
    if not snap or not snap.snapshot:
        return ""

    s = snap.snapshot
    lines: list[str] = [f"【系统面板（第{snap.chapter_number}章末存档，数值不可自相矛盾）】"]

    realm = str(s.get("realm") or "")
    sub = s.get("sub_level")
    max_s = s.get("max_sub")
    cp = s.get("combat_power")
    realm_str = realm
    if sub is not None and max_s:
        realm_str += f"·第{sub}/{max_s}层"
    elif sub is not None:
        realm_str += f"·第{sub}层"
    if cp:
        realm_str += f"（战力约{cp}）"
    if realm_str.strip():
        lines.append(f"- 境界：{realm_str}")

    location = str(s.get("location") or "").strip()
    if location:
        lines.append(f"- 章末位置：{location}（本章开笔位置以此与上一章正文结尾为准）")

    # 品阶数字 → 汉字标签（与 lab_ledger._GRADE_LABELS 保持一致）
    _PANEL_GRADE = {0: "凡品", 1: "灵品", 2: "仙品", 3: "神品", 4: "传说"}

    def _grade_tag(grade) -> str:
        """grade int → '[灵品]' 格式标签，None 返回空串。"""
        if grade is None:
            return ""
        return f"[{_PANEL_GRADE.get(int(grade), f'{grade}品')}]"

    skills_avail, skills_cd = [], []
    for sk in (s.get("skills") or []):
        tag = _grade_tag(sk.get("grade"))
        if sk.get("on_cooldown"):
            skills_cd.append(f"{sk['name']}{tag}（冷却{sk.get('cooldown_remaining', '?')}章）")
        else:
            skills_avail.append(f"{sk['name']}{tag}")
    if skills_avail:
        lines.append(f"- 可用技能：{'、'.join(skills_avail[:8])}")
    if skills_cd:
        lines.append(f"- ⛔冷却中（不可使用）：{'、'.join(skills_cd[:6])}")

    items = [
        f"{it['name']}{_grade_tag(it.get('grade'))}"
        for it in (s.get("items") or [])
    ]
    if items:
        lines.append(f"- 持有法宝：{'、'.join(items[:8])}")

    gfs = [gf["name"] for gf in (s.get("golden_fingers") or []) if gf.get("name")]
    if gfs:
        lines.append(f"- 金手指：{'、'.join(gfs)}")

    lines.append("- ★以上数据为硬性基准，本章境界/技能/法宝状态必须与之衔接，不可凭空突破或使用冷却中技能。")
    return "\n".join(lines)


def build_lab_draft_context(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
) -> LabDraftContext:
    """组装上章正文/结尾 + 事实前情块 + 双轨记忆/线索回灌块（仅基于 dabai_* 表）。"""
    cur = ch.chapter_number or 0
    summaries = _chapter_summaries(db, project, cur)
    hooks = _actual_hooks(db, project, cur)

    prev = None
    prev_tail = ""
    prev_full_block = ""
    prev_content_hash = ""
    if cur > 1:
        prev = (
            db.query(DabaiChapterOutline)
            .filter(
                DabaiChapterOutline.project_id == project.id,
                DabaiChapterOutline.chapter_number == cur - 1,
            )
            .first()
        )
        if prev and (prev.content or "").strip():
            prev_tail = _tail_of_content(prev.content or "", 1200)
            prev_full_block = _build_prev_full_block(prev.content or "")
            prev_content_hash = content_fingerprint(prev.content or "")

    memory_block = _build_memory_block(db, project, ch, summaries)
    entity_block = _build_entity_recall_block(db, project, ch)
    if entity_block:
        memory_block = (memory_block + "\n" + entity_block).strip() if memory_block else (
            "【既定事实记忆（复盘提取，不可违背）】\n" + entity_block
        )

    from app.services.dabai.lab_narrative_state import build_narrative_state_block

    narrative_state_block = build_narrative_state_block(
        db, project, before_chapter=cur,
    )
    opening_baseline = load_opening_realm_baseline(db, project, ch)
    realm_writing_block = build_writing_realm_block(project, ch, opening_baseline)

    return LabDraftContext(
        prev_tail=prev_tail,
        recent_plot_block=_build_recent_plot_block(db, project, ch, summaries, hooks),
        memory_block=memory_block,
        clue_block=_build_clue_block(db, project, ch),
        panel_block=_build_panel_block(db, project, ch),
        prev_full_block=prev_full_block,
        prev_hook_block=_build_prev_hook_block(prev, hooks),
        prev_content_hash=prev_content_hash,
        narrative_state_block=narrative_state_block,
        char_voice_block=build_char_voice_block(project, _chapter_stage_names(ch)),
        realm_writing_block=realm_writing_block,
    )


def _semantic_query_text(ch: DabaiChapterOutline) -> str:
    """以本章五拍要素 + 出场人物拼出语义检索 query。"""
    parts = [
        str(ch.title or ""), str(ch.shuang_type or ""), str(ch.yaqu_setup or ""),
        str(ch.emotion_turn or ""), str(ch.yinbao or ""), str(ch.shuang_payoff or ""),
        "、".join(_chapter_stage_names(ch)),
    ]
    return " ".join(p for p in parts if p.strip())[:1000]


async def _build_semantic_recall_block(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline,
) -> str:
    """pgvector 语义召回：与本章情节最相关的既往事实（跨越近期窗口的旧事实）。

    只保留窗口外命中（窗口内已由 ``_build_memory_block`` 近期轨全量注入），
    pgvector 不可用时 ``semantic_search_dabai`` 返回 []，本块为空。
    """
    from app.services.dabai.lab_embedding import semantic_search_dabai

    cur = ch.chapter_number or 0
    recent_from = cur - _RECENT_WINDOW
    query = _semantic_query_text(ch)
    if not query:
        return ""
    hits = await semantic_search_dabai(db, project.id, query, top_k=8, max_chapter=cur)
    hits = [m for m in hits if (m.chapter_number or 0) < recent_from]
    if not hits:
        return ""
    hits.sort(key=lambda m: m.chapter_number or 0)
    lines = [
        f"  - 第{m.chapter_number}章[{_MEM_LABELS.get(m.mem_type, m.mem_type)}] {m.content}"
        for m in hits
    ]
    # 该块由写正文/写前导演单/分场调度三处共享同一份上下文注入（一次召回）：
    # 写正文时作为衔接事实；导演单裁决章纲冲突时优先引用其中的恩怨/承诺/能力来历；
    # 分场调度时据此避免重复已写过的桥段。
    return (
        "▸与本章情节语义最相关的既往事实（裁决/调度时优先参考：旧角色恩怨、"
        "已立承诺、能力与道具来历；禁止与之矛盾或重复已写桥段）：\n"
        + "\n".join(lines)
    )


async def build_lab_draft_context_async(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    *,
    semantic: bool = True,
) -> LabDraftContext:
    """异步组装写章上下文：同步块 + pgvector 语义召回块（追加进 memory_block）。

    供 async 写作路径（draft / 导演单 / 分场）调用；纯同步场景仍可用
    ``build_lab_draft_context``（仅缺语义召回轨，实体召回不受影响）。
    """
    ctx = build_lab_draft_context(db, project, ch)
    if semantic:
        block = await _build_semantic_recall_block(db, project, ch)
        if block:
            ctx.memory_block = (
                (ctx.memory_block + "\n" + block).strip() if ctx.memory_block
                else "【既定事实记忆（复盘提取，不可违背）】\n" + block
            )
    return ctx
