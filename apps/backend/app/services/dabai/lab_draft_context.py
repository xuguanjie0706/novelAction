"""dabai 实验书架（dabai_* 表）写章上下文 — 前情/上章结尾/记忆回灌/线索回灌。

与精品文 ``draft_context`` 隔离：只读 dabai_* 表，不依赖 Project/Chapter/图谱/pgvector。
记忆与线索回灌是复盘台账的「读端」：没有回灌，复盘提取的事实对写作模型不可见。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiClue, DabaiMemory, DabaiPanelSnapshot

_MEM_LABELS = {
    "summary": "摘要", "fact": "事实", "event": "事件",
    "state": "状态", "relation": "关系",
}


@dataclass
class LabDraftContext:
    """实验书架写章前置上下文。"""

    prev_tail: str
    recent_plot_block: str
    memory_block: str = ""    # 复盘记忆回灌（重要度+时效 Top-K）
    clue_block: str = ""      # 未回收线索回灌（埋设越久越优先）
    panel_block: str = ""     # 系统面板快照块（上章末精确数值基准）


def _tail_of_content(content: str, max_len: int = 800) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    return text[-max_len:] if len(text) > max_len else text


def _build_memory_block(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline, top_k: int = 8,
) -> str:
    """重要度优先 + 同分按时效取 Top-K 记忆，展示按章号升序。"""
    rows = (
        db.query(DabaiMemory)
        .filter(
            DabaiMemory.project_id == project.id,
            DabaiMemory.chapter_number < ch.chapter_number,
        )
        .order_by(DabaiMemory.importance.desc(), DabaiMemory.chapter_number.desc())
        .limit(top_k)
        .all()
    )
    if not rows:
        return ""
    lines = [
        f"  - 第{m.chapter_number}章[{_MEM_LABELS.get(m.mem_type, m.mem_type)}] {m.content}"
        for m in sorted(rows, key=lambda m: (m.chapter_number or 0))
    ]
    return "【既定事实记忆（复盘提取，不可违背）】\n" + "\n".join(lines)


def _build_clue_block(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline, top_k: int = 8,
) -> str:
    """未回收线索按埋设章号升序（埋得越久越优先提醒回收）。"""
    rows = (
        db.query(DabaiClue)
        .filter(
            DabaiClue.project_id == project.id,
            DabaiClue.status == "open",
            DabaiClue.chapter_planted < ch.chapter_number,
        )
        .order_by(DabaiClue.chapter_planted)
        .limit(top_k)
        .all()
    )
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
    """组装上章结尾 + 近章前情块 + 记忆/线索回灌块（仅基于 dabai_* 表）。"""
    prev_tail = ""
    if (ch.chapter_number or 0) > 1:
        prev = (
            db.query(DabaiChapterOutline)
            .filter(
                DabaiChapterOutline.project_id == project.id,
                DabaiChapterOutline.chapter_number == ch.chapter_number - 1,
            )
            .first()
        )
        if prev and (prev.content or "").strip():
            prev_tail = _tail_of_content(prev.content or "", 800)

    recent_lines: list[str] = []
    written = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project.id,
            DabaiChapterOutline.chapter_number < ch.chapter_number,
            DabaiChapterOutline.content.isnot(None),
        )
        .order_by(DabaiChapterOutline.chapter_number.desc())
        .limit(3)
        .all()
    )
    for row in reversed(written):
        snippet = _tail_of_content(row.content or "", 120)
        hook = (row.end_hook or "").strip()
        line = f"  第{row.chapter_number}章《{row.title or ''}》"
        if hook:
            line += f"；末钩：{hook}"
        if snippet:
            line += f"；收束：…{snippet}"
        recent_lines.append(line)

    recent_plot_block = ""
    if recent_lines:
        recent_plot_block = "【前情提要（已发生事实，不可推翻）】\n" + "\n".join(recent_lines)

    return LabDraftContext(
        prev_tail=prev_tail,
        recent_plot_block=recent_plot_block,
        memory_block=_build_memory_block(db, project, ch),
        clue_block=_build_clue_block(db, project, ch),
        panel_block=_build_panel_block(db, project, ch),
    )
