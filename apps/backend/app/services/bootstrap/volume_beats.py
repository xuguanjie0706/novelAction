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


def _redistribute_needed(hints: list[int], planned: int) -> bool:
    """判断 LLM 给出的燃点章号是否退化（需确定性重排）。

    退化形态：只有 ≤1 条无需处理；出现重复章号；越界；过度聚集
    （跨度 < 卷长 25%）；或相邻间隔 < 2 章。
    """
    if len(hints) <= 1:
        return False
    if len(set(hints)) < len(hints):
        return True
    s = sorted(hints)
    if s[0] < 1 or s[-1] > planned:
        return True
    if (s[-1] - s[0]) < max(3, int(planned * 0.25)):
        return True
    return any(s[i + 1] - s[i] < 2 for i in range(len(s) - 1))


def _even_anchors(n: int, lo: int, hi: int) -> list[int]:
    """在 [lo, hi] 内取 n 个均匀锚点（升序）。"""
    if n <= 0:
        return []
    if hi < lo:
        hi = lo
    if n == 1:
        return [int(round((lo + hi) / 2))]
    step = (hi - lo) / (n - 1)
    return [int(round(lo + step * i)) for i in range(n)]


def align_volume_timeline(
    beats: list[dict],
    climax: dict | None,
    turning: dict | None,
    planned: int,
) -> None:
    """就地校正卷级时间轴，保证任意小说都得到合理章序分布。

    设计动机：LLM 常把全部节拍 chapter_hint 填成卷末同一章（如全 60 章），
    导致燃点/高潮/转折挤在一处、章纲展开无锚点。本函数做确定性兜底——
    不依赖模型自觉：

    1. 卷末高潮锚定在卷长 80%~90% 处；模型给的若不在 [60%,100%] 区间则改写。
    2. 燃点分布在卷长 18% 到「高潮前一拍」之间；若退化（重复/聚集/越界）则按
       均匀锚点重排，保留模型给出的相对先后；分布良好时仅保证全部早于高潮。
    3. 情感转折居中（默认 50%）且严格早于高潮。
    """
    planned = max(_safe_int(planned, 30), 6)

    # 1) 高潮锚定卷末
    climax_target = max(3, int(round(planned * 0.86)))
    if isinstance(climax, dict):
        ch = _safe_int(climax.get("chapter_hint"), 0)
        if not (planned * 0.6 <= ch <= planned):
            ch = climax_target
        climax["chapter_hint"] = max(1, min(ch, planned))
    climax_ch = climax["chapter_hint"] if isinstance(climax, dict) else planned

    # 2) 燃点分布
    n = len(beats)
    lo = max(2, int(round(planned * 0.18)))
    hi = min(planned - 1, max(lo + max(n - 1, 0) * 2, climax_ch - 2))
    if n:
        given = [_safe_int(b.get("chapter_hint"), 0) for b in beats]
        # 保留模型给出的相对先后（无效章号排到最后）
        order = sorted(
            range(n),
            key=lambda i: (given[i] if given[i] > 0 else planned + i, i),
        )
        if _redistribute_needed(given, planned) or max(given) >= climax_ch:
            anchors = _even_anchors(n, lo, hi)
            for rank, idx in enumerate(order):
                a = anchors[rank]
                beats[idx]["chapter_hint"] = a
                beats[idx]["chapter_span"] = str(a)
        else:
            for b in beats:
                if _safe_int(b.get("chapter_hint"), 0) >= climax_ch:
                    b["chapter_hint"] = max(1, climax_ch - 1)

    # 3) 情感转折居中且早于高潮
    if isinstance(turning, dict):
        t = _safe_int(turning.get("chapter_hint"), 0)
        if not (planned * 0.3 <= t < climax_ch):
            t = min(max(int(round(planned * 0.5)), lo + 1), max(climax_ch - 1, 1))
        turning["chapter_hint"] = max(1, t)


def normalize_must_payoffs(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [_clip(str(x), 80) for x in raw if str(x).strip()][:5]


def apply_volume_beat_fields(vol: dict, vol_extra: dict) -> str | None:
    """将 AI 卷 JSON 中的节拍字段写入 vol_extra，返回 highlight 列文本。"""
    planned = vol_extra.get("planned_chapters") or vol.get("planned_chapters") or 30
    planned = _safe_int(planned, 30)

    beats = normalize_beat_highlights(vol.get("beat_highlights"), planned)
    climax = normalize_climax_dict(vol.get("volume_climax"), planned)
    turning = normalize_turning_point(vol.get("emotional_turning_point"), planned)

    # 确定性兜底：保证章号分布合理（修复 LLM 把节拍全填卷末同一章的退化）
    align_volume_timeline(beats, climax, turning, planned)

    if beats:
        vol_extra["beat_highlights"] = beats
    if climax:
        vol_extra["volume_climax"] = climax
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


def _chapter_start_global(extra: dict) -> int:
    return max(_safe_int(extra.get("chapter_start_global"), 1), 1)


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

    from app.services.bootstrap.volume_chapter_starts import (
        format_volume_chapter_label,
        shift_chapter_refs_in_text,
    )

    start_g = _chapter_start_global(extra)
    lines: list[str] = []
    marker = " ← 本卷节拍" if is_current else ""
    if beats["pacing_skeleton"]:
        pacing = shift_chapter_refs_in_text(beats["pacing_skeleton"], start_g)
        lines.append(f"      节奏骨架：{pacing[:100]}{marker}")

    for i, b in enumerate(beats["beat_highlights"][:4], 1):
        if not isinstance(b, dict):
            continue
        bt = _BEAT_TYPE_ZH.get(b.get("beat_type", ""), b.get("beat_type", "燃点"))
        hint = _safe_int(b.get("chapter_hint"), 0)
        ch_lbl = format_volume_chapter_label(hint, start_g) if hint > 0 else "第?章"
        lines.append(
            f"      燃点#{i}·{ch_lbl}[{bt}]："
            f"{(b.get('description') or '')[:70]}"
        )

    climax = beats["volume_climax"]
    if isinstance(climax, dict) and climax.get("description"):
        ch = _safe_int(climax.get("chapter_hint"), 0)
        ch_lbl = format_volume_chapter_label(ch, start_g) if ch > 0 else "第?章"
        lines.append(
            f"      卷末高潮·{ch_lbl}："
            f"{str(climax['description'])[:70]}"
        )

    turning = beats["emotional_turning_point"]
    if isinstance(turning, dict) and turning.get("description"):
        ch = _safe_int(turning.get("chapter_hint"), 0)
        ch_lbl = format_volume_chapter_label(ch, start_g) if ch > 0 else "第?章"
        lines.append(
            f"      情感转折·{ch_lbl}："
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
【章号语义（必读，避免每卷都从「全书第1章」误解）】
- beat_highlights / volume_climax / emotional_turning_point 的 chapter_hint：只填**本卷内**章号（1 ～ planned_chapters），禁止填全书累计章号。
- pacing_skeleton 中的章段同样用**本卷内**章号（如「1-5章密钩」= 本卷第1-5章，不是全书第1-5章）。
- 第2卷起剧情须承接前卷 hook / 冲突，禁止每卷 summary 都写成「开局入门/重生第1天」式重置。

【卷级导演单 · 节拍（必填，与 phase 分工：phase=整卷情绪走向，节拍=章序锚点）】
- beat_highlights：2～4 个「燃点」，禁止整卷只有 1 个或超过 5 个
- volume_climax：本卷唯一主高潮（通常落在 planned_chapters 后 15%～25%）
- emotional_turning_point：主角认知/关系不可逆变化（dark_hour/turning 卷必填，其余卷可填空对象 {{}}）
- must_payoff_before_vol_end：本卷结束前必须回收的伏笔/承诺（0～3 条，具体到人物或秘密）
- pacing_skeleton：50 字内说明快/慢/打脸/情感章段分布（须写清大致章号）

每项必须引用已有人物名/势力/卷 conflict，禁止「展示实力」「悬念丛生」等空话。

【章号分布铁律（按卷长 planned_chapters 折算，禁止全部填卷末同一章）】
- 第 1 个燃点落在卷前 20%～30%；其余燃点依次向后均匀铺开，彼此间隔 ≥3 章。
- 所有燃点都必须早于 volume_climax；不得与高潮同章。
- volume_climax 落在卷长 80%～90%（如 30 章卷≈26、60 章卷≈53）。
- emotional_turning_point 落在卷长 45%～60% 且严格早于高潮。

【爽感类型多样性铁律（禁止整卷清一色打脸）】
- beat_type 至少出现 2 种不同类型；同一卷 face_slap 最多 2 个；相邻两个燃点不得同类型。
- 可选类型：face_slap 打脸 / reveal 揭秘 / power_up 实力跃迁 / relationship_turn 关系逆转
  / betrayal 背叛决裂 / sacrifice 牺牲至暗 / victory 阶段胜利 / emotional_peak 情感高点。
- 善用轮换：扮猪吃虎→夺宝/传承→反杀复仇→扬名/收服→美人侧目，而非反复「比试赢一个人」。

【payoff_of 铁律】须引用本卷 conflict 或前序具体事件（谁、第几章、做了什么），
禁止「承接X对主角的Y」式套话模板。

字段示例（合并进每卷对象；示例为 30 章卷，章号须随实际卷长缩放）：
  "summary": "本卷核心剧情，120字内（须含主角当卷目标与主要对手）",
  "beat_highlights": [
    {{
      "chapter_hint": 7,
      "chapter_span": "6-8",
      "beat_type": "power_up",
      "description": "主角在后山禁地以小博大，借雷灵草线索险渡突破，露出第一手底牌",
      "payoff_of": "承接第3章被陆苍断了修炼资源、被断言此生止步炼气"
    }},
    {{
      "chapter_hint": 14,
      "chapter_span": "13-15",
      "beat_type": "face_slap",
      "description": "宗门大比当众反超陆雷夺魁，狠打陆苍一脉的脸",
      "payoff_of": "承接第7章陆雷因误判主角实力而设下的杀局"
    }},
    {{
      "chapter_hint": 21,
      "chapter_span": "20-22",
      "beat_type": "reveal",
      "description": "姬如雪护法时主角无意暴露魔道气息，引出师门来历之谜",
      "payoff_of": "承接第1章随身玉佩的异常波动伏笔"
    }}
  ],
  "volume_climax": {{
    "chapter_hint": 27,
    "description": "陆苍勾结外敌设局围杀，主角当众揭其通敌、越级斩杀，掌控话语权（卷内总清算）"
  }},
  "emotional_turning_point": {{
    "chapter_hint": 16,
    "description": "禁地共患难后主角冰冷的心被姬如雪的信任融化，立誓变强护人（可选，opening 卷可简写）"
  }},
  "must_payoff_before_vol_end": ["回收第3章陆苍暗下的钝骨散毒素", "兑现第14章对陆苍一脉的当众羞辱"],
  "pacing_skeleton": "1-5密钩铺屈辱/6-8首突破/9-15首打脸/16-22加压揭谜/23-27高潮总清算/28-30留种"
"""
