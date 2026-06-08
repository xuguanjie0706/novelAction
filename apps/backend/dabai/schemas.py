"""每步 JSON 输出契约 + 轻量校验 / 归一化。

不依赖 pydantic / SQLAlchemy，纯 dict 契约，方便独立运行与序列化。
每个 STEP_CONTRACT[step] 描述：
  - required: 必填顶层键
  - shape:    "object" | "list"
  - item_required: 当 shape=="list" 时，每个元素的必填键
normalize_step() 做容错：补默认、裁剪、类型矫正，保证下游稳定。
"""

from __future__ import annotations

from typing import Any

# ── 章纲（爽点节拍器）字段契约 —— 本分支的核心 ──────────────────────────────────
CHAPTER_FIELDS = {
    "chapter_number": int,
    "title": str,
    "shuang_type": str,        # 一等公民：本章爽点类型
    "yaqu_setup": str,         # 憋屈势能（爽点前置弹簧）
    "yinbao": str,             # 引爆：怎么反转
    "shuang_payoff": str,      # 爽感量化（必须有观众/见证者）
    "witnesses": list,         # 见证者/被打脸者名单
    "end_hook": str,           # 章末强钩子
    "new_info_count": int,     # 信息密度
    "involved_characters": list,
    "is_big_beat": bool,       # 是否大爆点
    "expected_words": int,
}

STEP_CONTRACT: dict[str, dict[str, Any]] = {
    "benchmark": {
        "shape": "object",
        "required": ["topic", "reference_books", "style_profile"],
    },
    "positioning": {
        "shape": "object",
        "required": ["target_audience", "shuang_pool", "face_slap_frequency",
                     "golden_three_strategy", "pace_type", "taboo_lines"],
    },
    "golden_finger": {
        "shape": "object",
        "required": ["name", "type", "core_ability", "upgrade_mechanism",
                     "shuang_engine", "restriction"],
    },
    "power_ladder": {
        "shape": "object",
        "required": ["name", "levels"],
    },
    "factions": {
        "shape": "list",
        "item_required": ["name", "stance", "role"],
    },
    "characters": {
        "shape": "list",
        "item_required": ["name", "role", "tier"],
    },
    "storylines": {
        "shape": "list",
        "item_required": ["name", "type", "summary"],
    },
    "volumes": {
        "shape": "list",
        "item_required": ["volume_number", "title", "phase", "big_beats", "volume_climax"],
    },
    "chapter_outlines": {
        "shape": "list",
        "item_required": ["chapter_number", "title", "shuang_type",
                          "yaqu_setup", "shuang_payoff", "end_hook"],
    },
}


def validate_step(step: str, data: Any) -> list[str]:
    """返回缺失/形态错误列表（空列表=通过）。不抛异常，交由调用方决定重试。"""
    contract = STEP_CONTRACT.get(step)
    if not contract:
        return [f"未知步骤：{step}"]
    errors: list[str] = []
    if contract["shape"] == "object":
        if not isinstance(data, dict):
            return [f"{step} 期望 object，实际 {type(data).__name__}"]
        for key in contract.get("required", []):
            if key not in data or data[key] in (None, "", []):
                errors.append(f"{step} 缺字段：{key}")
    else:  # list
        if not isinstance(data, list) or not data:
            return [f"{step} 期望非空 list，实际 {type(data).__name__}"]
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                errors.append(f"{step}[{i}] 非 object")
                continue
            for key in contract.get("item_required", []):
                if key not in item or item[key] in (None, "", []):
                    errors.append(f"{step}[{i}] 缺字段：{key}")
    return errors


def _coerce_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def normalize_chapter(item: dict, idx: int, default_words: int = 2000) -> dict:
    """章纲单条容错归一化：补默认、矫正类型。爽点节拍器字段齐全。"""
    out = {k: item.get(k) for k in CHAPTER_FIELDS}
    out["chapter_number"] = _coerce_int(item.get("chapter_number"), idx + 1)
    out["title"] = (item.get("title") or f"第{idx + 1}章").strip()
    out["shuang_type"] = (item.get("shuang_type") or "").strip()
    out["yaqu_setup"] = (item.get("yaqu_setup") or "").strip()
    out["yinbao"] = (item.get("yinbao") or "").strip()
    out["shuang_payoff"] = (item.get("shuang_payoff") or "").strip()
    out["end_hook"] = (item.get("end_hook") or "").strip()
    out["witnesses"] = item.get("witnesses") or []
    out["involved_characters"] = item.get("involved_characters") or []
    out["new_info_count"] = _coerce_int(item.get("new_info_count"), 1)
    out["is_big_beat"] = bool(item.get("is_big_beat", False))
    out["expected_words"] = _coerce_int(item.get("expected_words"), default_words)
    return out


def normalize_step(step: str, data: Any) -> Any:
    """步骤级归一化入口。当前仅章纲需要深度容错，其余直接透传。"""
    if step == "chapter_outlines" and isinstance(data, list):
        return [normalize_chapter(it if isinstance(it, dict) else {}, i)
                for i, it in enumerate(data)]
    return data
