"""dabai 质检报告合并 — 规则层 + LLM 层打分归一。

纯函数，不绑定具体数据模型，供实验书架 ``lab_quality`` 复用，
保证 DBQ-* 警告与综合分口径一致；与已退役的主链路 ``quality_check`` 解耦。
"""
from __future__ import annotations

import re
from typing import Any

QC_VERSION = "dabai-qc-v3"

_BEAT_KEYS = ("yaqu", "trigger", "yinbao", "payoff", "hook")
_BEAT_LABELS = {
    "yaqu": "憋屈铺垫",
    "trigger": "转折扳机",
    "yinbao": "引爆",
    "payoff": "爽点+见证者",
    "hook": "章末钩子",
}
_BEAT_SCORE = {"pass": 100, "partial": 60, "miss": 20}


def _coerce_score(v: Any, default: int = 80) -> int:
    try:
        return max(0, min(100, int(float(v))))
    except (TypeError, ValueError):
        return default


def _beat_summary(beats: dict) -> tuple[int, list[str]]:
    """五拍状态 → (均分, 未落实拍的标签列表)。

    LLM 漏返回/返回非法值的拍按 partial(60) 计——禁止缺字段默认满分，
    否则 JSON 越残缺综合分越高。
    """
    scores: list[int] = []
    missing: list[str] = []
    for key in _BEAT_KEYS:
        status = str(beats.get(key) or "").lower()
        if status not in _BEAT_SCORE:
            scores.append(_BEAT_SCORE["partial"])
            missing.append(f"{_BEAT_LABELS[key]}（未返回，按 partial 计）")
            continue
        scores.append(_BEAT_SCORE[status])
        if status in ("partial", "miss"):
            missing.append(f"{_BEAT_LABELS[key]}（{status}）")
    return (round(sum(scores) / len(scores)) if scores else 100), missing


def _parse_future_cast_violations(llm: dict) -> list[dict]:
    """LLM 裁决的跨章角色写死/永久移除 → blocker 列表（DBQ-05）。"""
    raw = llm.get("future_cast_violations")
    if not isinstance(raw, list):
        return []
    blockers: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            reason = str(item.get("reason") or item.get("message") or "").strip()
            if not name and not reason:
                continue
            msg = f"后续章出场人物「{name}」被写死或永久移除" if name else reason
            if name and reason:
                msg = f"{msg}：{reason[:80]}"
            blockers.append({"rule_id": "DBQ-05", "message": msg[:160]})
        elif isinstance(item, str) and item.strip():
            blockers.append({"rule_id": "DBQ-05", "message": item.strip()[:160]})
    return blockers


_CRITICAL_KIND_RULE = {
    "realm": "DBQ-08",
    "pov": "DBQ-09",
    "credibility": "DBQ-10",
    "境界": "DBQ-08",
    "可信": "DBQ-10",
    "视角": "DBQ-09",
}

_CRITICAL_PREFIX_RE = re.compile(
    r"^\[(境界|可信|视角|realm|pov|credibility)\]",
    re.IGNORECASE,
)


def _parse_critical_violations(llm: dict) -> list[dict]:
    """LLM 硬伤清单 → blocker（境界/视角/战力可信度）。"""
    raw = llm.get("critical_violations")
    if not isinstance(raw, list):
        return []
    blockers: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            kind = str(item.get("kind") or item.get("type") or "").strip().lower()
            msg = str(item.get("message") or item.get("reason") or "").strip()
            if not msg:
                continue
            rid = _CRITICAL_KIND_RULE.get(kind, "DBQ-08")
            blockers.append({"rule_id": rid, "message": msg[:160]})
        elif isinstance(item, str) and item.strip():
            blockers.append({"rule_id": "DBQ-08", "message": item.strip()[:160]})
    return blockers


def _blockers_from_prefixed_suggestions(llm: dict) -> list[dict]:
    """chapter_suggestions 中带 [境界]/[可信]/[视角] 前缀的项升格为阻断。"""
    tips = llm.get("chapter_suggestions") or llm.get("suggestions") or []
    blockers: list[dict] = []
    for s in tips:
        text = str(s).strip()
        m = _CRITICAL_PREFIX_RE.match(text)
        if not m:
            continue
        kind = m.group(1).lower()
        rid = _CRITICAL_KIND_RULE.get(kind, "DBQ-08")
        body = _CRITICAL_PREFIX_RE.sub("", text).strip()
        blockers.append({
            "rule_id": rid,
            "message": body[:160] if body else text[:160],
        })
    return blockers


def _merge_report(rule: dict, llm: dict | None, llm_status: str) -> dict:
    """规则 + LLM 合并：硬伤（规则 DLB-07+ / LLM critical_violations）一律阻断。

    裁决权单轨：标记 ``llm_overridable`` 的规则 warning（如 DLB-03 位移证据）
    已注入 LLM prompt 由其裁决，LLM 正常返回时丢弃，避免规则误报否决 LLM 结论；
    LLM 降级时保留作兜底。其余规则 warning 计入综合分（每条 -5，封顶 -15，
    ``score_exempt`` 标记除外）。
    """
    report = dict(rule)
    report["version"] = QC_VERSION
    report["llm_status"] = llm_status
    rule_warnings = list(rule.get("warnings") or [])
    if llm_status == "ok":
        rule_warnings = [w for w in rule_warnings if not w.get("llm_overridable")]
    report["warnings"] = rule_warnings
    if llm_status in {"error", "parse_error"}:
        report["raw_score"] = int(rule.get("overall_score") or 0)
        report["warnings"] = [
            *rule_warnings,
            {
                "rule_id": "DBQ-00",
                "message": "LLM 质检未完成，本次报告不可作为通过依据，请重新质检",
            },
        ]
        if report.get("blockers"):
            report["status"] = "blocked"
            report["overall_score"] = min(40, int(rule.get("overall_score") or 40))
        else:
            report["overall_score"] = 0
            report["status"] = "unverified"
        return report
    if not isinstance(llm, dict) or llm_status != "ok":
        return report

    warnings = list(rule_warnings)
    continuity = _coerce_score(llm.get("continuity_score"))
    hook = _coerce_score(llm.get("hook_score"))
    beat_score, missing_beats = _beat_summary(llm.get("beats") or {})

    rep = str(llm.get("repetition_issue") or "").strip()
    hook_endhook_paste = rep and any(
        k in rep for k in ("end_hook", "章纲", "复读", "重复")
    )
    if hook_endhook_paste and str((llm.get("beats") or {}).get("hook") or "").lower() == "partial":
        beats_out = dict(llm.get("beats") or {})
        beats_out["hook"] = "pass"
        llm = {**llm, "beats": beats_out}
        missing_beats = [m for m in missing_beats if "章末钩子" not in m]
        if hook < 80:
            hook = 80
        beat_score, _ = _beat_summary(beats_out)

    if continuity < 70:
        warnings.append({
            "rule_id": "DBQ-01",
            "message": f"开头衔接弱（{continuity}分）：{str(llm.get('continuity_issue') or '')[:80]}",
        })
    for label in missing_beats:
        warnings.append({"rule_id": "DBQ-02", "message": f"五拍未落实：{label}"})
    if hook < 60:
        warnings.append({
            "rule_id": "DBQ-03",
            "message": f"章末钩子弱（{hook}分）：{str(llm.get('hook_issue') or '')[:80]}",
        })
    if rep:
        warnings.append({"rule_id": "DBQ-04", "message": f"本章内重复铺陈：{rep[:80]}"})

    naturalness = _coerce_score(llm.get("naturalness_score"), default=85)
    overused = [
        str(p).strip() for p in (llm.get("overused_phrases") or []) if str(p).strip()
    ][:5]
    witness_issue = str(llm.get("witness_reaction_issue") or "").strip()
    if naturalness < 70:
        msg = f"文字自然度偏低（{naturalness}分）"
        if witness_issue:
            msg += f"：{witness_issue[:60]}"
        warnings.append({"rule_id": "DBQ-07", "message": msg[:120]})
    elif overused:
        warnings.append({
            "rule_id": "DBQ-07",
            "message": f"套话重复：{'、'.join(overused[:3])}"[:120],
        })

    report["warnings"] = warnings
    report["llm"] = {
        "continuity_score": continuity,
        "continuity_issue": str(llm.get("continuity_issue") or "")[:200],
        "beats": {k: str((llm.get("beats") or {}).get(k) or "pass") for k in _BEAT_KEYS},
        "beat_issues": [str(x)[:80] for x in (llm.get("beat_issues") or [])][:5],
        "beat_score": beat_score,
        "hook_score": hook,
        "hook_issue": str(llm.get("hook_issue") or "")[:200],
        "naturalness_score": naturalness,
        "overused_phrases": overused,
        "witness_reaction_issue": witness_issue[:200],
        "chapter_suggestions": [
            str(s)[:120]
            for s in (llm.get("chapter_suggestions") or llm.get("suggestions") or [])
            if not _CRITICAL_PREFIX_RE.match(str(s).strip())
        ][:3],
        "future_chapter_suggestions": [
            str(s)[:120] for s in (llm.get("future_chapter_suggestions") or [])
        ][:2],
        # 向后兼容旧读端
        "suggestions": [
            str(s)[:120]
            for s in (llm.get("chapter_suggestions") or llm.get("suggestions") or [])
            if not _CRITICAL_PREFIX_RE.match(str(s).strip())
        ][:3],
    }
    llm_rewrite = str(llm.get("rewrite_prompt") or "").strip()
    if llm_rewrite:
        report["llm"]["rewrite_prompt"] = llm_rewrite[:800]

    cast_blockers = _parse_future_cast_violations(llm)
    critical_blockers = (
        _parse_critical_violations(llm)
        + _blockers_from_prefixed_suggestions(llm)
    )
    if cast_blockers or critical_blockers:
        merged = list(report.get("blockers") or [])
        seen = {str(b.get("message") or "") for b in merged}
        for b in cast_blockers + critical_blockers:
            if b.get("message") not in seen:
                merged.append(b)
                seen.add(str(b.get("message") or ""))
        report["blockers"] = merged

    # 质量原始分与门控分分离：blocker 仍把兼容字段 overall_score 封顶 40，
    # raw_score 保留正文自身质量，避免把「92分但有一条硬伤」误读为整体只有40分。
    overall = round(
        continuity * 0.35 + beat_score * 0.35 + hook * 0.15 + naturalness * 0.15,
    )
    penalty = 5 * len([w for w in rule_warnings if not w.get("score_exempt")])
    raw_score = max(0, overall - min(penalty, 15))
    report["raw_score"] = raw_score
    if report.get("blockers"):
        report["status"] = "blocked"
        report["overall_score"] = min(40, int(report.get("overall_score") or 40))
        if critical_blockers:
            llm_part = report.get("llm") if isinstance(report.get("llm"), dict) else {}
            report["llm"] = {
                **llm_part,
                "critical_violations": [
                    {"kind": b.get("rule_id"), "message": b.get("message")}
                    for b in critical_blockers
                ],
            }
        return report
    report["overall_score"] = raw_score
    report["status"] = "ok" if not warnings else "warning"
    return report
