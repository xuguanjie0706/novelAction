"""dabai 质检报告合并 — 规则层 + LLM 层打分归一。

纯函数，不绑定具体数据模型，供实验书架 ``lab_quality`` 复用，
保证 DBQ-* 警告与综合分口径一致；与已退役的主链路 ``quality_check`` 解耦。
"""
from __future__ import annotations

from typing import Any

QC_VERSION = "dabai-qc-v2"

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


def _merge_report(rule: dict, llm: dict | None, llm_status: str) -> dict:
    """规则 + LLM 合并：规则 blockers 仍是唯一阻断；LLM 只追加 warning 与建议。

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

    report["warnings"] = warnings
    report["llm"] = {
        "continuity_score": continuity,
        "continuity_issue": str(llm.get("continuity_issue") or "")[:200],
        "beats": {k: str((llm.get("beats") or {}).get(k) or "pass") for k in _BEAT_KEYS},
        "beat_issues": [str(x)[:80] for x in (llm.get("beat_issues") or [])][:5],
        "beat_score": beat_score,
        "hook_score": hook,
        "hook_issue": str(llm.get("hook_issue") or "")[:200],
        "chapter_suggestions": [
            str(s)[:120]
            for s in (llm.get("chapter_suggestions") or llm.get("suggestions") or [])
        ][:3],
        "future_chapter_suggestions": [
            str(s)[:120] for s in (llm.get("future_chapter_suggestions") or [])
        ][:2],
        # 向后兼容旧读端
        "suggestions": [
            str(s)[:120]
            for s in (llm.get("chapter_suggestions") or llm.get("suggestions") or [])
        ][:3],
    }
    llm_rewrite = str(llm.get("rewrite_prompt") or "").strip()
    if llm_rewrite:
        report["llm"]["rewrite_prompt"] = llm_rewrite[:800]

    cast_blockers = _parse_future_cast_violations(llm)
    if cast_blockers:
        report["blockers"] = list(report.get("blockers") or []) + cast_blockers

    # 综合分：任一 blocker（规则或 LLM 跨章边界）→ 40；
    # 否则 衔接40% + 五拍40% + 钩子20%，再扣规则层 warning 计权（每条 -5 封顶 -15）
    if report.get("blockers"):
        report["status"] = "blocked"
        report["overall_score"] = 40
        return report
    overall = round(continuity * 0.4 + beat_score * 0.4 + hook * 0.2)
    penalty = 5 * len([w for w in rule_warnings if not w.get("score_exempt")])
    report["overall_score"] = max(0, overall - min(penalty, 15))
    report["status"] = "ok" if not warnings else "warning"
    return report
