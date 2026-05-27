"""Bootstrap 下游：故事线织网 prompt 块（卷骨架 / 章纲展开）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import StoryLine


def build_storyline_weave_volumes_block(ctx: dict) -> str:
    """Step 9：将织网矩阵注入卷级 prompt（替代单行 storyline_summary）。"""
    weave = ctx.get("storyline_weave") or {}
    matrix = weave.get("weave_matrix") or {}
    crossovers = weave.get("crossover_nodes") or []
    if not matrix:
        summary = ctx.get("storyline_summary") or ""
        return f"\n故事线：{summary}\n" if summary else ""

    lines = ["\n【故事线织网矩阵（每卷 summary/conflict 须对齐对应节拍）】"]
    n_volumes = int(weave.get("n_volumes") or 0)
    phases = weave.get("volume_phases") or []

    for vol_i in range(n_volumes):
        phase = phases[vol_i] if vol_i < len(phases) else "rising"
        lines.append(f"\n  ▶ 第{vol_i}卷（phase={phase}）")
        for name, beats in matrix.items():
            if not isinstance(beats, list):
                continue
            row = next(
                (b for b in beats if isinstance(b, dict) and int(b.get("vol_index", -1)) == vol_i),
                None,
            )
            if not row or not row.get("is_active", True):
                continue
            beat = (row.get("beat") or "")[:60]
            tension = row.get("tension", "")
            cx = row.get("crossover_with") or []
            cx_txt = f"；交叉：{'、'.join(cx)}" if cx else ""
            lines.append(f"    - {name}：{beat}（张力{tension}）{cx_txt}")

    if crossovers:
        lines.append("\n  【卷级交叉点】")
        for c in crossovers[:12]:
            if not isinstance(c, dict):
                continue
            lines.append(
                f"    - 第{c.get('at_vol')}卷 {c.get('line_a')}×{c.get('line_b')}："
                f"{(c.get('trigger') or '')[:50]}"
            )
    lines.append(
        "\n⚠️ 每卷 phase 须与织网张力分布一致（dark_hour 允许多线低谷，climax 卷主线张力最高）。\n"
    )
    return "\n".join(lines)


def build_volume_storyline_weave_block(
    db: Session,
    project_id: str,
    vol_index: int,
    planned_chapters: int,
) -> str:
    """章纲展开：注入本卷各线计划节拍与篇幅建议。"""
    rows = (
        db.query(StoryLine)
        .filter(StoryLine.project_id == project_id)
        .order_by(StoryLine.sort_order.asc())
        .all()
    )
    if not rows:
        return ""

    has_weave = any(
        isinstance(sl.extra, dict) and sl.extra.get("volume_beats") for sl in rows
    )
    if not has_weave:
        return ""

    lines = [
        f"\n【本卷故事线导演单（vol_index={vol_index}，共{planned_chapters}章）】",
    ]
    for sl in rows:
        extra = sl.extra if isinstance(sl.extra, dict) else {}
        beats = extra.get("volume_beats") or []
        row = next(
            (b for b in beats if isinstance(b, dict) and int(b.get("vol_index", -1)) == vol_index),
            None,
        )
        if not row or not row.get("is_active", True):
            continue
        w = float(extra.get("weight") or 0)
        ch_budget = max(1, int(planned_chapters * w)) if w > 0 else 0
        lines.append(
            f"  - {sl.name}：{(row.get('beat') or '')[:50]}"
            f" | 张力{row.get('tension', '')}"
            f" | 建议启动章≈{row.get('chapter_hint_start', '—')}"
            f" | 高潮章≈{row.get('chapter_hint_peak', '—')}"
            + (f" | 本卷约分配 {ch_budget} 章戏份" if ch_budget else ""),
        )
        for cx in extra.get("crossover_nodes") or []:
            if isinstance(cx, dict) and int(cx.get("at_vol", -1)) == vol_index:
                lines.append(
                    f"    ★ 交叉 {sl.name}×{cx.get('with')}：{(cx.get('trigger') or '')[:40]}"
                )

    lines.append(
        '\n章纲 JSON 可填 "storyline_beat_ref": "故事线名" 标明本章主要兑现哪条线的卷节拍。\n'
    )
    return "\n".join(lines)
