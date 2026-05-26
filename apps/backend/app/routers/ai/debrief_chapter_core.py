"""
debrief_chapter_core.py — chapter_debrief 路由的纯业务辅助函数

本模块将 chapter_debrief 端点的各处理块提取为独立函数，
每个函数负责单一业务能力，返回值由路由层汇总。

子模块拆分：
  debrief_char_updater.py → create_undo_snapshot_if_new / apply_character_updates

约束：
  - 只操作已注入的 db session，不自行开关事务
  - 不导入路由层 schema（用 Any / 透传属性访问替代）
  - 所有 db.add() 在函数内完成，commit 在路由层统一提交
"""

from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models import (
    Character,
    CharacterChangeLog,
    OutlineNode,
    ReaderPromise,
    StoryLine,
)
from app.routers.ai.normalization import normalize_character_status, normalize_storyline_status
from app.services.ai.promise_debrief import apply_fulfilled_by_ids, apply_plan_promise_fulfillment
from app.routers.ai.text_utils import truncate
from app.utils.chapter_numbering import display_chapter_number

# 人物更新和撤销快照在独立模块，此处重导出以保持 chapter_debrief_route 导入路径不变
from app.routers.ai.debrief_char_updater import (  # noqa: F401
    apply_character_updates,
    create_undo_snapshot_if_new,
)


# ── 故事线更新 ─────────────────────────────────────────────────────

def apply_storyline_updates(
    db: Session,
    project_id: str,
    storyline_updates: List[Any],
    chapter_id: UUID,
    chapter: Any,
) -> list[str]:
    """批量更新故事线状态 / 追加章节节点，返回已更新的故事线名称列表。"""
    updated_storylines: list[str] = []
    for su in storyline_updates:
        storyline_uuid = None
        if su.storyline_id:
            try:
                storyline_uuid = UUID(str(su.storyline_id))
            except Exception:
                storyline_uuid = None

        if storyline_uuid:
            sl = db.query(StoryLine).filter(
                StoryLine.id == storyline_uuid,
                StoryLine.project_id == project_id,
            ).first()
        elif su.storyline_name:
            sl = db.query(StoryLine).filter(
                StoryLine.name == su.storyline_name,
                StoryLine.project_id == project_id,
            ).first()
        else:
            continue

        if not sl:
            continue

        if su.status is not None:
            normalized = normalize_storyline_status(su.status)
            if normalized:
                sl.status = normalized
        if su.append_beat:
            beats = list(sl.key_beats or [])
            chapter_key = str(chapter_id)
            beats = [
                b for b in beats
                if not (isinstance(b, dict) and b.get("chapter_id") == chapter_key)
            ]
            beats.append({
                "chapter": display_chapter_number(chapter.title, chapter.sort_order),
                "chapter_title": chapter.title,
                "beat": su.append_beat,
                "chapter_id": chapter_key,
            })
            sl.key_beats = beats

        updated_storylines.append(sl.name)
    return updated_storylines


# ── 新角色入库 ─────────────────────────────────────────────────────

def apply_new_characters(
    db: Session,
    project_id: str,
    new_characters: List[Any],
    chapter_id: UUID,
    chapter: Any,
) -> list[str]:
    """
    将复盘中发现的新角色批量写入 Character 表并记录审计日志。

    Returns:
        added_new_characters: 成功新建的角色名列表。
    """
    added: list[str] = []
    if not new_characters:
        return added

    existing_names = {
        c.name for c in db.query(Character.name).filter(
            Character.project_id == project_id
        ).all()
    }
    chapter_num = display_chapter_number(chapter.title, chapter.sort_order)
    _VALID_TIERS = {"core", "arc", "plot", "background"}
    _ARC_SCOPE_TO_TIER = {"single_chapter": "plot", "mini_arc": "arc", "long_arc": "core"}

    for nc in new_characters:
        stored_name = truncate((nc.name or "").strip(), 100)
        if not stored_name or stored_name in existing_names:
            continue
        tier = nc.character_tier if nc.character_tier in _VALID_TIERS else None
        if tier is None:
            tier = _ARC_SCOPE_TO_TIER.get(nc.arc_scope or "", "arc")
        new_char_id = uuid4()
        new_char = Character(
            id=new_char_id,
            project_id=project_id,
            name=stored_name,
            alias=[a.strip() for a in (nc.alias or []) if isinstance(a, str) and a.strip()] or None,
            role=truncate(nc.role or "supporting", 20),
            character_tier=tier,
            gender=truncate(nc.gender, 20) if nc.gender else None,
            age=truncate(nc.age, 50) if nc.age else None,
            faction=truncate(nc.faction, 100) if nc.faction else None,
            personality=nc.personality,
            motivation=nc.motivation,
            background=nc.background,
            current_realm=truncate(nc.current_realm, 100) if nc.current_realm else None,
            current_status=normalize_character_status(nc.current_status) or "alive",
            current_location=truncate(nc.current_location, 200) if nc.current_location else None,
            author_notes=nc.author_notes,
            extra={"first_appearance_chapter": chapter_num, "arc_scope": nc.arc_scope},
        )
        db.add(new_char)
        db.flush()

        _tier_labels = {
            "core": "核心长线", "arc": "弧线支柱",
            "plot": "剧情推手", "background": "背景填充",
        }
        db.add(CharacterChangeLog(
            project_id=project_id,
            character_id=new_char_id,
            character_name=new_char.name,
            chapter_id=chapter_id,
            chapter_number=str(chapter_num),
            chapter_title=chapter.title or "",
            source="debrief",
            summary=f"首次登场 · {_tier_labels.get(tier, tier)}",
            changes=[{
                "field": "created", "label": "首次入库",
                "before": None, "after": _tier_labels.get(tier, tier),
            }],
        ))
        existing_names.add(stored_name)
        added.append(stored_name)
    return added


# ── 下一章指令 ─────────────────────────────────────────────────────

def apply_next_chapter_directives(
    db: Session,
    project_id: str,
    next_chapter_directives: List[Any],
    chapter_id: UUID,
    chapter: Any,
) -> int:
    """将复盘指令写入下一个 OutlineNode.extra.directives_from_prev，最多保留 5 条。"""
    directives_applied = 0
    if not next_chapter_directives:
        return directives_applied

    for d in next_chapter_directives:
        try:
            target_id = d.get("outline_node_id")
            patch = d.get("patch") or {}
            if not patch:
                continue
            node = None
            if target_id:
                try:
                    node = db.query(OutlineNode).filter(
                        OutlineNode.id == UUID(str(target_id)),
                        OutlineNode.project_id == project_id,
                    ).first()
                except Exception:
                    node = None
            if not node:
                current_sort = chapter.sort_order or 0
                node = db.query(OutlineNode).filter(
                    OutlineNode.project_id == project_id,
                    OutlineNode.sort_order > current_sort,
                    OutlineNode.status != "done",
                ).order_by(OutlineNode.sort_order.asc()).first()
            if node:
                extra = dict(node.extra or {})
                prev = extra.get("directives_from_prev") or []
                prev.append({
                    "from_chapter_id": str(chapter_id),
                    "from_chapter_title": chapter.title,
                    "patch": patch,
                    "reason": d.get("reason", ""),
                    "applied_at": "now",
                })
                extra["directives_from_prev"] = prev[-5:]
                node.extra = extra
                directives_applied += 1
        except Exception:
            continue
    return directives_applied


# ── 语风 Kit 更新 ─────────────────────────────────────────────────

def apply_speech_kit_updates(
    db: Session,
    project_id: str,
    speech_kit_updates: List[Any],
    chapter_id: UUID,
    chapter: Any,
) -> int:
    """更新人物语风样本（signature_words / sample_dialogues / evolution_note）。"""
    count = 0
    if not speech_kit_updates:
        return count

    for sku in speech_kit_updates:
        try:
            cid = sku.get("character_id")
            if not cid:
                continue
            char = db.query(Character).filter(
                Character.id == UUID(str(cid)),
                Character.project_id == project_id,
            ).first()
            if not char:
                continue
            kit = dict(char.speech_kit or {})
            old_words = set(kit.get("signature_words") or [])
            new_words = [w.strip() for w in (sku.get("new_signature_words") or []) if w.strip()]
            kit["signature_words"] = list(old_words | set(new_words))[:8]
            old_dialogues = kit.get("sample_dialogues") or []
            new_dialogues = [d.strip() for d in (sku.get("new_sample_dialogues") or []) if d.strip()]
            kit["sample_dialogues"] = (old_dialogues + new_dialogues)[-8:]
            if sku.get("evolution_note"):
                notes = kit.get("recent_evolution_notes") or []
                notes.append({
                    "chapter_id": str(chapter_id),
                    "chapter_title": chapter.title,
                    "note": sku["evolution_note"][:200],
                })
                kit["recent_evolution_notes"] = notes[-5:]
            char.speech_kit = kit
            count += 1
        except Exception:
            continue
    return count


# ── 读者承诺操作 ──────────────────────────────────────────────────

def apply_reader_promise_ops(
    db: Session,
    project_id: str,
    new_reader_promises: List[Any],
    fulfilled_promise_texts: List[str],
    fulfilled_promise_ids: List[Any],
    chapter_id: UUID,
    chapter: Any,
    outline_node_id: Optional[UUID] = None,
) -> tuple[int, int]:
    """
    新增读者承诺 + 标记已兑现承诺（文本模糊匹配 → 精确 ID → 规划层兜底）。

    Returns:
        (promises_created, promises_fulfilled)
    """
    promises_created = 0
    promises_fulfilled = 0

    for p in (new_reader_promises or []):
        try:
            text = (p.get("promise_text") or "").strip()
            if not text:
                continue
            db.add(ReaderPromise(
                project_id=project_id,
                promise_text=text[:500],
                promise_type=p.get("promise_type", "chapter_ending"),
                source_chapter_id=chapter_id,
                source_chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
                expected_chapter_window=int(p.get("expected_within_chapters") or 3),
                priority=int(p.get("priority") or 3),
                audience_aware=int(p.get("audience_aware") or 3),
                status="open",
            ))
            promises_created += 1
        except Exception:
            continue

    if fulfilled_promise_texts:
        def _fuzzy_match(query: str, target: str, ngram: int = 4) -> bool:
            if query in target or target[:20] in query:
                return True
            if len(query) >= ngram:
                for i in range(len(query) - ngram + 1):
                    if query[i:i + ngram] in target:
                        return True
            return False

        open_promises = (
            db.query(ReaderPromise)
            .filter(ReaderPromise.project_id == project_id, ReaderPromise.status == "open")
            .all()
        )
        for promise in open_promises:
            for ft in fulfilled_promise_texts:
                ft = ft.strip()
                if ft and _fuzzy_match(ft, promise.promise_text or ""):
                    promise.status = "fulfilled"
                    promise.fulfilled_chapter_id = chapter_id
                    promise.fulfilled_chapter_number = chapter.sort_order
                    promises_fulfilled += 1
                    break

    if fulfilled_promise_ids:
        promises_fulfilled += apply_fulfilled_by_ids(
            db, project_id, chapter_id,
            chapter.sort_order or 0, fulfilled_promise_ids,
        )

    promises_fulfilled += apply_plan_promise_fulfillment(
        db, project_id, chapter_id,
        chapter.sort_order or 0,
        outline_node_id=outline_node_id,
    )

    return promises_created, promises_fulfilled
