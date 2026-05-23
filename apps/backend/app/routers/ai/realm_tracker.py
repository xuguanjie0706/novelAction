"""
realm_tracker.py — 境界变化追踪辅助

职责：当章节复盘检测到人物境界发生实质变化时，
  1. 将本次突破追加至 Character.arc_stages（成长轨迹）
  2. 生成一条 importance_score=0.95 的 MemoryChunk（境界突破里程碑）

设计约束：
- 仅被 debrief_routes.chapter_debrief 调用；返回值由调用方一起 flush/commit
- 不直接 commit，保留调用方事务控制权
- 新建记忆 chunk 返回给调用方，由调用方触发 embed_chunk_async
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models import Character, MemoryChunk


def sync_realm_to_arc_stages(
    char: Character,
    realm_label: str,
    chapter_number: int,
    chapter_id: str,
    chapter_title: str,
) -> None:
    """
    将新境界作为一个已完成的成长阶段追加到 Character.arc_stages。

    arc_stages 格式（列表，每项为 dict）：
      {"stage": "境界名", "completed": True, "chapter_number": 5, "chapter_id": "...", "chapter_title": "..."}

    规则：
    - 若该境界名已存在于 arc_stages 中（精确匹配），跳过（幂等）
    - 超出 50 条时裁剪最旧的，保留最近 50 条

    @param char: Character ORM 对象（调用方负责 commit）
    @param realm_label: 新境界的文字名称（如"灵徒九重"）
    @param chapter_number: 对应章节章号（整数）
    @param chapter_id: 对应章节 UUID 字符串
    @param chapter_title: 对应章节标题
    """
    existing = char.arc_stages if isinstance(char.arc_stages, list) else []
    # 幂等：相同境界名已存在则跳过
    if any(
        isinstance(s, dict) and s.get("stage") == realm_label
        for s in existing
    ):
        return
    entry = {
        "stage": realm_label,
        "realm": realm_label,
        "state": f"第{chapter_number}章突破",
        "chapter_range": str(chapter_number),
        "completed": True,
        "chapter_number": chapter_number,
        "chapter_id": chapter_id,
        "chapter_title": chapter_title[:120],
    }
    updated = list(existing) + [entry]
    # 裁剪上限
    char.arc_stages = updated[-50:]


def make_realm_memory_chunk(
    project_id: str,
    chapter_id: UUID,
    chapter_number: int,
    char_name: str,
    before_realm: str | None,
    after_realm: str,
) -> MemoryChunk:
    """
    为境界突破生成一条高重要度 MemoryChunk。

    importance_score=0.95 确保 RAG 召回时优先命中，
    防止写章时 AI 看不到主角当前境界而写出倒退剧情。

    @param project_id: 项目 UUID 字符串
    @param chapter_id: 本章 UUID
    @param chapter_number: 章号（整数）
    @param char_name: 突破的人物名
    @param before_realm: 突破前境界（None 表示首次记录）
    @param after_realm: 突破后境界
    @returns 未持久化的 MemoryChunk ORM 对象（调用方负责 db.add + commit）
    """
    transition = (
        f"从{before_realm}突破至{after_realm}"
        if before_realm and before_realm != after_realm
        else f"当前境界：{after_realm}"
    )
    content = (
        f"【境界里程碑】{char_name}{transition}。"
        f"本条记忆优先级极高（importance=0.95），写章时必须严格遵守此境界状态，"
        f"禁止在后续章节出现该角色境界倒退或低于【{after_realm}】的描写。"
    )
    return MemoryChunk(
        project_id=project_id,
        chapter_id=chapter_id,
        chapter_number=chapter_number,
        memory_type="character_state",
        title=f"{char_name}境界突破：{after_realm}",
        content=content,
        tags=[char_name, "境界", "突破", after_realm],
        importance_score=0.95,
    )


def normalize_debrief_milestone_ranks(
    hist: list[dict[str, Any]],
    name_to_rank: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """
    用力量体系白名单重算每条 milestone 的 realm_rank，覆盖 AI 乱填的序号（如 11）。

    复盘里程碑的排序与 current_realm 回写均依赖规范化后的 rank。
    """
    from app.routers.outline.helpers.realm_timeline import _rank_for_realm_label

    out: list[dict[str, Any]] = []
    for row in hist:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        label = str(item.get("realm_name") or "").strip()
        if not label:
            continue
        resolved = _rank_for_realm_label(label, name_to_rank) if name_to_rank else None
        if resolved is not None:
            item["realm_rank"] = resolved
        else:
            rr = item.get("realm_rank")
            try:
                item["realm_rank"] = int(rr) if rr is not None else None
            except (TypeError, ValueError):
                item["realm_rank"] = None
        out.append(item)
    out.sort(key=lambda h: int(h.get("chapter_number") or 0))
    return out


def _latest_realm_from_milestone_history(
    hist: list[dict[str, Any]],
    name_to_rank: dict[str, int] | None = None,
) -> tuple[str | None, int | None, int | None]:
    """
    从 debrief_realm_milestones 取**最新章节**的境界（非最大 rank）。

    AI 常把 realm_rank 填成与力量体系无关的整数；按章号取末条 + 白名单解析更贴近正文进度。

    Returns:
        (realm_name, realm_rank, chapter_number)
    """
    from app.routers.outline.helpers.realm_timeline import _rank_for_realm_label

    normalized = normalize_debrief_milestone_ranks(hist, name_to_rank)
    if not normalized:
        return None, None, None
    last = normalized[-1]
    label = str(last.get("realm_name") or "").strip()
    if not label:
        return None, None, None
    rank = last.get("realm_rank")
    try:
        rank = int(rank) if rank is not None else None
    except (TypeError, ValueError):
        rank = None
    if (rank is None or rank <= 0) and name_to_rank:
        rank = _rank_for_realm_label(label, name_to_rank)
    try:
        ch = int(last.get("chapter_number") or 0)
    except (TypeError, ValueError):
        ch = 0
    return label, rank, ch or None


def reconcile_character_realm_from_milestones(
    char: Character,
    name_to_rank: dict[str, int] | None = None,
) -> bool:
    """
    用 extra.debrief_realm_milestones 中**最新章节**快照回写 current_realm / realm_rank。

    同时规范化里程碑内 rank，修复历史脏数据。
    """
    extra = dict(char.extra) if isinstance(char.extra, dict) else {}
    raw = [h for h in (extra.get("debrief_realm_milestones") or []) if isinstance(h, dict)]
    if not raw:
        return False
    normalized = normalize_debrief_milestone_ranks(raw, name_to_rank)
    extra["debrief_realm_milestones"] = normalized
    char.extra = extra

    label, rank, _ = _latest_realm_from_milestone_history(normalized, name_to_rank)
    if not label:
        return False
    prev_name = (char.current_realm or "").strip()
    prev_rank = char.realm_rank
    if label == prev_name and rank == prev_rank:
        return normalized != raw
    char.current_realm = label[:100]
    if rank is not None and rank > 0:
        char.realm_rank = rank
    return True


def apply_realm_progression_side_effects(
    char: Character,
    *,
    realm_label: str,
    rank_snap: int | None,
    chapter_number: int,
    chapter_id: str,
    chapter_title: str,
    before_realm: str | None,
    before_rank: int | None,
    project_id: str,
    chapter_uuid: UUID,
    name_to_rank: dict[str, int] | None = None,
) -> MemoryChunk | None:
    """
    境界序号或名称有实质进展时：写 current_realm、arc_stages，必要时生成里程碑记忆。

    @returns 需 db.add 的 MemoryChunk，无则 None
    """
    label = (realm_label or "").strip()[:100]
    if not label:
        return None
    new_rank = rank_snap
    if new_rank is None and name_to_rank:
        from app.routers.outline.helpers.realm_timeline import _rank_for_realm_label

        new_rank = _rank_for_realm_label(label, name_to_rank)
    old_rank = before_rank if before_rank is not None else (char.realm_rank or 0)
    old_name = (before_realm or "").strip()
    rank_up = new_rank is not None and new_rank > old_rank
    name_progress = bool(label) and label != old_name and (
        new_rank is None or new_rank >= old_rank
    )
    if not rank_up and not name_progress:
        return None
    if new_rank is not None and (char.realm_rank is None or new_rank >= (char.realm_rank or 0)):
        char.realm_rank = new_rank
    char.current_realm = label
    sync_realm_to_arc_stages(
        char=char,
        realm_label=label,
        chapter_number=chapter_number,
        chapter_id=chapter_id,
        chapter_title=chapter_title,
    )
    if rank_up or (name_progress and label != old_name):
        return make_realm_memory_chunk(
            project_id=project_id,
            chapter_id=chapter_uuid,
            chapter_number=chapter_number,
            char_name=char.name,
            before_realm=before_realm,
            after_realm=label,
        )
    return None
