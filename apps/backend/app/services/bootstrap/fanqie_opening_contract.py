"""番茄收敛期：从 rhythm_map / face_slap_map 回填开局承诺 + ReaderPromise 种子。

设计动机：番茄专线（graph_fanqie）不跑通用 Step 12 `opening_contract`，导致创作端
「开局承诺」tab 空白——而开局追读承诺是番茄前1万字生死线，不能缺。番茄的等价信息其实
已经存在 `extra.rhythm_map`（前50章爽点节奏）与 `extra.face_slap_map`（首次打脸章节），
本模块在 converge 期把它们派生成与通用线相同契约的 `opening_contract` + `ReaderPromise`，
让 UI、章纲展开（vol1 前10章硬对齐）、复盘回收全部复用既有逻辑，不另开番茄分支。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import Project, ReaderPromise


def _first_tag_of_type(chapter_tags: list, *types: str, max_ch: int = 50) -> dict | None:
    """在 chapter_tags 中找首个指定类型、章号 ≤ max_ch 的条目。"""
    best = None
    for t in chapter_tags or []:
        if not isinstance(t, dict):
            continue
        if str(t.get("type")) in types and isinstance(t.get("ch"), int) and t["ch"] <= max_ch:
            if best is None or t["ch"] < best["ch"]:
                best = t
    return best


def derive_opening_contract_from_fanqie(extra: dict) -> dict:
    """从番茄规划产物派生 opening_contract dict；无可用数据时返回空 dict。

    opening_contract 字段契约与通用 Step 12 一致（见 vol1_chapter_plans 读取处）：
    chapter1_hook / chapter3_payoff / chapter5_foreshadow / chapter10_subscribe_reason /
    chapter_rhythm。
    """
    rhythm = (extra or {}).get("rhythm_map") or {}
    fsm = (extra or {}).get("face_slap_map") or {}
    tags = rhythm.get("chapter_tags") or []
    if not tags and not fsm:
        return {}

    ch1 = _first_tag_of_type(tags, "progress", "small_win", "big_win", max_ch=1)
    first_win = _first_tag_of_type(tags, "big_win", "small_win", max_ch=5)
    big = _first_tag_of_type(tags, "big_win", max_ch=10)
    first_slap_ch = fsm.get("first_slap_chapter")

    contract: dict = {}
    if ch1 and ch1.get("note"):
        contract["chapter1_hook"] = str(ch1["note"])[:200]
    if first_win and first_win.get("note"):
        contract["chapter3_payoff"] = str(first_win["note"])[:200]
    if fsm.get("escalation_path"):
        contract["chapter5_foreshadow"] = str(fsm["escalation_path"])[:200]
    if big and big.get("note"):
        contract["chapter10_subscribe_reason"] = str(big["note"])[:200]
    if fsm.get("slap_rhythm"):
        contract["chapter_rhythm"] = str(fsm["slap_rhythm"])[:200]
    if first_slap_ch:
        contract.setdefault(
            "chapter5_foreshadow",
            f"首次打脸不晚于第{first_slap_ch}章兑现",
        )
    return contract


def _contract_to_promise_entries(contract: dict) -> list[dict]:
    """把 opening_contract 关键字段转成 ReaderPromise 种子条目。"""
    mapping = [
        ("chapter1_hook", 1, "chapter_ending", 5),
        ("chapter3_payoff", 3, "chapter_ending", 5),
        ("chapter5_foreshadow", 5, "name_implication", 4),
        ("chapter10_subscribe_reason", 10, "chapter_ending", 4),
    ]
    entries: list[dict] = []
    for key, src_ch, ptype, prio in mapping:
        text = contract.get(key)
        if not text:
            continue
        entries.append({
            "text": str(text)[:500],
            "promise_type": ptype,
            "source_chapter_number": src_ch,
            "expected_chapter_window": max(1, src_ch),
            "priority": prio,
            "audience_aware": 3,
            "contract_key": key,
        })
    return entries


def backfill_fanqie_opening_contract(db: Session, project: Project) -> int:
    """番茄收敛期回填：派生 opening_contract 落 extra + 种 ReaderPromise。

    幂等：已存在 extra.opening_contract（非空）或已有 bootstrap_opening_contract 来源的
    ReaderPromise 时跳过，避免重复 converge 反复写入。

    Returns:
        新写入的 ReaderPromise 条数（0 表示跳过或无可用数据）。
    """
    extra = dict(project.extra or {})
    if extra.get("opening_contract"):
        return 0  # 已有（通用线或上次回填），尊重既有

    contract = derive_opening_contract_from_fanqie(extra)
    if not contract:
        return 0

    # 落 extra.opening_contract（新 dict + flag_modified 才可靠落库）
    project.extra = {**extra, "opening_contract": contract}
    flag_modified(project, "extra")
    db.commit()

    # 幂等保护：已有 bootstrap 开局来源的承诺则不再种
    exists = (
        db.query(ReaderPromise)
        .filter(ReaderPromise.project_id == project.id)
        .count()
    )
    if exists:
        return 0

    count = 0
    for m in _contract_to_promise_entries(contract):
        db.add(ReaderPromise(
            project_id=project.id,
            promise_text=m["text"],
            promise_type=m["promise_type"],
            source_chapter_number=m["source_chapter_number"],
            expected_chapter_window=m["expected_chapter_window"],
            priority=m["priority"],
            audience_aware=m["audience_aware"],
            status="open",
            extra={"origin": "fanqie_converge_opening_contract", "contract_key": m["contract_key"]},
        ))
        count += 1
    if count:
        db.commit()
    return count
