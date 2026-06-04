"""Bootstrap Fanfic：原著贴合 + 番茄爽感双校验。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.steps.fanfic._helpers import fanfic_meta_block, persist_extra
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_canon_audit(svc: Any, project: Project, ctx: dict) -> dict:
    system = "你是同人质检编辑。只返回 JSON。"
    canon = ctx.get("fanfic_canon") or {}
    dev = ctx.get("fanfic_deviation") or {}
    rhythm = ctx.get("rhythm_map") or {}
    prompt = f"""{fanfic_meta_block(ctx)}
魔改边界：{dev.get('divergence_point', '')}
禁止改动：{'; '.join((dev.get('forbidden_changes') or [])[:5])}
前50章爽点标签数：{len(rhythm.get('chapter_tags') or [])}

返回 JSON：
{{
  "canon_risk_score": "high|medium|low",
  "canon_issues": ["人设/时间线风险 2-5 条"],
  "satisfaction_density": "high|medium|low",
  "satisfaction_issues": ["爽感节奏问题 0-3 条"],
  "opening_verdict": "通过|需调整",
  "fix_hints": ["给章纲/开局的修正建议 2-4 条"]
}}"""

    last_err = ""
    for attempt in range(3):
        fix = f"\n【请修正：{last_err}】" if last_err else ""
        raw = await svc._call_with_retry(
            system, prompt + fix,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.positioning",
        )
        try:
            data = parse_json(raw)
        except Exception:
            last_err = "JSON 解析失败"
            continue
        if not isinstance(data, dict) or not data.get("opening_verdict"):
            last_err = "opening_verdict 必填"
            continue
        # 梗概多为 AI 推断，高风险时立旗标，供 UI 提示作者核对 + 章纲展开期回灌 fix_hints。
        risk = str(data.get("canon_risk_score") or "").strip().lower()
        verdict = str(data.get("opening_verdict") or "").strip()
        data["review_required"] = bool(risk == "high" or verdict == "需调整")
        persist_extra(project, svc, "fanfic_audit", data)
        if data["review_required"]:
            persist_extra(project, svc, "fanfic_canon_review_required", True)
        ctx["fanfic_audit"] = data
        return data
    return {}
