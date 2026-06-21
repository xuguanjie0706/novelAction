"""dabai 实验书架 — 后续章边界与跨章角色保护。

写章/导演单/质检共用：读取后 N 章章纲，约束本章不得提前兑现或写死后续出场人物。
"""
from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline

_LOOKAHEAD = 2

# 姓名附近窗口内命中即视为「写死/移除」——已弃用于正文质检（误报率过高），
# 跨章边界改由 LLM 质检 future_cast_violations 裁决；写章 prompt 仍注入 protected 名单。
_DEATH_KEYWORDS = (
    "死", "殁", "毙", "诛杀", "身亡", "殒命", "气绝", "断气",
    "没了声息", "当场死亡", "一击毙命", "贯穿胸口", "刺穿胸口",
)

# 章纲字段里暗示后续角色无法再出场
_OUTLINE_DEATH_HINTS = ("死", "殁", "毙", "诛", "杀", "身亡", "殒命", "灭口")


def _char_names(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = str(item or "").strip()
        if name and name not in seen:
            out.append(name)
            seen.add(name)
    return out


def collect_future_cast_names(
    db: Session,
    project_id: UUID,
    chapter_number: int,
    *,
    lookahead: int = _LOOKAHEAD,
) -> list[str]:
    """后 ``lookahead`` 章 ``involved_characters`` 并集（后续章主线出场人物）。"""
    if chapter_number <= 0:
        return []
    rows = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project_id,
            DabaiChapterOutline.chapter_number > chapter_number,
        )
        .order_by(DabaiChapterOutline.chapter_number.asc())
        .limit(lookahead)
        .all()
    )
    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for name in _char_names(row.involved_characters):
            if name not in seen:
                names.append(name)
                seen.add(name)
    return names


def _outline_brief(ch: DabaiChapterOutline) -> str:
    witnesses = "、".join(_char_names(ch.witnesses)[:4])
    involved = "、".join(_char_names(ch.involved_characters)[:6])
    lines = [
        f"第{ch.chapter_number}章《{ch.title or ''}》场景={ch.location or '—'} "
        f"爽点={ch.shuang_type or '—'}",
        f"  憋屈：{(ch.yaqu_setup or '')[:80]}",
        f"  爽点落点：{(ch.shuang_payoff or '')[:80]}",
        f"  章末钩子：{(ch.end_hook or '')[:100]}",
    ]
    if involved:
        lines.append(f"  主线出场：{involved}")
    if witnesses:
        lines.append(f"  见证者：{witnesses}")
    return "\n".join(lines)


def build_forward_chapter_boundary_block(
    db: Session,
    project_id: UUID,
    ch: DabaiChapterOutline,
    *,
    lookahead: int = _LOOKAHEAD,
) -> str:
    """写章 prompt 注入：后 N 章章纲摘要 + 不可越界红线。"""
    cur = int(ch.chapter_number or 0)
    rows = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project_id,
            DabaiChapterOutline.chapter_number > cur,
        )
        .order_by(DabaiChapterOutline.chapter_number.asc())
        .limit(lookahead)
        .all()
    )
    if not rows:
        return ""
    protected = collect_future_cast_names(db, project_id, cur, lookahead=lookahead)
    outlines = "\n\n".join(_outline_brief(r) for r in rows)
    protect_line = ""
    if protected:
        protect_line = (
            f"\n★后续章主线出场人物（本章禁止写死/永久移除/抓走导致无法按后续章纲出场）："
            f"{'、'.join(protected[:12])}★"
        )
    end_hook = (ch.end_hook or "").strip()
    hook_note = (
        f"\n★收笔方向（用场面定格兑现，勿把下列原句贴到段末）：\n  {end_hook[:200]}"
        if end_hook else ""
    )
    return (
        f"【后续{len(rows)}章章纲预览（禁止提前兑现；禁止破坏后续章主线）】\n"
        f"{outlines}{protect_line}{hook_note}\n"
        "执行要求：① 不得在本章结尾之后继续写「抢宝/抓人/杀人」等下一章才该发生的事；"
        "② 上述后续章「主线出场」人物本章若出现，只能重伤/击退/羞辱，不得死亡或永久离场；"
        "③ 五拍写完后以钩子方向定格收笔，钩子事件只演一次，禁止复述章纲 end_hook 原句。"
    )


def death_hit_for_name(content: str, name: str, *, window: int = 48) -> str | None:
    """正文是否在 name 附近出现死亡/永久移除语义；命中返回片段。

    .. deprecated::
        不再用于正文质检（「死死」「没死」等误报不可接受）；保留仅供回归对照。
    """
    text = (content or "").strip()
    nm = (name or "").strip()
    if not text or not nm or nm not in text:
        return None
    start = 0
    while True:
        idx = text.find(nm, start)
        if idx < 0:
            return None
        seg = text[max(0, idx - window): idx + len(nm) + window]
        if any(kw in seg for kw in _DEATH_KEYWORDS):
            return seg.strip()[:120]
        start = idx + len(nm)


def check_future_cast_violations(
    content: str,
    protected_names: list[str],
) -> list[dict]:
    """正文是否写死/永久移除后续章出场人物 → blocker 列表。

    .. deprecated::
        已移出规则层质检；跨章边界改由 LLM ``future_cast_violations`` 裁决。
    """
    violations: list[dict] = []
    plain = re.sub(r"<[^>]+>", "", content or "")
    for name in protected_names:
        hit = death_hit_for_name(plain, name)
        if hit:
            violations.append({
                "rule_id": "DLB-05",
                "message": (
                    f"后续章出场人物「{name}」在本章被写死或永久移除"
                    f"（…{hit[:60]}…），与后续章纲冲突"
                ),
            })
    return violations


def lint_outline_future_cast_conflict(chapters: list[dict]) -> list[tuple[int, str, str]]:
    """章纲 linter：第 N 章 payoff/yinbao 暗示杀死第 N+1~N+2 章 involved 人物。"""
    issues: list[tuple[int, str, str]] = []
    for i, ch in enumerate(chapters):
        num = int(ch.get("chapter_number") or 0)
        future: set[str] = set()
        for j in range(i + 1, min(i + 1 + _LOOKAHEAD, len(chapters))):
            for name in _char_names(chapters[j].get("involved_characters")):
                future.add(name)
        if not future:
            continue
        blob = " ".join(
            str(ch.get(k) or "") for k in ("yinbao", "shuang_payoff", "end_hook", "yaqu_setup")
        )
        for name in future:
            if name not in blob:
                continue
            if any(k in blob for k in _OUTLINE_DEATH_HINTS) and name in blob:
                issues.append((
                    num,
                    f"第{num}章节拍涉及后续章主线人物「{name}」且含死亡/消灭暗示，"
                    f"与第{num + 1}章后章纲冲突",
                    "改为击退/羞辱/暂退，或调整后续章纲出场安排",
                ))
    return issues
