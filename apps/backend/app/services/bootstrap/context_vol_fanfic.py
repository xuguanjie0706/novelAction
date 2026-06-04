"""按卷展开章纲时的同人原著约束块。"""
from __future__ import annotations

from app.models import OutlineNode, Project


def build_fanfic_canon_block(project: Project, volume_node: OutlineNode, ctx: dict) -> str:
    extra = project.extra if isinstance(project.extra, dict) else {}
    if not extra.get("fanfic_positioning"):
        return ""
    canon = extra.get("fanfic_canon") or {}
    dev = extra.get("fanfic_deviation") or {}
    entry = extra.get("fanfic_entry") or {}
    fp = extra.get("fanfic_positioning") or {}
    parts: list[str] = [
        "\n【同人·原著硬约束（章纲不得违背）】",
        f"  原著：{fp.get('source_work_title', '')} · {fp.get('fanfic_trope_label', '')}",
        f"  贴合档位：{fp.get('canon_fidelity', 'medium')}",
    ]
    if canon.get("world_summary"):
        parts.append(f"  世界观：{canon['world_summary']}")
    facts = canon.get("immutable_facts") or []
    if facts:
        parts.append("  不可改事实：")
        for f in facts[:6]:
            parts.append(f"    · {f}")
    if dev.get("forbidden_changes"):
        parts.append("  禁止改动：")
        for f in (dev["forbidden_changes"])[:5]:
            parts.append(f"    · {f}")
    if dev.get("divergence_point"):
        parts.append(f"  分歧点：{dev['divergence_point']}")
    if entry.get("entry_chapter_hint"):
        parts.append(f"  切入提示：{entry['entry_chapter_hint']}")
    for anc in (canon.get("timeline_anchors") or [])[:4]:
        parts.append(f"  原著节点：{anc}")
    audit = extra.get("fanfic_audit") or {}
    if audit.get("review_required") and audit.get("fix_hints"):
        parts.append("  ⚠️ 立项校验高风险，章纲须落实下列修正：")
        for h in (audit.get("fix_hints") or [])[:4]:
            parts.append(f"    · {h}")
    taboos = fp.get("ooc_taboos") or []
    if taboos:
        parts.append("  原著粉雷区：")
        for t in taboos[:4]:
            parts.append(f"    · {t}")
    parts.append(
        "  ⚠️ 章纲须推进「同人主线」而非复述原著；人设/关系突变须在 deviation 允许范围内。"
    )
    return "\n".join(parts)
