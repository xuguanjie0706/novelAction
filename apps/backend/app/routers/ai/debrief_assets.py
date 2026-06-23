import re
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Chapter, Character, Faction, Item, Skill
from app.routers.ai.schemas import AssetUpdates
from app.routers.ai.text_utils import safe_uuid, truncate
from app.utils.chapter_numbering import display_chapter_number


def find_character(
    db: Session,
    project_id: str,
    character_id: Optional[str] = None,
    character_name: Optional[str] = None,
) -> Optional[Character]:
    character_uuid = safe_uuid(character_id)
    if character_uuid:
        found = db.query(Character).filter(
            Character.id == character_uuid,
            Character.project_id == project_id,
        ).first()
        if found:
            return found
    if character_name:
        return db.query(Character).filter(
            Character.name == character_name,
            Character.project_id == project_id,
        ).first()
    return None


def _find_asset_by_id_or_name(
    db: Session,
    model,
    project_id: str,
    asset_id: Optional[str],
    asset_name: Optional[str],
):
    asset_uuid = safe_uuid(asset_id)
    if asset_uuid:
        found = db.query(model).filter(
            model.id == asset_uuid,
            model.project_id == project_id,
        ).first()
        if found:
            return found
    if asset_name:
        by_exact_name = db.query(model).filter(
            model.project_id == project_id,
            model.name == asset_name,
        ).first()
        if by_exact_name:
            return by_exact_name
        if model is Faction:
            return _find_faction_by_fuzzy_name(db, project_id, asset_name)
    return None


_FACTION_LOCATION_MARKERS = ("郡", "州", "府", "城", "县", "镇", "村", "域", "界", "岭", "谷", "海", "湖")


def _normalize_faction_name_candidates(name: Optional[str]) -> set[str]:
    text = (name or "").strip()
    if not text:
        return set()
    compact = re.sub(r"[\s·•\\\-_/（）()【】\[\]<>《》“”\"'`~!@#$%^&*+,，。；：、？?]+", "", text)
    if not compact:
        return set()
    candidates = {compact}
    for marker in _FACTION_LOCATION_MARKERS:
        if marker in compact:
            tail = compact.rsplit(marker, 1)[-1]
            if len(tail) >= 2:
                candidates.add(tail)
    if "的" in compact:
        tail = compact.rsplit("的", 1)[-1]
        if len(tail) >= 2:
            candidates.add(tail)
    return candidates


def _find_faction_by_fuzzy_name(db: Session, project_id: str, asset_name: str) -> Optional[Faction]:
    lookup_candidates = _normalize_faction_name_candidates(asset_name)
    if not lookup_candidates:
        return None
    factions = db.query(Faction).filter(Faction.project_id == project_id).all()
    for faction in factions:
        existing_candidates = _normalize_faction_name_candidates(faction.name)
        extra = dict(faction.extra or {})
        for alias in (extra.get("name_aliases") or []):
            existing_candidates |= _normalize_faction_name_candidates(str(alias))
        if lookup_candidates & existing_candidates:
            return faction
    return None


def _append_faction_alias(faction: Faction, alias_name: str) -> None:
    alias = (alias_name or "").strip()
    if not alias or alias == faction.name:
        return
    extra = dict(faction.extra or {})
    aliases = [str(v).strip() for v in (extra.get("name_aliases") or []) if str(v).strip()]
    if alias not in aliases:
        aliases.append(alias)
    extra["name_aliases"] = aliases
    faction.extra = extra


def merge_extra(existing: Optional[dict], **updates) -> dict:
    base = dict(existing or {})
    for key, value in updates.items():
        if value not in (None, "", []):
            base[key] = value
    return base


def link_item_to_character(character: Optional[Character], item: Item, chapter_number: int) -> None:
    if not character:
        return
    items = list(character.owned_items or [])
    item_id = str(item.id)
    if not any(
        isinstance(entry, dict)
        and (str(entry.get("item_id")) == item_id or entry.get("item_name") == item.name)
        for entry in items
    ):
        items.append({
            "item_id": item_id,
            "item_name": item.name,
            "acquired_chapter": chapter_number,
        })
    character.owned_items = items


def link_skill_to_character(
    character: Optional[Character],
    skill: Skill,
    mastery: Optional[str],
) -> None:
    if not character:
        return
    skills = list(character.known_skills or [])
    skill_id = str(skill.id)
    existing_ids = {
        str(entry.get("skill_id"))
        for entry in skills
        if isinstance(entry, dict) and entry.get("skill_id")
    }
    if skill_id in existing_ids:
        character.known_skills = [
            {
                **entry,
                "mastery": mastery or entry.get("mastery"),
            }
            if isinstance(entry, dict) and str(entry.get("skill_id")) == skill_id
            else entry
            for entry in skills
        ]
        return
    skills.append({
        "skill_id": skill_id,
        "skill_name": skill.name,
        "mastery": mastery or "初学",
    })
    character.known_skills = skills


def append_unique_uuid(values: Optional[list], value) -> list:
    result = [str(v) for v in (values or []) if v]
    text = str(value)
    if text not in result:
        result.append(text)
    return result


def apply_asset_updates(
    db: Session,
    project_id: str,
    chapter: Chapter,
    asset_updates: AssetUpdates,
) -> dict:
    """Persist durable A/B assets; C-tier assets stay as prose/memory only."""
    chapter_number = display_chapter_number(chapter.title, chapter.sort_order)
    stats = {
        "created_items": 0,
        "updated_items": 0,
        "created_skills": 0,
        "updated_skills": 0,
        "created_factions": 0,
        "updated_factions": 0,
    }

    for data in asset_updates.new_items:
        name = truncate((data.name or "").strip(), 100)
        if not name or data.tier == "C":
            continue
        owner = find_character(db, project_id, data.current_owner_id, data.current_owner_name)
        item = _find_asset_by_id_or_name(db, Item, project_id, None, name)
        if item:
            stats["updated_items"] += 1
        else:
            item = Item(id=uuid4(), project_id=project_id, name=name)
            db.add(item)
            stats["created_items"] += 1
            item.extra = merge_extra(item.extra, source_chapter_id=str(chapter.id))
        item.item_type = truncate(data.item_type or item.item_type or "artifact", 20)
        item.rarity = truncate(data.rarity or item.rarity or "rare", 20)
        item.description = data.description or item.description
        item.origin = data.origin or item.origin
        item.effects = data.effects or item.effects
        item.limitations = data.limitations or item.limitations
        item.current_owner_id = owner.id if owner else item.current_owner_id
        item.story_significance = data.story_significance or item.story_significance
        item.first_appearance_chapter = item.first_appearance_chapter or chapter_number
        item.status = truncate(data.status or item.status or "intact", 20)
        item.extra = merge_extra(
            item.extra,
            asset_tier=data.tier,
            reason_to_store=data.reason_to_store,
            first_recorded_chapter=chapter_number,
        )
        if owner:
            history = list(item.ownership_history or [])
            history.append({
                "owner_name": owner.name,
                "chapter": chapter_number,
                "event_description": data.reason_to_store or f"第{chapter_number}章首次纳入资产库",
            })
            item.ownership_history = history
            link_item_to_character(owner, item, chapter_number)

    for data in asset_updates.item_updates:
        item = _find_asset_by_id_or_name(db, Item, project_id, data.item_id, data.item_name)
        if not item:
            continue
        owner = find_character(db, project_id, data.current_owner_id, data.current_owner_name)
        item.status = truncate(data.status or item.status or "intact", 20)
        item.effects = data.effects or item.effects
        item.limitations = data.limitations or item.limitations
        item.story_significance = data.story_significance or item.story_significance
        if owner:
            item.current_owner_id = owner.id
            history = list(item.ownership_history or [])
            history.append({
                "owner_name": owner.name,
                "chapter": chapter_number,
                "event_description": data.event_note or f"第{chapter_number}章持有者更新",
            })
            item.ownership_history = history
            link_item_to_character(owner, item, chapter_number)
        item.extra = merge_extra(item.extra, last_update_note=data.event_note, last_update_chapter=chapter_number)
        stats["updated_items"] += 1

    for data in asset_updates.new_skills:
        name = truncate((data.name or "").strip(), 100)
        if not name or data.tier == "C":
            continue
        skill = _find_asset_by_id_or_name(db, Skill, project_id, None, name)
        if skill:
            stats["updated_skills"] += 1
        else:
            skill = Skill(id=uuid4(), project_id=project_id, name=name)
            db.add(skill)
            stats["created_skills"] += 1
            skill.extra = merge_extra(skill.extra, source_chapter_id=str(chapter.id))
        skill.skill_type = truncate(data.skill_type or skill.skill_type or "combat", 20)
        skill.grade = truncate(data.grade or skill.grade or "earth", 20)
        skill.source = truncate(data.source or skill.source, 200) if (data.source or skill.source) else skill.source
        skill.level_required = truncate(
            data.level_required or skill.level_required,
            100,
        ) if (data.level_required or skill.level_required) else skill.level_required
        skill.prerequisites = data.prerequisites or skill.prerequisites
        skill.description = data.description or skill.description
        skill.effects = data.effects or skill.effects
        skill.limitations = data.limitations or skill.limitations
        skill.first_appearance_chapter = skill.first_appearance_chapter or chapter_number
        skill.extra = merge_extra(
            skill.extra,
            asset_tier=data.tier,
            reason_to_store=data.reason_to_store,
            first_recorded_chapter=chapter_number,
        )
        mastered_ids = list(skill.mastered_by_character_ids or [])
        for char_id in data.mastered_by_character_ids:
            character = find_character(db, project_id, char_id, None)
            if character:
                mastered_ids = append_unique_uuid(mastered_ids, character.id)
                link_skill_to_character(character, skill, None)
        for char_name in data.mastered_by_character_names:
            character = find_character(db, project_id, None, char_name)
            if character:
                mastered_ids = append_unique_uuid(mastered_ids, character.id)
                link_skill_to_character(character, skill, None)
        skill.mastered_by_character_ids = mastered_ids

    for data in asset_updates.skill_updates:
        skill = _find_asset_by_id_or_name(db, Skill, project_id, data.skill_id, data.skill_name)
        if not skill:
            continue
        skill.effects = data.effects or skill.effects
        skill.limitations = data.limitations or skill.limitations
        character = find_character(
            db,
            project_id,
            data.add_mastered_by_character_id,
            data.add_mastered_by_character_name,
        )
        if character:
            skill.mastered_by_character_ids = append_unique_uuid(skill.mastered_by_character_ids, character.id)
            link_skill_to_character(character, skill, data.mastery)
        skill.extra = merge_extra(skill.extra, last_update_note=data.event_note, last_update_chapter=chapter_number)
        stats["updated_skills"] += 1

    for data in asset_updates.new_factions:
        name = truncate((data.name or "").strip(), 100)
        if not name or data.tier == "C":
            continue
        faction = _find_asset_by_id_or_name(db, Faction, project_id, None, name)
        if faction:
            stats["updated_factions"] += 1
        else:
            faction = Faction(id=uuid4(), project_id=project_id, name=name)
            db.add(faction)
            stats["created_factions"] += 1
            faction.extra = merge_extra(faction.extra, source_chapter_id=str(chapter.id))
        faction.faction_type = truncate(data.faction_type or faction.faction_type or "other", 20)
        faction.alignment = truncate(data.alignment or faction.alignment or "neutral", 20)
        faction.description = data.description or faction.description
        faction.territory = data.territory or faction.territory
        faction.strength_level = truncate(
            data.strength_level or faction.strength_level,
            100,
        ) if (data.strength_level or faction.strength_level) else faction.strength_level
        faction.goals = data.goals or faction.goals
        faction.resources = data.resources or faction.resources
        faction.attitude_to_protagonist = truncate(
            data.attitude_to_protagonist or faction.attitude_to_protagonist or "neutral",
            20,
        )
        faction.extra = merge_extra(
            faction.extra,
            asset_tier=data.tier,
            reason_to_store=data.reason_to_store,
            first_recorded_chapter=chapter_number,
        )
        _append_faction_alias(faction, name)

    for data in asset_updates.faction_updates:
        faction = _find_asset_by_id_or_name(db, Faction, project_id, data.faction_id, data.faction_name)
        if not faction:
            continue
        faction.alignment = truncate(data.alignment or faction.alignment or "neutral", 20)
        faction.goals = data.goals or faction.goals
        faction.resources = data.resources or faction.resources
        faction.attitude_to_protagonist = truncate(
            data.attitude_to_protagonist or faction.attitude_to_protagonist or "neutral",
            20,
        )
        faction.extra = merge_extra(faction.extra, last_update_note=data.event_note, last_update_chapter=chapter_number)
        stats["updated_factions"] += 1

    return stats
