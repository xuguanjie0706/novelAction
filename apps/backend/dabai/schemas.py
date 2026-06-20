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

from dabai.hooks import normalize_hook_type as _normalize_hook_type

# ── 章纲（爽点节拍器）字段契约 —— 本分支的核心 ──────────────────────────────────
CHAPTER_FIELDS = {
    "chapter_number": int,
    "title": str,
    "shuang_type": str,        # 一等公民：本章爽点类型
    "target_emotion": str,     # 一等公民：本章交付的目标情绪（情绪先于故事）
    "hook_type": str,          # 章尾钩子类型（HOOK_END_TYPES 13 式之一，追读引擎+轮换闸门）
    "location": str,           # 场景载体：本章主场景（具体地点+事件，防全书一个擂台打到底）
    "yaqu_setup": str,         # 憋屈势能（爽点前置弹簧）
    "emotion_turn": str,       # 转折拍：情绪扳机（从X情绪→靠什么触发→转到Y情绪）
    "yinbao": str,             # 引爆：怎么反转
    "shuang_payoff": str,      # 爽感量化（必须有观众/见证者）
    "witnesses": list,         # 见证者/被打脸者名单
    "end_hook": str,           # 章末强钩子
    "new_info_count": int,     # 信息密度
    "involved_characters": list,
    "is_big_beat": bool,       # 是否大爆点
    "expected_words": int,
    "realm_rank": int,         # 主角本章境界档（全书单调不减）
    "realm_sub_rank": int,     # 同境内小层 1～9（升大境时重置）
}

STEP_CONTRACT: dict[str, dict[str, Any]] = {
    "benchmark": {
        # 合并步：一次调用产出 benchmark + positioning 两块
        "shape": "object",
        "required": ["benchmark", "positioning"],
    },
    "positioning": {
        "shape": "object",
        "required": ["target_audience", "shuang_pool", "face_slap_frequency",
                     "golden_three_strategy", "pace_type", "taboo_lines"],
    },
    "plot_blueprint": {
        "shape": "object",
        "required": ["plot_blueprints", "adaptation_plan"],
    },
    "golden_finger": {
        # 合并步：一次调用产出 golden_finger + power_ladder + antagonist_ladder（力量与对立面）
        "shape": "object",
        "required": ["golden_finger", "power_ladder", "antagonist_ladder"],
    },
    "factions": {
        # 合并步：一次调用产出 factions + characters（阵营卡司）
        "shape": "object",
        "required": ["factions", "characters"],
    },
    "storylines": {
        # 合并步：一次调用产出 叙事规划三块（storylines + story_assets + mystery_schedule）
        "shape": "object",
        "required": ["storylines", "story_assets", "mystery_schedule"],
    },
    "story_assets": {
        # 剧情资产 + 初始关系（一次调用两块；落 dabai_assets/dabai_clues/dabai_relations）
        "shape": "object",
        "required": ["plot_assets", "initial_relations"],
    },
    "antagonist_ladder": {
        # 卷级反派阶梯：每卷 Boss roster（落 dabai_projects.extra）
        "shape": "list",
        "item_required": ["volume_number", "boss_name", "motive"],
    },
    "mystery_schedule": {
        # 跨卷谜题揭示排程（落 dabai_projects.extra + dabai_clues 种子）
        "shape": "object",
        "required": ["mysteries"],
    },
    "title_blurb": {
        # 书名海选 + 上架简介（chosen_title 回填 dabai_projects.title）
        "shape": "object",
        "required": ["title_candidates", "chosen_title", "blurb"],
    },
    "volumes": {
        "shape": "list",
        "item_required": ["volume_number", "title", "phase", "big_beats", "volume_climax"],
    },
    "volume_chapters": {
        # 单次整卷：节拍序列 + 五拍章纲（按次计费主路径；降级走 beat_sequence + chapter_outlines）
        "shape": "object",
        "required": ["beat_sequence", "chapter_outlines"],
    },
    "beat_sequence": {
        # 章纲阶段一：每章一行节拍（施工图，落 dabai_projects.extra）
        "shape": "list",
        "item_required": ["chapter_number", "title", "shuang_type", "location"],
    },
    "chapter_outlines": {
        "shape": "list",
        "item_required": ["chapter_number", "title", "shuang_type",
                          "yaqu_setup", "shuang_payoff", "end_hook"],
    },
    "chapter_repair": {
        # 定向修复：返回修正后的问题章（可为空数组=放弃修复，调用方保留原批）
        "shape": "list",
        "item_required": ["chapter_number", "title"],
    },
}


def expected_count_from_meta(meta: dict | None) -> int | None:
    """从 batch/global 区间推导本批期望章数（meta 缺省时返回 None）。"""
    if not meta:
        return None
    if meta.get("expected_count") is not None:
        return int(meta["expected_count"])
    gbs, gbe = meta.get("global_start"), meta.get("global_end")
    if gbs is not None and gbe is not None:
        return int(gbe) - int(gbs) + 1
    bs, be = meta.get("batch_start"), meta.get("batch_end")
    if bs is not None and be is not None:
        return int(be) - int(bs) + 1
    return None


def _validate_chapter_item_quality(step: str, item: dict, idx: int) -> list[str]:
    """五拍字段最短长度（生成期拦截空泛/摘要式章纲）。"""
    if step not in ("chapter_outlines", "volume_chapters"):
        return []
    errors: list[str] = []
    for field, min_len in (
        ("yaqu_setup", 10),
        ("emotion_turn", 6),
        ("yinbao", 6),
        ("shuang_payoff", 10),
    ):
        val = (item.get(field) or "").strip()
        if len(val) < min_len:
            errors.append(f"{step}[{idx}] {field} 过短（至少 {min_len} 字，须可拍画面）")
    if not (item.get("witnesses") or _payoff_has_witness(item.get("shuang_payoff", ""))):
        errors.append(f"{step}[{idx}] 缺见证者（witnesses 或 shuang_payoff 含当众/众人等）")
    return errors


def _payoff_has_witness(payoff: str) -> bool:
    return any(k in payoff for k in ("当着", "当众", "众人", "全场", "围观", "面前"))


def _validate_golden_finger_payload(step: str, data: Any) -> list[str]:
    """金手指合并步内层校验（json_object 不保证条数/语义，应用层硬拦）。"""
    if step != "golden_finger" or not isinstance(data, dict):
        return []
    gf = data.get("golden_finger")
    if not isinstance(gf, dict):
        return []
    errors: list[str] = []
    shuang = gf.get("first_10_shuang")
    if not isinstance(shuang, list):
        errors.append("golden_finger.first_10_shuang 须为非空数组")
        return errors
    items = [str(x).strip() for x in shuang if str(x).strip()]
    if len(items) < 10:
        errors.append(
            f"golden_finger.first_10_shuang 至少 10 条具体爽点（深挖版目标 14-20），"
            f"实际 {len(items)} 条"
        )
    errors.extend(_validate_power_ladder(data.get("power_ladder")))
    return errors


# 深挖版境界阶梯：每档不能只是「rank+名+一句话」，必须带战力标尺与格局，
# 否则越级打脸的强度差无从感知。门槛适中（避免反复重试），但拦截扁平化产出。
_LADDER_LEVEL_DEPTH_KEYS = ("power_benchmark", "world_scope")


def _validate_power_ladder(pl: Any) -> list[str]:
    """境界体系深度门：≥6 大境界 + 多数档位带战力标尺/格局字段。"""
    if not isinstance(pl, dict):
        return ["golden_finger.power_ladder 缺失或非对象"]
    levels = pl.get("levels")
    if not isinstance(levels, list) or len(levels) < 6:
        return [
            f"power_ladder.levels 至少 6 个大境界（实际 "
            f"{len(levels) if isinstance(levels, list) else 0} 个）"
        ]
    deep = 0
    for lv in levels:
        if not isinstance(lv, dict):
            continue
        if all(str(lv.get(k) or "").strip() for k in _LADDER_LEVEL_DEPTH_KEYS):
            deep += 1
    # 允许最高 1-2 个高境界留白，但绝大多数档位须有战力标尺 + 格局
    if deep < len(levels) - 2:
        return [
            "power_ladder.levels 过于扁平：多数档位缺 power_benchmark（战力标尺）"
            "或 world_scope（活动格局）——这是越级打脸强度差与格局打开的根，须补全"
        ]
    return []


def validate_chapter_coverage(step: str, data: Any, meta: dict | None) -> list[str]:
    """章纲/节拍数量必须与窗口一致；禁止模型只回大爆点摘要。"""
    expected = expected_count_from_meta(meta)
    if not expected or expected < 1:
        return []
    errors: list[str] = []
    if step == "volume_chapters" and isinstance(data, dict):
        beats = data.get("beat_sequence") or []
        chapters = data.get("chapter_outlines") or []
        if len(beats) != expected:
            errors.append(
                f"beat_sequence 数量不符：期望 {expected} 行，实际 {len(beats)} 行"
            )
        if len(chapters) != expected:
            errors.append(
                f"chapter_outlines 数量不符：期望 {expected} 章，实际 {len(chapters)} 章"
                "（禁止只写大爆点/跳章摘要，须逐章完整五拍）"
            )
        for i, item in enumerate(chapters if isinstance(chapters, list) else []):
            if isinstance(item, dict):
                errors.extend(_validate_chapter_item_quality(step, item, i))
        return errors
    if step in ("beat_sequence", "chapter_outlines") and isinstance(data, list):
        if len(data) != expected:
            errors.append(
                f"{step} 数量不符：期望 {expected} 章，实际 {len(data)} 章"
            )
        if step == "chapter_outlines":
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    errors.extend(_validate_chapter_item_quality(step, item, i))
    return errors


def validate_step(step: str, data: Any, meta: dict | None = None) -> list[str]:
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
        if step == "volume_chapters":
            chapters = (data.get("chapter_outlines") or []) if isinstance(data, dict) else []
            for i, item in enumerate(chapters if isinstance(chapters, list) else []):
                if isinstance(item, dict):
                    for key in STEP_CONTRACT["chapter_outlines"].get("item_required", []):
                        if key not in item or item[key] in (None, "", []):
                            errors.append(f"volume_chapters.chapter_outlines[{i}] 缺字段：{key}")
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
    errors.extend(validate_chapter_coverage(step, data, meta))
    errors.extend(_validate_golden_finger_payload(step, data))
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
    out["target_emotion"] = (item.get("target_emotion") or "").strip()
    out["hook_type"] = _normalize_hook_type(item.get("hook_type"))
    out["location"] = (item.get("location") or "").strip()
    out["yaqu_setup"] = (item.get("yaqu_setup") or "").strip()
    out["emotion_turn"] = (item.get("emotion_turn") or "").strip()
    out["yinbao"] = (item.get("yinbao") or "").strip()
    out["shuang_payoff"] = (item.get("shuang_payoff") or "").strip()
    out["end_hook"] = (item.get("end_hook") or "").strip()
    out["witnesses"] = item.get("witnesses") or []
    out["involved_characters"] = item.get("involved_characters") or []
    out["new_info_count"] = _coerce_int(item.get("new_info_count"), 1)
    out["is_big_beat"] = bool(item.get("is_big_beat", False))
    out["expected_words"] = _coerce_int(item.get("expected_words"), default_words)
    rr = item.get("realm_rank")
    out["realm_rank"] = _coerce_int(rr, 0) if rr not in (None, "") else None
    sr = item.get("realm_sub_rank")
    out["realm_sub_rank"] = _coerce_int(sr, 0) if sr not in (None, "") else None
    return out


def _normalize_volume(v: dict) -> dict:
    """卷级容错：境界区间矫正为整数（缺省 None，交由 linter / 后续补齐）。"""
    for k in ("realm_start_rank", "realm_end_rank"):
        val = v.get(k)
        v[k] = _coerce_int(val, 0) if val not in (None, "") else None
    return v


def normalize_beat_row(item: dict, idx: int) -> dict:
    """节拍行容错归一化：补默认、矫正类型。"""
    return {
        "chapter_number": _coerce_int(item.get("chapter_number"), idx + 1),
        "title": (item.get("title") or f"第{idx + 1}章").strip(),
        "shuang_type": (item.get("shuang_type") or "").strip(),
        "target_emotion": (item.get("target_emotion") or "").strip(),
        "location": (item.get("location") or "").strip(),
        "slap_target": (item.get("slap_target") or "").strip(),
        "realm_rank": _coerce_int(item.get("realm_rank"), 0) or None,
        "is_big_beat": bool(item.get("is_big_beat", False)),
        "one_line": (item.get("one_line") or "").strip(),
    }


def normalize_step(step: str, data: Any) -> Any:
    """步骤级归一化入口。章纲/卷需要境界字段容错，其余直接透传。"""
    if step in ("chapter_outlines", "chapter_repair") and isinstance(data, list):
        return [normalize_chapter(it if isinstance(it, dict) else {}, i)
                for i, it in enumerate(data)]
    if step == "beat_sequence" and isinstance(data, list):
        return [normalize_beat_row(it if isinstance(it, dict) else {}, i)
                for i, it in enumerate(data)]
    if step == "volume_chapters" and isinstance(data, dict):
        beats = data.get("beat_sequence")
        chapters = data.get("chapter_outlines")
        return {
            "beat_sequence": normalize_step(
                "beat_sequence", beats if isinstance(beats, list) else []),
            "chapter_outlines": normalize_step(
                "chapter_outlines", chapters if isinstance(chapters, list) else []),
        }
    if step == "volumes" and isinstance(data, list):
        return [_normalize_volume(v) if isinstance(v, dict) else v for v in data]
    return data
