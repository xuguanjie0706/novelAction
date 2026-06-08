"""章纲 chapter_plan 节点 ``extra`` 字段构建（含结构化生死声明）。

从 vol_chapter_plans 抽离：把"AI 返回的单章 JSON → OutlineNode.extra"的字段映射
集中在此，便于演进与单测，也让编排壳保持精简。
"""
from __future__ import annotations

from app.services.bootstrap.foreshadow_ops import prepare_chapter_foreshadow_for_node


def _declared_names(value: object) -> list[str]:
    """规整生死声明名单：去空白、去空串，保持顺序。"""
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def build_chapter_extra(item: dict, is_fanqie: bool) -> dict:
    """构建 OutlineNode.extra，番茄模式时追加爽感字段。

    ``deaths_declared`` / ``revives_declared``：结构化生死声明，作为一致性校验的精确
    主信号（无施害者/受害者歧义），与正文正则抽取取并集（见 event_ledger）。
    """
    fs_ops, _, _, foreshadow_legacy = prepare_chapter_foreshadow_for_node(item)
    base = {
        "foreshadow": foreshadow_legacy,
        "foreshadow_ops": fs_ops,
        "promise_fulfilled": (item.get("promise_fulfilled") or "").strip(),
        "end_hook": (item.get("end_hook") or "").strip(),
        "has_face_slap": item.get("has_face_slap", False),
        "has_emotional_beat": item.get("has_emotional_beat", False),
        "protagonist_want": (item.get("protagonist_want") or "").strip(),
        "protagonist_obstacle": (item.get("protagonist_obstacle") or "").strip(),
        "protagonist_choice": (item.get("protagonist_choice") or "").strip(),
        "choice_cost": (item.get("choice_cost") or "").strip(),
        "villain_action": (item.get("villain_action") or "").strip(),
        "supporting_spotlight": (item.get("supporting_spotlight") or "").strip(),
        "reader_emotion_target": (item.get("reader_emotion_target") or "").strip(),
        "deaths_declared": _declared_names(item.get("deaths")),
        "revives_declared": _declared_names(item.get("revives")),
        "bootstrap_generated": False,
        "lazy_expanded": True,
        "storyline_beat_ref": (item.get("storyline_beat_ref") or "").strip(),
    }
    if is_fanqie:
        base.update({
            "satisfaction_setup": (item.get("satisfaction_setup") or "").strip(),
            "satisfaction_payoff": (item.get("satisfaction_payoff") or "").strip(),
            "satisfaction_type": item.get("satisfaction_type") or None,
            "next_chapter_bait": (item.get("next_chapter_bait") or "").strip(),
            "face_slap_target": item.get("face_slap_target") or None,
            "face_slap_audience": (item.get("face_slap_audience") or "").strip(),
            "completion_risk": (item.get("completion_risk") or "").strip(),
        })
    return base
