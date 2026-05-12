"""Bootstrap 方案 B：单次全量 JSON 落库。"""

from __future__ import annotations

import logging
import uuid as _uuid_module
from typing import Any
from uuid import UUID

from app.models import (
    Character,
    CharacterRelationship,
    Faction,
    Item,
    MemoryChunk,
    OutlineNode,
    PowerSystem,
    Project,
    Skill,
    StoryLine,
    WorldSetting,
)
from app.services.bootstrap.parse import coerce_power_system_rank, safe_int
from app.services.bootstrap.prompts import setting_extra_with_defaults

logger = logging.getLogger(__name__)


async def save_all(
    svc: Any,
    data: dict,
    logline: str,
    premise: str = "",
    target_words: int = 1_200_000,
) -> Project:
    """把方案 B 生成的完整 JSON 一次性写入数据库。"""
    p = data["project"]
    project_kwargs = dict(
        title=p["title"],
        genre=p.get("genre", "玄幻"),
        logline=logline,
        premise=p.get("premise") or premise or "",
        world_overview=p.get("world_overview", ""),
        story_core=p.get("story_core", {}),
        target_words=target_words,
    )
    if svc.user_id is not None:
        project_kwargs["user_id"] = svc.user_id
    project = Project(**project_kwargs)
    svc.db.add(project)
    svc.db.flush()

    for i, ps in enumerate(data.get("power_systems", [])):
        levels = ps.get("levels", [])
        start_raw = ps.get("protagonist_start_rank")
        if start_raw is None:
            start_raw = ps.get("protagonist_current_rank")
        end_raw = ps.get("protagonist_end_rank")
        svc.db.add(PowerSystem(
            project_id=project.id,
            name=ps.get("name", "修炼体系"),
            system_type=ps.get("system_type", "cultivation"),
            description=ps.get("description"),
            cultivation_method=ps.get("cultivation_method"),
            breakthrough_condition=ps.get("breakthrough_condition"),
            special_rules=ps.get("special_rules"),
            levels=levels,
            protagonist_current_rank=coerce_power_system_rank(start_raw, levels, 1),
            protagonist_end_rank=coerce_power_system_rank(end_raw, levels, None),
            sort_order=i,
        ))

    _ss_name_to_uuid: dict[str, str] = {}
    for c in data.get("characters", []):
        cname = c.get("name", "")
        if cname:
            _ss_name_to_uuid[cname] = str(_uuid_module.uuid4())

    for i, f in enumerate(data.get("factions", [])):
        svc.db.add(Faction(
            project_id=project.id,
            name=f.get("name", f"势力{i+1}"),
            faction_type=f.get("faction_type", "sect"),
            alignment=f.get("alignment", "neutral"),
            description=f.get("description"),
            territory=f.get("territory"),
            strength_level=f.get("strength_level"),
            member_count=f.get("member_count"),
            top_power=f.get("top_power"),
            goals=f.get("goals"),
            resources=f.get("resources"),
            history=f.get("history"),
            secrets=f.get("secrets"),
            rivals=f.get("rivals", []),
            allies=f.get("allies", []),
            attitude_to_protagonist=f.get("attitude_to_protagonist", "neutral"),
            sort_order=i,
            extra={"active_period": f.get("active_period", "")},
        ))

    for i, sl in enumerate(data.get("storylines", [])):
        svc.db.add(StoryLine(
            project_id=project.id,
            name=sl.get("name", f"故事线{i+1}"),
            line_type=sl.get("line_type", "sub"),
            description=sl.get("description"),
            core_conflict=sl.get("core_conflict"),
            resolution_direction=sl.get("resolution_direction"),
            status=sl.get("status", "planned"),
            start_chapter=safe_int(sl.get("start_chapter"), None),
            sort_order=i,
        ))

    for i, sk in enumerate(data.get("skills", [])):
        raw_ids = sk.get("mastered_by_character_ids") or sk.get("mastered_by", [])
        mastered_ids: list[str] = []
        for val in raw_ids:
            if not isinstance(val, str):
                continue
            try:
                _uuid_module.UUID(val)
                mastered_ids.append(val)
            except ValueError:
                mapped = _ss_name_to_uuid.get(val)
                if mapped:
                    logger.warning(
                        "[single_shot] Skill '%s' mastered_by: AI 输出名字 '%s'，已映射到预分配 UUID %s",
                        sk.get("name", "?"), val, mapped,
                    )
                    mastered_ids.append(mapped)
                else:
                    logger.warning(
                        "[single_shot] Skill '%s' mastered_by: '%s' 不在人物列表，已丢弃",
                        sk.get("name", "?"), val,
                    )
        svc.db.add(Skill(
            project_id=project.id,
            name=sk.get("name", f"功法{i+1}"),
            skill_type=sk.get("skill_type", "combat"),
            grade=sk.get("grade", "earth"),
            source=sk.get("source"),
            level_required=sk.get("level_required"),
            description=sk.get("description"),
            effects=sk.get("effects"),
            limitations=sk.get("limitations"),
            mastered_by_character_ids=mastered_ids,
            sort_order=i,
        ))

    for i, it in enumerate(data.get("items", [])):
        owner_uuid_str: str | None = None
        owner_id = it.get("current_owner_id")
        if owner_id and isinstance(owner_id, str):
            try:
                _uuid_module.UUID(owner_id)
                owner_uuid_str = owner_id
            except ValueError:
                logger.warning(
                    "[single_shot] Item '%s' current_owner_id: '%s' 不是有效 UUID，尝试名字映射",
                    it.get("name", "?"), owner_id,
                )
        if owner_uuid_str is None:
            owner_name = it.get("current_owner_name") or it.get("current_owner", "") or ""
            if owner_name:
                mapped = _ss_name_to_uuid.get(owner_name)
                if mapped:
                    logger.warning(
                        "[single_shot] Item '%s' current_owner: 已通过名字 '%s' 映射到预分配 UUID %s",
                        it.get("name", "?"), owner_name, mapped,
                    )
                    owner_uuid_str = mapped
                else:
                    logger.warning(
                        "[single_shot] Item '%s' current_owner: '%s' 不在人物列表，owner_id 置空",
                        it.get("name", "?"), owner_name,
                    )
        svc.db.add(Item(
            project_id=project.id,
            name=it.get("name", f"道具{i+1}"),
            item_type=it.get("item_type", "artifact"),
            rarity=it.get("rarity", "rare"),
            description=it.get("description"),
            origin=it.get("origin"),
            effects=it.get("effects"),
            limitations=it.get("limitations"),
            story_significance=it.get("story_significance"),
            status=it.get("status", "intact"),
            current_owner_id=UUID(owner_uuid_str) if owner_uuid_str else None,
            sort_order=i,
        ))

    for s in data.get("settings", []):
        svc.db.add(WorldSetting(
            project_id=project.id,
            title=s.get("title", "设定"),
            content=s.get("content", ""),
            tags=s.get("tags", []),
            extra=setting_extra_with_defaults(s),
        ))

    _VALID_TIERS = {"core", "arc", "plot", "background"}
    char_map = {}
    for c in data.get("characters", []):
        _tier = c.get("character_tier", "core")
        if _tier not in _VALID_TIERS:
            _tier = "core"
        _preassigned_id = _ss_name_to_uuid.get(c.get("name", ""))
        char = Character(
            id=UUID(_preassigned_id) if _preassigned_id else _uuid_module.uuid4(),
            project_id=project.id,
            name=c.get("name", "未命名"),
            role=c.get("role", "supporting"),
            character_tier=_tier,
            gender=c.get("gender"),
            age=c.get("age"),
            faction=c.get("faction"),
            personality=c.get("personality"),
            background=c.get("background"),
            motivation=c.get("motivation"),
            arc=c.get("arc"),
            current_realm=c.get("current_realm"),
            speech_style=c.get("speech_style"),
            values=c.get("values"),
            fear=c.get("fear"),
            secrets=c.get("secrets"),
            strengths=c.get("strengths", []),
            weaknesses=c.get("weaknesses", []),
            special_traits=c.get("special_traits", []),
        )
        svc.db.add(char)
        svc.db.flush()
        char_map[char.name] = char

    def save_node(item, idx=0):
        planned = safe_int(item.get("planned_chapters"), 60)
        if planned not in (30, 60):
            planned = 60
        node = OutlineNode(
            project_id=project.id,
            parent_id=None,
            node_type="volume",
            title=item.get("title", f"第{idx+1}卷"),
            summary=item.get("summary"),
            hook=item.get("hook"),
            conflict=item.get("conflict"),
            sort_order=safe_int(item.get("sort_order"), idx),
            extra={"planned_chapters": planned},
        )
        svc.db.add(node)
        svc.db.flush()

    outline_data = data.get("outline", data.get("volumes", []))
    for idx, vol in enumerate(outline_data):
        save_node(vol, idx=idx)

    _ss_mem_chunks: list = []
    for m in data.get("memory", []):
        chunk = MemoryChunk(
            project_id=project.id,
            memory_type=m.get("memory_type", "setting"),
            title=m.get("title"),
            content=m.get("content", ""),
            tags=m.get("tags", []),
            chapter_number=0,
        )
        svc.db.add(chunk)
        _ss_mem_chunks.append(chunk)

    for r in data.get("relations", []):
        fc = char_map.get(r.get("from_name", ""))
        tc = char_map.get(r.get("to_name", ""))
        if fc and tc:
            svc.db.add(CharacterRelationship(
                project_id=project.id,
                from_character_id=fc.id,
                to_character_id=tc.id,
                relation_type=r.get("relation_type", "认识"),
                description=r.get("description"),
                intensity=safe_int(r.get("intensity"), 5, min_v=1, max_v=10) or 5,
            ))

    svc.db.commit()
    svc.db.refresh(project)

    try:
        from app.services.embedding_service import embed_texts as _embed_texts
        from app.models.memory import HAS_PGVECTOR
        if HAS_PGVECTOR and _ss_mem_chunks:
            _ss_texts = [(m, (m.title or "") + " " + (m.content or "")) for m in _ss_mem_chunks]
            _ss_vectors = await _embed_texts([t for _, t in _ss_texts])
            for (m, _), vec in zip(_ss_texts, _ss_vectors):
                m.embedding = vec
            svc.db.commit()
    except Exception as _exc:
        logger.warning("Single-shot memory embedding failed (non-fatal): %s", _exc)
    return project
