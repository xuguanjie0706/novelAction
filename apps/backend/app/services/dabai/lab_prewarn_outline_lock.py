"""导演单与章纲硬锁 — 防止 pre-warn 擅自拔高对手境界、编造越级叙事。

章纲 yaqu_setup 等已写明「陈山（练气三层）」时，人物表 bootstrap 的 start_realm
（如七层）不得覆盖；beat_execution / reminders / cast 须后处理对齐。
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.services.dabai.lab_realm_baseline import cn_to_int

_BEAT_KEYS = ("yaqu", "trigger", "yinbao", "payoff", "hook")

# 人名紧挨括号（非贪婪，避免「狂徒陈山」吞掉前缀）
_CAST_NAME_REALM_RE = re.compile(
    r"([\u4e00-\u9fff]{2,4}?)[（(]"
    r"(?:练气|炼气)[期境]?[^）)]*?([一二三四五六七八九十\d]+)层[）)]",
)

_OUTLINE_CAST_REALM_RE = _CAST_NAME_REALM_RE
_INLINE_CAST_REALM_RE = _CAST_NAME_REALM_RE


def _known_cast_names(ch: DabaiChapterOutline) -> list[str]:
    names: list[str] = []
    for field in ("involved_characters", "witnesses"):
        raw = getattr(ch, field, None) or []
        if isinstance(raw, list):
            names.extend(str(n).strip() for n in raw if str(n).strip())
    return list(dict.fromkeys(names))


def _resolve_cast_name(raw: str, known: list[str]) -> str:
    for n in sorted(known, key=len, reverse=True):
        if raw == n or raw.endswith(n):
            return n
    return raw


def extract_outline_cast_realms(ch: DabaiChapterOutline) -> dict[str, int]:
    """从章纲五拍字段抽取「人名（练气N层）」硬锁；同人多出处取首次。"""
    blob = " ".join(
        str(getattr(ch, f, None) or "")
        for f in ("yaqu_setup", "emotion_turn", "yinbao", "shuang_payoff", "end_hook")
    )
    known = _known_cast_names(ch)
    locked: dict[str, int] = {}
    for m in _OUTLINE_CAST_REALM_RE.finditer(blob):
        name = _resolve_cast_name(m.group(1).strip(), known)
        sub = cn_to_int(m.group(2))
        if name and sub is not None and name not in locked:
            locked[name] = sub
    return locked


def build_outline_cast_lock_block(ch: DabaiChapterOutline) -> str:
    """注入导演单 prompt：章纲已锁定的配角境界。"""
    locked = extract_outline_cast_realms(ch)
    if not locked:
        return ""
    lines = [
        "【章纲锁定·配角境界（硬约束，高于人物表 bootstrap 默认境界）】",
        "下列境界来自本章章纲五拍原文，导演单 beat_execution 只许换写法，"
        "禁止改成更高/更低层、禁止编造「越级秒杀震撼」等与章纲矛盾的战力叙事：",
    ]
    for name, sub in locked.items():
        lines.append(f"  - {name}：练气{sub}层（章纲锁定，勿擅自改层）")
    lines.append(
        "★人物表「境界:」若与上表冲突，以上表为准；conflict_notes 留空，"
        "在 beat_execution 按章纲层数落法即可。★"
    )
    return "\n".join(lines)


def _sub_to_label(sub: int) -> str:
    _cn = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
    return _cn.get(sub, str(sub))


def _clamp_name_realm_parens(text: str, name: str, correct_sub: int) -> str:
    """把文本中「name（练气X层）」的 X 改成章纲锁定值。"""
    if not text or not name:
        return text

    def repl(m: re.Match[str]) -> str:
        if m.group(1) != name:
            return m.group(0)
        sub = cn_to_int(m.group(2))
        if sub is None or sub == correct_sub:
            return m.group(0)
        label = _sub_to_label(correct_sub)
        return f"{name}（练气{label}层）"

    return _INLINE_CAST_REALM_RE.sub(repl, text)


def _clamp_loose_realm_near_name(text: str, name: str, correct_sub: int) -> str:
    """修正「name…练气七层」类非括号写法（仅当人名后 12 字内）。"""
    if not text or name not in text:
        return text
    label = _sub_to_label(correct_sub)
    pat = re.compile(
        rf"({re.escape(name)}[^。，！？\n]{{0,12}})"
        rf"(?:练气|炼气)[期境]?"
        rf"([一二三四五六七八九十\d]+)层",
    )

    def repl(m: re.Match[str]) -> str:
        sub = cn_to_int(m.group(2))
        if sub is None or sub == correct_sub:
            return m.group(0)
        return f"{m.group(1)}练气{label}层"

    return pat.sub(repl, text)


def _normalize_tiers_in_text(text: str, locked: dict[str, int]) -> str:
    """将战斗描述里与章纲锁矛盾的层数改为锁定值（仅单配角锁定时启用，防多角色互串）。"""
    if not locked or not text or len(locked) != 1:
        return text
    fight_ctx = any(
        k in text for k in ("秒杀", "废", "对决", "对手", "碾压", "越级")
    )
    out = text
    for name, sub in locked.items():
        if name not in out and not fight_ctx:
            continue
        label = _sub_to_label(sub)

        def repl(m: re.Match[str], *, s=sub, lb=label) -> str:
            mentioned = cn_to_int(m.group(1))
            if mentioned is None or mentioned == s:
                return m.group(0)
            return f"练气{lb}层"

        out = re.compile(
            r"(?:练气|炼气)[期境]?([一二三四五六七八九十\d]+)层",
        ).sub(repl, out)
    return out


def _clamp_text_for_locked_cast(text: str, locked: dict[str, int]) -> str:
    out = text
    for name, sub in locked.items():
        out = _clamp_name_realm_parens(out, name, sub)
        out = _clamp_loose_realm_near_name(out, name, sub)
    out = _normalize_tiers_in_text(out, locked)
    return out


def _reminder_contradicts_outline(reminder: str, locked: dict[str, int]) -> bool:
    """丢弃「必须七层不可三层」等与章纲锁矛盾的 reminders。"""
    r = reminder.strip()
    if not r:
        return True
    for name, sub in locked.items():
        if name not in r:
            continue
        for m in _INLINE_CAST_REALM_RE.finditer(r):
            if m.group(1) != name:
                continue
            mentioned = cn_to_int(m.group(2))
            if mentioned is not None and mentioned != sub:
                return True
        for m in re.finditer(
            rf"(?:练气|炼气)[期境]?([一二三四五六七八九十\d]+)层", r,
        ):
            mentioned = cn_to_int(m.group(1))
            if mentioned is not None and mentioned != sub:
                if "不可写成" in r or "必须" in r or "严格" in r:
                    return True
    if "越级秒杀" in r or "越级碾压" in r:
        return True
    return False


def sanitize_prewarn_outline_lock(
    result: dict,
    ch: DabaiChapterOutline,
) -> dict:
    """后处理导演单：五拍/reminders/cast/setup_check 对齐章纲境界锁。"""
    locked = extract_outline_cast_realms(ch)
    if not locked or not isinstance(result, dict):
        return result

    out = dict(result)
    beats = dict(out.get("beat_execution") or {})
    for key in _BEAT_KEYS:
        beats[key] = _clamp_text_for_locked_cast(str(beats.get(key) or ""), locked)
    out["beat_execution"] = beats

    cast = []
    for item in out.get("cast") or []:
        if not isinstance(item, dict):
            continue
        c = dict(item)
        if c.get("reason"):
            c["reason"] = _clamp_text_for_locked_cast(str(c["reason"]), locked)
        cast.append(c)
    out["cast"] = cast

    for field in ("setup_check", "opening_directive"):
        if out.get(field):
            out[field] = _clamp_text_for_locked_cast(str(out[field]), locked)

    reminders = [
        str(r).strip()
        for r in (out.get("reminders") or [])
        if str(r).strip() and not _reminder_contradicts_outline(str(r), locked)
    ]
    out["reminders"] = reminders[:3]

    notes = list(out.get("outline_realm_lock") or [])
    if not notes:
        out["outline_realm_lock"] = [
            f"{n}={s}层" for n, s in locked.items()
        ]
    return out


def format_locked_realm_label(sub: int, project: DabaiProject) -> str:
    """章纲锁定小层 → 与 bootstrap 一致的称述（如 练气期三层）。"""
    label = _sub_to_label(sub)
    levels = (project.power_ladder or {}).get("levels") or []
    major = str(levels[0].get("name") or "练气期").strip() if levels else "练气期"
    major = major.rstrip("境")
    if major.endswith("期"):
        return f"{major}{label}层"
    return f"{major}期{label}层"


def sync_cast_realm_from_outline(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
) -> list[str]:
    """章纲五拍锁定的配角境界 → 回写人物档案（修 bootstrap 与章纲打架）。

    首次出场章（debut_chapter）若 start_realm 与章纲矛盾，以章纲为准覆盖 start_realm，
    避免首稿写错七层后重写仍从人物表读七层。
    """
    locked = extract_outline_cast_realms(ch)
    if not locked:
        return []
    from app.services.dabai.lab_ledger import protagonist_name

    protag = protagonist_name(project)
    by_name = {str(c.name).strip(): c for c in (project.characters or []) if c.name}
    ch_num = int(ch.chapter_number or 0)
    stage = set(_known_cast_names(ch))
    logs: list[str] = []
    for name, sub in locked.items():
        if name == protag:
            # 主角境界走面板/复盘链，不用章纲括号里的配角格式锁
            continue
        c = by_name.get(name)
        if not c:
            continue
        label = format_locked_realm_label(sub, project)
        extra = dict(c.extra) if isinstance(c.extra, dict) else {}
        extra["current_realm"] = label
        extra["current_realm_source"] = f"outline_ch{ch_num}"
        if name in stage:
            if not extra.get("debut_chapter"):
                extra["debut_chapter"] = ch_num
            if int(extra.get("debut_chapter") or ch_num) == ch_num:
                old_start = str(c.start_realm or "").strip()
                if old_start and old_start != label:
                    extra["bootstrap_realm_corrected_from"] = old_start
                    c.start_realm = label
                    logs.append(f"{name} start_realm {old_start}→{label}")
        c.extra = extra
        db.add(c)
    if logs:
        db.flush()
    return logs
