"""角色生命周期一致性规则（LIFE-* / ALIGN-* / PROM-KILL）。

基于 ``event_ledger`` 抽取的跨卷事件时间轴，确定性地拦截番茄/修仙大纲最常见的
"低级逻辑硬伤"：人物死而复死、死后照常出场、盟友无过渡被当宿敌清算、核心仇恨
目标的击杀承诺严重超窗。

这些都是**机器可判定**的逻辑错误，不靠 LLM 自觉，也不靠事后质检评分——命中即在
章纲落库门禁报问题（LIFE-01 为阻断级）。

规则一览
--------
- LIFE-01（critical/阻断）：同一角色出现两次死亡且中间无复活事件（死而复死）。
- LIFE-02（high）：角色死亡后仍出现在后续章 involved_character_ids，且中间无复活。
- ALIGN-01（high）：角色已倒向我方（反水/投靠），之后被作为死亡受害者清算，
  且中间无"再叛/翻脸"过渡事件——阵营硬切。
- PROM-KILL（high）：读者承诺/开局承诺里明示要击杀的目标，实际击杀章号严重超出
  承诺窗口（番茄快节奏另设硬上限）。

红线：本文件 ≤ 600 行。
"""

from __future__ import annotations

from typing import Any

from app.services.outline_linter.event_ledger import (
    EVENT_ALLY,
    EVENT_DEATH,
    EVENT_ENEMY,
    EVENT_REVIVE,
    CharacterRef,
    LifecycleEvent,
    extract_events_from_text,
)
from app.services.outline_linter.schemas import LinterIssue

# 番茄/快节奏：核心仇恨（击杀）目标存活硬上限——超过即严重影响追读
FANQIE_KILL_HARD_CAP = 15
# 一般节奏：盟友被清算需要的最小"再叛过渡"容忍——这里不设距离阈值，只看有无过渡事件


def _has_event_between(
    events: list[LifecycleEvent],
    lo: int,
    hi: int,
    event_type: str,
    *,
    inclusive_hi: bool = True,
) -> bool:
    """events 中是否存在 (lo, hi] 区间内指定类型事件。"""
    for e in events:
        if e.event_type != event_type:
            continue
        if e.global_chapter <= lo:
            continue
        if (e.global_chapter <= hi) if inclusive_hi else (e.global_chapter < hi):
            return True
    return False


def lint_lifecycle(
    timeline: dict[str, list[LifecycleEvent]],
    appearances: dict[str, list[int]],
    *,
    window_lo: int,
    window_hi: int,
) -> list[LinterIssue]:
    """LIFE-01 / LIFE-02 / ALIGN-01（纯函数，便于单测）。

    Args:
        timeline:     char_id → 升序事件列表。
        appearances:  char_id → 该角色出现的全书章号升序列表（来自 involved_character_ids）。
        window_lo/hi: 仅当"较晚的那条事件"落在本卷全书章号区间 [lo, hi] 内才报问题，
                      避免每卷重复报同一历史矛盾。
    """
    issues: list[LinterIssue] = []

    for char_id, events in timeline.items():
        if not events:
            continue
        name = events[0].char_name
        deaths = [e for e in events if e.event_type == EVENT_DEATH]
        revives = [e for e in events if e.event_type == EVENT_REVIVE]

        # ── LIFE-01：死而复死（两次死亡中间无复活）────────────────────────────
        for i in range(1, len(deaths)):
            d_prev, d_cur = deaths[i - 1], deaths[i]
            if d_prev.global_chapter == d_cur.global_chapter:
                continue
            revived_between = any(
                d_prev.global_chapter < r.global_chapter <= d_cur.global_chapter
                for r in revives
            )
            if revived_between:
                continue
            if not (window_lo <= d_cur.global_chapter <= window_hi):
                continue
            issues.append(LinterIssue(
                rule_id="LIFE-01",
                severity="critical",
                scope="sequence",
                message=(
                    f"「{name}」死而复死：第{d_prev.global_chapter}章已死"
                    f"（{d_prev.evidence}），第{d_cur.global_chapter}章再次被杀"
                    f"（{d_cur.evidence}），其间无复活/诈死交代"
                ),
                chapter_number_in_volume=None,
                node_id=d_cur.node_id,
                suggestion=(
                    f"二选一：删除第{d_cur.global_chapter}章的再次死亡；"
                    f"或在第{d_prev.global_chapter}—{d_cur.global_chapter}章间补"
                    f"明确的复活/诈死铺垫"
                ),
            ))

        # ── LIFE-02：死后仍出场（无复活）────────────────────────────────────
        if deaths:
            first_death = deaths[0].global_chapter
            death_chapters = {d.global_chapter for d in deaths}
            later_revive = min(
                (r.global_chapter for r in revives if r.global_chapter > first_death),
                default=None,
            )
            for appear in appearances.get(char_id, []):
                if appear <= first_death:
                    continue
                if appear in death_chapters:
                    continue  # 该章本身是再次死亡，已由 LIFE-01 覆盖
                if later_revive is not None and appear >= later_revive:
                    break  # 复活之后的出场合法
                if not (window_lo <= appear <= window_hi):
                    continue
                issues.append(LinterIssue(
                    rule_id="LIFE-02",
                    severity="high",
                    scope="sequence",
                    message=(
                        f"「{name}」已于第{first_death}章死亡，却出现在第{appear}章，"
                        f"其间无复活交代"
                    ),
                    chapter_number_in_volume=None,
                    suggestion=(
                        f"确认第{appear}章是否应有「{name}」；"
                        f"若需其登场，先补复活/诈死设定，否则替换为其他角色"
                    ),
                ))
                break  # 每角色仅报最早一处，避免刷屏

        # ── ALIGN-01：盟友无过渡被清算 ──────────────────────────────────────
        allies = [e for e in events if e.event_type == EVENT_ALLY]
        enemies = [e for e in events if e.event_type == EVENT_ENEMY]
        for ally in allies:
            death_after = min(
                (d.global_chapter for d in deaths if d.global_chapter > ally.global_chapter),
                default=None,
            )
            if death_after is None:
                continue
            re_betrayed = any(
                ally.global_chapter < en.global_chapter <= death_after for en in enemies
            )
            if re_betrayed:
                continue
            if not (window_lo <= death_after <= window_hi):
                continue
            issues.append(LinterIssue(
                rule_id="ALIGN-01",
                severity="high",
                scope="sequence",
                message=(
                    f"「{name}」阵营硬切：第{ally.global_chapter}章已倒向我方"
                    f"（{ally.evidence}），第{death_after}章却被作为敌人/宿怨清算，"
                    f"其间无再叛/翻脸过渡"
                ),
                chapter_number_in_volume=None,
                suggestion=(
                    f"在第{ally.global_chapter}—{death_after}章间补「{name}」"
                    f"再次倒戈/暴露真面目的过渡章；或改写其结局，避免主角滥杀盟友"
                ),
            ))
            break

    return issues


def lint_kill_promise_window(
    promises: list[dict],
    char_refs: list[CharacterRef],
    timeline: dict[str, list[LifecycleEvent]],
    *,
    max_global: int,
    is_fast_pace: bool,
    window_lo: int,
    window_hi: int,
    hard_cap: int = FANQIE_KILL_HARD_CAP,
) -> list[LinterIssue]:
    """PROM-KILL：明示击杀目标的承诺是否在窗口内兑现（纯函数）。

    用事件抽取器解析承诺文本本身，确定"要被杀的是谁"，再到时间轴查该角色实际
    被杀章号——不依赖规划阶段恒为空的 ``promise_fulfilled`` 字段。

    Args:
        promises: [{text, src_chapter, window, priority}]。
        char_refs: 角色引用（用于在承诺文本中识别击杀目标）。
        max_global: 当前全书已规划到的最大章号。
        is_fast_pace: 番茄/快节奏，则核心击杀目标额外受 hard_cap 约束。
    """
    issues: list[LinterIssue] = []
    seen: set[tuple[str, int]] = set()

    for promise in promises:
        text = (promise.get("text") or "").strip()
        if not text:
            continue
        src = int(promise.get("src_chapter") or 0)
        window = int(promise.get("window") or 0)
        targets = {
            cid for cid, _, etype, _ in extract_events_from_text(text, char_refs)
            if etype == EVENT_DEATH
        }
        if not targets:
            continue
        deadline = (src + window) if (src and window) else 0
        # 快节奏核心仇恨目标：即使承诺没给窗口，也按硬上限约束（自 src 起算）
        cap_deadline = (src + hard_cap) if (is_fast_pace and src) else 0

        for cid in targets:
            events = timeline.get(cid, [])
            name = events[0].char_name if events else cid
            deaths = sorted(e.global_chapter for e in events if e.event_type == EVENT_DEATH)
            first_death = deaths[0] if deaths else None
            effective_deadline = deadline or cap_deadline
            if not effective_deadline:
                continue

            # 实际击杀章号（或至今未杀）
            late = first_death is not None and first_death > effective_deadline
            never = first_death is None and max_global > effective_deadline
            if not (late or never):
                continue

            # 归属：把问题报在"窗口截止"或"实际迟到击杀"所在卷，避免每卷重复
            attribution = first_death if late else effective_deadline
            if not (window_lo <= attribution <= window_hi):
                continue
            key = (cid, effective_deadline)
            if key in seen:
                continue
            seen.add(key)

            cap_note = (
                f"（番茄快节奏核心仇恨目标存活硬上限 {hard_cap} 章）"
                if (is_fast_pace and not deadline)
                else ""
            )
            if late:
                detail = f"实际于第{first_death}章才被击杀"
            else:
                detail = f"直到已规划的第{max_global}章仍未被击杀"
            issues.append(LinterIssue(
                rule_id="PROM-KILL",
                severity="high",
                scope="volume",
                message=(
                    f"击杀承诺超窗：承诺击杀「{name}」应在第{effective_deadline}章前完成"
                    f"{cap_note}，{detail}。核心仇恨目标长期存活将严重打击追读"
                ),
                suggestion=(
                    f"把「{name}」的清算提前到第{effective_deadline}章前；"
                    f"若确需养成长线反派，请改写承诺/降低其作为'即时仇恨目标'的定位"
                ),
            ))

    return issues


# ── DB 适配层 ────────────────────────────────────────────────────────────────

def _is_fast_pace(project: Any) -> bool:
    extra = project.extra if isinstance(project.extra, dict) else {}
    pos = extra.get("positioning") if isinstance(extra.get("positioning"), dict) else {}
    pace = (pos.get("pace_type") or "").lower()
    if pace:
        return pace == "fast"
    # 番茄/同人快线兜底
    return bool(extra.get("fanqie_positioning") or extra.get("fanfic_positioning"))


def _load_kill_promises(db: Any, project_id: Any) -> list[dict]:
    """读取可能含击杀目标的读者承诺（open / 全部，优先级≥3）。"""
    from app.models import ReaderPromise

    out: list[dict] = []
    for rp in (
        db.query(ReaderPromise)
        .filter(ReaderPromise.project_id == project_id)
        .all()
    ):
        out.append({
            "text": rp.promise_text or "",
            "src_chapter": int(rp.source_chapter_number or 0),
            "window": int(rp.expected_chapter_window or 0),
            "priority": int(rp.priority or 3),
        })
    return out


def run_lifecycle_rules(
    db: Any,
    project: Any,
    volume_node: Any,
    *,
    volume_start_global: int,
) -> list[LinterIssue]:
    """卷级生命周期校验：构建全书事件时间轴 → 跨卷硬校验本卷区间。"""
    from app.services.outline_linter.event_ledger import build_project_timeline

    timeline, rows, ref_map = build_project_timeline(db, project.id)
    char_refs = list(ref_map.values())

    # 出场索引：char_id → 升序全书章号
    appearances: dict[str, list[int]] = {}
    max_global = 0
    for row in rows:
        max_global = max(max_global, row.global_chapter)
        for cid in row.involved_character_ids:
            appearances.setdefault(str(cid), []).append(row.global_chapter)
    for lst in appearances.values():
        lst.sort()

    # 本卷全书章号区间
    vol_sort = int(volume_node.sort_order or 0)
    vol_rows = [r.global_chapter for r in rows if r.volume_index == vol_sort]
    window_lo = volume_start_global
    if vol_rows:
        window_hi = max(vol_rows)
    else:
        planned = int((volume_node.extra or {}).get("planned_chapters") or 30)
        window_hi = volume_start_global + planned - 1

    issues = lint_lifecycle(
        timeline, appearances, window_lo=window_lo, window_hi=window_hi,
    )
    issues.extend(lint_kill_promise_window(
        _load_kill_promises(db, project.id),
        char_refs,
        timeline,
        max_global=max_global,
        is_fast_pace=_is_fast_pace(project),
        window_lo=window_lo,
        window_hi=window_hi,
    ))
    return issues
