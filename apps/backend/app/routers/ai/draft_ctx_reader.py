"""
draft_ctx_reader.py — 读者模拟反馈 + 复盘闭环指令

从上章分析记录和复盘指令中构建写章上下文注入文本块。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ChapterAnalysisRecord


# ═══════════════════════════════════════════════════════════════
# 读者模拟反馈：上章分析结果注入写章路径
# ═══════════════════════════════════════════════════════════════

def build_reader_feedback_context(
    db: Session, project_id: str, prev_chapter,
) -> str:
    """
    查询上一章最近一次 ChapterAnalysisRecord，将读者评分/劝退点/裁定/钩子建议
    格式化为可追加到 writing_brief_context 的文本块。

    @param db: SQLAlchemy Session
    @param project_id: 当前项目 UUID 字符串
    @param prev_chapter: 上一章 Chapter ORM 对象（可为 None）
    @returns 格式化后的读者反馈文本；无数据时返回空字符串
    """
    if prev_chapter is None:
        return ""
    try:
        record = (
            db.query(ChapterAnalysisRecord)
            .filter(
                ChapterAnalysisRecord.project_id == project_id,
                ChapterAnalysisRecord.chapter_id == prev_chapter.id,
            )
            .order_by(ChapterAnalysisRecord.created_at.desc())
            .first()
        )
    except Exception:
        return ""
    if record is None:
        return ""

    lines = ["\n【上章读者模拟反馈（本章写作必须回应）】"]
    risk_zh = {"low": "低", "medium": "中", "high": "⚠️高"}
    risk_label = risk_zh.get(record.drop_risk or "low", record.drop_risk or "")
    lines.append(f"  综合评分：{record.score}/10  流失风险：{risk_label}")
    if record.what_hooked:
        lines.append(f"  ✅ 读者买单：{record.what_hooked[:120]}")
    if record.what_repelled:
        lines.append(f"  ⚠️ 读者劝退：{record.what_repelled[:120]}（本章须主动规避）")
    if record.verdict:
        lines.append(f"  模拟裁定：{record.verdict[:160]}")
    if record.hook_suggestions:
        suggestions = [str(s) for s in (record.hook_suggestions or [])[:2] if s]
        if suggestions:
            lines.append("  本章钩子优化建议：" + "；".join(suggestions)[:180])
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 复盘闭环辅助：prev_directives 格式化
# ═══════════════════════════════════════════════════════════════

def build_prev_directives(outline_node) -> str:
    """
    将 OutlineNode.extra.directives_from_prev 格式化为写章可用的纯文本指令块。

    @param outline_node: 当前章节对应的 OutlineNode ORM 对象（可为 None）
    @returns 格式化指令字符串；无有效指令时返回空字符串
    """
    if outline_node is None or not isinstance(outline_node.extra, dict):
        return ""
    dirs = outline_node.extra.get("directives_from_prev") or []
    if not dirs:
        return ""

    patch_key_zh = {
        "adjust_pacing": ("节奏调整", lambda v: v),
        "force_pov": ("强制POV视角", lambda v: v),
        "add_foreshadow": ("伏笔延续要求", lambda v: v),
        "reader_expectation_note": ("读者期待管理", lambda v: v),
        "must_resolve_promise_in_next_N_chapters": (
            "承诺兑现窗口",
            lambda v: f"本章或接下来 {v} 章内必须兑现已有读者承诺",
        ),
        "increase_screen_time_for": (
            "补足戏份",
            lambda v: "、".join(str(x) for x in (v or [])[:4]) + " 上章戏份不足，本章必须有实质场景",
        ),
    }

    dir_parts: list[str] = []
    for d in dirs[-2:]:
        patch = d.get("patch") or {}
        reason = (d.get("reason") or "").strip()
        from_title = (d.get("from_chapter_title") or "上章").strip()

        parts: list[str] = []
        for key, (label, fmt) in patch_key_zh.items():
            val = patch.get(key)
            if not val:
                continue
            try:
                parts.append(f"{label}：{fmt(val)}")
            except Exception:
                parts.append(f"{label}：{val}")

        if reason:
            parts.append(f"编辑理由：{reason}")
        if parts:
            dir_parts.append(f"[来自《{from_title}》复盘] " + "；".join(parts))

    return "\n".join(dir_parts)
