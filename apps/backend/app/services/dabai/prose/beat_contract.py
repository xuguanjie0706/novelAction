"""五拍单一事实源：导演单 beat_execution 优先换写法；章纲锁定的配角境界/战力档位不可被导演单改写。"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from app.models.dabai import DabaiChapterOutline, DabaiVolume

_BEAT_KEYS = ("yaqu", "trigger", "yinbao", "payoff", "hook")
_BEAT_LABELS = {
    "yaqu": "憋屈",
    "trigger": "转折扳机",
    "yinbao": "引爆",
    "payoff": "爽点",
    "hook": "章末钩子",
}


@dataclass
class BeatContract:
    """正文/分场共用的五拍契约。"""

    source: str  # prewarn | outline
    yaqu: str
    trigger: str
    yinbao: str
    payoff: str
    hook: str
    shuang_type: str
    location: str
    witnesses: str
    realm_rank: int | None
    is_big_beat: bool

    @property
    def has_execution(self) -> bool:
        return self.source == "prewarn"


def _witnesses_str(ch: DabaiChapterOutline) -> str:
    w = ch.witnesses or []
    if isinstance(w, list):
        joined = "、".join(str(x) for x in w if x)
        return joined or "围观众人"
    return "围观众人"


def _beats_from_prewarn(pre_warn_result: dict | None) -> dict[str, str]:
    if not isinstance(pre_warn_result, dict):
        return {}
    raw = pre_warn_result.get("beat_execution") or {}
    if not isinstance(raw, dict):
        return {}
    return {k: str(raw.get(k) or "").strip() for k in _BEAT_KEYS}


def _beats_from_outline(ch: DabaiChapterOutline) -> dict[str, str]:
    return {
        "yaqu": (ch.yaqu_setup or "").strip(),
        "trigger": (ch.emotion_turn or "").strip(),
        "yinbao": (ch.yinbao or "").strip(),
        "payoff": (ch.shuang_payoff or "").strip(),
        "hook": (ch.end_hook or "").strip(),
    }


def beat_similarity(a: str, b: str) -> float:
    """两字符串相似度 0~1（用于检测导演单是否照抄章纲）。"""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _witnesses_from_raw(raw) -> str:
    if isinstance(raw, list):
        joined = "、".join(str(x) for x in raw if x)
        return joined or "围观众人"
    return str(raw or "").strip() or "围观众人"


def resolve_beats_from_mapping(
    mapping: dict,
    pre_warn_result: dict | None = None,
) -> BeatContract:
    """从 dabaiwen OutlineNode.extra 映射解析五拍（与 resolve_beats 同优先级）。"""
    outline = {
        "yaqu": str(mapping.get("yaqu_setup") or "").strip(),
        "trigger": str(mapping.get("emotion_turn") or "").strip(),
        "yinbao": str(mapping.get("yinbao") or "").strip(),
        "payoff": str(mapping.get("shuang_payoff") or "").strip(),
        "hook": str(mapping.get("end_hook") or "").strip(),
    }
    prewarn = _beats_from_prewarn(pre_warn_result)
    if any(prewarn.get(k) for k in _BEAT_KEYS):
        source = "prewarn"
        beats = {k: prewarn.get(k) or outline.get(k, "") for k in _BEAT_KEYS}
    else:
        source = "outline"
        beats = outline

    return BeatContract(
        source=source,
        yaqu=beats["yaqu"],
        trigger=beats["trigger"] or "（未给，按②自行设计一个触发点过渡）",
        yinbao=beats["yinbao"],
        payoff=beats["payoff"],
        hook=beats["hook"],
        shuang_type=str(mapping.get("shuang_type") or "").strip(),
        location=str(mapping.get("location") or "").strip(),
        witnesses=_witnesses_from_raw(mapping.get("witnesses")),
        realm_rank=mapping.get("realm_rank"),
        is_big_beat=bool(mapping.get("is_big_beat")),
    )


def resolve_beats(
    ch: DabaiChapterOutline,
    pre_warn_result: dict | None = None,
    volume: DabaiVolume | None = None,
) -> BeatContract:
    """解析五拍：有 beat_execution 时用导演单，否则降级章纲。"""
    outline = _beats_from_outline(ch)
    prewarn = _beats_from_prewarn(pre_warn_result)
    if any(prewarn.get(k) for k in _BEAT_KEYS):
        source = "prewarn"
        beats = {k: prewarn.get(k) or outline.get(k, "") for k in _BEAT_KEYS}
    else:
        source = "outline"
        beats = outline

    return BeatContract(
        source=source,
        yaqu=beats["yaqu"],
        trigger=beats["trigger"] or "（未给，按②自行设计一个触发点过渡）",
        yinbao=beats["yinbao"],
        payoff=beats["payoff"],
        hook=beats["hook"],
        shuang_type=(ch.shuang_type or "").strip(),
        location=(ch.location or "").strip(),
        witnesses=_witnesses_str(ch),
        realm_rank=ch.realm_rank,
        is_big_beat=bool(getattr(ch, "is_big_beat", False)),
    )


def format_execution_block(contract: BeatContract) -> str:
    """导演单五拍执行块（正文 mandatory）。"""
    lines = [
        "【五拍执行（写前导演单裁决，须逐项落实；禁止照抄章纲原句）】",
        f"  爽点类型：{contract.shuang_type}",
        f"  场景载体：{contract.location}",
        f"  ①{ _BEAT_LABELS['yaqu']}：{contract.yaqu}",
        f"  ②{_BEAT_LABELS['trigger']}：{contract.trigger}",
        f"  ③{_BEAT_LABELS['yinbao']}：{contract.yinbao}",
        f"  ④{_BEAT_LABELS['payoff']}：{contract.payoff}（见证者：{contract.witnesses}）",
        f"  ⑤{_BEAT_LABELS['hook']}（收笔方向，勿复读本句）：{contract.hook}",
    ]
    return "\n".join(lines)


def format_outline_constraints_block(ch: DabaiChapterOutline) -> str:
    """章纲降级为情节结果约束（不含 yaqu 原文）。"""
    parts = [
        f"爽点类型={ch.shuang_type or ''}",
        f"见证者={_witnesses_str(ch)}",
        f"章末钩子方向={ch.end_hook or ''}",
    ]
    if ch.realm_rank:
        parts.append(f"章末境界档={ch.realm_rank}")
    if ch.is_big_beat:
        parts.append("大爆点章=true")
    if ch.location:
        parts.append(f"主场景={ch.location}")
    return "【情节结果约束（结果须达成，表述由五拍执行/分场决定）】\n  " + "；".join(parts)


def format_outline_full_block(ch: DabaiChapterOutline, realm_name=None) -> str:
    """无导演单降级：完整五拍章纲。"""
    realm = ""
    if ch.realm_rank and realm_name:
        realm = realm_name(ch.realm_rank)
    lines = [
        f"  爽点类型：{ch.shuang_type or ''}",
        f"  场景载体：{ch.location or ''}",
        f"  憋屈铺垫：{ch.yaqu_setup or ''}",
        f"  转折扳机：{ch.emotion_turn or '（未给）'}",
        f"  引爆方式：{ch.yinbao or ''}",
        f"  爽感落点：{ch.shuang_payoff or ''}（见证者：{_witnesses_str(ch)}）",
        f"  章末钩子（收笔方向，勿复读本句）：{ch.end_hook or ''}",
    ]
    if realm:
        lines.append(f"  境界：{realm}")
    return "\n".join(lines)
