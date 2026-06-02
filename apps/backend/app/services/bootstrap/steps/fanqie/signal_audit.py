"""Bootstrap Fanqie Steps 17-18：算法双校验。

两个校验维度完全独立，对应番茄算法的两个核心行为：
1. 类型信号强度：推荐标签匹配（决定能不能被推到对的读者）
2. 爽感密度审计：完读率（决定算法愿不愿意继续推）

这不是「文学审美评估」，而是「平台算法审计」。
产物写入 Project.extra['signal_audit']。
"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_signal_audit(svc: Any, project: Project, ctx: dict) -> dict:
    """
    执行番茄算法双校验：类型信号强度 + 爽感密度审计。

    对于不通过的检查项，自动生成修复建议并写回对应的 extra 字段。

    @returns signal_audit dict（含 overall_pass 和 fix_suggestions）
    """
    system = (
        "你是番茄小说算法审核官，代入番茄的推荐算法逻辑做审核。"
        "只返回 JSON，不要解释文字。"
    )
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    contrast = ctx.get("contrast_design") or {}
    gf = ctx.get("golden_finger") or {}
    fsm = ctx.get("face_slap_map") or {}
    op5 = ctx.get("opening_5chapters") or {}
    rm = ctx.get("rhythm_map") or {}

    ch1 = op5.get("chapter_1", {})
    ch1_struct = ch1.get("structure", {})
    first_slap_ch = fsm.get("first_slap_chapter", 99)
    trigger_est = contrast.get("trigger_word_estimate", "")
    dry_spells = rm.get("auto_dry_spells") or rm.get("dry_spell_warnings") or []
    tags_sample = (rm.get("chapter_tags") or [])[:10]

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{fanqie_pos.get('genre_archetype', '')}
平台标签：{fanqie_pos.get('platform_tags', [])}
核心爽感：{fanqie_pos.get('core_satisfaction', '')}
算法钩子：{fanqie_pos.get('algo_hook', '')}

第1章前200字规划：{ch1_struct.get('opening_200_words', '（未设定）')}
第1章首句：{op5.get('first_sentence', '（未设定）')}
金手指触发时机：{trigger_est or '（未设定）'}
首次打脸章节：第{first_slap_ch}章
连续过渡警告：{dry_spells or '（无警告）'}
前10章节奏标签：{_fmt_tags(tags_sample)}

请作为番茄算法审核官，执行双校验，返回 JSON：
{{
  "genre_signal_check": {{
    "pass": true,
    "score": 8,
    "issue": "类型信号问题（如有），否则 null",
    "detail": "评估：第1章前200字能否让读者在5秒内判断类型？平台标签是否准确？（30字内）",
    "fix": "修复建议（如 pass=true 则填 null）"
  }},
  "golden_finger_timing_check": {{
    "pass": true,
    "trigger_word_estimate": "具体字数（如650）",
    "threshold": 800,
    "issue": "若超过800字触发则说明问题，否则 null",
    "fix": "修复建议（如 pass=true 则填 null）"
  }},
  "first_slap_timing_check": {{
    "pass": true,
    "chapter": {first_slap_ch},
    "threshold": 5,
    "issue": "若超过第5章则说明问题，否则 null",
    "fix": "修复建议（如 pass=true 则填 null）"
  }},
  "satisfaction_density_check": {{
    "pass": true,
    "dry_spell_count": {len(dry_spells)},
    "worst_dry_spell": "最长连续过渡区间（如有），否则 null",
    "issue": "问题说明（如有），否则 null",
    "fix": "修复建议（如 pass=true 则填 null）"
  }},
  "hook_quality_check": {{
    "pass": true,
    "score": 7,
    "issue": "算法钩子是否足够吸引目标读者？有无明显问题？",
    "fix": "优化建议（最重要的一条，或 null）"
  }},
  "overall_pass": true,
  "overall_score": 85,
  "critical_fixes": ["最需要在正式写作前修复的问题（按优先级排，最多3条；若全部通过则为空数组）"],
  "algo_optimization_tips": ["提升番茄算法推荐量的额外建议（2-3条，针对本书的具体建议）"]
}}

评分标准：
- 类型信号 ≥7分：第1章前200字类型清晰，平台标签准确
- 金手指触发 ≤800字：否则读者流失前未获得爽感期待
- 首次打脸 ≤第5章：番茄算法基准线
- 满分100分：各项检查通过各+20分，algo_optimization加分
- 只返回 JSON"""

    last_err = ""
    for attempt in range(3):
        fix = f"\n【请修正：{last_err}】" if last_err else ""
        raw = await svc._call_with_retry(
            system, prompt + fix,
            max_tokens=max_tokens_bootstrap_completion(),
            task="quality.check",
        )
        try:
            data = parse_json(raw)
        except Exception:
            last_err = "JSON 解析失败"
            continue
        if not isinstance(data, dict):
            last_err = "须为 JSON 对象"
            continue
        required = {"genre_signal_check", "overall_pass", "overall_score"}
        if missing := required - data.keys():
            last_err = f"缺少字段：{missing}"
            continue

        extra = dict(project.extra or {})
        extra["signal_audit"] = data
        # 将不通过的检查项写入 consistency_issues（兼容前端展示）
        issues = _collect_issues(data)
        extra["consistency_issues"] = issues
        project.extra = extra
        svc.db.commit()

        ctx["signal_audit"] = data
        return data

    return {}


def _fmt_tags(tags: list) -> str:
    if not tags:
        return "（未生成）"
    return "  ".join(
        f"Ch{t.get('ch','')}:{t.get('type','')}" for t in tags[:10] if isinstance(t, dict)
    )


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
