"""dabai 质检硬伤规则 — 境界错/上帝视角/战力崩（零 LLM，写进 blockers）。

设计动机：此前 LLM 把 [境界]/[可信]/[视角] 仅写进 chapter_suggestions，
综合分仍可达 90+，重写门控失效。本模块提供可确定性拦截的子集；
其余由 qc_merge 把 LLM critical_violations 与带前缀建议升格为阻断。
"""
from __future__ import annotations

import re

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.services.dabai.lab_char_voice import resolve_char_realm
from app.services.dabai.lab_prewarn_outline_lock import (
    extract_outline_cast_realms,
    format_locked_realm_label,
)
from app.services.dabai.lab_realm_baseline import cn_to_int, parse_realm_label

# 上帝视角 / 作者下场（命中即 DLB-07 阻断）
_GOD_POV_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"此人正是[^。！？\n]{4,80}"), "上帝视角旁白直接报出人物身份"),
    (re.compile(r"殊不知"), "作者下场「殊不知」式全知叙述"),
    (re.compile(r"其实这是[^。！？\n]{4,60}"), "作者下场「其实这是…」式点评"),
    (re.compile(r"这正是[^。！？\n]{4,60}(?:奥妙|玄机|关键)"), "作者下场分析剧情奥妙"),
    (
        re.compile(
            r"(?<!「)(?<!『)(?<!\")(?<!')[^「」\n]{0,12}"
            r"(?:练气|炼气|筑基)[^。！？\n]{0,12}(?:[一二三四五六七八九十\d]+)层[^。！？\n]{0,8}修为"
        ),
        "旁白直接报出角色修为（非对话/非感知描写）",
    ),
)

# 感知/议论语境豁免（±30 字窗口内出现则不算上帝视角报境界）
_PERCEPTION_CTX = (
    "听说", "传闻", "据说", "议论", "惊呼", "失声", "察觉", "感知", "探查",
    "灵识", "扫过", "看出", "辨认", "认出", "眼力", "一眼", "暗道", "心中",
    "暗想", "猜测", "估计", "像是", "似乎", "约莫", "恐怕", "莫非",
)

_REALM_NEAR_NAME_RE = re.compile(
    r"(练气|炼气|筑基)[期境]?[^。，！？\n]{0,6}([一二三四五六七八九十\d]+)层",
)


def _in_dialogue_quote(text: str, pos: int) -> bool:
    """pos 是否落在「」对话引号内。"""
    before = text[:pos]
    opens = before.count("「") + before.count("『")
    closes = before.count("」") + before.count("』")
    return opens > closes


def _realm_levels_attributed_to_name(content: str, name: str) -> list[int]:
    """正文中旁白明确归属该角色的层数（排除对话议论）。"""
    levels: list[int] = []
    if not name or not content:
        return levels
    esc = re.escape(name)
    pat = re.compile(
        rf"{esc}(?:是|乃|已有|已达|修为为|为)?[^。，！？\n]{{0,6}}"
        rf"(?:练气|炼气|筑基)[期境]?[^。，！？\n]{{0,6}}([一二三四五六七八九十\d]+)层"
        rf"|"
        rf"(?:练气|炼气|筑基)[期境]?[^。，！？\n]{{0,6}}([一二三四五六七八九十\d]+)层"
        rf"[^。，！？\n]{{0,6}}{esc}",
    )
    for m in pat.finditer(content):
        if _in_dialogue_quote(content, m.start()):
            continue
        for g in (m.group(1), m.group(2)):
            if g is None:
                continue
            sub = cn_to_int(g)
            if sub is not None:
                levels.append(sub)
    return levels


def _realm_mentions_near_name(content: str, name: str) -> list[int]:
    """正文中紧挨人名出现的「X层」小层整数列表（粗粒度，仅战力检测兜底）。"""
    levels: list[int] = []
    if not name or not content:
        return levels
    start = 0
    while True:
        idx = content.find(name, start)
        if idx < 0:
            break
        if _in_dialogue_quote(content, idx):
            start = idx + len(name)
            continue
        window = content[max(0, idx - 45): idx + len(name) + 45]
        for m in _REALM_NEAR_NAME_RE.finditer(window):
            sub = cn_to_int(m.group(2))
            if sub is not None:
                levels.append(sub)
        start = idx + len(name)
    return levels


def _plain(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _extract_sub_level(realm_label: str, project: DabaiProject) -> int | None:
    parsed = parse_realm_label(realm_label, project)
    if parsed and parsed.get("sub_level") is not None:
        return int(parsed["sub_level"])
    m = re.search(r"([一二三四五六七八九十\d]+)层", realm_label or "")
    if m:
        return cn_to_int(m.group(1))
    return None


def _has_perception_context(content: str, pos: int) -> bool:
    window = content[max(0, pos - 35): pos + 35]
    return any(k in window for k in _PERCEPTION_CTX)


def check_god_pov_violations(content: str) -> list[dict]:
    """规则 DLB-07：限知第三人称下的全知旁白/作者下场。"""
    plain = _plain(content)
    if not plain:
        return []
    blockers: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()
    for pat, label in _GOD_POV_PATTERNS:
        for m in pat.finditer(plain):
            span = (m.start(), m.end())
            if any(not (span[1] <= s0 or span[0] >= s1) for s0, s1 in seen_spans):
                continue
            snippet = m.group(0).strip()[:60]
            if pat.pattern.find("修为") >= 0 and _has_perception_context(plain, m.start()):
                continue
            seen_spans.add(span)
            blockers.append({
                "rule_id": "DLB-07",
                "message": f"{label}：「{snippet}…」"[:160],
            })
            break
    return blockers


def check_cast_realm_mismatch(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    content: str,
) -> list[dict]:
    """规则 DLB-08：出场配角正文称述境界与人物档案不一致（无突破/误判描写）。"""
    plain = _plain(content)
    if not plain:
        return []
    involved = getattr(ch, "involved_characters", None) or []
    witnesses = getattr(ch, "witnesses", None) or []
    stage = list(dict.fromkeys(
        [str(n).strip() for n in involved + witnesses if str(n).strip()]
    ))
    locked = extract_outline_cast_realms(ch) if ch else {}
    by_name = {str(c.name).strip(): c for c in (project.characters or []) if c.name}
    blockers: list[dict] = []
    exempt_markers = ("突破", "误判", "看走眼", "伪装", "压制", "隐瞒", "其实已是", "早已")

    for name in stage:
        c = by_name.get(name)
        if not c:
            continue
        if name in locked:
            arch_realm = format_locked_realm_label(locked[name], project)
            expected_sub = locked[name]
        else:
            arch_realm = resolve_char_realm(c, project=project, ch=ch)
            expected_sub = _extract_sub_level(arch_realm, project)
        if expected_sub is None:
            continue
        mentioned = _realm_levels_attributed_to_name(plain, name)
        if not mentioned:
            continue
        for sub in mentioned:
            if sub == expected_sub:
                continue
            near_idx = plain.find(name)
            window = plain[max(0, near_idx - 80): near_idx + 80] if near_idx >= 0 else ""
            if any(m in window for m in exempt_markers):
                continue
            blockers.append({
                "rule_id": "DLB-08",
                "message": (
                    f"配角境界与档案不符：{name} 档案为「{arch_realm}」，"
                    f"正文近旁写「练气{sub}层」且无突破/误判描写"
                )[:160],
            })
            break
    return blockers


def check_credibility_hard_gaps(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    content: str,
    *,
    protagonist_name: str = "",
) -> list[dict]:
    """规则 DLB-09：主角越级碾压但正文无金手指/阴寒/奇袭等依据词（粗粒度）。"""
    plain = _plain(content)
    if not plain or not protagonist_name:
        return []
    protag_sub = None
    for sub in _realm_levels_attributed_to_name(plain, protagonist_name):
        protag_sub = sub
        break
    if protag_sub is None:
        for m in _REALM_NEAR_NAME_RE.finditer(plain):
            ctx = plain[max(0, m.start() - 30): m.end() + 30]
            if protagonist_name in ctx:
                protag_sub = cn_to_int(m.group(2))
                break
    if protag_sub is None:
        return []

    instant = any(k in plain for k in ("一招", "秒杀", "废掉", "丹田尽碎", "丹田被废", "一息"))
    if not instant:
        return []

    opp_higher = False
    outline_locked = extract_outline_cast_realms(ch)
    stage = [str(n).strip() for n in (ch.involved_characters or []) if str(n).strip()]
    by_name = {str(c.name).strip(): c for c in (project.characters or []) if c.name}
    for name in stage:
        if name == protagonist_name:
            continue
        if name in outline_locked:
            exp = outline_locked[name]
            if exp >= protag_sub + 3:
                opp_higher = True
                break
            continue
        for sub in _realm_levels_attributed_to_name(plain, name):
            if sub >= protag_sub + 3:
                opp_higher = True
                break
        if not opp_higher:
            c = by_name.get(name)
            if c:
                exp = _extract_sub_level(
                    resolve_char_realm(c, project=project, ch=ch), project,
                )
                if exp is not None and exp >= protag_sub + 3:
                    opp_higher = True
        if opp_higher:
            break
    if not opp_higher:
        return []

    basis = (
        "万魂幡", "阴寒", "腐蚀", "奇袭", "破绽", "轻敌", "偷袭", "空当",
        "森冷", "魔道", "幡", "冻结", "蚀", "灌顶",
    )
    fight_zone = plain
    for kw in ("一招", "秒杀", "废掉", "丹田"):
        idx = plain.find(kw)
        if idx >= 0:
            fight_zone = plain[max(0, idx - 400): idx + 200]
            break
    if any(b in fight_zone for b in basis):
        return []

    return [{
        "rule_id": "DLB-09",
        "message": (
            f"战力硬伤：主角约练气{protag_sub}层却一招废掉高至少三层的对手，"
            f"战斗段落未见金手指/阴寒法力/奇袭破绽等铺垫"
        )[:160],
    }]


def run_critical_rule_checks(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    content: str,
    *,
    protagonist_name: str = "",
) -> list[dict]:
    """汇总规则层硬伤 → blocker 列表。"""
    blockers: list[dict] = []
    blockers.extend(check_god_pov_violations(content))
    blockers.extend(check_cast_realm_mismatch(project, ch, content))
    if protagonist_name:
        blockers.extend(check_credibility_hard_gaps(
            project, ch, content, protagonist_name=protagonist_name,
        ))
    return blockers
