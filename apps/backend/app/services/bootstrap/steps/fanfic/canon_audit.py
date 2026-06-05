"""Bootstrap Fanfic：原著贴合 + 番茄爽感双校验。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.json_once import call_bootstrap_json_once
from app.services.bootstrap.steps.fanfic._helpers import fanfic_meta_block, persist_extra

_STEP = "fanfic_canon_audit"


async def gen_canon_audit(svc: Any, project: Project, ctx: dict) -> dict:
    system = "你是同人质检编辑。只返回 JSON。"
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

    def _validate(data: Any) -> str | None:
        if not isinstance(data, dict) or not data.get("opening_verdict"):
            return "opening_verdict 必填"
        risk = str(data.get("canon_risk_score") or "").strip().lower()
        verdict = str(data.get("opening_verdict") or "").strip()
        data["review_required"] = bool(risk == "high" or verdict == "需调整")
        return None

    data = await call_bootstrap_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate,
    )
    persist_extra(project, svc, "fanfic_audit", data)
    if data.get("review_required"):
        persist_extra(project, svc, "fanfic_canon_review_required", True)
    ctx["fanfic_audit"] = data
    return data
