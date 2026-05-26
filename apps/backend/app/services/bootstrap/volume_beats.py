"""卷级节拍（燃点 / 卷末高潮 / pacing）归一化、落库与下游 prompt 格式化。"""
from __future__ import annotations

from typing import Any

VALID_BEAT_TYPES = frozenset({
    "face_slap",
    "reveal",
    "power_up",
    "relationship_turn",
    "betrayal",
    "sacrifice",
    "victory",
    "emotional_peak",
})

_BEAT_TYPE_ZH = {
    "face_slap": "打脸/爽点",
    "reveal": "揭秘",
    "power_up": "实力跃迁",
    "relationship_turn": "关系逆转",
    "betrayal": "背叛/决裂",
    "sacrifice": "牺牲/至暗",
    "victory": "阶段性胜利",
    "emotional_peak": "情感高点",
}


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s[:n] if len(s) > n else s


def normalize_beat_highlights(raw: Any, planned_chapters: int) -> list[dict]:
    """清洗燃点列表（2–4 条为宜，最多 5 条）。"""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:5]:
        if not isinstance(item, dict):
            continue
        desc = _clip(str(item.get("description") or ""), 120)
        if not desc:
            continue
        hint = _safe_int(item.get("chapter_hint"), 0)
        if hint < 1:
            span = str(item.get("chapter_span") or "").strip()
            if span and "-" in span:
                hint = _safe_int(span.split("-")[0], 1)
            else:
                hint = 1
        if planned_chapters > 0:
            hint = max(1, min(hint, planned_chapters))
        beat_type = str(item.get("beat_type") or "face_slap").strip().lower()
        if beat_type not in VALID_BEAT_TYPES:
            beat_type = "face_slap"
        out.append({
            "chapter_hint": hint,
            "chapter_span": _clip(str(item.get("chapter_span") or f"{hint}"), 12),
            "beat_type": beat_type,
            "description": desc,
            "payoff_of": _clip(str(item.get("payoff_of") or ""), 80),
        })
    return out


def normalize_climax_dict(raw: Any, planned_chapters: int) -> dict | None:
    if isinstance(raw, str) and raw.strip():
        hint = max(planned_chapters - 2, 1) if planned_chapters > 2 else 1
        return {
            "chapter_hint": hint,
            "description": _clip(raw, 150),
        }
    if not isinstance(raw, dict):
        return None
    desc = _clip(str(raw.get("description") or ""), 150)
    if not desc:
        return None
    hint = _safe_int(raw.get("chapter_hint"), 0)
    if hint < 1:
        hint = max(int(planned_chapters * 0.85), 1) if planned_chapters else 1
    if planned_chapters > 0:
        hint = max(1, min(hint, planned_chapters))
    return {"chapter_hint": hint, "description": desc}


def normalize_turning_point(raw: Any, planned_chapters: int) -> dict | None:
    if isinstance(raw, str) and raw.strip():
        hint = max(int(planned_chapters * 0.55), 1) if planned_chapters else 1
        return {"chapter_hint": hint, "description": _clip(raw, 120)}
    if not isinstance(raw, dict):
        return None
    desc = _clip(str(raw.get("description") or ""), 120)
    if not desc:
        return None
    hint = _safe_int(raw.get("chapter_hint"), 0)
    if hint < 1:
        hint = max(int(planned_chapters * 0.55), 1) if planned_chapters else 1
    if planned_chapters > 0:
        hint = max(1, min(hint, planned_chapters))
    return {"chapter_hint": hint, "description": desc}


def normalize_must_payoffs(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [_clip(str(x), 80) for x in raw if str(x).strip()][:5]


def apply_volume_beat_fields(vol: dict, vol_extra: dict) -> str | None:
    """将 AI 卷 JSON 中的节拍字段写入 vol_extra，返回 highlight 列文本。"""
    planned = vol_extra.get("planned_chapters") or vol.get("planned_chapters") or 30
    planned = _safe_int(planned, 30)

    beats = normalize_beat_highlights(vol.get("beat_highlights"), planned)
    if beats:
        vol_extra["beat_highlights"] = beats

    climax = normalize_climax_dict(vol.get("volume_climax"), planned)
    if climax:
        vol_extra["volume_climax"] = climax

    turning = normalize_turning_point(vol.get("emotional_turning_point"), planned)
    if turning:
        vol_extra["emotional_turning_point"] = turning

    payoffs = normalize_must_payoffs(vol.get("must_payoff_before_vol_end"))
    if payoffs:
        vol_extra["must_payoff_before_vol_end"] = payoffs

    pacing = _clip(str(vol.get("pacing_skeleton") or ""), 200)
    if pacing:
        vol_extra["pacing_skeleton"] = pacing

    if climax:
        return climax["description"]
    return None


def volume_beats_from_extra(extra: dict | None) -> dict:
    """从 OutlineNode.extra 提取节拍结构（兼容旧卷无数据）。"""
    ex = extra if isinstance(extra, dict) else {}
    return {
        "beat_highlights": ex.get("beat_highlights") or [],
        "volume_climax": ex.get("volume_climax"),
        "emotional_turning_point": ex.get("emotional_turning_point"),
        "must_payoff_before_vol_end": ex.get("must_payoff_before_vol_end") or [],
        "pacing_skeleton": ex.get("pacing_skeleton") or "",
    }


def has_volume_beats(extra: dict | None) -> bool:
    b = volume_beats_from_extra(extra)
    return bool(
        b["beat_highlights"]
        or b["volume_climax"]
        or b["pacing_skeleton"]
    )


def format_volume_beats_skeleton_block(
    volume_node: Any,
    *,
    is_current: bool = False,
) -> str:
    """全卷骨架列表中单卷节拍摘要（供 context_vol_tier345）。"""
    extra = volume_node.extra if isinstance(volume_node.extra, dict) else {}
    beats = volume_beats_from_extra(extra)
    if not has_volume_beats(extra):
        return ""

    lines: list[str] = []
    marker = " ← 本卷节拍" if is_current else ""
    if beats["pacing_skeleton"]:
        lines.append(f"      节奏骨架：{beats['pacing_skeleton'][:100]}{marker}")

    for i, b in enumerate(beats["beat_highlights"][:4], 1):
        if not isinstance(b, dict):
            continue
        bt = _BEAT_TYPE_ZH.get(b.get("beat_type", ""), b.get("beat_type", "燃点"))
        lines.append(
            f"      燃点#{i}·第{b.get('chapter_hint', '?')}章[{bt}]："
            f"{(b.get('description') or '')[:70]}"
        )

    climax = beats["volume_climax"]
    if isinstance(climax, dict) and climax.get("description"):
        lines.append(
            f"      卷末高潮·第{climax.get('chapter_hint', '?')}章："
            f"{str(climax['description'])[:70]}"
        )

    turning = beats["emotional_turning_point"]
    if isinstance(turning, dict) and turning.get("description"):
        lines.append(
            f"      情感转折·第{turning.get('chapter_hint', '?')}章："
            f"{str(turning['description'])[:60]}"
        )

    payoffs = beats["must_payoff_before_vol_end"]
    if payoffs:
        lines.append(f"      卷末前必兑现：{'；'.join(str(p)[:30] for p in payoffs[:3])}")

    return "\n".join(lines)


def build_volume_beat_expand_block(
    volume_node: Any,
    batch_start: int,
    batch_end: int,
) -> str:
    """章纲展开：本卷节拍硬约束（仅当有 beat 数据时返回）。"""
    extra = volume_node.extra if isinstance(volume_node.extra, dict) else {}
    if not has_volume_beats(extra):
        return ""

    beats = volume_beats_from_extra(extra)
    planned = _safe_int((extra or {}).get("planned_chapters"), 30)

    lines: list[str] = [
        "\n【卷级导演单 · 节拍硬约束（Step 9，章纲必须按章号兑现）】",
        "以下燃点/高潮已在卷级定稿；本章纲的 core_event / end_hook / has_face_slap "
        "须在对应章段落实，且与卷 conflict / volume_boss 同链。",
    ]
    if volume_node.summary:
        lines.append(f"卷摘要：{str(volume_node.summary)[:200]}")
    if volume_node.conflict:
        lines.append(f"卷核心冲突：{str(volume_node.conflict)[:120]}")
    if beats["pacing_skeleton"]:
        lines.append(f"节奏骨架：{beats['pacing_skeleton']}")

    in_batch: list[str] = []
    for i, b in enumerate(beats["beat_highlights"], 1):
        if not isinstance(b, dict):
            continue
        hint = _safe_int(b.get("chapter_hint"), 0)
        if batch_start <= hint <= batch_end:
            bt = _BEAT_TYPE_ZH.get(b.get("beat_type", ""), "燃点")
            in_batch.append(
                f"  · 燃点#{i}（目标第{hint}章，类型{bt}）：{b.get('description', '')}"
                + (f" ← 承接：{b['payoff_of']}" if b.get("payoff_of") else "")
            )
    if in_batch:
        lines.append("▍本批须覆盖的燃点")
        lines.extend(in_batch)

    climax = beats["volume_climax"]
    if isinstance(climax, dict):
        ch = _safe_int(climax.get("chapter_hint"), 0)
        if batch_start <= ch <= batch_end:
            lines.append(
                f"▍本批须落实卷末高潮（第{ch}章）：{climax.get('description', '')}"
            )
        elif ch > batch_end:
            lines.append(
                f"▍卷末高潮预定第{ch}章（本批请为其铺垫加压，勿提前总清算）"
            )

    turning = beats["emotional_turning_point"]
    if isinstance(turning, dict):
        ch = _safe_int(turning.get("chapter_hint"), 0)
        if batch_start <= ch <= batch_end:
            lines.append(
                f"▍本批须落实情感转折点（第{ch}章）：{turning.get('description', '')}"
            )

    if beats["must_payoff_before_vol_end"]:
        lines.append("▍卷末前必须回收/兑现")
        for p in beats["must_payoff_before_vol_end"]:
            lines.append(f"  · {p}")

    # 批次外燃点提示
    outside = [
        b for b in beats["beat_highlights"]
        if isinstance(b, dict) and not (batch_start <= _safe_int(b.get("chapter_hint"), 0) <= batch_end)
    ]
    if outside:
        hints = ", ".join(f"第{_safe_int(b.get('chapter_hint'), 0)}章" for b in outside[:4])
        lines.append(f"（其他批次燃点锚点：{hints}，本批勿抢跑兑现）")

    lines.append(
        "编辑铁律：目标章的 end_hook / core_event 须含燃点或高潮描述中的关键词；"
        "打脸类燃点对应章 has_face_slap=true；"
        "volume_climax 章 pacing 建议 climax。"
    )
    if planned:
        lines.append(f"（本卷共 {planned} 章）")
    return "\n".join(lines)


def build_volume_beat_draft_block(
    volume_node: Any,
    chapter_in_volume: int,
) -> str:
    """写正文：本卷内单章对应的节拍约束（无数据或章号无效时返回空）。"""
    extra = volume_node.extra if isinstance(volume_node.extra, dict) else {}
    if not has_volume_beats(extra) or chapter_in_volume < 1:
        return ""

    beats = volume_beats_from_extra(extra)
    lines: list[str] = [
        "【卷级导演单 · 本章节拍（须与卷 conflict 同链兑现）】",
    ]
    if beats["pacing_skeleton"]:
        lines.append(f"全卷节奏：{beats['pacing_skeleton']}")

    matched = False
    for i, b in enumerate(beats["beat_highlights"], 1):
        if not isinstance(b, dict):
            continue
        hint = _safe_int(b.get("chapter_hint"), 0)
        if abs(hint - chapter_in_volume) <= 1:
            matched = True
            bt = _BEAT_TYPE_ZH.get(b.get("beat_type", ""), "燃点")
            lines.append(
                f"▍燃点#{i}（锚第{hint}章·{bt}）：{b.get('description', '')}"
            )
            if b.get("payoff_of"):
                lines.append(f"  承接：{b['payoff_of']}")

    climax = beats["volume_climax"]
    if isinstance(climax, dict) and climax.get("description"):
        ch = _safe_int(climax.get("chapter_hint"), 0)
        if abs(ch - chapter_in_volume) <= 1:
            matched = True
            lines.append(f"▍卷末高潮（锚第{ch}章）：{climax['description']}")
        elif chapter_in_volume < ch - 3:
            lines.append(f"（卷末高潮预定第{ch}章，本章勿提前总清算）")

    turning = beats["emotional_turning_point"]
    if isinstance(turning, dict) and turning.get("description"):
        ch = _safe_int(turning.get("chapter_hint"), 0)
        if abs(ch - chapter_in_volume) <= 1:
            matched = True
            lines.append(f"▍情感转折（锚第{ch}章）：{turning['description']}")

    if beats["must_payoff_before_vol_end"] and chapter_in_volume >= max(
        _safe_int((extra or {}).get("planned_chapters"), 30) - 5, 1
    ):
        matched = True
        lines.append("▍卷末前须兑现")
        for p in beats["must_payoff_before_vol_end"]:
            lines.append(f"  · {p}")

    if not matched:
        return ""

    lines.append("正文须用具体场面落实以上节拍，禁止口号式交代。")
    return "\n".join(lines)


def append_volume_beat_draft_brief(
    volume_node: Any | None,
    outline_node: Any | None,
    writing_brief_context: str,
) -> str:
    """写章路径：追加本卷节拍块。"""
    if not volume_node or not outline_node:
        return writing_brief_context
    if outline_node.node_type != "chapter_plan":
        return writing_brief_context
    ch_in_vol = (outline_node.sort_order or 0) + 1
    block = build_volume_beat_draft_block(volume_node, ch_in_vol)
    if block:
        return writing_brief_context + "\n\n" + block
    return writing_brief_context


VOLUME_JSON_BEAT_SCHEMA = """
【卷级导演单 · 节拍（必填，与 phase 分工：phase=整卷情绪走向，节拍=章序锚点）】
- beat_highlights：2～4 个「燃点」，禁止整卷只有 1 个或超过 5 个
- volume_climax：本卷唯一主高潮（通常落在 planned_chapters 后 15%～25%）
- emotional_turning_point：主角认知/关系不可逆变化（dark_hour/turning 卷必填，其余卷可填空对象 {{}}）
- must_payoff_before_vol_end：本卷结束前必须回收的伏笔/承诺（0～3 条，具体到人物或秘密）
- pacing_skeleton：50 字内说明快/慢/打脸/情感章段分布（须写清大致章号）

每项必须引用已有人物名/势力/卷 conflict，禁止「展示实力」「悬念丛生」等空话。
燃点 chapter_hint 须落在 1～planned_chapters 内，且彼此间隔 ≥3 章（避免连续两章同类型爆点）。

字段示例（合并进每卷对象）：
  "summary": "本卷核心剧情，120字内（须含主角当卷目标与主要对手）",
  "beat_highlights": [
    {{
      "chapter_hint": 8,
      "chapter_span": "7-9",
      "beat_type": "face_slap",
      "description": "主角在宗门大比当众击败陆青云，夺回信物（具体场面）",
      "payoff_of": "承接卷 conflict 中的退婚羞辱"
    }}
  ],
  "volume_climax": {{
    "chapter_hint": 28,
    "description": "主角与 volume_boss 的当面对决，揭开血指印真相（卷内总清算）"
  }},
  "emotional_turning_point": {{
    "chapter_hint": 18,
    "description": "主角接受师父已死的真相，从复仇转为守护（可选，opening 卷可简写）"
  }},
  "must_payoff_before_vol_end": ["回收第5章埋下的长老密室阵图线索"],
  "pacing_skeleton": "1-5密钩/6-12第一次燃/13-20加压/21-27高潮/28-30留种"
"""
