"""dabai 实验书架境界基准 — 写作期以已写情节/面板为准，章纲 realm_rank 仅作大境天花板。

设计动机：Bootstrap 节拍表预排的 realm_rank / shuang_type 不应压过正文与五拍；
开笔对齐上章面板/复盘，章末对齐五拍 yinbao 与导演单 realm_end，复盘回写 sub_rank。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiMemory, DabaiPanelSnapshot

_CN_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_LEGACY_MAJOR_RE = re.compile(
    r"(炼气|筑基|金丹|元婴|化神|炼虚|合体|大乘|淬体|气海|灵纹|神宫|王座|涅槃|至尊|神吞|引灵)"
    r"(?:境|期)?",
)

_SUB_RE = re.compile(r"([一二三四五六七八九十]+|\d+)[重层]")

_BREAKTHROUGH_MARKERS = (
    "突破", "狂飙", "暴涨", "灌顶", "连破", "破境", "破级", "提升至", "直达", "冲破",
)

_STALL_ENDING_RE = re.compile(
    r"(一层巅峰|一重巅峰|一层圆满|同层巅峰|卡在.*?临界点)",
)


@dataclass
class RealmBaseline:
    """开笔境界基准（来自已写情节，非章纲预估）。"""

    label: str
    major_name: str
    major_rank: int | None
    sub_level: int | None
    source: str
    source_chapter: int | None = None


def cn_to_int(text: str) -> int | None:
    """中文数字或阿拉伯数字 → int。"""
    t = (text or "").strip()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    if t in _CN_NUM:
        return _CN_NUM[t]
    if len(t) == 2 and t[0] == "十" and t[1] in _CN_NUM:
        return 10 + _CN_NUM[t[1]]
    if len(t) == 2 and t[0] in _CN_NUM and t[1] == "十":
        return _CN_NUM[t[0]] * 10
    return None


def major_to_rank(project: DabaiProject, major: str) -> int | None:
    """大境词干 → power_ladder.rank。"""
    stem = (major or "").strip().rstrip("境期")
    if not stem:
        return None
    for lvl in (project.power_ladder or {}).get("levels") or []:
        name = str(lvl.get("name") or "").strip()
        name_stem = name.rstrip("境期")
        if stem in name or name.startswith(stem) or name_stem == stem or stem.startswith(name_stem):
            try:
                return int(lvl.get("rank") or 0) or None
            except (TypeError, ValueError):
                return None
    return None


def parse_realm_label(text: str, project: DabaiProject) -> dict | None:
    """从文本解析大境 + 小层，返回 {major_name, major_rank, sub_level, label}。"""
    plain = (text or "").strip()
    if not plain or "境" not in plain and "期" not in plain and not _LEGACY_MAJOR_RE.search(plain):
        return None

    levels = (project.power_ladder or {}).get("levels") or []
    matched_name = ""
    major_rank: int | None = None

    for lv in sorted(levels, key=lambda x: len(str(x.get("name", ""))), reverse=True):
        name = str(lv.get("name") or "").strip()
        if name and name in plain:
            matched_name = name
            try:
                major_rank = int(lv.get("rank") or 0) or None
            except (TypeError, ValueError):
                major_rank = None
            break

    if not matched_name:
        m = _LEGACY_MAJOR_RE.search(plain)
        if not m:
            return None
        stem = m.group(1)
        matched_name = f"{stem}境" if "境" not in plain[m.start(): m.start() + 6] else stem
        major_rank = major_to_rank(project, stem)

    idx = plain.find(matched_name.split("境")[0]) if matched_name else 0
    tail = plain[max(0, idx):]
    sub_level: int | None = None
    sm = _SUB_RE.search(tail)
    if sm:
        sub_level = cn_to_int(sm.group(1))
        if sub_level is None and sm.group(1).isdigit():
            sub_level = int(sm.group(1))

    label = matched_name
    if sub_level is not None:
        label = f"{matched_name}·第{sub_level}层"
    return {
        "major_name": matched_name,
        "major_rank": major_rank,
        "sub_level": sub_level,
        "label": label,
    }


def _label_from_snapshot(snapshot: dict) -> str:
    realm = str(snapshot.get("realm") or "").strip()
    sub = snapshot.get("sub_level")
    if not realm:
        return ""
    if sub is not None:
        try:
            return f"{realm}·第{int(sub)}层"
        except (TypeError, ValueError):
            pass
    return realm


def load_opening_realm_baseline(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
) -> RealmBaseline | None:
    """读开笔境界：上章面板 > meta > 上章正文末段。"""
    cur = int(ch.chapter_number or 0)
    snap = (
        db.query(DabaiPanelSnapshot)
        .filter(
            DabaiPanelSnapshot.project_id == project.id,
            DabaiPanelSnapshot.chapter_number < cur,
        )
        .order_by(DabaiPanelSnapshot.chapter_number.desc())
        .first()
    )
    if snap and isinstance(snap.snapshot, dict):
        label = _label_from_snapshot(snap.snapshot)
        parsed = parse_realm_label(label, project) or {}
        if label:
            return RealmBaseline(
                label=label,
                major_name=str(parsed.get("major_name") or snap.snapshot.get("realm") or ""),
                major_rank=parsed.get("major_rank"),
                sub_level=parsed.get("sub_level"),
                source=f"第{snap.chapter_number}章末面板",
                source_chapter=snap.chapter_number,
            )

    meta = project.meta or {}
    meta_label = str(meta.get("protagonist_realm") or "").strip()
    if meta_label:
        parsed = parse_realm_label(meta_label, project) or {}
        return RealmBaseline(
            label=meta_label,
            major_name=str(parsed.get("major_name") or meta_label),
            major_rank=parsed.get("major_rank"),
            sub_level=parsed.get("sub_level"),
            source="全书 meta",
            source_chapter=meta.get("protagonist_realm_chapter"),
        )

    if cur <= 1:
        return None

    prev = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project.id,
            DabaiChapterOutline.chapter_number == cur - 1,
        )
        .first()
    )
    if prev and (prev.content or "").strip():
        tail = re.sub(r"<[^>]+>", "", prev.content or "")[-2500:]
        parsed = parse_realm_label(tail, project)
        if parsed and parsed.get("label"):
            return RealmBaseline(
                label=parsed["label"],
                major_name=str(parsed.get("major_name") or ""),
                major_rank=parsed.get("major_rank"),
                sub_level=parsed.get("sub_level"),
                source=f"第{cur - 1}章正文末段",
                source_chapter=cur - 1,
            )
    return None


def format_baseline_block(baseline: RealmBaseline | None) -> str:
    """注入导演单/正文：开笔境界事实基准。"""
    if not baseline or not baseline.label:
        return ""
    ch_note = f"（{baseline.source}）" if baseline.source else ""
    return (
        f"【开笔境界基准（已写情节，须对齐）】\n"
        f"  {baseline.label}{ch_note}\n"
        f"  ★fact_lock.realm 须与此一致；禁止为迁就章纲节拍压低开笔层数。★\n"
    )


def build_prewarn_realm_rules_block() -> str:
    """导演单 prompt：境界情节驱动裁决规则（须精确到小层）。"""
    return (
        "【境界裁决·情节驱动（重要）】\n"
        "1. fact_lock.realm = 本章开笔境界，须写「大境名·第N层」完整格式（如 炼气境·第1层），"
        "对齐【系统面板】/【开笔境界基准】/上章正文；禁止只写大境名而漏小层。\n"
        "2. fact_lock.realm_sub_rank = 开笔小层整数 1～9，须与 realm 字符串中的层数一致。\n"
        "3. fact_lock.realm_end = 本章章末目标境界，同样须「大境·第N层」；五拍 yinbao/shuang_payoff "
        "若写突破/暴涨/灌顶，须写清对应小层；本章无修为变化则与 realm 相同。\n"
        "4. fact_lock.realm_end_sub_rank = 章末小层 1～9；有突破则 ≥ realm_sub_rank；无变化则相同。\n"
        "5. beat_execution.yinbao/payoff 的修为结果须与 fact_lock.realm_end 一致；"
        "禁止正文 rhetoric「暴涨/狂飙」却在章末仍停在与开笔相同的小层（如一重→一层巅峰）。\n"
        "6. conflict_notes「无依据跳级」仅指跨越大境界且无面板/正文依据；"
        "同境内按五拍突破到小层三/六/九不算冲突。\n"
        "7. forbidden 勿写「禁止本章突破」类，除非五拍明确无修为变化。\n"
    )


def outline_realm_end_hint(ch: DabaiChapterOutline, project: DabaiProject) -> str | None:
    """从本章五拍提取章末境界提示（规划层，供导演单 realm_end 默认）。"""
    blob = " ".join(
        str(getattr(ch, k, None) or "")
        for k in ("yinbao", "shuang_payoff", "emotion_turn", "title")
    )
    if not blob.strip():
        return None
    if not any(m in blob for m in _BREAKTHROUGH_MARKERS) and not _SUB_RE.search(blob):
        return None
    parsed = parse_realm_label(blob, project)
    return parsed.get("label") if parsed else None


def sanitize_prewarn_realm(
    result: dict,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    baseline: RealmBaseline | None,
) -> dict:
    """后处理导演单：开笔对齐基准，realm_end 对齐五拍，修正「暴涨→一层巅峰」矛盾。"""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    fact = dict(out.get("fact_lock") or {})
    beats = dict(out.get("beat_execution") or {})

    if baseline and baseline.label:
        fact["realm"] = baseline.label

    end_hint = outline_realm_end_hint(ch, project)
    realm_end = str(fact.get("realm_end") or "").strip()
    if end_hint:
        hint_parsed = parse_realm_label(end_hint, project) or {}
        start_label = str(fact.get("realm") or (baseline.label if baseline else ""))
        start_parsed = parse_realm_label(start_label, project) or {}
        hint_sub = hint_parsed.get("sub_level") or 0
        start_sub = start_parsed.get("sub_level") or (baseline.sub_level if baseline else 0) or 0
        if not realm_end or hint_sub > start_sub:
            fact["realm_end"] = end_hint
            realm_end = end_hint
    elif not realm_end and fact.get("realm"):
        fact["realm_end"] = str(fact["realm"])
        realm_end = str(fact["realm"])

    realm_end = str(fact.get("realm_end") or "")
    yinbao = str(beats.get("yinbao") or "")
    if realm_end and yinbao and _STALL_ENDING_RE.search(yinbao):
        end_parsed = parse_realm_label(realm_end, project) or {}
        start_parsed = parse_realm_label(str(fact.get("realm") or ""), project) or {}
        end_sub = end_parsed.get("sub_level") or 0
        start_sub = start_parsed.get("sub_level") or 0
        if end_sub > start_sub:
            sub_word = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九"}.get(
                end_sub, str(end_sub),
            )
            major = end_parsed.get("major_name") or start_parsed.get("major_name") or "炼气境"
            beats["yinbao"] = _STALL_ENDING_RE.sub(
                f"{major}{sub_word}重",
                yinbao,
                count=1,
            )

    out["fact_lock"] = _sync_sub_rank_fields(fact, project)
    out["beat_execution"] = beats
    return out


def _sync_sub_rank_fields(fact: dict, project: DabaiProject) -> dict:
    """把 realm / realm_end 字符串与小层整数字段对齐（导演单后处理）。"""
    out = dict(fact)
    for label_key, sub_key in (("realm", "realm_sub_rank"), ("realm_end", "realm_end_sub_rank")):
        label = str(out.get(label_key) or "").strip()
        if not label:
            continue
        parsed = parse_realm_label(label, project) or {}
        sub = out.get(sub_key)
        try:
            sub_int = int(sub) if sub not in (None, "") else None
        except (TypeError, ValueError):
            sub_int = None
        parsed_sub = parsed.get("sub_level")
        if parsed_sub is not None:
            out[sub_key] = int(parsed_sub)
            if parsed.get("label"):
                out[label_key] = str(parsed["label"])
        elif sub_int is not None and parsed.get("major_name"):
            out[label_key] = f"{parsed['major_name']}·第{sub_int}层"
    return out


def build_writing_realm_block(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    baseline: RealmBaseline | None,
) -> str:
    """正文 prompt 境界块：情节基准 + 章纲大境天花板（非「禁止乱跳档」）。"""
    levels = (project.power_ladder or {}).get("levels") or []
    ceiling_rank = ch.realm_rank
    ceiling_name = next(
        (str(l.get("name") or "") for l in levels if int(l.get("rank") or -1) == (ceiling_rank or -1)),
        None,
    )
    lines = ["【境界衔接（情节为准）】"]
    if baseline and baseline.label:
        lines.append(
            f"- 开笔境界：{baseline.label}（{baseline.source}，须紧接，禁止无故倒退）"
        )
    end_hint = outline_realm_end_hint(ch, project)
    if end_hint:
        lines.append(f"- 五拍规划章末：{end_hint}（yinbao/引爆须落实，禁止「暴涨」却停同层）")
    if ceiling_rank and ceiling_name:
        lines.append(
            f"- 章纲大境天花板：第{ceiling_rank}档「{ceiling_name}」"
            "（仅限制跨越大境；同境内小层可按五拍/导演单上涨）"
        )
    lines.append(
        "- ★禁止无故境界倒退★；修为变化须有过程描写，与【系统面板】/导演单 realm_end 一致。"
    )
    return "\n".join(lines) + "\n"


def apply_realm_from_debrief(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    *,
    realm_info: dict | None = None,
    memories: list | None = None,
) -> str | None:
    """复盘后同步：meta、realm_rank、realm_sub_rank（情节回写章纲）。"""
    label: str | None = None
    sub_level: int | None = None
    major_rank: int | None = None

    if isinstance(realm_info, dict):
        realm_str = str(realm_info.get("realm") or "").strip()
        try:
            raw_sub = realm_info.get("sub_level")
            sub_level = int(raw_sub) if raw_sub not in (None, "") else None
        except (TypeError, ValueError):
            sub_level = None
        if realm_str:
            compose = f"{realm_str}·第{sub_level}层" if sub_level else realm_str
            parsed = parse_realm_label(compose, project)
            if parsed:
                label = parsed["label"]
                major_rank = parsed.get("major_rank")
                sub_level = sub_level if sub_level is not None else parsed.get("sub_level")

    if not label:
        content = re.sub(r"<[^>]+>", "", ch.content or "").strip()
        parsed = parse_realm_label(content[-2500:] if content else "", project)
        if parsed:
            label = parsed["label"]
            major_rank = parsed.get("major_rank")
            sub_level = parsed.get("sub_level")

    if not label and memories:
        for mem in reversed(memories):
            if getattr(mem, "mem_type", None) != "state":
                continue
            text = getattr(mem, "content", "") or ""
            if "境" not in text and "重" not in text and "层" not in text:
                continue
            parsed = parse_realm_label(text, project)
            if parsed:
                label = parsed["label"]
                major_rank = parsed.get("major_rank")
                sub_level = parsed.get("sub_level")
                break

    if not label:
        return None

    meta = dict(project.meta or {})
    meta["protagonist_realm"] = label
    meta["protagonist_realm_chapter"] = ch.chapter_number
    project.meta = meta

    if major_rank:
        if ch.realm_rank is None or major_rank >= int(ch.realm_rank):
            ch.realm_rank = major_rank
    if sub_level is not None:
        ch.realm_sub_rank = int(sub_level)

    _sync_protagonist_character_realm(db, project, label, ch.chapter_number)

    return label


def _sync_protagonist_character_realm(
    db: Session,
    project: DabaiProject,
    label: str,
    chapter_number: int,
) -> None:
    """复盘后把主角 current_realm 写入人物 extra（start_realm 保留开局快照）。"""
    from app.models.dabai import DabaiCharacter
    from app.services.dabai.lab_ledger import protagonist_name

    protag = protagonist_name(project)
    row = (
        db.query(DabaiCharacter)
        .filter(
            DabaiCharacter.project_id == project.id,
            DabaiCharacter.name == protag,
        )
        .first()
    )
    if not row:
        return
    extra = dict(row.extra or {})
    extra["current_realm"] = label
    extra["current_realm_chapter"] = chapter_number
    row.extra = extra
