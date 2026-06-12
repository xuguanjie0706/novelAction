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
# 上一章完整正文注入上限（防极端长章爆 context；正常 2000-3000 字章全量进入）
_PREV_FULL_MAX = 9000


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
) -> dict[int, str]:
    """复盘实际提取的章末钩子（clue_type=hook），chapter_planted → 钩子文本。"""
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
    hooks: dict[int, str] = {}
    for c in rows:
        num = int(c.chapter_planted or 0)
        desc = (c.description or "").strip()
        hooks[num] = f"{(c.title or '').strip()}{('：' + desc) if desc else ''}"
    return hooks


def _build_recent_plot_block(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    summaries: dict[int, str],
    hooks: dict[int, str],
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
        hook = hooks.get(num, "")
        if hook:
            line += f"；实际末钩：{hook}"
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
    prev: DabaiChapterOutline | None, hooks: dict[int, str],
) -> str:
    """上章末钩单列硬约束：复盘实际提取的钩子优先，章纲计划值兜底并标注。"""
    if not prev:
        return ""
    num = int(prev.chapter_number or 0)
    actual = hooks.get(num, "")
    if actual:
        return (
            "【上章末钩（已写入正文的对读者承诺，本章开篇必须正面回应，"
            "禁止无视或悄悄推翻）】\n  " + actual
        )
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

    return LabDraftContext(
        prev_tail=prev_tail,
        recent_plot_block=_build_recent_plot_block(db, project, ch, summaries, hooks),
        memory_block=_build_memory_block(db, project, ch, summaries),
        clue_block=_build_clue_block(db, project, ch),
        panel_block=_build_panel_block(db, project, ch),
        prev_full_block=prev_full_block,
        prev_hook_block=_build_prev_hook_block(prev, hooks),
        prev_content_hash=prev_content_hash,
    )
