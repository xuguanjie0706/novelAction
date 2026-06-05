"""Bootstrap Fanfic：原著设定结构化（canon_pack）。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.json_once import call_bootstrap_json_once
from app.services.bootstrap.steps.fanfic._helpers import fanfic_meta_block, persist_extra

_STEP = "fanfic_canon_pack"

_VAGUE_FACT_MARKERS = (
    "保持原著风格", "忠于原著", "尊重原著", "原著风格", "符合原著",
    "贴合原著", "还原原著", "不要OOC", "不能OOC", "保持人设",
)


def _facts_are_executable(facts: Any) -> tuple[bool, str]:
    if not isinstance(facts, list) or len(facts) < 4:
        return False, "immutable_facts 至少 4 条"
    bad: list[str] = []
    for f in facts:
        s = str(f or "").strip()
        if len(s) < 6:
            bad.append(s or "(空)")
            continue
        if any(marker in s for marker in _VAGUE_FACT_MARKERS):
            bad.append(s)
    if bad:
        return False, (
            "immutable_facts 含无法校验的空话（须写具体事实，如「角色A在原著中已死于X事件」），"
            f"问题条目：{bad[:3]}"
        )
    return True, ""


async def gen_canon_pack(svc: Any, project: Project, ctx: dict) -> dict:
    system = "你是同人设定编辑。只根据作者提供的梗概结构化原著，禁止编造梗概中未出现的关键设定。只返回 JSON。"
    meta = ctx.get("fanfic_meta") or {}
    prompt = f"""{fanfic_meta_block(ctx)}
创意：{ctx['logline']}

原著梗概：
{(meta.get('canon_synopsis') or '')[:4000]}

返回 JSON：
{{
  "world_summary": "世界观一句话（30字内）",
  "timeline_anchors": ["原著关键时间节点 3-6 条"],
  "immutable_facts": ["不可在正文中推翻的原著事实 4-8 条"],
  "power_system_from_source": "原著力量/等级体系简述（无则写「无明确体系」）",
  "key_relationships": ["重要人物关系 4-8 条，格式：A—关系—B"],
  "character_roster": [
    {{
      "name": "原著角色名",
      "role_in_source": "在原著中的身份",
      "traits": "性格关键词（一句话）",
      "speech_hint": "说话风格提示（10字内）",
      "importance": "major|supporting|minor"
    }}
  ]
}}

要求：
1. character_roster 至少 5 人，须来自梗概
2. immutable_facts 必须可执行校验（禁止「保持原著风格」）
3. 只返回 JSON"""

    def _validate(data: Any) -> str | None:
        if not isinstance(data, dict):
            return "须为 JSON 对象"
        roster = data.get("character_roster")
        if not isinstance(roster, list) or len(roster) < 3:
            return "character_roster 至少 3 人"
        if not data.get("world_summary"):
            return "world_summary 不能为空"
        facts_ok, facts_err = _facts_are_executable(data.get("immutable_facts"))
        if not facts_ok:
            return facts_err
        return None

    data = await call_bootstrap_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.settings",
        validate=_validate,
    )
    persist_extra(project, svc, "fanfic_canon", data)
    ctx["fanfic_canon"] = data
    return data
