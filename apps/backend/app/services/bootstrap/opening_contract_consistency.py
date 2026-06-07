"""开局承诺 ↔ 卷级对立面 roster 一致性校验。

设计动机
--------
开局追读承诺（Step 12, ``Project.extra.opening_contract``）与卷级对立面 roster
（Step 4.5, ``Project.extra.antagonist_ladder``）由两个独立步骤生成，互不校验。
承诺生成 LLM 只拿到卷一骨架 + 反派摘要，看不到"哪个 Boss 属于哪一卷"，于是会
许下"第10章清算陆长歌"——而 roster 早已把陆长歌定为第3卷 Boss。结果开局承诺与
大纲（跟随 roster 的卷骨架/章纲）必然矛盾，这正是"开局承诺与大纲展开不一致"的根因。

本模块在 Bootstrap 一致性扫描期做确定性交叉核验：用事件抽取器找出承诺文本里
**明示要被击杀的目标**，若该目标是 roster 中 ``vol_index ≥ 1`` 的后续卷 Boss，
即判定为 OC-LADDER 冲突——开局根本不可能兑现，必须修正承诺或调整 roster。

复用 ``outline_linter.event_ledger`` 的施害者/受害者有向匹配，避免把"陆长歌屠主角
满门"里的陆长歌误判成被击杀目标。

红线：本文件 ≤ 600 行。
"""

from __future__ import annotations

from typing import Any

# 承诺 dict 里参与"击杀目标"判定的文本字段（值可能是 str 或 list[str]）
_CONTRACT_TEXT_KEYS = (
    "first_200_words_test",
    "chapter1_hook",
    "chapter3_payoff",
    "chapter5_foreshadow",
    "chapter10_subscribe_reason",
    "chapter_rhythm",
    "opening_traps_to_avoid",
)


def _contract_text(contract: dict) -> str:
    """把开局承诺各字段拼成一段可供事件抽取的文本。"""
    if not isinstance(contract, dict):
        return ""
    parts: list[str] = []
    for key in _CONTRACT_TEXT_KEYS:
        val = contract.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val)
        elif isinstance(val, list):
            parts.extend(str(x) for x in val if str(x).strip())
    # 兜底：未列入白名单的字符串字段也纳入（承诺结构可能扩展）
    for key, val in contract.items():
        if key in _CONTRACT_TEXT_KEYS:
            continue
        if isinstance(val, str) and val.strip():
            parts.append(val)
    return " ".join(parts)


def _ladder_boss_volumes(ladder: list[dict]) -> dict[str, int]:
    """boss_name → vol_index（仅取名字 ≥2 字的有效 Boss）。"""
    out: dict[str, int] = {}
    for row in ladder or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("boss_name") or row.get("name") or "").strip()
        vi = row.get("vol_index")
        if vi is None:
            vi = row.get("volume_index")
        try:
            vi_int = int(vi)
        except (TypeError, ValueError):
            continue
        if len(name) >= 2:
            # 同名取最早卷（保守：越早越不应在开局被"提前清算"判罚）
            out[name] = min(out.get(name, vi_int), vi_int)
    return out


def check_contract_vs_ladder(
    contract: dict,
    ladder: list[dict],
) -> list[dict]:
    """交叉核验开局承诺与 roster，返回 consistency_issues 风格的 dict 列表。

    Args:
        contract: ``Project.extra.opening_contract``。
        ladder:   ``Project.extra.antagonist_ladder``（normalize 后，每条含
                  ``vol_index`` / ``boss_name``）。

    Returns:
        冲突列表；每条形如 consistency_scan 的 issue dict（severity/type/...）。
    """
    from app.services.outline_linter.event_ledger import (
        EVENT_DEATH,
        CharacterRef,
        extract_events_from_text,
    )

    boss_vol = _ladder_boss_volumes(ladder)
    if not boss_vol or not isinstance(contract, dict) or not contract:
        return []

    text = _contract_text(contract)
    if not text:
        return []

    refs = [CharacterRef(id=name, name=name) for name in boss_vol]
    kill_targets = {
        char_name
        for _, char_name, etype, _ in extract_events_from_text(text, refs)
        if etype == EVENT_DEATH
    }

    issues: list[dict] = []
    for name in sorted(kill_targets):
        vi = boss_vol.get(name)
        if vi is None or vi < 1:
            continue  # 第1卷可清算目标 / 未登记 → 不罚
        issues.append({
            "severity": "high",
            "type": "opening_contract_ladder_conflict",
            "rule_id": "OC-LADDER",
            "description": (
                f"开局承诺要求清算「{name}」，但 roster 将其定为第{vi + 1}卷 Boss，"
                f"前10章不可能兑现，导致开局承诺与大纲必然矛盾"
            ),
            "suggestion": (
                f"二选一：把开局承诺改为「{name}」登场施压/留下仇恨钩（不承诺其死亡）；"
                f"或在 roster 中将「{name}」改为第1卷可清算的小 Boss"
            ),
            "auto_detected": True,
        })
    return issues


def check_project_contract_consistency(project: Any) -> list[dict]:
    """工程入口：从 Project.extra 读取承诺与 roster 并校验。"""
    from app.services.bootstrap.antagonist_roster import load_antagonist_ladder

    extra = project.extra if isinstance(getattr(project, "extra", None), dict) else {}
    contract = extra.get("opening_contract")
    ladder = load_antagonist_ladder(project)
    if not isinstance(contract, dict) or not ladder:
        return []
    return check_contract_vs_ladder(contract, ladder)
