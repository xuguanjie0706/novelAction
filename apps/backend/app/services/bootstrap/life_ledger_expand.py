"""章纲懒展开：角色生死账本 prompt 块（生成期注入，防「死而复杀」低级硬伤）。

两层防线：
1. ``build_life_ledger_expand_block``：生成**前**，把前文（跨卷 + 本卷前窗口）已死角色
   作为只读事实注入 prompt——确定性、不依赖模型自觉。
2. ``detect_intra_batch_life_violations``：生成**后**，对刚返回的本批 JSON 跑确定性
   抽取，捕获「同一批内死而复死」（前置账本无法覆盖的同窗口场景），命中即回灌
   ``build_life_violation_hint`` 提示让模型重输出本批——把"靠模型在长数组里自检"
   降级为"确定性检测 + 定向重试"。
"""
from __future__ import annotations

from typing import Any

from app.services.outline_linter.event_ledger import (
    EVENT_DEATH,
    EVENT_REVIVE,
    CharacterRef,
    ChapterTextRow,
    LifecycleEvent,
    build_timeline,
    declared_from_extra,
    extract_events_from_text,
    load_character_refs,
    load_chapter_rows,
    node_event_text,
    resolve_declared_events,
)


def _prior_global_cutoff(volume_start_global: int, batch_start: int) -> int:
    """本批开始前已「确定」的全书章号上界（不含本批）。"""
    if batch_start <= 1:
        return volume_start_global - 1
    return volume_start_global + batch_start - 2


def _rows_from_prior_nodes(
    prior_nodes: list[Any],
    volume_start_global: int,
    cutoff_global: int,
) -> list[ChapterTextRow]:
    rows: list[ChapterTextRow] = []
    for node in prior_nodes or []:
        sort_order = int(getattr(node, "sort_order", 0) or 0)
        global_ch = volume_start_global + sort_order
        if global_ch > cutoff_global:
            continue
        decl_deaths, decl_revives = declared_from_extra(getattr(node, "extra", None))
        rows.append(
            ChapterTextRow(
                global_chapter=global_ch,
                text=node_event_text(node),
                node_id=str(getattr(node, "id", "") or ""),
                volume_index=None,
                involved_character_ids=[
                    str(x) for x in (getattr(node, "involved_character_ids", None) or [])
                ],
                declared_deaths=decl_deaths,
                declared_revives=decl_revives,
            )
        )
    return rows


def _first_death_chapters(timeline: dict[str, list[LifecycleEvent]]) -> list[tuple[str, int, str]]:
    """char_name → (first_death_global, evidence snippet)."""
    out: list[tuple[str, int, str]] = []
    for events in timeline.values():
        deaths = [e for e in events if e.event_type == EVENT_DEATH]
        if not deaths:
            continue
        first = min(deaths, key=lambda e: e.global_chapter)
        revives = [e for e in events if e.event_type == EVENT_REVIVE]
        if any(r.global_chapter > first.global_chapter for r in revives):
            continue
        out.append((first.char_name, first.global_chapter, first.evidence[:60]))
    out.sort(key=lambda x: x[1])
    return out


def build_life_ledger_expand_block(
    db: Any,
    project_id: Any,
    *,
    prior_nodes: list[Any] | None,
    volume_start_global: int,
    batch_start: int,
    batch_end: int,
) -> str:
    """从已落库 + 本卷前批章纲抽取死亡事件，拼成生成 prompt 约束块。"""
    cutoff = _prior_global_cutoff(volume_start_global, batch_start)
    refs = load_character_refs(db, project_id) if db and project_id else []
    rows = [
        r for r in load_chapter_rows(db, project_id)
        if r.global_chapter <= cutoff
    ] if db and project_id else []

    mem_rows = _rows_from_prior_nodes(prior_nodes or [], volume_start_global, cutoff)
    seen_globals = {r.global_chapter for r in rows}
    for r in mem_rows:
        if r.global_chapter not in seen_globals:
            rows.append(r)
            seen_globals.add(r.global_chapter)

    deaths = _first_death_chapters(build_timeline(refs, rows))
    in_batch_rule = build_life_ledger_in_batch_rule(batch_start=batch_start, batch_end=batch_end)

    if not deaths:
        return in_batch_rule

    lines = [
        "【角色生死账本（只读事实，本批第"
        f"{batch_start}～{batch_end}章不得违反）】",
        "下列角色在前文已宣告死亡；本批禁止再以活人实体出场、再次被击杀，"
        "或 title/core_event 写「斩杀/秒杀/格杀」该角色，除非同章写明残魂/化身/假死/遗物：",
    ]
    for name, g_ch, evidence in deaths[:24]:
        hint = f"（{evidence}）" if evidence else ""
        lines.append(f"  · {name}：第{g_ch}章死亡{hint}")
    lines.append(
        "  ⚠️ 若需写「打脸曾凌辱主角的走狗」，须换用新名字或写该角色的后继者/同党，"
        "不得复用已死亡角色名。"
    )
    return "\n".join(lines) + in_batch_rule


# ── 生成后：本批内确定性死而复死检测 + 定向重试提示 ──────────────────────────

def _item_event_text(item: dict) -> str:
    """从 AI 返回的单章 JSON 拼出参与生死判定的文本（镜像 ``node_event_text``）。"""
    parts = [
        item.get("title") or "",
        item.get("core_event") or item.get("summary") or "",
        item.get("character_change") or item.get("conflict") or "",
        item.get("end_hook") or "",
        item.get("protagonist_choice") or "",
        item.get("choice_cost") or "",
        item.get("villain_action") or "",
        item.get("power_milestone") or "",
        item.get("satisfaction_payoff") or "",
        item.get("supporting_spotlight") or "",
    ]
    return " ".join(p for p in parts if isinstance(p, str) and p.strip())


def collect_prior_deaths(
    db: Any,
    project_id: Any,
    *,
    prior_nodes: list[Any] | None,
    volume_start_global: int,
    batch_start: int,
) -> tuple[list[CharacterRef], dict[str, tuple[str, int]]]:
    """本批开始前（前卷 + 本卷前窗口）已死且未复活的角色。

    Returns:
        (char_refs, dead) —— dead: char_id → (角色名, 首次死亡全书章号)。
        char_refs 一并返回，避免调用方重复加载。
    """
    cutoff = _prior_global_cutoff(volume_start_global, batch_start)
    refs = load_character_refs(db, project_id) if db and project_id else []
    rows = [
        r for r in load_chapter_rows(db, project_id)
        if r.global_chapter <= cutoff
    ] if db and project_id else []

    mem_rows = _rows_from_prior_nodes(prior_nodes or [], volume_start_global, cutoff)
    seen = {r.global_chapter for r in rows}
    for r in mem_rows:
        if r.global_chapter not in seen:
            rows.append(r)
            seen.add(r.global_chapter)

    dead: dict[str, tuple[str, int]] = {}
    for cid, events in build_timeline(refs, rows).items():
        deaths = [e for e in events if e.event_type == EVENT_DEATH]
        if not deaths:
            continue
        first = min(deaths, key=lambda e: e.global_chapter)
        revives = [e for e in events if e.event_type == EVENT_REVIVE]
        if any(r.global_chapter > first.global_chapter for r in revives):
            continue
        dead[cid] = (events[0].char_name, first.global_chapter)
    return refs, dead


def detect_intra_batch_life_violations(
    batch_data: list,
    *,
    batch_start: int,
    char_refs: list[CharacterRef],
    dead_before: dict[str, tuple[str, int]],
    volume_start_global: int,
) -> list[tuple[str, int, int, str]]:
    """检测刚生成的本批内（含与既往）死而复死。

    逐章按全书章号顺序推进一张活/死账本：复活解除标记，死亡时若该角色已死且本章
    未给复活/假死交代，则记一条违规。

    Returns:
        [(角色名, 首次死亡全书章号, 再次死亡全书章号, 证据片段)]。
    """
    dead: dict[str, tuple[str, int]] = dict(dead_before)
    violations: list[tuple[str, int, int, str]] = []
    for i, item in enumerate(batch_data):
        if not isinstance(item, dict):
            continue
        g = volume_start_global + (batch_start + i) - 1
        # 事件 = 正文正则 ∪ 结构化生死声明（item.deaths/revives），按 (cid, etype) 去重
        events = list(extract_events_from_text(_item_event_text(item), char_refs))
        events.extend(
            resolve_declared_events(item.get("deaths"), item.get("revives"), char_refs)
        )
        if not events:
            continue
        seen_pair: set[tuple[str, str]] = set()
        deduped: list[tuple[str, str, str, str]] = []
        for ev in events:
            key = (ev[0], ev[2])
            if key not in seen_pair:
                seen_pair.add(key)
                deduped.append(ev)
        events = deduped
        revived_now = {cid for cid, _, et, _ in events if et == EVENT_REVIVE}
        for cid in revived_now:
            dead.pop(cid, None)
        for cid, name, etype, evidence in events:
            if etype != EVENT_DEATH or cid in revived_now:
                continue
            if cid in dead:
                violations.append((name, dead[cid][1], g, evidence))
            else:
                dead[cid] = (name, g)
    return violations


def build_life_violation_hint(violations: list[tuple[str, int, int, str]]) -> str:
    """把检测到的死而复死违规拼成「重输出本批」的定向修正提示。"""
    if not violations:
        return ""
    lines = ["\n【⚠️ 上一轮本批出现「死而复死」硬伤，必须修正后重输出整批 JSON】"]
    seen: set[tuple[str, int, int]] = set()
    for name, d_ch, k_ch, evidence in violations:
        key = (name, d_ch, k_ch)
        if key in seen:
            continue
        seen.add(key)
        hint = f"（{evidence[:40]}）" if evidence else ""
        lines.append(
            f"  · 「{name}」已在第{d_ch}章死亡，第{k_ch}章却再次被击杀{hint}——"
            f"本批改为：击杀其党羽/后继者/冒名者，或为该角色补残魂/化身/假死交代；"
            f"禁止复用已死角色名再死一次或当活人出场。"
        )
    lines.append("  重输出前逐章核对：无任何角色在已死且未复活状态下再次死亡。")
    return "\n".join(lines)


def build_life_ledger_in_batch_rule(*, batch_start: int, batch_end: int) -> str:
    """同批 JSON 内自检规则（整卷单次 1–30 章时前无账本，靠此条兜底）。"""
    return (
        f"\n【角色生死 · 本批内自检（第{batch_start}～{batch_end}章，输出 JSON 前逐章核对）】\n"
        "1. 在同一 JSON 数组内，若较早章节已在 title/summary/core_event/character_change/"
        "end_hook/protagonist_choice 中写某具名角色死亡（斩杀/击杀/吸成干尸/陨落/身死等），"
        "则更后章节禁止：\n"
        "   a) 将该角色列入 involved_characters 作为活人；\n"
        "   b) 标题或 core_event 再次写「击杀/斩杀/秒杀/格杀」该角色；\n"
        "   c) 除非同章明确残魂/化身/假死/遗物/记忆闪回，且 character_change 注明非活人。\n"
        "2. 反例：第3章「赵管事被吸成干尸」→ 第16章禁止「秒杀赵管事」"
        "（应改为对其爪牙/后继者立威，或写残魂/冒名）。\n"
        "3. 已死亡配角不得因「需要打脸」而复活当活人；换名或换对象。\n"
        "4. 每个有人死亡/复活的章节，必须在该章 deaths/revives 数组如实列出角色名"
        "（这是机器确定性校验的主信号；死了却不填 deaths 等同埋下硬伤）。\n"
    )
