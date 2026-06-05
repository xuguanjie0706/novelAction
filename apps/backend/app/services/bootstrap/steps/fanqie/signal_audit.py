"""Bootstrap Fanqie：算法双校验（规则版，无 LLM）。

设计动机（2026-06）
------------------
原实现走 ``quality.check``，管理后台误标为「章节质检」，且与写作期质检重复。
Bootstrap 阶段改为纯规则审计（金手指字数 / 首次打脸章 / 节奏 dry_spell 等），
零 token；产物 schema 与下游 ``consistency_issues`` 兼容。
"""
from __future__ import annotations

import re
from typing import Any

from app.models import Project

_STEP = "signal_audit"


def _first_int(s: str) -> int | None:
    m = re.search(r"\d+", str(s))
    return int(m.group()) if m else None


def _build_signal_audit_by_rules(ctx: dict) -> dict:
    """从已有 Bootstrap 产物做番茄算法规则审计，不调用 LLM。"""
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    contrast = ctx.get("contrast_design") or {}
    gf = ctx.get("golden_finger") or {}
    fsm = ctx.get("face_slap_map") or {}
    rm = ctx.get("rhythm_map") or {}

    genre_archetype = (fanqie_pos.get("genre_archetype") or "").strip()
    platform_tags = fanqie_pos.get("platform_tags") or []
    algo_hook = (fanqie_pos.get("algo_hook") or "").strip()
    opening_hook = (contrast.get("initial_state_headline") or "").strip() or algo_hook

    first_slap_ch = fsm.get("first_slap_chapter")
    if not isinstance(first_slap_ch, int):
        first_slap_ch = _first_int(str(first_slap_ch or "")) or 99

    trigger_raw = str(
        contrast.get("trigger_word_estimate")
        or gf.get("trigger_timing")
        or gf.get("activation_timing")
        or "",
    ).strip()
    trigger_words = _first_int(trigger_raw)

    dry_spells = rm.get("auto_dry_spells") or rm.get("dry_spell_warnings") or []
    dry_count = len(dry_spells) if isinstance(dry_spells, list) else 0
    worst_dry = dry_spells[0] if dry_spells else None

    genre_pass = bool(genre_archetype) and bool(platform_tags)
    genre_check = {
        "pass": genre_pass,
        "score": 8 if genre_pass else 4,
        "issue": None if genre_pass else "缺少类型公式或平台标签",
        "detail": f"类型={genre_archetype or '未设定'}；标签数={len(platform_tags)}",
        "fix": None if genre_pass else "补全 fanqie_positioning.genre_archetype 与 platform_tags",
    }

    gf_pass = trigger_words is None or trigger_words <= 800
    gf_check = {
        "pass": gf_pass,
        "trigger_word_estimate": str(trigger_words or trigger_raw or "未设定"),
        "threshold": 800,
        "issue": None if gf_pass else f"金手指触发约第{trigger_words}字，超过800字阈值",
        "fix": None if gf_pass else "将金手指触发前移到800字内，或在 contrast_design 调整 trigger_word_estimate",
    }

    slap_pass = isinstance(first_slap_ch, int) and first_slap_ch <= 5
    slap_check = {
        "pass": slap_pass,
        "chapter": first_slap_ch,
        "threshold": 5,
        "issue": None if slap_pass else f"首次打脸在第{first_slap_ch}章，超过第5章",
        "fix": None if slap_pass else "将 face_slap_map.first_slap_chapter 调整到 ≤5",
    }

    density_pass = dry_count <= 1
    density_check = {
        "pass": density_pass,
        "dry_spell_count": dry_count,
        "worst_dry_spell": worst_dry,
        "issue": None if density_pass else f"存在 {dry_count} 处连续过渡区间",
        "fix": None if density_pass else "在 rhythm_map 中增加 small_win/big_win 锚点",
    }

    hook_pass = len(opening_hook) >= 8
    hook_check = {
        "pass": hook_pass,
        "score": 8 if hook_pass else 5,
        "issue": None if hook_pass else "开局钩子/处境 headline 过短或缺失",
        "fix": None if hook_pass else "补全 contrast_design.initial_state_headline 或 fanqie_positioning.algo_hook",
    }

    checks = (genre_check, gf_check, slap_check, density_check, hook_check)
    overall_pass = all(c.get("pass") for c in checks)
    overall_score = min(100, sum(20 for c in checks if c.get("pass")) + (5 if overall_pass else 0))

    critical_fixes = []
    for key, label, chk in (
        ("genre", "类型信号", genre_check),
        ("gf", "金手指时机", gf_check),
        ("slap", "首次打脸", slap_check),
        ("density", "爽感密度", density_check),
        ("hook", "算法钩子", hook_check),
    ):
        if not chk.get("pass") and chk.get("issue"):
            critical_fixes.append(f"[{label}] {chk['issue']}")
    critical_fixes = critical_fixes[:3]

    return {
        "genre_signal_check": genre_check,
        "golden_finger_timing_check": gf_check,
        "first_slap_timing_check": slap_check,
        "satisfaction_density_check": density_check,
        "hook_quality_check": hook_check,
        "overall_pass": overall_pass,
        "overall_score": overall_score,
        "critical_fixes": critical_fixes,
        "algo_optimization_tips": [] if overall_pass else ["规则审计未全通过，请按 critical_fixes 修正规划产物"],
        "_generated_by": "rule",
    }


async def gen_signal_audit(svc: Any, project: Project, ctx: dict) -> dict:
    """
    执行番茄算法双校验（规则版）。

    @returns signal_audit dict（含 overall_pass 和 fix_suggestions）
    """
    data = _build_signal_audit_by_rules(ctx)

    extra = dict(project.extra or {})
    extra["signal_audit"] = data
    extra["consistency_issues"] = _collect_issues(data)
    project.extra = extra
    svc.db.commit()
    ctx["signal_audit"] = data
    return data


def _collect_issues(audit: dict) -> list[dict]:
    """把未通过的校验项整理为 consistency_issues 格式（供前端展示）。"""
    issues = []
    for key, label in (
        ("genre_signal_check", "类型信号"),
        ("golden_finger_timing_check", "金手指触发时机"),
        ("first_slap_timing_check", "首次打脸时机"),
        ("satisfaction_density_check", "爽感密度"),
        ("hook_quality_check", "算法钩子质量"),
    ):
        check = audit.get(key, {})
        if isinstance(check, dict) and not check.get("pass", True):
            issues.append({
                "type": "fanqie_signal",
                "label": label,
                "issue": check.get("issue", "未通过"),
                "fix": check.get("fix", ""),
            })
    for tip in audit.get("critical_fixes") or []:
        issues.append({"type": "fanqie_critical", "label": "关键修复", "issue": tip})
    return issues
