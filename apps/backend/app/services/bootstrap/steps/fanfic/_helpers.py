"""同人 Bootstrap 步骤共享工具。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from sqlalchemy.orm.attributes import flag_modified

TROPE_LABELS = {
    "transmigration": "穿书",
    "rebirth": "重生",
    "au": "AU平行",
}

# 三档同人的「信息差」来源不同 —— 这是同人金手指的核心爽点来源，必须分流。
TROPE_INFO_EDGE = {
    "transmigration": (
        "穿书信息差：主角拥有原著上帝视角（知道剧情走向、谁是反派、何处有机缘），"
        "金手指应建立在「我知道接下来会发生什么」之上；爽点=预判踩点、提前布局、反杀书中恶人。"
    ),
    "rebirth": (
        "重生信息差：主角带前世记忆重活，知道自己与他人的命运结局；"
        "金手指=用前世教训改写今生，爽点=避坑+抢先一步+对前世仇人降维打击。"
    ),
    "au": (
        "AU平行信息差：原著设定为底但走向已变，主角优势来自「带入设定/能力而非剧情记忆」；"
        "金手指=跨设定的能力或视角差，爽点=用原著规则玩出原著没有的新解法。"
    ),
}


def trope_info_edge(ctx: dict) -> str:
    fp = ctx.get("fanfic_positioning") or {}
    meta = ctx.get("fanfic_meta") or {}
    trope = fp.get("fanfic_trope") or meta.get("fanfic_trope") or "transmigration"
    return TROPE_INFO_EDGE.get(trope, TROPE_INFO_EDGE["transmigration"])


def persist_extra(project: Project, svc: Any, key: str, data: Any) -> None:
    extra = dict(project.extra or {})
    extra[key] = data
    project.extra = extra
    flag_modified(project, "extra")
    svc.db.commit()


def fanfic_meta_block(ctx: dict) -> str:
    meta = ctx.get("fanfic_meta") or {}
    fp = ctx.get("fanfic_positioning") or {}
    canon = ctx.get("fanfic_canon") or {}
    lines = [
        f"原著：{meta.get('source_work_title') or fp.get('source_work_title', '')}",
        f"同人类型：{fp.get('fanfic_trope_label') or TROPE_LABELS.get(meta.get('fanfic_trope', ''), '')}",
        f"核心爽感：{fp.get('core_satisfaction', '')}",
        f"原著贴合度：{fp.get('canon_fidelity', 'medium')}",
    ]
    if meta.get("focal_characters"):
        lines.append(f"主视角/CP：{meta['focal_characters']}")
    if canon.get("world_summary"):
        lines.append(f"世界观摘要：{str(canon['world_summary'])[:200]}")
    return "\n".join(lines)


def fanfic_as_fanqie_positioning(ctx: dict) -> dict:
    """供复用番茄 golden_finger / face_slap 等步骤的兼容定位块。"""
    fp = ctx.get("fanfic_positioning") or {}
    trope = fp.get("fanfic_trope_label") or TROPE_LABELS.get(fp.get("fanfic_trope", ""), "同人")
    return {
        "genre_archetype": f"同人·{trope}",
        "core_satisfaction": fp.get("core_satisfaction", ""),
        "competitor_works": [fp.get("source_work_title", "原著")],
        "differentiation": fp.get("differentiation", ""),
        "platform_tags": fp.get("platform_tags", []),
        "algo_hook": fp.get("algo_hook", ""),
        "taboo_check": fp.get("taboo_check", ""),
    }


def entry_as_contrast(ctx: dict) -> dict:
    """将 fanfic_entry 映射为 contrast_design，供番茄金手指步骤读取。"""
    entry = ctx.get("fanfic_entry") or {}
    return {
        "initial_state_headline": entry.get("initial_state_headline", ""),
        "trigger_event": entry.get("trigger_event", ""),
        "trigger_word_estimate": entry.get("trigger_word_estimate", "约第650字处"),
        "final_destination": entry.get("final_destination", ""),
        "contrast_ratio_note": entry.get("contrast_ratio_note", ""),
        "humiliation_scenes": entry.get("humiliation_scenes") or [],
        "protagonist_pain_point": entry.get("protagonist_pain_point", ""),
    }
